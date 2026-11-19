import dataclasses

import pytest

from aeroturn import db, guards, lab
from aeroturn.facts import crew_facts
from aeroturn.timeutil import at


def test_fdp_table():
    assert guards.max_fdp_minutes(at("04:40"), 2) == 11 * 60
    assert guards.max_fdp_minutes(at("04:40"), 3) == 10 * 60 + 30
    assert guards.max_fdp_minutes(at("14:00"), 1) == 12 * 60 + 30
    assert guards.max_fdp_minutes(at("09:00"), 2) == 13 * 60
    assert guards.max_fdp_minutes(at("18:00"), 10) == 9 * 60  # floor


def _crew(conn, cid):
    return crew_facts(db.one(conn, "SELECT * FROM crew WHERE crew_id = ?", (cid,)))


def test_inbound_crew_cannot_fly_the_outbound(conn):
    v = guards.check_crew_for_sector(_crew(conn, "C-A01"), aircraft_type="B777", off_blocks=at("16:35"), block_min=420)
    assert not v.ok and {x.rule for x in v.violations} == {"FTL-001"}


def test_inbound_crew_on_blocks_check():
    c = guards.CrewFacts("X", "X", "CPT", ("B777",), "FIT", "ON_DUTY", at("04:40"), sectors_flown=2)
    assert guards.check_inbound_crew_on_blocks([c], eibt=at("15:20")).ok
    late = guards.check_inbound_crew_on_blocks([c], eibt=at("15:55"))
    assert not late.ok and late.facts["min_margin_min"] == -15


def test_fatigue_rating_rest_and_reachability(conn):
    def rules(cid, off, report=None):
        return {x.rule for x in guards.check_crew_for_sector(_crew(conn, cid), aircraft_type="B777",
                                                              off_blocks=at(off), block_min=420,
                                                              report_time=at(report) if report else None).violations}
    assert "FTL-004" in rules("C-B01", "17:15")
    assert "FTL-003" in rules("S-03", "17:15", "15:04")
    assert "FTL-002" in rules("S-05", "17:15", "15:25")
    assert "FTL-006" in rules("S-02", "15:50", "15:35")


def test_long_airport_standby_reduces_fdp(conn):
    early = guards.check_crew_for_sector(_crew(conn, "S-01"), aircraft_type="B777", off_blocks=at("17:15"),
                                         block_min=420, report_time=at("15:06"))
    late = guards.check_crew_for_sector(_crew(conn, "S-04"), aircraft_type="B777", off_blocks=at("17:15"),
                                        block_min=420, report_time=at("15:09"))
    assert not early.ok and late.ok
    assert late.facts["margin_min"] == 174  # FDP from report 15:09, max 12:00 -> 03:09; on-blocks 00:15


def _mx(status="OPEN", licence=None, auth=()):
    return guards.MxFacts("MX-0412", "29", "HYD SYS C", True, status, licence, auth)


def test_maintenance_release_rules():
    assert [v.rule for v in guards.check_maintenance_release([_mx()], aircraft_type="B777")] == ["MX-001"]
    assert [v.rule for v in guards.check_maintenance_release([_mx("CLOSED", "B2", ("B777",))],
                                                             aircraft_type="B777")] == ["MX-002"]
    assert guards.check_maintenance_release([_mx("CLOSED", "B1", ("B777",))], aircraft_type="B777") == []


def test_crs_signature_rules():
    item = guards.MxFacts("MX-0412", "29", "HYD", True, "OPEN", task_earliest_complete=at("16:30"))
    sign = lambda lic, t: {v.rule for v in guards.check_crs_signature(  # noqa: E731
        item, licence=lic, type_auth=["B777"], aircraft_type="B777", signed_at=at(t)).violations}
    assert sign("B2", "16:30") == {"MX-002"}
    assert sign("B1", "15:00") == {"MX-003"}
    assert sign("B1", "16:30") == set()


def test_passenger_tiers_and_mct():
    umnr = guards.PaxFacts("1", "A", "Kid", 9, "Y", "NONE", ("UMNR",), "BKK")
    wchr = guards.PaxFacts("2", "B", "W", 70, "Y", "NONE", ("WCHR",), "BKK")
    gold = guards.PaxFacts("3", "C", "G", 40, "Y", "GOLD", (), "BKK")
    std = guards.PaxFacts("4", "D", "S", 40, "Y", "NONE", (), "BKK")
    assert [guards.pax_tier(p) for p in (umnr, wchr, gold, std)] == [1, 2, 3, 4]
    assert guards.pax_mct_minutes(wchr) == 80 and guards.pax_mct_minutes(umnr) == 75
    assert guards.pax_mct_minutes(std, remote_arrival=True) == 85
    assert not guards.exit_row_permitted(umnr) and guards.exit_row_permitted(std)


def test_umnr_meda_downgrade_exit_rules():
    eibt = at("15:20")
    partner_late = guards.OptionFacts("F1", "IP1", "BKK", at("22:30"), at("04:00+1"), False)
    umnr = guards.PaxFacts("1", "A", "Kid", 9, "Y", "NONE", ("UMNR",), "BKK")
    rules = {v.rule for v in guards.check_pax_option(umnr, partner_late, cabin="Y", eibt=eibt, remote_arrival=False)}
    assert "PAX-003" in rules
    meda = guards.PaxFacts("2", "B", "M", 60, "J", "NONE", ("MEDA",), "BKK")
    rules = {v.rule for v in guards.check_pax_option(meda, partner_late, cabin="Y", eibt=eibt, remote_arrival=False,
                                                     seat_is_exit=True)}
    assert {"PAX-004", "PAX-005", "PAX-008"} <= rules


def test_guards_cannot_be_mutated():
    with pytest.raises(guards.GuardTamperError):
        guards.LIMITS = None
    with pytest.raises(guards.GuardTamperError):
        guards.max_fdp_minutes = lambda *a: 9999
    with pytest.raises(dataclasses.FrozenInstanceError):
        guards.LIMITS.min_rest_min = 0
    with pytest.raises(TypeError):
        guards.RULES["FTL-001"] = "x"
    assert all(a["blocked"] for a in lab.immutability_probe())


def test_guard_source_is_pinned():
    assert guards.verify_guard_integrity()["ok"], "run scripts/pin_guards.py after a reviewed change"


def test_network_changes_require_controller():
    for t in ("GATE_REASSIGNMENT", "RETIME", "CREW_SWAP", "HOLD_FLIGHT", "DEPARTURE_RELEASE"):
        assert guards.requires_controller_approval(t)
