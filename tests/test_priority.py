from aeroturn import db, recovery, tools


def test_plan_processes_vulnerable_first(conn):
    plan = recovery.plan_recovery(conn, persist=False)
    tiers = [a["group_tier"] for a in plan["assignments"]]
    assert tiers == sorted(tiers)
    first = [a["ssr"] for a in plan["assignments"][:6]]
    assert first[:2] == ["UMNR", "UMNR"] and "MEDA" in first
    assert plan["unresolved"] == []


def test_vulnerable_get_earliest_legal_options(conn):
    plan = recovery.plan_recovery(conn, persist=False)
    by_name = {a["name"]: a for a in plan["assignments"]}
    assert by_name["Lina Haddad"]["to_flight_no"] == "EK372"    # UMNR: home carrier, before 22:00
    assert by_name["Rajan Iyer"]["to_flight_no"] == "EK504"     # MEDA stays on the MEDIF carrier
    assert by_name["Bilal Qureshi"]["to_flight_no"] == "EK606"  # WCHR: 16:35 breaks his 80-min MCT
    fam = {a["to_flight_no"] for a in plan["assignments"] if a["pnr"] == "GEO3FM"}
    assert fam == {"EK372"}                                      # family kept together


def test_unconstrained_plan_is_blocked(conn):
    naive = recovery.plan_naive(conn)
    r = tools.execute_atomic_passenger_rebook(conn, plan_id=naive["plan_id"])
    assert r["status"] == "BLOCKED"
    assert {"PAX-001", "PAX-002", "PAX-003", "PAX-004", "PAX-006"} <= set(r["guard"]["rules_violated"])
    assert db.check_invariants(conn)["all_clear"]
    assert recovery.connection_risk(conn)["at_risk"] == 45  # nothing was written


def test_priority_inversion_from_explicit_assignments_is_blocked(conn):
    pid = {r["first_name"] + " " + r["last_name"]: r["pax_id"] for r in db.rows(conn, "SELECT * FROM passengers")}
    std = [p for p in recovery.connection_risk(conn)["passengers"]
           if p["at_risk"] and p["tier"] == 4 and p["onward_flight"] == "EK384"]
    items = [{"pax_id": p["pax_id"], "flight": "EK372"} for p in std[:3]]
    items.append({"pax_id": pid["Lina Haddad"], "flight": "EK376"})
    r = tools.execute_atomic_passenger_rebook(conn, assignments=items)
    assert r["status"] == "BLOCKED" and "PAX-001" in r["guard"]["rules_violated"]


def test_out_of_scope_passenger_cannot_be_moved(conn):
    safe = next(p for p in recovery.connection_risk(conn)["passengers"] if not p["at_risk"])
    r = tools.execute_atomic_passenger_rebook(conn, assignments=[{"pax_id": safe["pax_id"], "flight": "EK376"}])
    assert r["status"] == "BLOCKED" and "PAX-009" in r["guard"]["rules_violated"]


def test_umnr_on_partner_flight_is_blocked(conn):
    pid = db.one(conn, "SELECT pax_id FROM passengers WHERE first_name = 'Ethan' AND last_name = 'Tan'")["pax_id"]
    r = tools.execute_atomic_passenger_rebook(conn, assignments=[{"pax_id": pid, "flight": "IP4410"}])
    assert r["status"] == "BLOCKED" and {"PAX-003", "PAX-007"} <= set(r["guard"]["rules_violated"])
