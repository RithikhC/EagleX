"""Below-wing turnaround critical-path tracker (CPM) for the EK-813 rotation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from . import db, guards
from .timeutil import fmt, hm, minutes, parse, plus


def _engineer_arrival(conn: sqlite3.Connection, eibt: datetime) -> datetime:
    """B1 engineer is dispatched at event start; inspection starts after on-blocks + chocks/safety."""
    eng = db.one(conn, "SELECT * FROM engineers WHERE licence = 'B1' ORDER BY proximity_min LIMIT 1")
    dispatched = parse(db.get_meta(conn, "engineer_dispatched_at", "2026-11-21T14:50"))
    ready = plus(dispatched, eng["proximity_min"] if eng else 30)
    return max(ready, plus(eibt, 15))


def _crew_ready(conn: sqlite3.Connection, flight_id: str) -> datetime:
    """When can the full operating crew be at the aircraft?"""
    clock = db.now(conn)
    rows = db.rows(conn, """
        SELECT c.*, a.status AS asg_status, a.report_at FROM crew_assignments a JOIN crew c ON c.crew_id = a.crew_id
        WHERE a.flight_id = ? AND a.status IN ('ROSTERED','ASSIGNED')""", (flight_id,))
    latest = parse(rows[0]["report_at"]) if rows else clock
    for r in rows:
        latest = max(latest, parse(r["report_at"]) if r["report_at"] else plus(clock, r["proximity_min"]))
    has_cpt = any(r["rank"] == "CPT" and r["fitness"] == "FIT" for r in rows)
    if not has_cpt:
        # No legal captain yet: assume the nearest standby is called now (call-out + travel).
        latest = max(latest, plus(clock, guards.LIMITS.callout_response_min + 15))
    return plus(latest, 15)  # walk to aircraft / security


def critical_path(conn: sqlite3.Connection, flight_id: str = "EK813-1121") -> dict:
    flight = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (flight_id,))
    inbound = db.one(conn, "SELECT * FROM flights WHERE aircraft_reg = ? AND role = 'INBOUND_DISRUPTED'",
                     (flight["aircraft_reg"],))
    eibt = parse(inbound["eibt"])
    tasks = db.rows(conn, "SELECT * FROM turnaround_tasks WHERE flight_id = ?", (flight_id,))
    mx = {m["item_id"]: m for m in db.rows(conn, "SELECT * FROM maintenance_items")}
    by_id = {t["task_id"]: t for t in tasks}
    for t in tasks:
        t["deps"] = json.loads(t["depends_on"])

    engineer_at_aircraft = _engineer_arrival(conn, eibt)
    crew_ready = _crew_ready(conn, flight_id)

    es: dict[str, datetime] = {}
    ef: dict[str, datetime] = {}
    order = _topo(tasks)
    for tid in order:
        t = by_id[tid]
        start = max([ef[d] for d in t["deps"]] or [eibt])
        if tid == "MXI":
            item = mx.get(t["mx_item_id"]) or {}
            if item.get("status") == "CLOSED":
                start = max(start, engineer_at_aircraft)
                signed = parse(item["crs_signed_at"])
                t["duration_min"] = max(0, minutes(start, signed))
                t["note"] = f"CRS signed {hm(signed)}"
            else:
                start = max(start, engineer_at_aircraft)
                t["note"] = "B1 engineer dispatched"
        if tid == "CREW":
            start = max(start, crew_ready)
            t["note"] = f"operating crew at aircraft {hm(crew_ready)}"
        es[tid] = start
        ef[tid] = plus(start, t["duration_min"])

    eobt = max(ef.values())
    # backward pass
    lf: dict[str, datetime] = {}
    ls: dict[str, datetime] = {}
    succs = {tid: [s["task_id"] for s in tasks if tid in s["deps"]] for tid in by_id}
    for tid in reversed(order):
        t = by_id[tid]
        lf[tid] = min([ls[s] for s in succs[tid]] or [eobt])
        ls[tid] = plus(lf[tid], -t["duration_min"])
    out = []
    for tid in order:
        t = by_id[tid]
        slack = minutes(es[tid], ls[tid])
        out.append({
            "task_id": tid, "name": t["name"], "resource": t["resource"], "kind": t["kind"],
            "start": fmt(es[tid]), "end": fmt(ef[tid]), "start_hm": hm(es[tid]), "end_hm": hm(ef[tid]),
            "duration_min": t["duration_min"], "slack_min": slack, "critical": slack == 0,
            "depends_on": t["deps"], "note": t.get("note", ""),
        })
    std = parse(flight["std"])
    return {
        "flight_id": flight_id, "flight_no": flight["flight_no"], "eibt": fmt(eibt), "eibt_hm": hm(eibt),
        "eobt": fmt(eobt), "eobt_hm": hm(eobt), "std_hm": hm(std), "delay_vs_std_min": max(0, minutes(std, eobt)),
        "turn_min": minutes(eibt, eobt),
        "critical_path": [t["task_id"] for t in out if t["critical"]],
        "tasks": out,
    }


def _topo(tasks: list[dict]) -> list[str]:
    deps = {t["task_id"]: set(t["deps"]) for t in tasks}
    order, done = [], set()
    while len(order) < len(deps):
        progressed = False
        for tid in sorted(deps):
            if tid not in done and deps[tid] <= done:
                order.append(tid)
                done.add(tid)
                progressed = True
        if not progressed:  # pragma: no cover
            raise ValueError("cycle in turnaround tasks")
    return order
