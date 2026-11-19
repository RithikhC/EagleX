"""The edge-case catalogue must stay green: every case runs on its own sandbox and asserts its outcome."""

import pytest

from aeroturn import agent, costs, db, edge_cases, hitl, reconcile


@pytest.mark.parametrize("case_id", [c.id for c in edge_cases.CASES])
def test_edge_case_passes(case_id):
    r = edge_cases.run_case(case_id)
    failed = [ch["label"] + (f" ({ch['detail']})" if ch["detail"] else "") for ch in r["checks"] if not ch["passed"]]
    assert r["passed"], f"{case_id} {r['title']}: " + "; ".join(failed)
    assert len(r["checks"]) >= 3 and r["steps"]


def test_reconcile_is_a_no_op_after_a_normal_run(conn):
    agent.AeroTurnAgent(conn, client=None).run()
    before = [(c["change_id"], c["status"]) for c in hitl.history(conn)]
    r = reconcile.reconcile(conn)
    assert r["events"] == [] and r["escalations"] == []
    assert [(c["change_id"], c["status"]) for c in hitl.history(conn)] == before


def test_escalation_is_idempotent(conn):
    a = reconcile.escalate(conn, "Topic", "Same reason", ["x"])
    b = reconcile.escalate(conn, "Topic", "Same reason", ["x"])
    assert not a.get("repeat") and b.get("repeat")
    assert len(reconcile.escalations(conn)) == 1


def test_withdraw_and_expire_only_touch_pending_changes(conn):
    agent.AeroTurnAgent(conn, client=None).run()
    gate = next(c for c in hitl.pending(conn) if c["change_type"] == "GATE_REASSIGNMENT")
    hold = next(c for c in hitl.pending(conn) if c["change_type"] == "HOLD_FLIGHT")
    assert hitl.withdraw(conn, gate["change_id"], "test")["status"] == "WITHDRAWN"
    assert hitl.withdraw(conn, gate["change_id"], "again")["status"] == "WITHDRAWN"  # unchanged, not re-logged
    assert hitl.expire(conn, hold["change_id"])["status"] == "EXPIRED"
    assert hitl.approve(conn, hold["change_id"], edge_cases.CONTROLLER)["status"] == "EXPIRED"


def test_partial_hold_protects_most_when_the_slowest_needs_too_long(conn):
    """A 3-min hold that saves 10 of 11 beats a 23-min hold for all, and stranded passengers are never 'free'."""
    agent.AeroTurnAgent(conn, client=None).run()
    gate = next(c for c in hitl.pending(conn) if c["change_type"] == "GATE_REASSIGNMENT")
    hitl.reject(conn, gate["change_id"], edge_cases.CONTROLLER, "test")
    reconcile.reconcile(conn)
    r205 = next(c for c in hitl.pending(conn) if c["change_type"] == "GATE_REASSIGNMENT")
    hitl.approve(conn, r205["change_id"], edge_cases.CONTROLLER)
    kul = next(h for h in costs.hold_analysis(conn) if h["flight"] == "EK346")
    assert kul["hold_for_all_min"] > 15 and kul["hold_needed_min"] <= 5
    assert kul["pax_protected"] < kul["pax_at_risk"] and kul["recommended"]
    assert kul["rebook_cost"] > 10 * kul["hold_cost"]


def test_base_scenario_holds_unchanged(conn):
    rec = [h["flight"] for h in costs.hold_analysis(conn) if h["recommended"]]
    assert rec == ["EK418"]
    assert db.one(conn, "SELECT COUNT(*) AS n FROM audit_log WHERE action = 'ESCALATION'")["n"] == 0
