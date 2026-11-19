"""Automated standby crew pairing matcher.

Finds a legal replacement crew member within terminal proximity. Every
candidate, including the closest one physically, goes through the
flight-time-limitation guard.
"""

from __future__ import annotations

import sqlite3

from . import db, guards
from .facts import crew_facts
from .timeutil import dur, hm, parse, plus


def find_standby_crew(conn: sqlite3.Connection, *, flight_id: str, rank: str = "CPT", off_blocks=None) -> dict:
    from .turnaround import critical_path

    flight = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (flight_id,))
    clock = db.now(conn)
    if off_blocks is None:
        off_blocks = parse(flight["etd"]) if flight["etd"] else parse(critical_path(conn, flight_id)["eobt"])
    assigned = {r["crew_id"] for r in db.rows(conn, "SELECT crew_id FROM crew_assignments WHERE flight_id = ?",
                                              (flight_id,))}
    rows = db.rows(conn, """SELECT * FROM crew WHERE rank = ? AND (duty_kind IN ('AIRPORT_STANDBY','HOME_STANDBY')
                            OR duty_kind = 'ON_DUTY')""", (rank,))
    candidates = []
    for r in rows:
        if r["crew_id"] in assigned:
            continue
        cf = crew_facts(r)
        on_standby = r["duty_kind"] in ("AIRPORT_STANDBY", "HOME_STANDBY")
        report = plus(clock, guards.LIMITS.callout_response_min + r["proximity_min"]) if on_standby else clock
        verdict = guards.check_crew_for_sector(cf, aircraft_type=flight["aircraft_type"], off_blocks=off_blocks,
                                               block_min=flight["block_min"], report_time=report)
        f = verdict.facts
        candidates.append({
            "crew_id": r["crew_id"], "name": r["name"], "rank": r["rank"], "status": r["duty_kind"],
            "type_ratings": r["type_ratings"], "location": r["location"], "proximity_min": r["proximity_min"],
            "can_report": hm(report), "fdp_basis": f.get("fdp_basis"),
            "fdp_limit": hm(f.get("fdp_limit")) if f.get("fdp_limit") else None,
            "margin": dur(f["margin_min"]) if "margin_min" in f else None,
            "margin_min": f.get("margin_min"),
            "legal": verdict.ok,
            "violations": [v.as_dict() for v in verdict.violations],
        })
    legal = sorted([c for c in candidates if c["legal"]], key=lambda c: (c["proximity_min"], -(c["margin_min"] or 0)))
    illegal = sorted([c for c in candidates if not c["legal"]], key=lambda c: c["proximity_min"])
    selected = legal[0] if legal else None
    return {
        "flight": flight["flight_no"], "flight_id": flight_id, "rank": rank, "planned_off_blocks": hm(off_blocks),
        "sector_block_min": flight["block_min"], "projected_on_blocks": hm(plus(off_blocks, flight["block_min"])),
        "selected": selected,
        "candidates": legal + illegal,
        "summary": (f"{selected['name']} ({selected['crew_id']}) is the nearest legal {rank}: {selected['location']}, "
                    f"{selected['proximity_min']} min away, FDP margin {selected['margin']}."
                    if selected else f"No legal {rank} available - escalate to crew control."),
    }
