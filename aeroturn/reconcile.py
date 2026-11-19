"""Continuous re-validation ("reconcile").

The world keeps moving after a plan is staged: a flight holds, a standby
captain reports fatigue, an inspection finds a leak, a controller says no,
a deadline passes. reconcile() re-checks everything with fresh facts:

  1. every PENDING change is re-run through the guards; expired ones are
     expired, illegal ones are WITHDRAWN (never silently left in the queue);
  2. a legal replacement is staged when one exists (next legal stand,
     next legal captain, new critical-path ETD);
  3. passengers whose connections broke are re-planned atomically;
  4. anything with no legal option is ESCALATED to humans, with the reason
     and the options. The model never "solves" a problem by breaking a floor.

Everything here goes through the same guarded tools as the agent.
"""

from __future__ import annotations

import json
import sqlite3

from . import audit, config, costs, db, guards, hitl, recovery, tools, turnaround
from .timeutil import fmt, hm, parse, plus

ACTOR = "AGENT:reconcile"


def escalate(conn: sqlite3.Connection, topic: str, reason: str, options: list[str] | None = None) -> dict:
    """Hand a problem with no legal automated answer to humans. Idempotent per (topic, reason)."""
    item = {"topic": topic, "reason": reason, "options": options or []}
    if any(e["topic"] == topic and e["reason"] == reason for e in escalations(conn)):
        return item | {"repeat": True}
    audit.log(conn, "SYSTEM", "ESCALATION", item)
    return item


def rejected_gates(conn: sqlite3.Connection) -> list[str]:
    """Stands a controller rejected (or the agent withdrew): never re-proposed in this disruption."""
    return sorted({json.loads(r["payload"]).get("new_gate") for r in db.rows(
        conn, "SELECT payload FROM schedule_changes WHERE change_type = 'GATE_REASSIGNMENT' "
              "AND status = 'REJECTED'")} - {None})


def no_stand_escalation(conn: sqlite3.Connection, go: dict) -> dict:
    least = max(go["options"], key=lambda o: o["crew_fdp_margin_min"])
    return escalate(
        conn, "Inbound crew duty",
        f"No stand keeps the inbound crew within FDP: best case {least['gate']} at {least['eibt']} is "
        f"{-least['crew_fdp_margin_min']} min over. Commander's discretion (ORO.FTL.205(f)) is the "
        f"commander's decision after an unforeseen delay; AeroTurn never plans on it.",
        [f"Controller allocates {least['gate']} manually", "Crew control logs the discretion report",
         "Extended rest for the inbound crew"])


def no_captain_escalation(conn: sqlite3.Connection, sc: dict) -> dict:
    return escalate(
        conn, "EK813 captain",
        "No captain passes flight-time limitations; EK813 stays grounded (any release is blocked by FTL-005).",
        [f"{c['crew_id']} {c['name']}: {', '.join(v['rule'] for v in c['violations'])}"
         for c in sc["candidates"]] + ["Crew control: call an off-duty captain, or controller retimes/cancels"])


def escalations(conn: sqlite3.Connection) -> list[dict]:
    return [json.loads(r["detail"]) | {"seq": r["seq"], "sim_time": r["sim_time"]} for r in db.rows(
        conn, "SELECT seq, sim_time, detail FROM audit_log WHERE action = 'ESCALATION' ORDER BY seq")]


def _stage(conn, change_type: str, flight_no: str, details: dict, why: str) -> dict:
    return tools.dispatch(conn, "stage_controller_schedule_change",
                          {"change_type": change_type, "flight_no": flight_no, "details": details, "justification": why},
                          actor=ACTOR)


def _has(conn, change_type: str, statuses=("PENDING", "APPROVED")) -> list[dict]:
    marks = ",".join("?" * len(statuses))
    return db.rows(conn, f"SELECT * FROM schedule_changes WHERE change_type = ? AND status IN ({marks}) "
                         f"ORDER BY staged_at", (change_type, *statuses))


_ORDER = {"CREW_SWAP": 0, "GATE_REASSIGNMENT": 1, "HOLD_FLIGHT": 2, "RETIME": 3, "DEPARTURE_RELEASE": 4}

UNRESOLVED_CARE = {
    "UMNR": "UMNR care protocol: escort stays with the child, lounge or hotel with escort, next home-carrier flight "
            "departing before 22:00; guardian informed by phone",
    "MEDA": "MEDIF re-clearance with the partner's medical desk, or next home-carrier flight; medical team informed",
}


