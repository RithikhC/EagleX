"""Human-in-the-loop gate: Operations Controller approvals and engineer sign-off.

This module is NOT part of the agent tool registry. Only the OCC console
(a human clicking Approve or Reject) and the tests call it.

Approval is not a rubber stamp. The guards run again with fresh facts at
approval time, so a change that became illegal while it sat in the queue
cannot be approved, and the controller cannot override a guard either.
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


def approve(conn: sqlite3.Connection, change_id: str, who: ControllerIdentity, note: str = "") -> dict:
    from .tools import guard_for_change

    _check_identity(who, "OPS_CONTROLLER")
    ch = db.one(conn, "SELECT * FROM schedule_changes WHERE change_id = ?", (change_id,))
    if not ch:
        raise ApprovalError(f"unknown change {change_id}")
    if ch["status"] != "PENDING":
        return {"status": ch["status"], "change_id": change_id, "message": f"change is {ch['status']}, not PENDING"}
    clock = db.now(conn)
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

    conn.execute("BEGIN IMMEDIATE")
    try:
        _apply(conn, ch["change_type"], flight, details, g["derived"])
        conn.execute("""UPDATE schedule_changes SET status = 'APPROVED', decided_by = ?, decided_at = ?,
                        decision_note = ?, applied_at = ? WHERE change_id = ?""",
                     (f"{who.name} ({who.licence_id})", fmt(clock), note, fmt(clock), change_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    audit.log(conn, "CONTROLLER", f"APPROVED {ch['change_type']}",
              {"change_id": change_id, "by": who.name, "licence": who.licence_id, "note": note})
    return {"status": "APPROVED", "change_id": change_id, "change_type": ch["change_type"],
            "flight": flight["flight_no"], "applied": g["derived"]}


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
        duty_start = row["duty_start"] if row["duty_kind"] == "AIRPORT_STANDBY" else derived["report_at"]
        conn.execute("UPDATE crew SET duty_kind = 'ON_DUTY', duty_start = ?, location = ? WHERE crew_id = ?",
                     (duty_start, f"Assigned {flight['flight_no']}", row["crew_id"]))
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
    """A licensed engineer certifies the deferred defect. The guard checks licence, type and timing."""
    from .turnaround import critical_path

    item = db.one(conn, "SELECT * FROM maintenance_items WHERE item_id = ?", (item_id,))
    eng = db.one(conn, "SELECT * FROM engineers WHERE eng_id = ?", (eng_id,))
    if not item or not eng:
        raise ApprovalError("unknown item or engineer")
    if item["status"] == "CLOSED":
        return {"status": "ALREADY_CLOSED", "item_id": item_id}
    clock = db.now(conn)
    cpm = critical_path(conn, config.OUTBOUND_FLIGHT_ID)
    task = next((t for t in cpm["tasks"] if t["task_id"] == "MXI"), None)
    earliest = parse(task["end"]) if task else None
    aircraft = db.one(conn, "SELECT type FROM aircraft WHERE reg = ?", (item["aircraft_reg"],))["type"]
    v = guards.check_crs_signature(mx_facts(conn, item, earliest), licence=eng["licence"],
                                   type_auth=eng["type_auth"].split(","), aircraft_type=aircraft, signed_at=clock)
    if not v.ok:
        audit.log(conn, "GUARD", "CRS REFUSED", {"item": item_id, "engineer": eng_id,
                                                 "rules": [x.rule for x in v.violations]})
        return {"status": "REFUSED", "item_id": item_id, "guard": v.as_dict()}
    conn.execute("UPDATE maintenance_items SET status = 'CLOSED', crs_eng_id = ?, crs_signed_at = ?, crs_remarks = ? "
                 "WHERE item_id = ?", (eng_id, fmt(clock), remarks or "Inspection and leak check satisfactory", item_id))
    audit.log(conn, "ENGINEER", "CRS SIGNED", {"item": item_id, "engineer": eng["name"], "licence": eng["licence"]})
    return {"status": "SIGNED", "item_id": item_id, "engineer": eng["name"], "at": hm(clock)}


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
