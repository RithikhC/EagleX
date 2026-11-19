"""Crew matcher, turnaround critical path, costs, audit chain, notifications."""

from aeroturn import audit, config, costs, crew, db, lab, narrative, tools, turnaround


def test_standby_matcher_picks_nearest_legal_captain(conn):
    r = crew.find_standby_crew(conn, flight_id=config.OUTBOUND_FLIGHT_ID, rank="CPT")
    assert r["selected"]["crew_id"] == "S-04"
    why = {c["crew_id"]: {v["rule"] for v in c["violations"]} for c in r["candidates"]}
    assert why["C-A01"] == {"FTL-001"}   # inbound captain: physically closest, legally impossible
    assert why["S-01"] == {"FTL-001"}    # 9h airport standby: max FDP cut by 5h06 (beyond 4h), 16h cap
    assert why["S-03"] == {"FTL-003"}    # A380-only
    assert why["S-05"] == {"FTL-002"}    # 9h rest
    assert why["S-02"] == set()          # legal but 35 min away


def test_critical_path_runs_through_maintenance(conn):
    cpm = turnaround.critical_path(conn, config.OUTBOUND_FLIGHT_ID)
    assert cpm["eobt_hm"] == "17:15" and cpm["delay_vs_std_min"] == 65
    assert "MXI" in cpm["critical_path"] and "BRD" in cpm["critical_path"]


def test_eu261_bands():
    assert costs.eu261_amount(1200, 170) == 0
    assert costs.eu261_amount(1200, 200) == 250
    assert costs.eu261_amount(3000, 200) == 400
    assert costs.eu261_amount(7000, 200) == 300
    assert costs.eu261_amount(7000, 300) == 600


def test_aeroturn_beats_legacy(conn):
    plan = tools.plan_passenger_recovery(conn)
    tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])
    c = costs.disruption_cost(conn)
    assert c["savings"] > 0
    assert c["aeroturn"]["same_day"] == 45 and c["legacy_auto_reprotect"]["same_day"] == 0
    assert c["aeroturn"]["vulnerable_same_day"] == 10
    assert c["outbound_rotation"]["eu261"] == 0


def test_hold_analysis_recommends_only_the_cheap_short_hold(conn):
    rows = costs.hold_analysis(conn)
    assert any(not r["allowed"] for r in rows) and all(r["hold_needed_min"] > 0 for r in rows)
    rec = [r for r in rows if r["recommended"]]
    assert [(r["flight"], r["hold_needed_min"]) for r in rec] == [("EK418", 8)]
    assert rec[0]["hold_cost"] < rec[0]["rebook_cost"]


def test_audit_chain_detects_tampering(conn):
    tools.dispatch(conn, "get_turnaround_and_crew_state", {})
    tools.dispatch(conn, "stage_controller_schedule_change", {
        "change_type": "GATE_REASSIGNMENT", "flight_no": "EK812", "details": {"new_gate": "B14"}, "justification": "x"})
    assert audit.verify_chain(conn)["ok"]
    t = lab.tamper_demo(config.RUNTIME_DB)
    assert t["before"]["ok"] and not t["after"]["ok"]


def test_notification_templates_cannot_carry_facts(conn):
    assert tools.validate_template("Dear {first_name}, you fly {new_flight} at {dep_time}.") == []
    bad = tools.validate_template("Dear {first_name}, you fly EK372 at 18:25 from gate A12, seat 24K.")
    assert len(bad) >= 3
    plan = tools.plan_passenger_recovery(conn)
    tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])
    r = tools.send_passenger_notifications(conn, narrative.DEFAULT_TEMPLATES)
    assert r["status"] == "SENT" and r["sent"] == 45 and r["by_category"]["UMNR_GUARDIAN"] == 2
    lina = db.one(conn, "SELECT n.message FROM notifications n JOIN passengers p ON p.pax_id = n.pax_id "
                        "WHERE p.first_name = 'Lina'")["message"]
    assert "EK372" in lina and "guardian" in lina.lower()


def test_grounding_check_flags_invented_numbers(conn):
    facts = narrative.brief_facts(conn)
    ok = narrative.grounding_check("EK812 in-block 15:20, 45 connections at risk.", facts)
    bad = narrative.grounding_check("We saved EUR 99,999 and protected 77 passengers.", facts)
    assert ok["grounded"] and not bad["grounded"] and "99999" in bad["ungrounded"]