def reconcile(conn: sqlite3.Connection) -> dict:
    events: list[str] = []
    raised: list[dict] = []
    clock = db.now(conn)
    inb = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))
    eibt = parse(inb["eibt"])

    # 1. re-validate every pending change with fresh facts (crew first: a retime is judged with the staged crew)
    for ch in sorted(hitl.pending(conn), key=lambda c: _ORDER.get(c["change_type"], 9)):
        if ch["valid_until"] and clock > parse(ch["valid_until"]):
            hitl.expire(conn, ch["change_id"])
            events.append(f"{ch['change_type']} {ch['change_id']} expired (decision window {hm(ch['valid_until'])})")
            continue
        flight = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (ch["flight_id"],))
        try:
            g = tools.guard_for_change(conn, ch["change_type"], flight, ch["payload"])
        except tools.ToolError as exc:
            g = {"verdict": {"ok": False, "rules_violated": [str(exc)]}}
        if not g["verdict"]["ok"]:
            rules = ", ".join(g["verdict"]["rules_violated"])
            hitl.withdraw(conn, ch["change_id"], f"no longer legal: {rules}", actor=ACTOR)
            events.append(f"{ch['change_type']} {ch['change_id']} withdrawn: no longer legal ({rules})")
        elif ch["valid_until"] and g["derived"].get("valid_until") not in (None, ch["valid_until"]):
            # still legal, but the facts behind it moved (e.g. a new in-block time): re-stage with fresh numbers
            hitl.withdraw(conn, ch["change_id"], f"superseded: decision window now {hm(g['derived']['valid_until'])}",
                          actor=ACTOR)
            payload = {k: v for k, v in ch["payload"].items() if not k.startswith("_")}
            r = _stage(conn, ch["change_type"], ch["flight_no"], payload,
                       f"Re-staged with fresh facts: decision window {hm(ch['valid_until'])} → "
                       f"{hm(g['derived']['valid_until'])}. " + (ch["justification"] or "")[:300])
            events.append(f"{ch['change_type']} re-staged with fresh facts as {r.get('change_id')}: decision window "
                          f"{hm(ch['valid_until'])} → {hm(g['derived']['valid_until'])}")

    # 2. arrival stand
    if not _has(conn, "GATE_REASSIGNMENT") and inb["status"] == "APPROACH" and inb["gate_id"] == "B14":
        rejected = rejected_gates(conn)
        go = tools.evaluate_gate_options(conn, exclude=rejected)
        legal = [o for o in go["options"] if o["legal"] and o["gate"] not in rejected]
        still_open = [o for o in legal if clock <= plus(parse(o["eibt_iso"]), -5)]
        best = min(still_open, key=lambda o: (o["misconnects"], o["hold_for_stand_min"])) if still_open else None
        if best:
            why = [f"controller rejected {', '.join(rejected)}"] if rejected else []
            if go["recommended"] and go["recommended"] != best["gate"] and go["recommended"] not in rejected:
                why.append(f"{go['recommended']}'s decision window has closed")
            r = _stage(conn, "GATE_REASSIGNMENT", "EK812", {"new_gate": best["gate"]},
                       f"{best['gate']}: best legal stand still open (in-block {best['eibt']}, crew margin "
                       f"{best['crew_fdp_margin_min']} min)" + (f"; {'; '.join(why)}" if why else ""))
            events.append(f"staged GATE_REASSIGNMENT → {best['gate']}: {r.get('status')}"
                          + (f" ({'; '.join(why)})" if why else ""))
        elif legal:
            last = max(plus(parse(o["eibt_iso"]), -5) for o in legal)
            raised.append(escalate(conn, "Arrival stand", f"Every decision window has closed (last at {hm(last)}): "
                                   f"EK812 will hold for B14 and the inbound crew exceeds FDP unless a stand is "
                                   f"allocated by hand now.",
                                   [f"Allocate {', '.join(o['gate'] for o in legal)} manually and file a "
                                    f"commander's-discretion report", "Crew control plans extended rest"]))
        else:
            raised.append(no_stand_escalation(conn, go))

    # 3. outbound captain
    out = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (config.OUTBOUND_FLIGHT_ID,))
    fit_cpt = db.one(conn, """SELECT c.crew_id FROM crew_assignments a JOIN crew c ON c.crew_id = a.crew_id
                              WHERE a.flight_id = ? AND a.status IN ('ROSTERED','ASSIGNED') AND c.rank = 'CPT'
                              AND c.fitness = 'FIT'""", (out["flight_id"],))
    if not fit_cpt and not _has(conn, "CREW_SWAP", ("PENDING",)):
        sc = tools.find_standby_crew(conn, "EK813", "CPT")
        unfit = db.one(conn, "SELECT crew_id FROM crew_assignments WHERE flight_id = ? AND role = 'CPT' "
                             "AND status = 'REMOVED' ORDER BY crew_id LIMIT 1", (out["flight_id"],))
        if sc["selected"]:
            sel = sc["selected"]
            r = _stage(conn, "CREW_SWAP", "EK813", {"remove_crew_id": unfit["crew_id"] if unfit else "C-B01",
                                                    "add_crew_id": sel["crew_id"], "role": "CPT"},
                       f"Re-validation: {sel['name']} is now the nearest legal captain (margin {sel['margin']}).")
            events.append(f"staged CREW_SWAP → {sel['crew_id']}: {r.get('status')}")
        else:
            raised.append(no_captain_escalation(conn, sc))

    # 4. outbound ETD vs critical path
    cpm = turnaround.critical_path(conn, out["flight_id"])
    approved_etd = parse(out["etd"]) if out["etd"] else None
    if not _has(conn, "RETIME", ("PENDING",)) and (approved_etd is None or approved_etd < parse(cpm["eobt"])) \
            and out["status"] != "RELEASED":
        r = _stage(conn, "RETIME", "EK813", {"new_etd": cpm["eobt_hm"]},
                   f"Re-validation: critical path {' > '.join(cpm['critical_path'])} now gives EOBT {cpm['eobt_hm']}.")
        events.append(f"staged RETIME → {cpm['eobt_hm']}: {r.get('status')}")

    # 5. passengers: first ask whether a short hold beats stranding them, then re-plan the rest atomically
    rebook = None
    risk = recovery.connection_risk(conn)
    if risk["at_risk"]:
        decided = {r["flight_id"] for r in _has(conn, "HOLD_FLIGHT", ("PENDING", "APPROVED", "REJECTED", "EXPIRED"))}
        for h in costs.hold_analysis(conn):
            if not h["recommended"] or h["flight_id"] in decided or clock > plus(parse(h["std"]), -5):
                continue
            r = _stage(conn, "HOLD_FLIGHT", h["flight"], {"hold_min": h["hold_needed_min"]},
                       f"Re-validation: holding {h['flight']} {h['hold_needed_min']} min protects {h['pax_protected']} "
                       f"connection(s) for AED {h['hold_cost']:,} instead of AED {h['rebook_cost']:,} to re-accommodate.")
            events.append(f"staged HOLD_FLIGHT {h['flight']} +{h['hold_needed_min']} min for {h['pax_protected']} "
                          f"passenger(s): {r.get('status')} (AED {h['hold_cost']:,} vs AED {h['rebook_cost']:,})")
        risk = recovery.connection_risk(conn)
    if risk["at_risk"]:
        p = tools.dispatch(conn, "plan_passenger_recovery", {"objective": "earliest_arrival"}, actor=ACTOR)
        r = tools.dispatch(conn, "execute_atomic_passenger_rebook", {"plan_id": p["plan_id"]}, actor=ACTOR)
        if r.get("status") == "ROLLED_BACK":
            p = tools.dispatch(conn, "plan_passenger_recovery", {"objective": "earliest_arrival"}, actor=ACTOR)
            r = tools.dispatch(conn, "execute_atomic_passenger_rebook", {"plan_id": p["plan_id"]}, actor=ACTOR)
        if r.get("status") != "NOOP":  # NOOP: only passengers with no legal seat today are left (escalated below)
            events.append(f"{risk['at_risk']} connection(s) at risk under in-block {hm(eibt)}: re-planning")
            events.append(f"rebooking {r.get('status')}: {r.get('summary', {}).get('rebooked', 0)} passenger(s)")
        rebook = {"status": r.get("status"), "rebooked": r.get("summary", {}).get("rebooked", 0),
                  "unresolved": [u["name"] for u in p.get("unresolved", [])]}
        prow = {x["pax_id"]: x for x in db.rows(conn, "SELECT * FROM passengers")}
        for u in p.get("unresolved", []):
            ssr = set((prow[u["pax_id"]]["ssr"] or "").split(","))
            care = next((v for k, v in UNRESOLVED_CARE.items() if k in ssr),
                        "Protect on the next available flight; hotel and meals")
            raised.append(escalate(conn, f"Passenger {u['name']}",
                                   f"No legal option today ({guards.TIER_LABELS[u['tier']]}): {u['reason']}", [care]))
    raised = [e for e in raised if not e.get("repeat")]
    audit.log(conn, "SYSTEM", "RECONCILE", {"events": len(events), "escalations": len(raised)})
    return {"events": events, "escalations": raised, "rebook": rebook, "at": fmt(clock)}
