"""Cascading network delay cost calculator: EU261, duty of care, connection preservation.

EU261 basis used here (simplified, for illustration):
  * EK-812 departed Larnaca (EU), so passengers on a single booking are covered
    for their whole journey to the final destination (CJEU C-537/17 Wegener;
    arrival-delay rule from C-402/07 Sturgeon and C-11/11 Folkerts).
  * Final-arrival delay of 3h or more triggers compensation by great-circle
    distance origin -> final destination: <=1500 km EUR250, <=3500 km EUR400,
    >3500 km EUR600, halved for >3500 km when the delay is 3h-4h (Art. 7(2)(c)).
  * EK-813 departs DXB on a non-EU carrier, so EU261 does not apply to it.
    Its delay is costed with a per-minute tactical delay cost (assumption).
Commercial rates are assumptions from config.py, not legal advice.
"""

from __future__ import annotations

import json
import sqlite3

from . import config, db
from .dataset import haversine_km
from .timeutil import at, hm, minutes, parse, plus


def eu261_amount(distance_km: int, arrival_delay_min: int) -> int:
    if arrival_delay_min < 180:
        return 0
    if distance_km <= 1500:
        return 250
    if distance_km <= 3500:
        return 400
    return 300 if arrival_delay_min < 240 else 600


_AIRPORTS: dict[str, dict] = {}   # reference data never changes during a scenario: read once per process


def _airports(conn) -> dict[str, dict]:
    if not _AIRPORTS:
        _AIRPORTS.update({r["code"]: dict(r) for r in conn.execute("SELECT code, lat, lon, is_eu FROM airports")})
    return _AIRPORTS


def _coords(conn) -> dict:
    return {k: (v["lat"], v["lon"]) for k, v in _airports(conn).items()}


def _eu_origin(conn, code: str) -> bool:
    a = _airports(conn).get(code)
    return bool(a and a["is_eu"])


def passenger_cost(conn, pax: dict, orig_flight: dict, new_flight: dict | None, *, new_sta=None, new_std=None) -> dict:
    ap = _airports(conn)
    distance = haversine_km((ap[pax["journey_origin"]]["lat"], ap[pax["journey_origin"]]["lon"]),
                            (ap[pax["final_dest"]]["lat"], ap[pax["final_dest"]]["lon"]))
    orig_sta = parse(orig_flight["sta"])
    orig_std = parse(orig_flight["std"])
    if new_flight is not None:
        new_sta = parse(new_flight["eta"] or new_flight["sta"])
        new_std = parse(new_flight["etd"] or new_flight["std"])
    delay = minutes(orig_sta, new_sta)
    wait = minutes(orig_std, new_std)
    covered = _eu_origin(conn, pax["journey_origin"])
    eu = eu261_amount(distance, delay) if covered else 0
    if pax["is_infant"]:
        eu = 0  # infants travelling free of charge are excluded (Art. 3(3))
    meals = config.MEAL_VOUCHER_EUR if wait >= 120 else 0
    overnight = new_std.date() > orig_std.date()
    hotel = config.HOTEL_NIGHT_EUR if overnight else 0
    return {"distance_km": distance, "arrival_delay_min": delay, "eu261": eu, "meals": meals, "hotel": hotel,
            "total": eu + meals + hotel, "same_day": not overnight}


