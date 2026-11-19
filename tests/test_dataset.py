import hashlib
import json

from aeroturn import config, db, recovery, tools
from aeroturn.dataset import build_dataset
from aeroturn.timeutil import at


def test_scenario_counts_match_the_brief(conn):
    s = tools.get_turnaround_and_crew_state(conn)
    assert s["inbound"]["passengers"] == 342
    assert s["inbound"]["connecting"] == 280
    assert s["inbound"]["delay_min"] == 75
    assert s["connections"]["at_risk"] == 45
    assert s["connections"]["vulnerable_at_risk"] == 10
    assert s["connections"]["critical_at_risk"] == 6


def test_inbound_crew_is_twenty_minutes_from_fdp_limit(conn):
    s = tools.get_turnaround_and_crew_state(conn)
    assert s["inbound_crew"]["fdp_limit"] == "15:40"
    assert s["inbound_crew"]["margin_at_eibt_min"] == 20


def test_open_dispatch_blocking_hydraulic_item(conn):
    s = tools.get_turnaround_and_crew_state(conn)
    mx = {m["item"]: m for m in s["maintenance"]}
    assert mx["MX-0412"]["dispatch_blocking"] and mx["MX-0412"]["status"] == "OPEN"
    assert not mx["MX-0398"]["dispatch_blocking"]


def test_pristine_state_is_consistent(conn):
    assert db.check_invariants(conn)["all_clear"]


def test_dataset_is_deterministic(tmp_path):
    a = build_dataset(tmp_path / "a.sqlite", tmp_path / "a.json")
    b = build_dataset(tmp_path / "b.sqlite", tmp_path / "b.json")
    assert a == b
    pa = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["passengers"]
    pb = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))["passengers"]
    assert hashlib.sha256(json.dumps(pa).encode()).digest() == hashlib.sha256(json.dumps(pb).encode()).digest()


def test_committed_snapshot_matches_generator(tmp_path):
    build_dataset(tmp_path / "c.sqlite", tmp_path / "c.json")
    fresh = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    committed = json.loads(config.SNAPSHOT_JSON.read_text(encoding="utf-8"))
    assert fresh["passengers"] == committed["passengers"]
    assert committed["summary"]["passengers_on_ek812"] == 342


def test_hold_for_stand_makes_things_worse(conn):
    assert recovery.connection_risk(conn, eibt=at("15:55"), use_original=True)["at_risk"] > 45
