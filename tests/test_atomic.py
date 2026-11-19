import sqlite3

import pytest

from aeroturn import db, faults, recovery, tools


def _leg2(conn):
    return {r["pax_id"]: (r["flight_id"], r["seat_no"]) for r in
            db.rows(conn, "SELECT pax_id, flight_id, seat_no FROM bookings WHERE leg_no = 2")}


@pytest.mark.parametrize("kind,step", [("SEAT_CONFLICT", 7), ("SEAT_CONFLICT", 30), ("BAG_SYSTEM_FAULT", 4)])
def test_midway_failure_rolls_back_everything(conn, kind, step):
    before = _leg2(conn)
    plan = tools.plan_passenger_recovery(conn)
    faults.arm(conn, kind, step)
    r = tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])
    assert r["status"] == "ROLLED_BACK"
    assert r["state_identical_to_before"]
    assert r["provisional_steps_reverted"] == r["failed_at_step"] - 1 >= 1
    assert r["all_clear"] and all(v == 0 for v in r["invariants_after"].values())
    assert _leg2(conn) == before
    assert faults.peek(conn) is None  # faults are one-shot


def test_replan_after_rollback_commits_cleanly(conn):
    plan = tools.plan_passenger_recovery(conn)
    faults.arm(conn, "SEAT_CONFLICT", 7)
    assert tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])["status"] == "ROLLED_BACK"
    plan2 = tools.plan_passenger_recovery(conn)
    r = tools.execute_atomic_passenger_rebook(conn, plan_id=plan2["plan_id"])
    assert r["status"] == "COMMITTED" and r["summary"]["rebooked"] == 45
    assert db.check_invariants(conn)["all_clear"]
    assert recovery.connection_risk(conn)["at_risk"] == 0
    bad = db.rows(conn, """SELECT r.bag_tag FROM bag_routing r JOIN bookings b ON b.pax_id = r.pax_id
                           AND b.leg_no = r.leg_no WHERE r.flight_id <> b.flight_id""")
    assert bad == []  # every bag travels with its owner


def test_executed_plan_cannot_be_replayed(conn):
    plan = tools.plan_passenger_recovery(conn)
    tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])
    with pytest.raises(tools.ToolError):
        tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])


def test_db_rejects_double_seat_and_duplicate_leg(conn):
    b = db.one(conn, "SELECT * FROM bookings WHERE pax_id IS NOT NULL AND seat_no IS NOT NULL AND leg_no = 2 LIMIT 1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO bookings(pax_id, leg_no, flight_id, seat_no, cabin, source, booked_at) "
                     "VALUES(NULL, NULL, ?, ?, ?, 'X', 'now')", (b["flight_id"], b["seat_no"], b["cabin"]))
    other = db.one(conn, "SELECT flight_id FROM flights WHERE flight_id <> ? AND role = 'ONWARD' LIMIT 1",
                   (b["flight_id"],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO bookings(pax_id, leg_no, flight_id, seat_no, cabin, source, booked_at) "
                     "VALUES(?, 2, ?, NULL, 'Y', 'X', 'now')", (b["pax_id"], other["flight_id"]))


def test_deferred_fk_blocks_orphaned_bag_at_commit(conn):
    r = db.one(conn, "SELECT pax_id FROM bag_routing WHERE leg_no = 2 LIMIT 1")
    conn.execute("BEGIN")
    conn.execute("DELETE FROM bookings WHERE pax_id = ? AND leg_no = 2", (r["pax_id"],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("COMMIT")
    conn.execute("ROLLBACK")
    assert db.check_invariants(conn)["all_clear"]


def test_bag_cannot_be_routed_under_another_passenger(conn):
    tag = db.one(conn, "SELECT bag_tag, pax_id FROM bags LIMIT 1")
    other = db.one(conn, "SELECT pax_id FROM passengers WHERE pax_id <> ? LIMIT 1", (tag["pax_id"],))
    with pytest.raises(sqlite3.IntegrityError, match="BAG-001"):
        conn.execute("UPDATE bag_routing SET pax_id = ? WHERE bag_tag = ?", (other["pax_id"], tag["bag_tag"]))


def test_stale_plan_is_refused(conn):
    plan = tools.plan_passenger_recovery(conn)
    conn.execute("UPDATE flights SET eibt = '2026-11-21T15:30' WHERE flight_id = 'EK812-1121'")
    r = tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])
    assert r["status"] == "BLOCKED" and r["reason"] == "STALE_PLAN"


def test_reset_works_while_connections_are_open(conn):
    """Regression: on Windows an open SQLite file cannot be deleted; reset must restore in place."""
    plan = tools.plan_passenger_recovery(conn)
    tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"])
    other = db.connect()
    db.reset_runtime()
    assert recovery.connection_risk(conn)["at_risk"] == 45
    assert recovery.connection_risk(other)["at_risk"] == 45
    other.close()