def disruption_cost(conn: sqlite3.Connection, plan: dict | None = None) -> dict:
    """Compare legacy auto-reprotection with the AeroTurn plan (or current state)."""
    from .recovery import disrupted_pax_ids
    from .turnaround import critical_path

    flights = {f["flight_id"]: f for f in db.rows(conn, "SELECT * FROM flights")}
    pax = {p["pax_id"]: p for p in db.rows(conn, "SELECT * FROM passengers")}
    scope = sorted(disrupted_pax_ids(conn))

    # Strategy A: legacy auto-reprotect onto the same flight number tomorrow (+24h)
    legacy = {"eu261": 0, "meals": 0, "hotel": 0, "total": 0, "same_day": 0, "vulnerable_same_day": 0}
    for pid in scope:
        p = pax[pid]
        orig = flights[p["original_onward_flight"]]
        c = passenger_cost(conn, p, orig, None, new_std=plus(parse(orig["std"]), 24 * 60),
                           new_sta=plus(parse(orig["sta"]), 24 * 60))
        for k in ("eu261", "meals", "hotel", "total"):
            legacy[k] += c[k]

    # Strategy B: AeroTurn (plan if given, else what is booked now)
    if plan is not None:
        target = {a["pax_id"]: a["to_flight_id"] for a in plan["assignments"]}
    else:
        target = {r["pax_id"]: r["flight_id"] for r in
                  db.rows(conn, "SELECT pax_id, flight_id FROM bookings WHERE leg_no = 2 AND pax_id IS NOT NULL")}
    from .guards import pax_tier
    from .facts import pax_facts
    aero = {"eu261": 0, "meals": 0, "hotel": 0, "total": 0, "same_day": 0, "vulnerable_same_day": 0,
            "vulnerable": 0, "under_3h": 0}
    per_pax = []
    for pid in scope:
        p = pax[pid]
        orig = flights[p["original_onward_flight"]]
        fid = target.get(pid)
        if not fid or (fid == p["original_onward_flight"] and flights[fid]["status"] != "HELD"):
            per_pax.append({"pax_id": pid, "name": f"{p['first_name']} {p['last_name']}", "dest": p["final_dest"],
                            "from": orig["flight_no"], "to": "-", "status": "AWAITING DECISION"})
            continue
        new = flights[fid]
        c = passenger_cost(conn, p, orig, new)
        vul = pax_tier(pax_facts(p)) <= 2
        for k in ("eu261", "meals", "hotel", "total"):
            aero[k] += c[k]
        aero["same_day"] += int(c["same_day"])
        aero["under_3h"] += int(c["arrival_delay_min"] < 180)
        aero["vulnerable"] += int(vul)
        aero["vulnerable_same_day"] += int(vul and c["same_day"])
        per_pax.append({"pax_id": pid, "name": f"{p['first_name']} {p['last_name']}", "dest": p["final_dest"],
                        "from": orig["flight_no"], "to": new["flight_no"] + (" (held)" if new["status"] == "HELD" else ""),
                        "new_arrival": hm(new["eta"] or new["sta"]),
                        "delay_min": c["arrival_delay_min"], "distance_km": c["distance_km"], "eu261": c["eu261"],
                        "care": c["meals"] + c["hotel"], "vulnerable": vul})

    # Outbound rotation and its knock-on effect
    cpm = critical_path(conn, config.OUTBOUND_FLIGHT_ID)
    out = flights[config.OUTBOUND_FLIGHT_ID]
    out_delay = max(0, minutes(parse(out["std"]), parse(out["etd"]) if out["etd"] else parse(cpm["eobt"])))
    rotation_buffer = 30  # CDG ground time above minimum turn (assumption)
    knock_on = max(0, out_delay - rotation_buffer)
    outbound = {
        "flight": out["flight_no"], "delay_min": out_delay, "pax": out["load_pax"],
        "eu261": 0, "eu261_note": "Departure from DXB on a non-EU carrier: EU261 not applicable",
        "delay_cost": int(round(out_delay * (config.DELAY_COST_EUR_PER_MIN + config.PAX_MINUTE_EUR * out["load_pax"]))),
        "knock_on_return_delay_min": knock_on,
        "knock_on_cost": knock_on * config.DELAY_COST_EUR_PER_MIN,
    }
    held = [f for f in flights.values() if f["status"] == "HELD" and f["etd"]]
    hold_cost = sum(int(round(minutes(parse(f["std"]), parse(f["etd"])) *
                              (config.DELAY_COST_EUR_PER_MIN + config.PAX_MINUTE_EUR * f["load_pax"]))) for f in held)
    outbound_hold = {"flights": [f["flight_no"] for f in held], "cost": hold_cost}
    savings = legacy["total"] - aero["total"]
    return {
        "currency": config.CURRENCY,
        "scope_passengers": len(scope),
        "legacy_auto_reprotect": legacy | {"label": "Legacy: auto-reprotect to same flight +24h"},
        "aeroturn": aero | {"label": "AeroTurn priority-protected plan"},
        "savings": savings,
        "outbound_rotation": outbound,
        "connection_holds": outbound_hold,
        "network_total_aeroturn": aero["total"] + outbound["delay_cost"] + outbound["knock_on_cost"] + hold_cost,
        "network_total_legacy": legacy["total"] + outbound["delay_cost"] + outbound["knock_on_cost"],
        "assumptions": {"delay_cost_eur_per_min": config.DELAY_COST_EUR_PER_MIN,
                        "meal_voucher_eur": config.MEAL_VOUCHER_EUR, "hotel_night_eur": config.HOTEL_NIGHT_EUR,
                        "rotation_buffer_min": rotation_buffer},
        "per_passenger": per_pax,
    }


