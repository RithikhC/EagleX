"""Tamper-evident, hash-chained audit trail.

Every tool call, guard verdict, transaction outcome, LLM decision summary and
human approval is appended here. Each entry stores sha256(prev_hash + entry),
so editing or deleting any historic row breaks the chain.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from . import db

GENESIS = "0" * 64


def _digest(prev_hash: str, ts: str, sim_time: str, actor: str, action: str, detail: str) -> str:
    payload = json.dumps([prev_hash, ts, sim_time, actor, action, detail], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def log(conn: sqlite3.Connection, actor: str, action: str, detail: dict | str | None = None) -> str:
    """Append an audit entry. Safe to call inside or outside a transaction."""
    detail_s = detail if isinstance(detail, str) else json.dumps(detail or {}, default=str, sort_keys=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sim_time = db.get_meta(conn, "sim_clock", "")
    row = conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    prev = row["hash"] if row else GENESIS
    h = _digest(prev, ts, sim_time, actor, action, detail_s)
    conn.execute(
        "INSERT INTO audit_log(ts, sim_time, actor, action, detail, prev_hash, hash) VALUES(?,?,?,?,?,?,?)",
        (ts, sim_time, actor, action, detail_s, prev, h))
    return h


def verify_chain(conn: sqlite3.Connection) -> dict:
    prev = GENESIS
    n = 0
    for r in conn.execute("SELECT * FROM audit_log ORDER BY seq"):
        n += 1
        expect = _digest(prev, r["ts"], r["sim_time"], r["actor"], r["action"], r["detail"])
        if r["prev_hash"] != prev or r["hash"] != expect:
            return {"ok": False, "entries": n, "broken_at_seq": r["seq"]}
        prev = r["hash"]
    return {"ok": True, "entries": n, "head": prev}


def recent(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    return db.rows(conn, "SELECT seq, sim_time, actor, action, detail, hash FROM audit_log ORDER BY seq DESC LIMIT ?",
                   (limit,))
