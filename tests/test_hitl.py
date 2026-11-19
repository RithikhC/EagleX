import pytest

from aeroturn import config, db, hitl, tools, turnaround

CTRL = hitl.ControllerIdentity("Fatima Al Zarooni", "OCC-1123")


def _stage_gate(conn, gate="C31"):
    return tools.dispatch(conn, "stage_controller_schedule_change", {
        "change_type": "GATE_REASSIGNMENT", "flight_no": "EK812", "details": {"new_gate": gate},
        "justification": "test"})


def test_staging_changes_nothing(conn):
    r = _stage_gate(conn)
    assert r["status"] == "PENDING"
    assert db.one(conn, "SELECT gate_id FROM flights WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))["gate_id"] == "B14"


def test_holding_for_planned_gate_is_blocked_by_crew_fdp(conn):
    r = _stage_gate(conn, "B14")
    assert r["status"] == "BLOCKED" and r["guard"]["rules_violated"] == ["FTL-001"]
    assert hitl.pending(conn) == []


def test_agent_has_no_approval_tool(conn):
    names = set(tools.TOOLS)
    assert not any("approve" in n or "reject" in n or "sign" in n for n in names)
    r = tools.dispatch(conn, "approve_change", {"change_id": "X"})
    assert r["status"] == "REJECTED"


def test_override_arguments_do_not_exist(conn):
    r = tools.dispatch(conn, "propose_departure", {"flight_no": "EK813", "off_blocks": "16:30", "override": True})
    assert r["status"] == "REJECTED_INVALID_ARGS"


@pytest.mark.parametrize("who", [hitl.ControllerIdentity("AeroTurn agent", "X1"),
                                 hitl.ControllerIdentity("LLM", "X2"),
                                 hitl.ControllerIdentity("Jane", ""),
                                 hitl.ControllerIdentity("Jane", "J1", role="ENGINEER")])
def test_non_human_or_wrong_role_cannot_approve(conn, who):
    cid = _stage_gate(conn)["change_id"]
    with pytest.raises(hitl.ApprovalError):
        hitl.approve(conn, cid, who)


def test_controller_approval_applies_gate(conn):
    cid = _stage_gate(conn)["change_id"]
    r = hitl.approve(conn, cid, CTRL, "go")
    assert r["status"] == "APPROVED"
    f = db.one(conn, "SELECT gate_id, eibt FROM flights WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))
    assert f["gate_id"] == "C31" and f["eibt"].endswith("15:20")


def test_gate_decision_expires(conn):
    cid = _stage_gate(conn)["change_id"]
    hitl.advance_clock(conn, "15:16")
    assert hitl.approve(conn, cid, CTRL)["status"] == "EXPIRED"


def test_guards_rerun_at_approval(conn):
    r = tools.dispatch(conn, "stage_controller_schedule_change", {
        "change_type": "CREW_SWAP", "flight_no": "EK813",
        "details": {"remove_crew_id": "C-B01", "add_crew_id": "S-04", "role": "CPT"}, "justification": "test"})
    assert r["status"] == "PENDING"
    conn.execute("UPDATE crew SET fitness = 'UNFIT' WHERE crew_id = 'S-04'")  # standby captain reports fatigue
    res = hitl.approve(conn, r["change_id"], CTRL)
    assert res["status"] == "BLOCKED_AT_APPROVAL" and "FTL-004" in res["guard"]["rules_violated"]


def test_full_departure_release_flow(conn):
    eobt = turnaround.critical_path(conn, config.OUTBOUND_FLIGHT_ID)["eobt_hm"]
    assert eobt == "17:15"
    r = tools.propose_departure(conn, "EK813", eobt)
    assert r["status"] == "BLOCKED" and {"FTL-005", "MX-001"} <= set(r["guard"]["rules_violated"])
    swap = tools.stage_controller_schedule_change(conn, "CREW_SWAP", "EK813",
                                                  {"remove_crew_id": "C-B01", "add_crew_id": "S-04", "role": "CPT"},
                                                  "fatigue")
    assert hitl.approve(conn, swap["change_id"], CTRL)["status"] == "APPROVED"
    r = tools.propose_departure(conn, "EK813", eobt)
    assert r["status"] == "BLOCKED" and r["guard"]["rules_violated"] == ["MX-001"]   # only maintenance left
    assert hitl.sign_crs(conn, "MX-0412", "E-01")["status"] == "REFUSED"               # too early (MX-003)
    hitl.advance_clock(conn, "16:30")
    assert hitl.sign_crs(conn, "MX-0412", "E-02")["status"] == "REFUSED"               # B2 licence (MX-002)
    assert hitl.sign_crs(conn, "MX-0412", "E-01")["status"] == "SIGNED"
    eobt = turnaround.critical_path(conn, config.OUTBOUND_FLIGHT_ID)["eobt_hm"]
    r = tools.propose_departure(conn, "EK813", eobt)
    assert r["status"] == "PENDING"
    assert hitl.approve(conn, r["change_id"], CTRL)["status"] == "APPROVED"
    assert db.one(conn, "SELECT status FROM flights WHERE flight_id = ?", (config.OUTBOUND_FLIGHT_ID,))["status"] == "RELEASED"


def _stage_hold(conn):
    return tools.dispatch(conn, "stage_controller_schedule_change", {
        "change_type": "HOLD_FLIGHT", "flight_no": "EK418", "details": {"hold_min": 8}, "justification": "test"})


def test_hold_protects_connections_only_once_approved(conn):
    from aeroturn import recovery
    r = _stage_hold(conn)
    assert r["status"] == "PENDING"
    risk = recovery.connection_risk(conn)
    assert risk["at_risk"] == 41 and risk["awaiting_hold_decision"] == 4
    plan = tools.plan_passenger_recovery(conn)
    assert plan["summary"]["rebooked"] == 41  # planner leaves the held passengers alone
    tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])
    assert hitl.approve(conn, r["change_id"], CTRL)["status"] == "APPROVED"
    risk = recovery.connection_risk(conn)
    assert risk["at_risk"] == 0 and risk["awaiting_hold_decision"] == 0
    assert db.one(conn, "SELECT status FROM flights WHERE flight_no = 'EK418'")["status"] == "HELD"


def test_rejected_hold_returns_passengers_to_rebooking(conn):
    from aeroturn import recovery
    r = _stage_hold(conn)
    plan = tools.plan_passenger_recovery(conn)
    tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])
    hitl.reject(conn, r["change_id"], CTRL, "SYD slot cannot move")
    assert recovery.connection_risk(conn)["at_risk"] == 4
    plan = tools.plan_passenger_recovery(conn)
    assert tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])["status"] == "COMMITTED"
    assert recovery.connection_risk(conn)["at_risk"] == 0
    assert db.check_invariants(conn)["all_clear"]


def test_hold_cap_and_expiry(conn):
    from aeroturn import recovery
    r = tools.dispatch(conn, "stage_controller_schedule_change", {
        "change_type": "HOLD_FLIGHT", "flight_no": "EK384", "details": {"hold_min": 55}, "justification": "x"})
    assert r["status"] == "BLOCKED" and r["guard"]["rules_violated"] == ["NET-001"]
    _stage_hold(conn)
    hitl.advance_clock(conn, "16:08")  # decision window (STD - 5) has passed
    assert recovery.connection_risk(conn)["awaiting_hold_decision"] == 0
