"""SQLite schema, connection handling, invariants and state fingerprinting.

Layered protection against double-booking and orphaned state:

  * UNIQUE(flight_id, seat_no)  -> a seat can never be sold twice
  * UNIQUE(pax_id, leg_no)      -> a passenger can never hold two segments for the same leg
  * UNIQUE(pax_id, flight_id)   -> parent key for bag routing
  * bag_routing (pax_id, flight_id) -> bookings  FOREIGN KEY ... DEFERRABLE INITIALLY DEFERRED
        -> a bag can never stay routed on a flight its passenger is not booked on;
           checked at COMMIT, so a half-finished rebooking cannot be committed
  * triggers: seat cabin must match booking cabin; bag owner must match routing owner
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE airports(
  code TEXT PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL, country TEXT NOT NULL,
  is_eu INTEGER NOT NULL DEFAULT 0, lat REAL NOT NULL, lon REAL NOT NULL);

CREATE TABLE gates(
  gate_id TEXT PRIMARY KEY, concourse TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('CONTACT','REMOTE')),
  taxi_min INTEGER NOT NULL, transfer_penalty_min INTEGER NOT NULL DEFAULT 0);

CREATE TABLE aircraft(reg TEXT PRIMARY KEY, type TEXT NOT NULL, config TEXT NOT NULL, seats_total INTEGER NOT NULL);

CREATE TABLE flights(
  flight_id TEXT PRIMARY KEY, flight_no TEXT NOT NULL, carrier TEXT NOT NULL,
  operated_by_home INTEGER NOT NULL DEFAULT 1,
  origin TEXT NOT NULL REFERENCES airports(code), dest TEXT NOT NULL REFERENCES airports(code),
  std TEXT NOT NULL, sta TEXT NOT NULL, etd TEXT, eta TEXT, eibt TEXT, atd TEXT,
  aircraft_reg TEXT, aircraft_type TEXT NOT NULL, config TEXT NOT NULL, seats_total INTEGER NOT NULL,
  gate_id TEXT REFERENCES gates(gate_id), status TEXT NOT NULL, block_min INTEGER NOT NULL,
  distance_km INTEGER NOT NULL, role TEXT NOT NULL, load_pax INTEGER NOT NULL DEFAULT 0);

CREATE TABLE seats(
  flight_id TEXT NOT NULL REFERENCES flights(flight_id), seat_no TEXT NOT NULL,
  cabin TEXT NOT NULL CHECK(cabin IN ('F','J','Y')), row_no INTEGER NOT NULL, letter TEXT NOT NULL,
  is_aisle INTEGER NOT NULL, is_window INTEGER NOT NULL, is_exit INTEGER NOT NULL,
  PRIMARY KEY(flight_id, seat_no));

CREATE TABLE passengers(
  pax_id TEXT PRIMARY KEY, pnr TEXT NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
  age INTEGER NOT NULL, cabin TEXT NOT NULL, loyalty TEXT NOT NULL DEFAULT 'NONE', ssr TEXT NOT NULL DEFAULT '',
  lang TEXT NOT NULL DEFAULT 'en', journey_origin TEXT NOT NULL, final_dest TEXT NOT NULL,
  is_connecting INTEGER NOT NULL, is_infant INTEGER NOT NULL DEFAULT 0,
  original_onward_flight TEXT, remarks TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '');

CREATE TABLE bookings(
  booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
  pax_id TEXT REFERENCES passengers(pax_id),
  leg_no INTEGER,
  flight_id TEXT NOT NULL REFERENCES flights(flight_id),
  seat_no TEXT,
  cabin TEXT NOT NULL CHECK(cabin IN ('F','J','Y')),
  source TEXT NOT NULL,
  booked_at TEXT NOT NULL,
  FOREIGN KEY(flight_id, seat_no) REFERENCES seats(flight_id, seat_no),
  UNIQUE(flight_id, seat_no),
  UNIQUE(pax_id, leg_no),
  UNIQUE(pax_id, flight_id));
CREATE INDEX ix_bookings_flight ON bookings(flight_id);

CREATE TRIGGER trg_booking_cabin_matches_seat
BEFORE INSERT ON bookings
WHEN NEW.seat_no IS NOT NULL
 AND (SELECT cabin FROM seats WHERE flight_id = NEW.flight_id AND seat_no = NEW.seat_no) IS NOT NEW.cabin
BEGIN
  SELECT RAISE(ABORT, 'SEAT-CABIN mismatch: booking cabin differs from seat cabin');
END;

CREATE TABLE booking_history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, txn_id TEXT NOT NULL, pax_id TEXT, leg_no INTEGER,
  flight_id TEXT, seat_no TEXT, cabin TEXT, action TEXT NOT NULL, at TEXT NOT NULL);

CREATE TABLE bags(
  bag_tag TEXT PRIMARY KEY, pax_id TEXT NOT NULL REFERENCES passengers(pax_id),
  weight_kg REAL NOT NULL, special TEXT NOT NULL DEFAULT '');

CREATE TABLE bag_routing(
  bag_tag TEXT NOT NULL REFERENCES bags(bag_tag), leg_no INTEGER NOT NULL,
  pax_id TEXT NOT NULL, flight_id TEXT NOT NULL, status TEXT NOT NULL,
  PRIMARY KEY(bag_tag, leg_no),
  FOREIGN KEY(pax_id, flight_id) REFERENCES bookings(pax_id, flight_id) DEFERRABLE INITIALLY DEFERRED);

CREATE TRIGGER trg_bag_owner_insert
BEFORE INSERT ON bag_routing
WHEN NEW.pax_id IS NOT (SELECT pax_id FROM bags WHERE bag_tag = NEW.bag_tag)
BEGIN
  SELECT RAISE(ABORT, 'BAG-001 PPBM: bag routed under a passenger who does not own it');
END;
CREATE TRIGGER trg_bag_owner_update
BEFORE UPDATE ON bag_routing
WHEN NEW.pax_id IS NOT (SELECT pax_id FROM bags WHERE bag_tag = NEW.bag_tag)
BEGIN
  SELECT RAISE(ABORT, 'BAG-001 PPBM: bag routed under a passenger who does not own it');
END;

CREATE TABLE crew(
  crew_id TEXT PRIMARY KEY, name TEXT NOT NULL, rank TEXT NOT NULL CHECK(rank IN ('CPT','FO','PUR','CC')),
  base TEXT NOT NULL, type_ratings TEXT NOT NULL, fitness TEXT NOT NULL DEFAULT 'FIT',
  duty_kind TEXT NOT NULL, duty_start TEXT, sectors_flown INTEGER NOT NULL DEFAULT 0,
  rest_before_duty_min INTEGER NOT NULL, location TEXT NOT NULL, proximity_min INTEGER NOT NULL,
  notes TEXT NOT NULL DEFAULT '', standby_kind TEXT, standby_start TEXT);

CREATE TABLE crew_assignments(
  flight_id TEXT NOT NULL REFERENCES flights(flight_id), crew_id TEXT NOT NULL REFERENCES crew(crew_id),
  role TEXT NOT NULL, status TEXT NOT NULL, report_at TEXT, PRIMARY KEY(flight_id, crew_id));

CREATE TABLE engineers(
  eng_id TEXT PRIMARY KEY, name TEXT NOT NULL, licence TEXT NOT NULL, type_auth TEXT NOT NULL,
  location TEXT NOT NULL, proximity_min INTEGER NOT NULL);

CREATE TABLE maintenance_items(
  item_id TEXT PRIMARY KEY, aircraft_reg TEXT NOT NULL, ata TEXT NOT NULL, title TEXT NOT NULL,
  description TEXT NOT NULL, category TEXT NOT NULL, raised_at TEXT NOT NULL, raised_station TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED')), blocks_dispatch INTEGER NOT NULL,
  mel_ref TEXT, est_task_min INTEGER NOT NULL, crs_eng_id TEXT, crs_signed_at TEXT, crs_remarks TEXT);

CREATE TABLE turnaround_tasks(
  task_id TEXT NOT NULL, flight_id TEXT NOT NULL, name TEXT NOT NULL, duration_min INTEGER NOT NULL,
  depends_on TEXT NOT NULL, resource TEXT NOT NULL, kind TEXT NOT NULL, mx_item_id TEXT,
  PRIMARY KEY(flight_id, task_id));

CREATE TABLE gate_allocations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, gate_id TEXT NOT NULL REFERENCES gates(gate_id),
  flight_id TEXT NOT NULL, start TEXT NOT NULL, "end" TEXT NOT NULL, status TEXT NOT NULL);

CREATE TABLE schedule_changes(
  change_id TEXT PRIMARY KEY, change_type TEXT NOT NULL, flight_id TEXT NOT NULL, payload TEXT NOT NULL,
  justification TEXT NOT NULL, guard_report TEXT NOT NULL, status TEXT NOT NULL,
  staged_by TEXT NOT NULL, staged_at TEXT NOT NULL, valid_until TEXT,
  decided_by TEXT, decided_at TEXT, decision_note TEXT, applied_at TEXT);

CREATE TABLE plans(
  plan_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, objective TEXT NOT NULL, basis TEXT NOT NULL,
  assignments TEXT NOT NULL, summary TEXT NOT NULL, status TEXT NOT NULL, created_by TEXT NOT NULL);

CREATE TABLE txn_log(
  txn_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, kind TEXT NOT NULL, outcome TEXT NOT NULL,
  detail TEXT NOT NULL);

CREATE TABLE notifications(
  id INTEGER PRIMARY KEY AUTOINCREMENT, pax_id TEXT NOT NULL, category TEXT NOT NULL, channel TEXT NOT NULL,
  message TEXT NOT NULL, created_at TEXT NOT NULL, template_source TEXT NOT NULL);

CREATE TABLE audit_log(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, sim_time TEXT NOT NULL, actor TEXT NOT NULL,
  action TEXT NOT NULL, detail TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
"""

