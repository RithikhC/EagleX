"""Human-in-the-loop gate: Operations Controller approvals and engineer sign-off.

This module is NOT part of the agent tool registry. Only the OCC console
(a human clicking Approve or Reject) and the tests call it.

Approval is not a rubber stamp. The guards run again with fresh facts at
approval time, so a change that became illegal while it sat in the queue
cannot be approved, and the controller cannot override a guard either.

An approval is bound to the state the controller saw: every staged change
carries a hash of the facts it depends on (who else holds the stand, the
standby's duty record, the flight's schedule). At execution the hash is
recomputed; if the world moved, the approval is refused as STALE and the
change is re-staged for a fresh decision. Approve and execute can be two
steps (approve(..., execute=False) then execute_approved()).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from . import audit, config, db, guards
from .facts import mx_facts
from .timeutil import fmt, hm, parse, plus

_FORBIDDEN_NAMES = ("agent", "aeroturn", "llm", "assistant", "bot", "system")


@dataclass(frozen=True, slots=True)
class ControllerIdentity:
    name: str
    licence_id: str
    role: str = "OPS_CONTROLLER"


class ApprovalError(PermissionError):
    pass


def _check_identity(who: ControllerIdentity, role: str) -> None:
    if not isinstance(who, ControllerIdentity) or who.role != role:
        raise ApprovalError(f"only a human {role} may perform this action")
    n = who.name.strip().lower()
    if not n or any(x in n for x in _FORBIDDEN_NAMES) or not who.licence_id.strip():
        raise ApprovalError("a named human with a licence/staff ID is required")


def pending(conn: sqlite3.Connection) -> list[dict]:
    return _changes(conn, "status = 'PENDING'")


def history(conn: sqlite3.Connection) -> list[dict]:
    return _changes(conn, "1 = 1")


def _changes(conn, where: str) -> list[dict]:
    out = []
    for r in db.rows(conn, f"SELECT * FROM schedule_changes WHERE {where} ORDER BY staged_at, change_id"):
        r["payload"] = json.loads(r["payload"])
        r["guard_report"] = json.loads(r["guard_report"])
        f = db.one(conn, "SELECT flight_no FROM flights WHERE flight_id = ?", (r["flight_id"],))
        r["flight_no"] = f["flight_no"] if f else r["flight_id"]
        out.append(r)
    return out


def approve(conn: sqlite3.Connection, change_id: str, who: ControllerIdentity, note: str = "",
            seen_hash: str | None = None, execute: bool = True) -> dict:
    """A named controller approves a PENDING change.

    seen_hash: the state hash shown on the controller's card (defaults to the hash recorded at staging).
    execute=False records an AUTHORISED decision bound to that hash; execute_approved() applies it later.
    """
    from .tools import guard_for_change

    _check_identity(who, "OPS_CONTROLLER")
    ch = db.one(conn, "SELECT * FROM schedule_changes WHERE change_id = ?", (change_id,))
    if not ch:
        raise ApprovalError(f"unknown change {change_id}")
    if ch["status"] != "PENDING":
        return {"status": ch["status"], "change_id": change_id, "message": f"change is {ch['status']}, not PENDING"}
    clock = db.now(conn)
    bound = seen_hash or ch["state_hash"]
    if ch["valid_until"] and clock > parse(ch["valid_until"]):
        conn.execute("UPDATE schedule_changes SET status = 'EXPIRED', decided_by = ?, decided_at = ? WHERE change_id = ?",
                     (who.name, fmt(clock), change_id))
        audit.log(conn, "CONTROLLER", "EXPIRED", {"change_id": change_id, "by": who.name})
        return {"status": "EXPIRED", "change_id": change_id,
                "message": f"Decision window closed at {hm(ch['valid_until'])}. The situation has moved on."}
    flight = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (ch["flight_id"],))
    details = json.loads(ch["payload"])
    g = guard_for_change(conn, ch["change_type"], flight, details)
    if not g["verdict"]["ok"]:
        audit.log(conn, "GUARD", "APPROVAL BLOCKED", {"change_id": change_id, "by": who.name,
                                                      "rules": g["verdict"]["rules_violated"]})
        return {"status": "BLOCKED_AT_APPROVAL", "change_id": change_id, "guard": g["verdict"],
                "message": "Re-validation failed. Immutable floors cannot be overridden, even by a controller."}
    if bound and _current_hash(conn, ch) != bound:
        return _stale(conn, ch, who.name, bound, "between the controller's view and the approval")
    if not execute:
        conn.execute("UPDATE schedule_changes SET status = 'AUTHORISED', decided_by = ?, decided_at = ?, "
                     "decision_note = ?, approved_hash = ? WHERE change_id = ?",
                     (f"{who.name} ({who.licence_id})", fmt(clock), note, bound, change_id))
        audit.log(conn, "CONTROLLER", f"AUTHORISED {ch['change_type']}",
                  {"change_id": change_id, "by": who.name, "bound_to_state": bound})
        return {"status": "AUTHORISED", "change_id": change_id, "change_type": ch["change_type"],
                "bound_to_state": bound, "message": "Approved for the state shown; executes on execute_approved()."}

    conn.execute("BEGIN IMMEDIATE")
    try:
        _apply(conn, ch["change_type"], flight, details, g["derived"])
        conn.execute("""UPDATE schedule_changes SET status = 'APPROVED', decided_by = ?, decided_at = ?,
                        decision_note = ?, applied_at = ?, approved_hash = ? WHERE change_id = ?""",
                     (f"{who.name} ({who.licence_id})", fmt(clock), note, fmt(clock), bound, change_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    audit.log(conn, "CONTROLLER", f"APPROVED {ch['change_type']}",
              {"change_id": change_id, "by": who.name, "licence": who.licence_id, "note": note})
    return {"status": "APPROVED", "change_id": change_id, "change_type": ch["change_type"],
            "flight": flight["flight_no"], "applied": g["derived"], "bound_to_state": bound}


def _current_hash(conn, ch: dict) -> str:
    from .tools import decision_state_hash
    return decision_state_hash(conn, ch["change_type"], ch["flight_id"], json.loads(ch["payload"]))


def execute_approved(conn: sqlite3.Connection, change_id: str) -> dict:
    """Apply an AUTHORISED change, but only to the state the controller approved.

    The state hash is recomputed first. If anything the decision depends on changed, nothing is applied:
    the approval is marked STALE and the change is re-staged (with fresh guards) for a new decision.
    """
    from .tools import guard_for_change

    ch = db.one(conn, "SELECT * FROM schedule_changes WHERE change_id = ?", (change_id,))
    if not ch or ch["status"] != "AUTHORISED":
        return {"status": ch["status"] if ch else "UNKNOWN", "change_id": change_id,
                "message": "only an AUTHORISED change can be executed"}
    now_hash = _current_hash(conn, ch)
    if now_hash != ch["approved_hash"]:
        return _stale(conn, ch, "EXECUTOR", ch["approved_hash"], "between the approval and its execution")
    flight = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (ch["flight_id"],))
    details = json.loads(ch["payload"])
    g = guard_for_change(conn, ch["change_type"], flight, details)  # defence in depth
    if not g["verdict"]["ok"]:
        return _stale(conn, ch, "EXECUTOR", ch["approved_hash"], "guards no longer pass", g["verdict"])
    clock = db.now(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        _apply(conn, ch["change_type"], flight, details, g["derived"])
        conn.execute("UPDATE schedule_changes SET status = 'APPROVED', applied_at = ? WHERE change_id = ?",
                     (fmt(clock), change_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    audit.log(conn, "EXECUTOR", f"EXECUTED {ch['change_type']}", {"change_id": change_id, "state": now_hash})
    return {"status": "APPROVED", "change_id": change_id, "change_type": ch["change_type"],
            "flight": flight["flight_no"], "applied": g["derived"], "bound_to_state": now_hash}


def _stale(conn, ch: dict, by: str, bound: str, when: str, verdict: dict | None = None) -> dict:
    """Refuse an approval whose state moved on, then re-stage the decision with fresh facts."""
    from .tools import decision_facts
    now_hash = _current_hash(conn, ch)
    details = json.loads(ch["payload"])
    conn.execute("UPDATE schedule_changes SET status = 'STALE', decided_at = ?, decision_note = ? WHERE change_id = ?",
                 (fmt(db.now(conn)), f"state {bound} -> {now_hash} {when}; nothing applied", ch["change_id"]))
    audit.log(conn, "GUARD", "APPROVAL STALE", {"change_id": ch["change_id"], "by": by, "approved_state": bound,
                                                "current_state": now_hash, "when": when})
    restaged = _restage(conn, ch, details)
    return {"status": "STALE", "change_id": ch["change_id"], "change_type": ch["change_type"],
            "approved_state": bound, "current_state": now_hash, "guard": verdict,
            "facts_now": decision_facts(conn, ch["change_type"], ch["flight_id"], details),
            "restaged": restaged,
            "message": f"The state changed {when}. Nothing was applied; the decision is back with the controller."}


def _restage(conn, ch: dict, details: dict) -> dict:
    """Stage the decision again against today's facts. For a stand: the same stand if still legal, else the best
    legal alternative, else escalate."""
    from . import tools
    flight = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (ch["flight_id"],))
    actor = "AGENT:re-stage"
    why = f"Re-staged after {ch['change_id']} went stale: the controller decides again on the current state."
    if ch["change_type"] == "GATE_REASSIGNMENT":
        same = tools.gate_option(conn, details["new_gate"])
        if same and same["legal"]:
            return tools._stage(conn, "GATE_REASSIGNMENT", flight, details, why, actor)
        go = tools.evaluate_gate_options(conn, exclude=[details["new_gate"].upper()])
        if go["recommended"]:
            return tools._stage(conn, "GATE_REASSIGNMENT", flight, {"new_gate": go["recommended"]},
                                why + f" {details['new_gate']} is no longer free; {go['recommended']} is the best "
                                      f"legal stand now.", actor)
        from .reconcile import escalate
        return {"status": "ESCALATED", **escalate(conn, "Arrival stand", f"{details['new_gate']} went stale and no "
                                                  "legal stand is free", ["Controller allocates a stand manually"])}
    return tools._stage(conn, ch["change_type"], flight, details, why, actor)


def reject(conn: sqlite3.Connection, change_id: str, who: ControllerIdentity, note: str) -> dict:
    _check_identity(who, "OPS_CONTROLLER")
    ch = db.one(conn, "SELECT * FROM schedule_changes WHERE change_id = ?", (change_id,))
    if not ch or ch["status"] != "PENDING":
        return {"status": ch["status"] if ch else "UNKNOWN", "change_id": change_id}
    conn.execute("UPDATE schedule_changes SET status = 'REJECTED', decided_by = ?, decided_at = ?, decision_note = ? "
                 "WHERE change_id = ?", (f"{who.name} ({who.licence_id})", fmt(db.now(conn)), note, change_id))
    audit.log(conn, "CONTROLLER", f"REJECTED {ch['change_type']}", {"change_id": change_id, "by": who.name,
                                                                    "note": note})
    return {"status": "REJECTED", "change_id": change_id}


def withdraw(conn: sqlite3.Connection, change_id: str, reason: str, actor: str = "AGENT") -> dict:
    """The proposer retracts its own pending proposal (e.g. it became illegal). Never touches approved changes."""
    ch = db.one(conn, "SELECT * FROM schedule_changes WHERE change_id = ?", (change_id,))
    if not ch or ch["status"] != "PENDING":
        return {"status": ch["status"] if ch else "UNKNOWN", "change_id": change_id}
    conn.execute("UPDATE schedule_changes SET status = 'WITHDRAWN', decided_by = ?, decided_at = ?, decision_note = ? "
                 "WHERE change_id = ?", (actor, fmt(db.now(conn)), reason[:300], change_id))
    audit.log(conn, actor, f"WITHDRAWN {ch['change_type']}", {"change_id": change_id, "reason": reason[:300]})
    return {"status": "WITHDRAWN", "change_id": change_id, "change_type": ch["change_type"]}


def expire(conn: sqlite3.Connection, change_id: str) -> dict:
    """A decision window closed without a decision."""
    ch = db.one(conn, "SELECT * FROM schedule_changes WHERE change_id = ?", (change_id,))
    if not ch or ch["status"] != "PENDING":
        return {"status": ch["status"] if ch else "UNKNOWN", "change_id": change_id}
    conn.execute("UPDATE schedule_changes SET status = 'EXPIRED', decided_at = ? WHERE change_id = ?",
                 (fmt(db.now(conn)), change_id))
    audit.log(conn, "SYSTEM", f"EXPIRED {ch['change_type']}", {"change_id": change_id})
    return {"status": "EXPIRED", "change_id": change_id, "change_type": ch["change_type"]}


def _apply(conn, change_type: str, flight: dict, details: dict, derived: dict) -> None:
    fid = flight["flight_id"]
    if change_type == "GATE_REASSIGNMENT":
        new_gate = details["new_gate"].upper()
        conn.execute("UPDATE flights SET gate_id = ?, eibt = ? WHERE flight_id = ?", (new_gate, derived["eibt"], fid))
        conn.execute("UPDATE flights SET gate_id = ? WHERE flight_id = ?", (new_gate, config.OUTBOUND_FLIGHT_ID))
        conn.execute("UPDATE gate_allocations SET status = 'RELEASED' WHERE flight_id = ? AND status = 'PLANNED'", (fid,))
        conn.execute('INSERT INTO gate_allocations(gate_id, flight_id, start, "end", status) VALUES(?,?,?,?,?)',
                     (new_gate, f"{fid} / {config.OUTBOUND_FLIGHT_ID}", derived["eibt"], derived["gate_until"],
                      "ALLOCATED"))
    elif change_type == "CREW_SWAP":
        if details.get("remove_crew_id"):
            conn.execute("UPDATE crew_assignments SET status = 'REMOVED' WHERE flight_id = ? AND crew_id = ?",
                         (fid, details["remove_crew_id"]))
        row = db.one(conn, "SELECT * FROM crew WHERE crew_id = ?", (details["add_crew_id"],))
        sb_kind = {"AIRPORT_STANDBY": "AIRPORT", "HOME_STANDBY": "HOME"}.get(row["duty_kind"])
        # FDP counts from reporting; remember the standby so its 4h/6h reduction and 16h cap still apply.
        # The duty counters are read-only (DB trigger); this approved change holds the write token briefly.
        conn.execute("INSERT OR REPLACE INTO meta VALUES('duty_write_token', 'HITL_APPROVED_CREW_CHANGE')")
        conn.execute("UPDATE crew SET duty_kind = 'ON_DUTY', duty_start = ?, location = ?, standby_kind = ?, "
                     "standby_start = ? WHERE crew_id = ?",
                     (derived["report_at"], f"Assigned {flight['flight_no']}", sb_kind,
                      row["duty_start"] if sb_kind else None, row["crew_id"]))
        conn.execute("DELETE FROM meta WHERE key = 'duty_write_token'")
        conn.execute("INSERT OR REPLACE INTO crew_assignments VALUES(?,?,?,?,?)",
                     (fid, row["crew_id"], details.get("role", row["rank"]), "ASSIGNED", derived["report_at"]))
    elif change_type == "RETIME":
        conn.execute("UPDATE flights SET etd = ?, eta = ?, status = 'DELAYED' WHERE flight_id = ?",
                     (derived["new_etd"], fmt(plus(parse(derived["new_etd"]), flight["block_min"])), fid))
    elif change_type == "HOLD_FLIGHT":
        conn.execute("UPDATE flights SET etd = ?, eta = ?, status = 'HELD' WHERE flight_id = ?",
                     (derived["new_etd"], fmt(plus(parse(derived["new_etd"]), flight["block_min"])), fid))
    elif change_type == "DEPARTURE_RELEASE":
        conn.execute("UPDATE flights SET status = 'RELEASED', etd = ?, eta = ? WHERE flight_id = ?",
                     (derived["off_blocks"], fmt(plus(parse(derived["off_blocks"]), flight["block_min"])), fid))
    else:  # pragma: no cover
        raise ApprovalError(f"cannot apply {change_type}")


# ---------------------------------------------------------------------------
# Licensed engineer sign-off (human action)
# ---------------------------------------------------------------------------
def sign_crs(conn: sqlite3.Connection, item_id: str, eng_id: str, remarks: str = "") -> dict:
    """A licensed engineer certifies the deferred defect now. Same validation as any recorded sign-off."""
    if not db.one(conn, "SELECT 1 FROM engineers WHERE eng_id = ?", (eng_id,)):
        raise ApprovalError("unknown engineer")
    return record_crs(conn, item_id, eng_id, signed_at=fmt(db.now(conn)), result="OK",
                      remarks=remarks or "Inspection and leak check satisfactory", source="engineer console")


def record_crs(conn: sqlite3.Connection, item_id: str, eng_id: str, *, signed_at: str, result: str = "OK",
               remarks: str = "", source: str = "maintenance system") -> dict:
    """Validate an inspection sign-off before it can release the aircraft.

    "OK" is not trusted on its own. In Python: the engineer ID must be on the licensed roster with the right
    licence and type authorisation (MX-004 / MX-002), the signature must come after the defect was raised and not
    in the future (MX-005), and not before the inspection could have been finished (MX-003). An invalid sign-off
    keeps the item OPEN (so any departure release stays blocked by MX-001) and alerts maintenance control.
    """
    from .turnaround import critical_path

    item = db.one(conn, "SELECT * FROM maintenance_items WHERE item_id = ?", (item_id,))
    if not item:
        raise ApprovalError("unknown maintenance item")
    if item["status"] == "CLOSED":
        return {"status": "ALREADY_CLOSED", "item_id": item_id}
    eng = db.one(conn, "SELECT * FROM engineers WHERE eng_id = ?", (eng_id,))
    clock = db.now(conn)
    signed = parse(signed_at)
    cpm = critical_path(conn, config.OUTBOUND_FLIGHT_ID)
    task = next((t for t in cpm["tasks"] if t["task_id"] == "MXI"), None)
    earliest = parse(task["end"]) if task else None
    aircraft = db.one(conn, "SELECT type FROM aircraft WHERE reg = ?", (item["aircraft_reg"],))["type"]
    v = guards.check_crs_signature(mx_facts(conn, item, earliest), licence=eng["licence"] if eng else "",
                                   type_auth=eng["type_auth"].split(",") if eng else (), aircraft_type=aircraft,
                                   signed_at=signed, on_roster=eng is not None, raised_at=parse(item["raised_at"]),
                                   now=clock, eng_id=eng_id)
    if result.upper() != "OK" or not v.ok:
        rules = [x.rule for x in v.violations] or ["MX-001"]
        audit.log(conn, "GUARD", "CRS REFUSED", {"item": item_id, "engineer": eng_id, "signed_at": hm(signed),
                                                 "source": source, "rules": rules})
        from .reconcile import escalate
        alert = escalate(conn, "Maintenance control",
                         f"{item_id} sign-off from {source} rejected ({', '.join(sorted(set(rules)))}): engineer "
                         f"{eng_id}, signed {hm(signed)}, defect raised {hm(item['raised_at'])}. The item stays OPEN "
                         f"and {config.OUTBOUND_FLIGHT_ID.split('-')[0]} stays blocked.",
                         ["Maintenance control verifies the record and the engineer",
                          "A rostered B1 engineer re-inspects and signs"])
        return {"status": "REFUSED", "item_id": item_id, "guard": v.as_dict(), "alert": alert,
                "message": "Sign-off rejected. The defect stays open; the departure stays blocked."}
    conn.execute("UPDATE maintenance_items SET status = 'CLOSED', crs_eng_id = ?, crs_signed_at = ?, crs_remarks = ? "
                 "WHERE item_id = ?", (eng_id, fmt(signed), remarks or "Inspection satisfactory", item_id))
    audit.log(conn, "ENGINEER", "CRS SIGNED", {"item": item_id, "engineer": eng["name"], "licence": eng["licence"],
                                               "signed_at": hm(signed), "source": source})
    return {"status": "SIGNED", "item_id": item_id, "engineer": eng["name"], "at": hm(signed)}


def advance_clock(conn: sqlite3.Connection, to_hhmm: str) -> dict:
    """Simulation control: move the scenario clock forward (never backward)."""
    new = parse(to_hhmm)
    cur = db.now(conn)
    if new is None or new <= cur:
        return {"status": "UNCHANGED", "clock": hm(cur)}
    db.set_meta(conn, "sim_clock", fmt(new))
    inb = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))
    if inb["eibt"] and new >= parse(inb["eibt"]) and inb["status"] == "APPROACH":
        conn.execute("UPDATE flights SET status = 'ON_BLOCKS' WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))
    audit.log(conn, "SIMULATION", "CLOCK", {"from": hm(cur), "to": hm(new)})
    return {"status": "ADVANCED", "clock": hm(new)}
