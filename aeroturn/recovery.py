"""Connection-risk analysis and the priority-protected rebooking planner.

This is deterministic code. The LLM may pick an objective and read the
result, but it cannot change the tier ordering, the MCT rules or the seat
eligibility rules: those come from guards.py.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime

from . import db, guards
from .facts import bag_counts, option_facts, pax_facts
from .timeutil import fmt, hm, minutes, parse, plus

CRITICALITY = ["UMNR", "MEDA", "WCHC", "BLND", "DEAF", "DPNA", "PREG", "WCHS", "WCHR", "INFT"]
OBJECTIVES = ("earliest_arrival", "home_carrier_first")


def inbound(conn: sqlite3.Connection) -> dict:
    return db.one(conn, "SELECT * FROM flights WHERE role = 'INBOUND_DISRUPTED'")


def arrival_basis(conn: sqlite3.Connection, *, gate_id: str | None = None, eibt: datetime | None = None) -> dict:
    f = inbound(conn)
    gate = db.one(conn, "SELECT * FROM gates WHERE gate_id = ?", (gate_id or f["gate_id"],))
    return {"eibt": eibt or parse(f["eibt"]), "gate_id": gate["gate_id"], "remote": gate["kind"] == "REMOTE"}


def connection_risk(conn: sqlite3.Connection, *, eibt: datetime | None = None, gate_id: str | None = None,
                    use_original: bool = False) -> dict:
    """Evaluate every connection of EK-812 passengers against passenger-specific MCT."""
    basis = arrival_basis(conn, gate_id=gate_id, eibt=eibt)
    bags = bag_counts(conn)
    if use_original:
        sql = """SELECT p.*, f.flight_id AS onward_id, f.flight_no AS onward_no, f.std AS onward_std, f.etd AS onward_etd
                 FROM passengers p JOIN flights f ON f.flight_id = p.original_onward_flight WHERE p.is_connecting = 1"""
    else:
        sql = """SELECT p.*, f.flight_id AS onward_id, f.flight_no AS onward_no, f.std AS onward_std, f.etd AS onward_etd
                 FROM passengers p JOIN bookings b ON b.pax_id = p.pax_id AND b.leg_no = 2
                 JOIN flights f ON f.flight_id = b.flight_id WHERE p.is_connecting = 1"""
    holds = {} if use_original else pending_holds(conn)
    out = []
    for r in db.rows(conn, sql):
        pf = pax_facts(r, bags.get(r["pax_id"], 0))
        # the original disruption scope is judged against the schedule, live risk against estimates
        std = parse(r["onward_std"] if use_original else (r["onward_etd"] or r["onward_std"]))
        mct = guards.pax_mct_minutes(pf, remote_arrival=basis["remote"])
        slack = minutes(basis["eibt"], std)
        at_risk = slack < mct or (pf.bag_count > 0 and slack < guards.LIMITS.bag_mct_min)
        held = holds.get(r["onward_id"])
        hold_pending = bool(at_risk and held and minutes(basis["eibt"], held) >= max(
            mct, guards.LIMITS.bag_mct_min if pf.bag_count else 0))
        tier = guards.pax_tier(pf)
        out.append({
            "pax_id": pf.pax_id, "pnr": pf.pnr, "name": pf.name, "age": pf.age, "cabin": pf.cabin,
            "loyalty": pf.loyalty, "ssr": ",".join(pf.ssr), "tier": tier, "tier_label": guards.TIER_LABELS[tier],
            "vulnerable": tier <= 2, "dest": pf.final_dest, "onward_flight": r["onward_no"],
            "onward_flight_id": r["onward_id"], "onward_std": hm(std), "mct_min": mct, "slack_min": slack,
            "at_risk": at_risk and not hold_pending, "hold_pending": hold_pending,
            "bags": pf.bag_count, "is_infant": pf.is_infant, "remarks": r["remarks"],
        })
    out.sort(key=lambda x: (not x["at_risk"], x["tier"], x["onward_std"], x["pnr"]))
    at_risk = [x for x in out if x["at_risk"]]
    return {
        "basis": {"eibt": hm(basis["eibt"]), "gate_id": basis["gate_id"], "remote": basis["remote"]},
        "connecting": len(out),
        "at_risk": len(at_risk),
        "awaiting_hold_decision": sum(1 for x in out if x["hold_pending"]),
        "vulnerable_at_risk": sum(1 for x in at_risk if x["vulnerable"]),
        "critical_at_risk": sum(1 for x in at_risk if x["tier"] == 1),
        "by_tier": {guards.TIER_LABELS[t]: sum(1 for x in at_risk if x["tier"] == t) for t in (1, 2, 3, 4)},
        "by_flight": _count(at_risk, "onward_flight"),
        "bags_at_risk": sum(x["bags"] for x in at_risk),
        "passengers": out,
    }


def pending_holds(conn: sqlite3.Connection) -> dict[str, datetime]:
    """Departing connections with a still-valid HOLD awaiting the controller -> proposed new ETD."""
    clock = db.now(conn)
    out = {}
    for r in db.rows(conn, "SELECT * FROM schedule_changes WHERE change_type = 'HOLD_FLIGHT' AND status = 'PENDING'"):
        if r["valid_until"] and clock > parse(r["valid_until"]):
            continue
        new_etd = json.loads(r["guard_report"]).get("derived", {}).get("new_etd")
        if new_etd:
            out[r["flight_id"]] = parse(new_etd)
    return out


def disrupted_pax_ids(conn: sqlite3.Connection) -> set[str]:
    """Scope of this disruption: passengers whose ORIGINAL connection breaks."""
    return {p["pax_id"] for p in connection_risk(conn, use_original=True)["passengers"] if p["at_risk"]}


def _count(items, key):
    out: dict[str, int] = {}
    for x in items:
        out[x[key]] = out.get(x[key], 0) + 1
    return out


# ---------------------------------------------------------------------------
# Inventory helpers
# ---------------------------------------------------------------------------
def candidate_flights(conn: sqlite3.Connection, dest: str, after: datetime) -> list[dict]:
    rows = db.rows(conn, """SELECT * FROM flights WHERE origin = 'DXB' AND dest = ? AND role = 'ONWARD'
                            AND status NOT IN ('DEPARTED','CANCELLED')""", (dest,))
    return [r for r in rows if parse(r["etd"] or r["std"]) > after]


def free_seats(conn: sqlite3.Connection, flight_ids: list[str]) -> dict[str, list[dict]]:
    if not flight_ids:
        return {}
    marks = ",".join("?" * len(flight_ids))
    out: dict[str, list[dict]] = {fid: [] for fid in flight_ids}
    for r in db.rows(conn, f"""
            SELECT s.* FROM seats s
            LEFT JOIN bookings b ON b.flight_id = s.flight_id AND b.seat_no = s.seat_no
            WHERE b.booking_id IS NULL AND s.flight_id IN ({marks})
            ORDER BY s.flight_id, s.row_no, s.letter""", flight_ids):
        out[r["flight_id"]].append(r)
    return out


def free_counts(seats_by_flight: dict[str, list[dict]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for fid, seats in seats_by_flight.items():
        c: dict[str, int] = {}
        for s in seats:
            c[s["cabin"]] = c.get(s["cabin"], 0) + 1
        out[fid] = c
    return out


def _pick_seats(free: list[dict], members: list[guards.PaxFacts], cabin: str, respect_rules: bool = True) -> list | None:
    """Choose seats for a group in one cabin. Returns list aligned with members (None for infants)."""
    seated = [m for m in members if not m.is_infant]
    pool = [s for s in free if s["cabin"] == cabin]
    if len(pool) < len(seated):
        return None
    chosen: dict[str, dict] = {}
    # families: try to keep them in one row
    if len(seated) > 1:
        rows: dict[int, list[dict]] = {}
        for s in pool:
            if not respect_rules or not s["is_exit"] or all(guards.exit_row_permitted(m) for m in seated):
                rows.setdefault(s["row_no"], []).append(s)
        for row_no in sorted(rows):
            if len(rows[row_no]) >= len(seated):
                for m, s in zip(seated, rows[row_no]):
                    chosen[m.pax_id] = s
                break
    if not chosen:
        remaining = list(pool)
        for m in seated:
            def score(s, m=m):
                prm = bool(set(m.ssr) & (guards.PRM_SSR | {"UMNR", "MEDA", "PREG"}))
                return (s["row_no"] if prm else 0) - (3 if prm and s["is_aisle"] else 0) + (0 if prm else s["row_no"] / 100)
            ok = [s for s in remaining if not respect_rules or not s["is_exit"] or guards.exit_row_permitted(m)]
            if not ok:
                return None
            best = min(ok, key=score)
            chosen[m.pax_id] = best
            remaining.remove(best)
    return [chosen.get(m.pax_id) for m in members]


def _group_sort_key(members: list[guards.PaxFacts], original_std: str) -> tuple:
    tier = guards.group_tier(members)
    ssr = {x for m in members for x in m.ssr}
    crit = min([CRITICALITY.index(x) for x in ssr if x in CRITICALITY] or [len(CRITICALITY)])
    return (tier, crit, original_std, members[0].pnr)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------
def plan_recovery(conn: sqlite3.Connection, *, objective: str = "earliest_arrival", created_by: str = "AGENT",
                  persist: bool = True, only: set[str] | None = None,
                  reserved: set[tuple[str, str]] | None = None) -> dict:
    """Priority-protected plan. ``only`` limits it to some passengers (re-planning one failed batch);
    ``reserved`` seats (flight_id, seat_no) are held for batches that have not run yet and are never offered."""
    if objective not in OBJECTIVES:
        objective = "earliest_arrival"
    basis = arrival_basis(conn)
    eibt, remote = basis["eibt"], basis["remote"]
    risk = connection_risk(conn)
    at_risk = [p for p in risk["passengers"] if p["at_risk"] and (only is None or p["pax_id"] in only)]
    prow = {r["pax_id"]: r for r in db.rows(conn, "SELECT * FROM passengers")}
    bags = bag_counts(conn)
    bag_tags: dict[str, list[str]] = {}
    for r in conn.execute("SELECT bag_tag, pax_id FROM bags ORDER BY bag_tag"):
        bag_tags.setdefault(r["pax_id"], []).append(r["bag_tag"])

    groups: dict[str, list[dict]] = {}
    for p in at_risk:
        groups.setdefault(p["pnr"], []).append(p)

    dests = sorted({p["dest"] for p in at_risk})
    flights = {d: candidate_flights(conn, d, eibt) for d in dests}
    all_ids = [f["flight_id"] for fl in flights.values() for f in fl]
    inventory = free_seats(conn, all_ids)
    if reserved:
        inventory = {fid: [s for s in seats if (fid, s["seat_no"]) not in reserved] for fid, seats in inventory.items()}
    inv_hash = hashlib.sha256(json.dumps({k: [s["seat_no"] for s in v] for k, v in sorted(inventory.items())})
                              .encode()).hexdigest()[:16]
    start_counts = free_counts(inventory)

    ordered = sorted(groups.values(),
                     key=lambda g: _group_sort_key([pax_facts(prow[x["pax_id"]], bags.get(x["pax_id"], 0)) for x in g],
                                                   g[0]["onward_std"]))
    assignments, unresolved = [], []
    for g in ordered:
        members = [pax_facts(prow[x["pax_id"]], bags.get(x["pax_id"], 0)) for x in g]
        tier = guards.group_tier(members)
        opts = [option_facts(f) for f in flights[g[0]["dest"]]]
        if objective == "home_carrier_first":
            opts.sort(key=lambda o: (not o.operated_by_home, o.sta))
        else:
            opts.sort(key=lambda o: (o.sta, not o.operated_by_home))
        placed = False
        skipped: list[str] = []
        for opt in opts:
            violations = [v for m in members
                          for v in guards.check_pax_option(m, opt, cabin=m.cabin, eibt=eibt, remote_arrival=remote)]
            if violations:
                skipped.append(f"{opt.flight_no}: {violations[0].rule}")
                continue
            cabins = [members[0].cabin]
            if tier == 1:  # protection upgrade for critical-vulnerable passengers only
                cabins += [c for c in ("J", "F") if guards.CABIN_RANK[c] > guards.CABIN_RANK[members[0].cabin]]
            for cabin in cabins:
                seats = _pick_seats(inventory[opt.flight_id], members, cabin)
                if seats is None:
                    continue
                for m, s in zip(members, seats):
                    if s:
                        inventory[opt.flight_id].remove(s)
                    orig = next(x for x in g if x["pax_id"] == m.pax_id)
                    assignments.append({
                        "pax_id": m.pax_id, "pnr": m.pnr, "name": m.name, "tier": guards.pax_tier(m),
                        "group_tier": tier, "tier_label": guards.TIER_LABELS[guards.pax_tier(m)],
                        "ssr": ",".join(m.ssr), "cabin_booked": m.cabin, "cabin": cabin,
                        "upgrade": cabin != m.cabin, "from_flight": orig["onward_flight"],
                        "from_std": orig["onward_std"], "to_flight_id": opt.flight_id, "to_flight_no": opt.flight_no,
                        "to_std": hm(opt.std), "to_sta": hm(opt.sta), "partner": not opt.operated_by_home,
                        "seat_no": s["seat_no"] if s else None, "seat_is_exit": bool(s and s["is_exit"]),
                        "bags": bag_tags.get(m.pax_id, []), "dest": m.final_dest,
                        "skipped": list(skipped),
                    })
                placed = True
                break
            if placed:
                break
            skipped.append(f"{opt.flight_no}: no {'/'.join(cabins)} seats")
        if not placed:
            for m in members:
                unresolved.append({"pax_id": m.pax_id, "name": m.name, "tier": guards.pax_tier(m),
                                   "dest": m.final_dest, "reason": "; ".join(skipped) or "no flights"})

    plan = {
        "plan_id": f"PLAN-{uuid.uuid4().hex[:8].upper()}",
        "objective": objective,
        "created_by": created_by,
        "basis": {"eibt": fmt(eibt), "gate_id": basis["gate_id"], "remote": remote, "inventory_hash": inv_hash},
        "free_before": start_counts,
        "assignments": assignments,
        "unresolved": unresolved,
        "summary": _plan_summary(assignments, unresolved),
    }
    if persist:
        _persist(conn, plan)
    return plan


def plan_naive(conn: sqlite3.Connection, *, persist: bool = True) -> dict:
    """What an unconstrained, commercially-biased optimiser would do.

    Revenue first (cabin, loyalty), one MCT for everyone, no UMNR/MEDA carrier
    rules, no group integrity. Used to show what the guards catch.
    """
    basis = arrival_basis(conn)
    eibt = basis["eibt"]
    risk = connection_risk(conn)
    at_risk = [p for p in risk["passengers"] if p["at_risk"]]
    prow = {r["pax_id"]: r for r in db.rows(conn, "SELECT * FROM passengers")}
    bags = bag_counts(conn)
    rank_cabin = {"F": 0, "J": 1, "Y": 2}
    rank_loyal = {"PLATINUM": 0, "GOLD": 1, "SILVER": 2, "BLUE": 3, "NONE": 4}
    order = sorted(at_risk, key=lambda p: (rank_cabin[p["cabin"]], rank_loyal.get(p["loyalty"], 4), p["pax_id"]))
    dests = sorted({p["dest"] for p in at_risk})
    flights = {d: candidate_flights(conn, d, eibt) for d in dests}
    inventory = free_seats(conn, [f["flight_id"] for fl in flights.values() for f in fl])
    start_counts = free_counts(inventory)
    assignments = []
    for p in order:
        m = pax_facts(prow[p["pax_id"]], bags.get(p["pax_id"], 0))
        opts = sorted((option_facts(f) for f in flights[p["dest"]]), key=lambda o: o.std)
        for opt in opts:
            if opt.std < plus(eibt, guards.LIMITS.base_mct_min):   # one-size-fits-all MCT
                continue
            pool = [s for s in inventory[opt.flight_id] if s["cabin"] == m.cabin]
            if m.is_infant:
                seat = None
            elif pool:
                seat = pool[0]
                inventory[opt.flight_id].remove(seat)
            else:
                continue
            assignments.append({
                "pax_id": m.pax_id, "pnr": m.pnr, "name": m.name, "tier": guards.pax_tier(m),
                "group_tier": guards.pax_tier(m), "tier_label": guards.TIER_LABELS[guards.pax_tier(m)],
                "ssr": ",".join(m.ssr), "cabin_booked": m.cabin, "cabin": m.cabin, "upgrade": False,
                "from_flight": p["onward_flight"], "from_std": p["onward_std"], "to_flight_id": opt.flight_id,
                "to_flight_no": opt.flight_no, "to_std": hm(opt.std), "to_sta": hm(opt.sta),
                "partner": not opt.operated_by_home, "seat_no": seat["seat_no"] if seat else None,
                "seat_is_exit": bool(seat and seat["is_exit"]), "bags": [], "dest": m.final_dest, "skipped": [],
            })
            break
    plan = {
        "plan_id": f"NAIVE-{uuid.uuid4().hex[:6].upper()}", "objective": "revenue_first (unconstrained)",
        "created_by": "UNCONSTRAINED_BASELINE",
        "basis": {"eibt": fmt(eibt), "gate_id": basis["gate_id"], "remote": basis["remote"]},
        "free_before": start_counts, "assignments": assignments, "unresolved": [],
        "summary": _plan_summary(assignments, []),
    }
    if persist:
        _persist(conn, plan)
    return plan


def _plan_summary(assignments: list[dict], unresolved: list[dict]) -> dict:
    vul = [a for a in assignments if a["tier"] <= 2]
    return {
        "rebooked": len(assignments), "unresolved": len(unresolved),
        "vulnerable_rebooked": len(vul), "upgrades": sum(1 for a in assignments if a["upgrade"]),
        "partner_flights": sum(1 for a in assignments if a["partner"]),
        "bags_rerouted": sum(len(a["bags"]) for a in assignments),
        "flights_used": sorted({a["to_flight_no"] for a in assignments}),
    }


def _persist(conn: sqlite3.Connection, plan: dict) -> None:
    conn.execute("INSERT INTO plans VALUES(?,?,?,?,?,?,?,?)",
                 (plan["plan_id"], fmt(db.now(conn)), plan["objective"], json.dumps(plan["basis"]),
                  json.dumps(plan["assignments"]), json.dumps(plan["summary"] | {"unresolved_list": plan["unresolved"],
                                                                                  "free_before": plan["free_before"]}),
                  "PROPOSED", plan["created_by"]))


def load_plan(conn: sqlite3.Connection, plan_id: str) -> dict | None:
    r = db.one(conn, "SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
    if not r:
        return None
    summary = json.loads(r["summary"])
    return {"plan_id": r["plan_id"], "objective": r["objective"], "basis": json.loads(r["basis"]),
            "assignments": json.loads(r["assignments"]), "unresolved": summary.pop("unresolved_list", []),
            "free_before": summary.pop("free_before", {}), "summary": summary, "status": r["status"],
            "created_by": r["created_by"]}