# Tables whose content defines "passenger & bag state" for rollback fingerprinting.
STATE_TABLES = ("bookings", "bag_routing", "booking_history")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or config.RUNTIME_DB)
    if not path.exists():
        reset_runtime(path)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = DELETE")
    return conn


@contextmanager
def session(path: Path | str | None = None):
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def reset_runtime(path: Path | str | None = None) -> Path:
    """Restore the pristine scenario into the runtime database.

    Uses SQLite's online backup API so the reset works while other connections
    (e.g. the Streamlit console) still have the file open. On Windows an open
    file cannot be deleted, so a delete-and-copy reset would fail there.
    """
    path = Path(path or config.RUNTIME_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not config.PRISTINE_DB.exists():
        from .dataset import build_dataset
        build_dataset(config.PRISTINE_DB, config.SNAPSHOT_JSON)
    if path.exists():
        src = sqlite3.connect(str(config.PRISTINE_DB))
        dst = sqlite3.connect(str(path), timeout=15)
        try:
            src.backup(dst)
            return path
        except sqlite3.Error:
            pass  # unreadable/corrupt runtime file: fall back to replacing it
        finally:
            src.close()
            dst.close()
    for suffix in ("", "-journal", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    shutil.copyfile(config.PRISTINE_DB, path)
    return path


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))