def hold_analysis(conn: sqlite3.Connection) -> list[dict]:
    """Would holding a departing connection be cheaper (and kinder) than re-accommodation?

    Hold cost  = minutes x (aircraft delay cost + passenger-minute cost x passengers on board).
    Rebook cost = EU261 + care for the protected passengers under the AeroTurn plan.
    """
    from .guards import LIMITS
    from .recovery import connection_risk, plan_recovery

    risk = connection_risk(conn, use_original=True)
    eibt = at(risk["basis"]["eibt"])
    by_flight: dict[str, list[dict]] = {}
    for p in risk["passengers"]:
        if p["at_risk"]:
            by_flight.setdefault(p["onward_flight_id"], []).append(p)
    # where would each passenger go without a hold? (current AeroTurn booking, else a dry-run plan)
    target = {r["pax_id"]: r["flight_id"] for r in db.rows(
        conn, "SELECT pax_id, flight_id FROM bookings WHERE leg_no = 2 AND source = 'AEROTURN'")}
    dry = plan_recovery(conn, persist=False)
    for a in dry["assignments"]:
        target.setdefault(a["pax_id"], a["to_flight_id"])
    pax = {p["pax_id"]: p for p in db.rows(conn, "SELECT * FROM passengers")}
    flights = {f["flight_id"]: f for f in db.rows(conn, "SELECT * FROM flights")}
    holds, frozen = {}, {}
    for r in db.rows(conn, "SELECT flight_id, status, guard_report FROM schedule_changes "
                           "WHERE change_type = 'HOLD_FLIGHT' AND status <> 'BLOCKED' ORDER BY staged_at"):
        holds[r["flight_id"]] = r["status"]
        d = json.loads(r["guard_report"]).get("derived", {})
        if "rebook_cost" in d:   # economics as they stood when the hold was proposed
            frozen[r["flight_id"]] = d
    out = []
    for fid, plist in by_flight.items():
        f = flights[fid]
        std = parse(f["std"])
        need = max(max(minutes(std, plus(eibt, p["mct_min"])),
                       minutes(std, plus(eibt, LIMITS.bag_mct_min)) if p["bags"] else 0) for p in plist)
        hold_cost = int(round(need * (config.DELAY_COST_EUR_PER_MIN + config.PAX_MINUTE_EUR * f["load_pax"])))
        rebook_cost = 0
        for p in plist:
            t = target.get(p["pax_id"])
            if t and t != fid:
                rebook_cost += passenger_cost(conn, pax[p["pax_id"]], f, flights[t])["total"]
        if fid in frozen:
            need, hold_cost, rebook_cost = frozen[fid]["hold_min"], frozen[fid]["hold_cost"], frozen[fid]["rebook_cost"]
        allowed = need <= LIMITS.max_connection_hold_min
        recommended = allowed and need <= config.MAX_RECOMMENDED_HOLD_MIN and hold_cost < rebook_cost
        out.append({
            "flight": f["flight_no"], "flight_id": fid, "dest": f["dest"], "std": hm(std),
            "pax_protected": len(plist), "vulnerable_protected": sum(1 for p in plist if p["vulnerable"]),
            "hold_needed_min": need, "allowed": allowed, "hold_cost": hold_cost, "rebook_cost": rebook_cost,
            "net_saving": rebook_cost - hold_cost, "recommended": recommended,
            "onboard_pax_delayed": f["load_pax"], "hold_status": holds.get(fid, "-"),
        })
    out.sort(key=lambda x: (not x["recommended"], x["hold_needed_min"]))
    return out
