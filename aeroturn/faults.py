"""Chaos / fault injection for the atomic-rollback demo.

Armed from the OCC console or from tests, never by the LLM: there is no agent
tool for it. Faults are one-shot: they fire once, then disarm, so the agent's
re-plan and retry can succeed.

SEAT_CONFLICT     another sales channel sells a seat the plan is about to use
                  (a real race: plan computed at T0, seat sold at T1, batch at T2)
BAG_SYSTEM_FAULT  the baggage handling system rejects a transfer message mid-batch
"""

from __future__ import annotations

import json
import sqlite3

from . import db

KINDS = ("SEAT_CONFLICT", "BAG_SYSTEM_FAULT")


class BagSystemFault(RuntimeError):
    pass


def arm(conn: sqlite3.Connection, kind: str, at_step: int) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown fault {kind}")
    spec = {"kind": kind, "at_step": max(1, int(at_step))}
    db.set_meta(conn, "chaos", json.dumps(spec))
    return spec


def disarm(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM meta WHERE key = 'chaos'")


def peek(conn: sqlite3.Connection) -> dict | None:
    raw = db.get_meta(conn, "chaos")
    return json.loads(raw) if raw else None


def take(conn: sqlite3.Connection) -> dict | None:
    spec = peek(conn)
    if spec:
        disarm(conn)
    return spec