def now(conn: sqlite3.Connection):
    from .timeutil import parse
    return parse(get_meta(conn, "sim_clock", config.SCENARIO_START_CLOCK))


def rows(conn: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(conn: sqlite3.Connection, sql: str, params=()) -> dict | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def state_fingerprint(conn: sqlite3.Connection, tables=STATE_TABLES) -> str:
    """SHA-256 over the full ordered content of the passenger/bag state tables."""
    h = hashlib.sha256()
    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
        order = ", ".join(cols)
        for r in conn.execute(f"SELECT {order} FROM {t} ORDER BY {order}"):
            h.update(json.dumps(list(r), default=str).encode())
        h.update(f"|{t}|".encode())
    return h.hexdigest()


def check_invariants(conn: sqlite3.Connection) -> dict:
    """Independent post-hoc verification that state is consistent.

    Every count below must be zero at all times outside an open transaction.
    """
    q = {
        "seat_double_bookings": """
            SELECT flight_id, seat_no, COUNT(*) AS n FROM bookings WHERE seat_no IS NOT NULL
            GROUP BY flight_id, seat_no HAVING n > 1""",
        "duplicate_leg_bookings": """
            SELECT pax_id, leg_no, COUNT(*) AS n FROM bookings WHERE pax_id IS NOT NULL
            GROUP BY pax_id, leg_no HAVING n > 1""",
        "orphaned_bags": """
            SELECT r.bag_tag, r.flight_id, r.pax_id FROM bag_routing r
            LEFT JOIN bookings b ON b.pax_id = r.pax_id AND b.flight_id = r.flight_id
            WHERE b.booking_id IS NULL""",
        "bag_owner_mismatch": """
            SELECT r.bag_tag FROM bag_routing r JOIN bags g ON g.bag_tag = r.bag_tag
            WHERE r.pax_id <> g.pax_id""",
        "bags_left_on_old_connection": """
            SELECT g.bag_tag, b.flight_id AS pax_on, r.flight_id AS bag_on FROM bags g
            JOIN passengers p ON p.pax_id = g.pax_id AND p.is_connecting = 1
            JOIN bookings b ON b.pax_id = g.pax_id AND b.leg_no = 2
            JOIN bag_routing r ON r.bag_tag = g.bag_tag AND r.leg_no = 2
            WHERE r.flight_id <> b.flight_id""",
        "connecting_pax_without_onward_segment": """
            SELECT p.pax_id FROM passengers p
            LEFT JOIN bookings b ON b.pax_id = p.pax_id AND b.leg_no = 2
            WHERE p.is_connecting = 1 AND b.booking_id IS NULL""",
        "seat_overflow": """
            SELECT b.flight_id, b.cabin, COUNT(*) AS used,
                   (SELECT COUNT(*) FROM seats s WHERE s.flight_id = b.flight_id AND s.cabin = b.cabin) AS cap
            FROM bookings b WHERE b.seat_no IS NOT NULL GROUP BY b.flight_id, b.cabin HAVING used > cap""",
    }
    out = {}
    for name, sql in q.items():
        found = rows(conn, sql)
        out[name] = {"count": len(found), "sample": found[:5]}
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    out["foreign_key_violations"] = {"count": len(fk), "sample": [tuple(r) for r in fk[:5]]}
    out["all_clear"] = all(v["count"] == 0 for v in out.values() if isinstance(v, dict))
    return out
