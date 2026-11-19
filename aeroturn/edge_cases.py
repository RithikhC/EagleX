"""Edge cases: what happens when the world keeps moving after the agent has planned.

Each case copies the scenario into its own throw-away sandbox, applies ONE realistic perturbation
(an ATC hold, a second fatigue report, a stand conflict, a leak found during the inspection...),
lets AeroTurn respond with the same guarded tools, re-validation (reconcile.py) and controller
workflow as the live console, and then checks the outcome with plain, readable assertions.

Cases run on the deterministic policy (no LLM) so every run gives the same answer. The guards,
transactions and approvals are identical whichever brain proposes the actions.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from . import audit, config, db, hitl, lab, reconcile, recovery, tools, turnaround
from .timeutil import fmt, hm, parse, plus

CONTROLLER = hitl.ControllerIdentity("Duty Ops Controller", "OCC-2611")


# ---------------------------------------------------------------------------
# Case runner
# ---------------------------------------------------------------------------
class Run:
    """Collects the timeline and the checks of one case."""

    def __init__(self, conn: sqlite3.Connection | None):
        self.conn = conn
        self.steps: list[dict] = []
        self.checks: list[dict] = []

    def _add(self, who: str, text: str) -> None:
        self.steps.append({"who": who, "text": text, "clock": hm(db.now(self.conn)) if self.conn else ""})

    def world(self, text: str) -> None:
        self._add("WORLD", text)

    def model(self, text: str) -> None:
        self._add("AEROTURN", text)

    def guard(self, text: str) -> None:
        self._add("GUARD", text)

    def human(self, text: str) -> None:
        self._add("HUMAN", text)

    def escalated(self, text: str) -> None:
        self._add("ESCALATION", text)

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"label": label, "passed": bool(ok), "detail": detail})
        return bool(ok)

    def reconcile(self) -> dict:
        r = reconcile.reconcile(self.conn)
        for e in r["events"]:
            (self.guard if "withdrawn" in e or "expired" in e else self.model)(f"Re-validation: {e}")
        for e in r["escalations"]:
            self.escalated(f"{e['topic']}: {e['reason']}")
        if not r["events"] and not r["escalations"]:
            self.model("Re-validation: every pending decision still legal, nothing to change")
        return r

    def agent(self) -> dict:
        from .agent import AeroTurnAgent
        a = AeroTurnAgent(self.conn, client=None)
        out = a.run()
        staged = [e.title for e in a.trace if e.kind == "hitl"]
        commits = [e.title for e in a.trace if e.kind in ("txn_commit", "txn_rollback")]
        self.model(f"Agent run: {len(staged)} change(s) staged for the controller"
                   + (f"; {'; '.join(commits)}" if commits else ""))
        for e in a.trace:
            if e.kind == "escalation":
                self.escalated(e.title.replace("ESCALATED to humans: ", ""))
        return out


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    category: str
    perturbation: str
    risk: str              # what a naive system would get wrong
    base: str              # "fresh" (pristine 14:50), "baseline" (after a normal agent run) or "none"
    fn: Callable[[Run], tuple[str, str]]


# ---------------------------------------------------------------------------
# Sandboxes
# ---------------------------------------------------------------------------
def _baseline_file():
    return lab.sandbox_path("edge_baseline")


def _ensure_baseline() -> None:
    """A copy of the scenario right after a normal agent run, built once and reused by every case."""
    from .agent import AeroTurnAgent
    target = _baseline_file()
    stamp = f"{config.PRISTINE_DB.stat().st_mtime_ns}" if config.PRISTINE_DB.exists() else "none"
    if target.exists():
        try:
            c = db.connect(target)
            ok = db.get_meta(c, "edge_baseline_of") == stamp
            c.close()
            if ok:
                return
        except sqlite3.Error:
            pass
    tag = f"sb_edgebuild_{uuid.uuid4().hex[:6]}"
    c = lab.fresh_sandbox(tag)
    AeroTurnAgent(c, client=None).run()
    db.set_meta(c, "edge_baseline_of", stamp)
    c.close()
    try:
        os.replace(lab.sandbox_path(tag), target)
    except OSError:  # another visitor built it at the same moment (Windows keeps open files locked)
        lab.sandbox_path(tag).unlink(missing_ok=True)


def _open(base: str) -> tuple[sqlite3.Connection | None, object]:
    if base == "none":
        return None, None
    path = lab.sandbox_path(f"sb_edge_{uuid.uuid4().hex[:8]}")
    if base == "fresh":
        db.reset_runtime(path)
    else:
        _ensure_baseline()
        src = sqlite3.connect(str(_baseline_file()))
        dst = sqlite3.connect(str(path))
        src.backup(dst)
        src.close()
        dst.close()
    return db.connect(path), path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pending(conn, change_type: str | None = None) -> list[dict]:
    return [c for c in hitl.pending(conn) if change_type in (None, c["change_type"])]


def _changes(conn, change_type: str) -> list[dict]:
    return [c for c in hitl.history(conn) if c["change_type"] == change_type]


def _fid(conn, flight_no: str) -> str:
    return db.one(conn, "SELECT flight_id FROM flights WHERE flight_no = ? ORDER BY std LIMIT 1", (flight_no,))["flight_id"]


def _leg2(conn, pax_id: str) -> dict:
    return db.one(conn, """SELECT f.flight_no, f.std, b.cabin, b.seat_no FROM bookings b
                           JOIN flights f ON f.flight_id = b.flight_id WHERE b.pax_id = ? AND b.leg_no = 2""", (pax_id,))


def _perturb(conn, what: str, detail: dict) -> None:
    audit.log(conn, "SIMULATION", "PERTURBATION", {"event": what, **detail})


def _atc_hold(conn, minutes_: int) -> None:
    inb = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))
    conn.execute("UPDATE flights SET eta = ?, eibt = ? WHERE flight_id = ?",
                 (fmt(plus(parse(inb["eta"]), minutes_)), fmt(plus(parse(inb["eibt"]), minutes_)),
                  config.INBOUND_FLIGHT_ID))
    _perturb(conn, f"ATC holding +{minutes_} min for EK812", {})


def _sell_out(conn, flight_nos: list[str], cabins: tuple[str, ...] | None = None, leave: int = 0) -> int:
    """The last seats are sold to other customers (inventory closed)."""
    n = 0
    for fno in flight_nos:
        fid = _fid(conn, fno)
        free = [s for s in recovery.free_seats(conn, [fid])[fid] if cabins is None or s["cabin"] in cabins]
        drop = free[: max(0, len(free) - leave)]
        conn.executemany("DELETE FROM seats WHERE flight_id = ? AND seat_no = ?", [(fid, s["seat_no"]) for s in drop])
        n += len(drop)
    _perturb(conn, "Inventory sold out", {"flights": flight_nos, "seats": n})
    return n


def _unfit(conn, crew_id: str, note: str) -> str:
    conn.execute("UPDATE crew SET fitness = 'UNFIT', notes = ? WHERE crew_id = ?", (note, crew_id))
    _perturb(conn, "Crew unfit", {"crew_id": crew_id, "note": note})
    return db.one(conn, "SELECT name FROM crew WHERE crew_id = ?", (crew_id,))["name"]


def _leak(conn, extra_min: int = 90) -> tuple[str, str]:
    old = turnaround.critical_path(conn, config.OUTBOUND_FLIGHT_ID)["eobt_hm"]
    conn.execute("UPDATE turnaround_tasks SET duration_min = duration_min + ? WHERE flight_id = ? AND task_id = 'MXI'",
                 (extra_min, config.OUTBOUND_FLIGHT_ID))
    conn.execute("UPDATE maintenance_items SET est_task_min = est_task_min + ?, description = description || ? "
                 "WHERE item_id = 'MX-0412'", (extra_min, f" UPDATE: ACMP case-drain leak found; pump replacement "
                                                         f"+{extra_min} min."))
    _perturb(conn, "MX finding", {"item": "MX-0412", "extra_min": extra_min})
    return old, turnaround.critical_path(conn, config.OUTBOUND_FLIGHT_ID)["eobt_hm"]


def _divert_into_c31(conn) -> None:
    conn.execute('INSERT INTO gate_allocations(gate_id, flight_id, start, "end", status) VALUES(?,?,?,?,?)',
                 ("C31", "EK2290 (medical diversion)", f"{config.SCENARIO_DATE}T15:05",
                  f"{config.SCENARIO_DATE}T17:40", "ALLOCATED"))
    _perturb(conn, "Stand conflict", {"gate": "C31", "by": "EK2290"})


# World events a presenter can inject into the LIVE session (then re-validation responds)
WORLD_EVENTS: dict[str, tuple[str, Callable]] = {
    "atc15": ("ATC holds EK812 +15 min", lambda c: _atc_hold(c, 15)),
    "atc25": ("ATC holds EK812 +25 min", lambda c: _atc_hold(c, 25)),
    "fatigue": ("Standby Capt. Mehta reports fatigue",
                lambda c: _unfit(c, "S-04", "Fatigue report filed on call-out. Removed from duty (non-negotiable).")),
    "leak": ("Inspection finds a leak: +90 min", lambda c: _leak(c, 90)),
    "divert": ("Medical diversion takes stand C31", _divert_into_c31),
}


def inject(conn: sqlite3.Connection, key: str) -> str:
    label, fn = WORLD_EVENTS[key]
    fn(conn)
    return label


def _bookings_hash(conn) -> str:
    rows = conn.execute("SELECT pax_id, leg_no, flight_id, seat_no, cabin FROM bookings ORDER BY pax_id, leg_no").fetchall()
    return hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest()[:12]


def _nobody_dropped(run: Run) -> bool:
    """Every broken connection is rebooked, protected by a proposed hold, or escalated by name."""
    risk = recovery.connection_risk(run.conn)
    esc = {e["topic"] for e in reconcile.escalations(run.conn)}
    open_ = [p for p in risk["passengers"] if p["at_risk"]]
    missing = [p["name"] for p in open_ if f"Passenger {p['name']}" not in esc]
    detail = (f"{len(open_)} with no legal seat today, all escalated by name; {risk['awaiting_hold_decision']} "
              f"protected by a proposed hold") if not missing else "not escalated: " + ", ".join(missing[:5])
    return run.check("Nobody silently dropped: every broken connection is rebooked, held or escalated by name",
                     not missing, detail)


def _baseline_note(run: Run) -> None:
    pend = _pending(run.conn)
    run.model("Starting point: the agent has already run. Staged for the controller: "
              + ", ".join(f"{c['change_type']} {c['payload'].get('new_gate') or c['payload'].get('add_crew_id') or c['payload'].get('new_etd') or c['flight_no']}"
                          for c in pend) + "; 45 passengers rebooked in one transaction.")


# ---------------------------------------------------------------------------
# The cases
# ---------------------------------------------------------------------------
def ec01_atc_hold_15(run: Run) -> tuple[str, str]:
    c = run.conn
    tools.dispatch(c, "stage_controller_schedule_change", {
        "change_type": "GATE_REASSIGNMENT", "flight_no": "EK812", "details": {"new_gate": "C31"},
        "justification": "C31: crew lands legally, fewest misconnects"})
    p = tools.dispatch(c, "plan_passenger_recovery", {"objective": "earliest_arrival"})
    run.model(f"Stages stand C31 (decide by 15:15) and builds plan {p['plan_id']} for {p['summary']['rebooked']} "
              f"passengers, assuming in-block 15:20.")
    _atc_hold(c, 15)
    run.world("ATC puts EK812 into a 15-minute hold. Landing 15:27, in-block 15:35.")
    x = tools.dispatch(c, "execute_atomic_passenger_rebook", {"plan_id": p["plan_id"]})
    run.guard(f"Executing the old plan: {x['status']} ({x.get('reason', '')}). {x.get('message', '')}")
    r = run.reconcile()
    gate = _pending(c, "GATE_REASSIGNMENT")
    c31 = next(o for o in tools.evaluate_gate_options(c)["options"] if o["gate"] == "C31")
    run.check("The plan built for 15:20 is refused as stale", x.get("reason") == "STALE_PLAN")
    run.check("C31 re-staged with the new decision window (15:30)",
              bool(gate) and gate[0]["payload"]["new_gate"] == "C31" and str(gate[0]["valid_until"]).endswith("15:30"))
    run.check("Inbound crew still legal at C31, with 5 min margin", c31["legal"] and c31["crew_fdp_margin_min"] == 5,
              f"margin {c31['crew_fdp_margin_min']} min")
    n = (r["rebook"] or {}).get("rebooked", 0)
    run.check("A fresh plan for 15:35 is committed in one transaction", (r["rebook"] or {}).get("status") == "COMMITTED",
              f"{n} passengers")
    _nobody_dropped(run)
    left = len((r["rebook"] or {}).get("unresolved", []))
    return (f"Stale plan refused; C31 re-staged for 15:35 (crew margin 5 min); {n} passengers rebooked"
            + (f", {left} with no legal seat today escalated." if left else ".")), "resolved"


def ec02_atc_hold_25(run: Run) -> tuple[str, str]:
    c = run.conn
    _baseline_note(run)
    _atc_hold(c, 25)
    run.world("ATC holds EK812 for 25 minutes. Landing 15:37: the inbound crew's duty ends 15:40.")
    r = run.reconcile()
    go = tools.evaluate_gate_options(c)
    gate = _changes(c, "GATE_REASSIGNMENT")[0]
    run.check("C31 withdrawn: the inbound crew would exceed its FDP (FTL-001)",
              gate["status"] == "WITHDRAWN" and "FTL-001" in (gate["decision_note"] or ""))
    run.check("Every stand fails FTL-001", go["recommended"] is None and all(not o["legal"] for o in go["options"]),
              ", ".join(f"{o['gate']} {o['crew_fdp_margin_min']:+} min" for o in go["options"]))
    run.check("Nothing staged that depends on commander's discretion", not _pending(c, "GATE_REASSIGNMENT"))
    run.check("Escalated to humans, with the options", any(e["topic"] == "Inbound crew duty" for e in r["escalations"]))
    _nobody_dropped(run)
    return "No legal stand exists. Nothing illegal staged; crew control and the controller get the decision.", "escalated"


def ec03_standby_fatigue(run: Run) -> tuple[str, str]:
    c = run.conn
    _baseline_note(run)
    name = _unfit(c, "S-04", "Fatigue report filed 14:52 on call-out. Removed from duty (non-negotiable).")
    run.world(f"{name}, the standby captain the agent picked, files a fatigue report on call-out.")
    sw = _pending(c, "CREW_SWAP")[0]
    a = hitl.approve(c, sw["change_id"], CONTROLLER, "Approve Mehta")
    run.human(f"Controller presses Approve on {sw['change_id']} (Capt. Mehta).")
    rules = (a.get("guard") or {}).get("rules_violated", [])
    run.guard(f"Approval re-runs the guards with fresh facts: {a['status']} ({', '.join(rules)}).")
    run.reconcile()
    new = _pending(c, "CREW_SWAP")
    a2 = hitl.approve(c, new[0]["change_id"], CONTROLLER, "Approve Farouk") if new else {"status": "NONE"}
    if new:
        run.human(f"Controller approves {new[0]['change_id']}: {a2['status']}.")
    cpt = db.one(c, """SELECT c.crew_id, c.name FROM crew_assignments a JOIN crew c ON c.crew_id = a.crew_id
                       WHERE a.flight_id = ? AND a.status = 'ASSIGNED' AND c.rank = 'CPT' AND c.fitness = 'FIT'""",
                 (config.OUTBOUND_FLIGHT_ID,))
    run.check("The controller's approval is blocked: fatigue is absolute (FTL-004)",
              a["status"] == "BLOCKED_AT_APPROVAL" and "FTL-004" in rules)
    run.check("The Mehta swap is withdrawn, not left in the queue",
              db.one(c, "SELECT status FROM schedule_changes WHERE change_id = ?", (sw["change_id"],))["status"] == "WITHDRAWN")
    run.check("Next legal captain staged: Capt. Omar Farouk (S-02)", bool(new) and new[0]["payload"]["add_crew_id"] == "S-02")
    run.check("EK813 now has a fit, legal captain", a2["status"] == "APPROVED" and cpt and cpt["crew_id"] == "S-02",
              cpt["name"] if cpt else "none")
    return "Approval blocked by FTL-004; the agent withdrew the swap and Capt. Farouk is approved instead.", "resolved"


def ec04_no_captain(run: Run) -> tuple[str, str]:
    c = run.conn
    _baseline_note(run)
    _unfit(c, "S-04", "Fatigue report filed 14:52 on call-out.")
    _unfit(c, "S-02", "Sick call 14:55.")
    run.world("Both legal standby captains drop out: Capt. Mehta (fatigue) and Capt. Farouk (sick).")
    r = run.reconcile()
    cpm = turnaround.critical_path(c, config.OUTBOUND_FLIGHT_ID)
    d = tools.dispatch(c, "propose_departure", {"flight_no": "EK813", "off_blocks": cpm["eobt_hm"],
                                                "justification": "Release request"})
    rules = (d.get("guard") or {}).get("rules_violated", [])
    run.guard(f"Departure release at {cpm['eobt_hm']}: {d['status']} ({', '.join(rules)}).")
    sc = tools.find_standby_crew(c, "EK813", "CPT")
    run.check("Mehta swap withdrawn (FTL-004)", any(ch["status"] == "WITHDRAWN" and "FTL-004" in (ch["decision_note"] or "")
                                                    for ch in _changes(c, "CREW_SWAP")))
    run.check("No illegal captain is proposed instead", not _pending(c, "CREW_SWAP") and sc["selected"] is None,
              "; ".join(f"{x['name']}: {x['violations'][0]['rule']}" for x in sc["candidates"][:4]))
    run.check("EK813 stays grounded: release blocked by FTL-005", d["status"] == "BLOCKED" and "FTL-005" in rules)
    run.check("Escalated to crew control with every candidate's blocking rule",
              any(e["topic"] == "EK813 captain" for e in r["escalations"]))
    return "No legal captain exists. EK813 stays on the ground and crew control gets the decision.", "escalated"


def ec05_vulnerable_sold_out(run: Run) -> tuple[str, str]:
    c = run.conn
    n = _sell_out(c, ["EK372", "EK376", "EK504", "EK508"])
    run.world(f"Revenue management sells the last {n} seats on EK372 and EK376 (Bangkok before 22:00) and on "
              f"EK504 and EK508 (Mumbai, home carrier).")
    run.agent()
    lina, rajan = _leg2(c, "PX0001"), _leg2(c, "PX0007")
    esc = {e["topic"]: e for e in reconcile.escalations(c)}
    risk = recovery.connection_risk(c)
    run.check("Lina Haddad (UMNR, 10) is not put on a partner, overnight or post-22:00 flight",
              lina["flight_no"] == "EK384", f"still on {lina['flight_no']}")
    run.check("Rajan Iyer (MEDA) is not moved to a partner without MEDIF clearance",
              rajan["flight_no"] == "EK500", f"still on {rajan['flight_no']}")
    run.check("Both escalated with their care protocol",
              "UMNR care" in " ".join(esc.get("Passenger Lina Haddad", {}).get("options", []))
              and "MEDIF" in " ".join(esc.get("Passenger Rajan Iyer", {}).get("options", [])))
    run.check("Everyone else still rebooked (only those two left open)", risk["at_risk"] == 2,
              f"{risk['at_risk']} open")
    return "Lina and Mr Iyer are handed to humans with their care protocol; the other 43 are rebooked.", "escalated"


def ec06_family_last_seats(run: Run) -> tuple[str, str]:
    c = run.conn
    _sell_out(c, ["EK372"], cabins=("Y",), leave=1)
    run.world("Only 1 economy seat (and 1 business seat) is left on EK372, the 18:25 to Bangkok. Lina (UMNR), "
              "Mr Prasert (wheelchair, WCHC) and the Georgiou family with a baby all want it.")
    run.agent()
    lina, som = _leg2(c, "PX0001"), _leg2(c, "PX0002")
    fam = db.rows(c, """SELECT f.flight_no FROM passengers p JOIN bookings b ON b.pax_id = p.pax_id AND b.leg_no = 2
                        JOIN flights f ON f.flight_id = b.flight_id WHERE p.pnr = 'GEO3FM'""")
    flights = {r["flight_no"] for r in fam}
    run.check("Lina (UMNR) gets the last economy seat on EK372", lina["flight_no"] == "EK372" and lina["cabin"] == "Y",
              f"{lina['flight_no']} {lina['cabin']} {lina['seat_no']}")
    run.check("Mr Prasert (WCHC) gets a protection upgrade to business on the same flight",
              som["flight_no"] == "EK372" and som["cabin"] == "J", f"{som['flight_no']} {som['cabin']}")
    run.check("The Georgiou family stays together (no PNR split, PAX-006)", len(fam) == 3 and len(flights) == 1,
              ", ".join(sorted(flights)))
    run.check("The family moves to the next flight with room for all three", flights == {"EK376"})
    return "Priority order decides the last seats; the family travels together on EK376 at 21:50.", "resolved"


def ec07_gate_rejected(run: Run) -> tuple[str, str]:
    c = run.conn
    _baseline_note(run)
    g = _pending(c, "GATE_REASSIGNMENT")[0]
    hitl.reject(c, g["change_id"], CONTROLLER, "C31 needed for a VIP movement")
    run.human(f"Controller rejects stand C31 ({g['change_id']}): needed for a VIP movement.")
    run.reconcile()
    new = _pending(c, "GATE_REASSIGNMENT")
    a = hitl.approve(c, new[0]["change_id"], CONTROLLER, "R205 approved") if new else {"status": "NONE"}
    run.human(f"Controller approves {new[0]['payload']['new_gate'] if new else '-'}: {a['status']}. EK812 now arrives "
              f"at a remote stand, so every connection needs 25 more minutes (bussing).")
    r2 = run.reconcile()
    proposed = [ch["payload"]["new_gate"] for ch in _changes(c, "GATE_REASSIGNMENT")]
    run.check("C31 is never proposed again", proposed.count("C31") == 1)
    run.check("Next legal stand staged: R205, citing the rejection",
              bool(new) and new[0]["payload"]["new_gate"] == "R205" and "rejected C31" in new[0]["justification"])
    run.check("Approval of R205 passes the guards", a["status"] == "APPROVED")
    hold = next((h for h in _pending(c, "HOLD_FLIGHT") if h["flight_no"] == "EK346"), None)
    run.check("EK346, the last flight to Kuala Lumpur today, is offered a short hold instead of stranding its connections",
              hold is not None and hold["payload"]["hold_min"] <= 5,
              f"+{hold['payload']['hold_min']} min" if hold else "no hold")
    n = (r2["rebook"] or {}).get("rebooked", 0)
    run.check("The other connections broken by the remote-stand MCT are re-planned atomically",
              n > 0 and (r2["rebook"] or {}).get("status") == "COMMITTED", f"{n} more passengers")
    _nobody_dropped(run)
    held = recovery.connection_risk(c)["awaiting_hold_decision"]
    return (f"R205 approved after the rejection; EK346 +{hold['payload']['hold_min'] if hold else '?'} min protects "
            f"{held} passengers and {n} more are rebooked."), "resolved"


def ec08_deadline_missed(run: Run) -> tuple[str, str]:
    c = run.conn
    _baseline_note(run)
    g = _pending(c, "GATE_REASSIGNMENT")[0]
    hitl.advance_clock(c, "15:16")
    run.world("Nobody decides on C31. The clock passes 15:15, the end of its decision window.")
    run.reconcile()
    r205 = _pending(c, "GATE_REASSIGNMENT")
    hitl.advance_clock(c, "15:19")
    run.world("Still no decision. The clock passes 15:18, R205's window.")
    r2 = run.reconcile()
    late = hitl.approve(c, r205[0]["change_id"], CONTROLLER, "late") if r205 else {"status": "NONE"}
    run.human(f"Controller finally presses Approve on R205: {late['status']}.")
    run.check("C31 expired at 15:15",
              db.one(c, "SELECT status FROM schedule_changes WHERE change_id = ?", (g["change_id"],))["status"] == "EXPIRED")
    run.check("R205 staged while its window was still open (until 15:18)",
              bool(r205) and r205[0]["payload"]["new_gate"] == "R205" and str(r205[0]["valid_until"]).endswith("15:18"))
    run.check("A late approval cannot apply an expired decision", late["status"] == "EXPIRED")
    run.check("Escalated once every window had closed", any(e["topic"] == "Arrival stand" for e in r2["escalations"]))
    return "C31 expired, R205 was offered with 2 minutes left, then escalated. No stale decision was ever applied.", "escalated"


def ec09_leak_found(run: Run) -> tuple[str, str]:
    c = run.conn
    _baseline_note(run)
    old, new = _leak(c, 90)
    run.world(f"The engineer finds a leaking hydraulic pump: replacement adds 90 minutes. Critical-path EOBT moves "
              f"{old} → {new}.")
    run.reconcile()
    retimes, gates = _changes(c, "RETIME"), _changes(c, "GATE_REASSIGNMENT")
    pend_rt, pend_g = _pending(c, "RETIME"), _pending(c, "GATE_REASSIGNMENT")
    run.check(f"The {old} retime is withdrawn (TURN-001: earlier than the critical path)",
              any(r["status"] == "WITHDRAWN" and "TURN-001" in (r["decision_note"] or "") for r in retimes))
    run.check(f"A new retime to {new} is staged", bool(pend_rt) and pend_rt[0]["payload"]["new_etd"] == new)
    run.check("C31 withdrawn: the longer turn now clashes with EK2350 at 18:45 (GATE-001)",
              any(g["status"] == "WITHDRAWN" and "GATE-001" in (g["decision_note"] or "") for g in gates))
    run.check("R205 staged instead", bool(pend_g) and pend_g[0]["payload"]["new_gate"] == "R205")
    run.check("Capt. Mehta's swap re-checked at the later departure and still legal",
              any(ch["payload"]["add_crew_id"] == "S-04" for ch in _pending(c, "CREW_SWAP")))
    return f"One maintenance finding cascades: retime {old} → {new} and stand C31 → R205, re-checked automatically.", "resolved"


def ec10_duplicate_run(run: Run) -> tuple[str, str]:
    c = run.conn
    _baseline_note(run)
    before = {"pending": sorted(ch["change_id"] for ch in _pending(c)), "bookings": _bookings_hash(c),
              "notifications": db.one(c, "SELECT COUNT(*) AS n FROM notifications")["n"]}
    run.world("A network blip makes the orchestrator start the agent a second time on the same situation.")
    run.agent()
    after = {"pending": sorted(ch["change_id"] for ch in _pending(c)), "bookings": _bookings_hash(c),
             "notifications": db.one(c, "SELECT COUNT(*) AS n FROM notifications")["n"]}
    run.check("No duplicate proposals in the controller queue", before["pending"] == after["pending"],
              f"{len(after['pending'])} pending")
    run.check("No passenger rebooked twice (bookings unchanged)", before["bookings"] == after["bookings"])
    run.check("Each passenger notified once", before["notifications"] == after["notifications"],
              f"{after['notifications']} notifications")
    return "The second run is idempotent: same queue, same bookings, same notifications.", "resolved"


def ec11_bag_system(run: Run) -> tuple[str, str]:
    tag = f"sb_edge_{uuid.uuid4().hex[:8]}"
    try:
        r = lab.rollback_experiment("BAG_SYSTEM_FAULT", at_step=12, tag=tag)
    finally:
        lab.sandbox_path(tag).unlink(missing_ok=True)
    f, rt = r["first"], r["retry"]
    run.world("The baggage reconciliation system times out while the 45-passenger rebooking is being written.")
    run.guard(f"Transaction fails at step {f.get('failed_at_step')}: {str(f.get('error', ''))[:90]}. ROLLBACK.")
    run.model(f"Re-plan on fresh inventory and retry: {rt['status']} ({rt.get('summary', {}).get('rebooked', 0)} "
              f"passengers, {rt.get('summary', {}).get('bags_rerouted', 0)} bags).")
    run.check("The failing transaction rolls back", f["status"] == "ROLLED_BACK")
    run.check("State identical to before (fingerprint)", r["before"]["fingerprint"] == r["after"]["fingerprint"])
    run.check("No half-moved passenger or orphaned bag", r["before"]["leg2"] == r["after"]["leg2"]
              and r["after"]["invariants"].get("orphaned_bags", 0) == 0)
    run.check("Retry commits everyone", rt["status"] == "COMMITTED" and r["final"]["at_risk_remaining"] == 0)
    run.check("Database invariants clear after the retry", all(v == 0 for v in r["final"]["invariants"].values()))
    return "All-or-nothing: the failed write left no trace and the retry committed all 45 passengers and their bags.", "resolved"


def ec12_stand_conflict(run: Run) -> tuple[str, str]:
    c = run.conn
    _baseline_note(run)
    _divert_into_c31(c)
    run.world("A medical diversion, EK2290, is given stand C31 from 15:05 to 17:40.")
    run.reconcile()
    gates, pend = _changes(c, "GATE_REASSIGNMENT"), _pending(c, "GATE_REASSIGNMENT")
    r205 = next(o for o in tools.evaluate_gate_options(c)["options"] if o["gate"] == "R205")
    run.check("C31 withdrawn: stand no longer free (GATE-001)",
              any(g["status"] == "WITHDRAWN" and "GATE-001" in (g["decision_note"] or "") for g in gates))
    run.check("R205 staged instead", bool(pend) and pend[0]["payload"]["new_gate"] == "R205")
    run.check("Inbound crew legal at R205", r205["legal"], f"margin {r205['crew_fdp_margin_min']} min")
    return "C31 is gone; the agent withdrew it and staged R205 before the controller could approve a clash.", "resolved"


def ec13_hold_rejected(run: Run) -> tuple[str, str]:
    c = run.conn
    _baseline_note(run)
    h = _pending(c, "HOLD_FLIGHT")[0]
    waiting = recovery.connection_risk(c)["awaiting_hold_decision"]
    hitl.reject(c, h["change_id"], CONTROLLER, "Slot restriction at SYD: no hold")
    run.human(f"Controller rejects the {h['flight_no']} hold: Sydney slot restriction. {waiting} passengers were "
              f"waiting on that decision.")
    r = run.reconcile()
    n = (r["rebook"] or {}).get("rebooked", 0)
    ek418 = db.one(c, "SELECT std, etd, status FROM flights WHERE flight_id = ?", (h["flight_id"],))
    run.check(f"The {waiting} passengers waiting on the hold are rebooked at once", n == waiting and waiting > 0,
              f"{n} rebooked")
    run.check("No connection left at risk", recovery.connection_risk(c)["at_risk"] == 0)
    run.check(f"{h['flight_no']} leaves on time: nobody on board is delayed",
              ek418["status"] != "HELD" and (ek418["etd"] in (None, ek418["std"])))
    return f"Hold rejected; the {waiting} Sydney passengers move to the next flight in one transaction.", "resolved"


CASES: list[Case] = [
    Case("EC-01", "ATC holding: +15 minutes", "Timing",
         "EK812 is held 15 min after the agent planned: in-block 15:20 → 15:35.",
         "Executing a plan built for 15:20, or letting C31 expire at the old 15:15 deadline.", "fresh", ec01_atc_hold_15),
    Case("EC-02", "ATC holding: +25 minutes", "Crew duty",
         "EK812 is held 25 min: landing 15:37, two minutes before the inbound crew's duty ends.",
         "Planning on commander's discretion, or leaving an illegal stand in the queue.", "baseline", ec02_atc_hold_25),
    Case("EC-03", "The replacement captain is fatigued too", "Crew duty",
         "Capt. Mehta files a fatigue report on call-out, after the swap was staged.",
         "A controller approving a swap that has just become illegal.", "baseline", ec03_standby_fatigue),
    Case("EC-04", "No legal captain anywhere", "Crew duty",
         "Both legal standby captains drop out (fatigue, sickness).",
         "Picking the 'least illegal' captain to keep the flight moving.", "baseline", ec04_no_captain),
    Case("EC-05", "Seats sell out for vulnerable passengers", "Passengers",
         "Every home-carrier seat Lina (UMNR) and Mr Iyer (MEDA) could use today is sold.",
         "Putting a child alone on a partner or a 03:05 flight, or a medical case on an uncleared carrier.",
         "fresh", ec05_vulnerable_sold_out),
    Case("EC-06", "A family of three and one seat left", "Passengers",
         "One economy and one business seat left on the 18:25 to Bangkok.",
         "Splitting the family, or giving the seat to a frequent flyer before a child alone.", "fresh",
         ec06_family_last_seats),
    Case("EC-07", "The controller rejects stand C31", "Controller",
         "C31 is refused; the next legal stand is remote, which adds 25 min to every connection.",
         "Proposing C31 again, or forgetting that a remote stand breaks more connections.", "baseline",
         ec07_gate_rejected),
    Case("EC-08", "Nobody decides in time", "Controller",
         "The controller misses C31's 15:15 window, then R205's 15:18 window.",
         "Applying a decision after its window closed.", "baseline", ec08_deadline_missed),
    Case("EC-09", "The inspection finds a leak", "Maintenance",
         "The hydraulic pump must be replaced: +90 min on the critical path.",
         "Keeping a retime that is now too early, and a stand that is now double-booked.", "baseline", ec09_leak_found),
    Case("EC-10", "The agent runs twice", "Robustness",
         "The orchestrator restarts the agent on the same situation.",
         "Duplicate proposals, double bookings, passengers notified twice.", "baseline", ec10_duplicate_run),
    Case("EC-11", "The baggage system fails mid-commit", "Atomicity",
         "Bag reconciliation times out halfway through writing the rebooking.",
         "Half the passengers moved, bags left on the wrong flight.", "none", ec11_bag_system),
    Case("EC-12", "A diversion takes the stand", "Stands",
         "A medical diversion is given C31 from 15:05 to 17:40.",
         "The controller approving a stand that is now occupied.", "baseline", ec12_stand_conflict),
    Case("EC-13", "The controller rejects the hold", "Controller",
         "The EK418 Sydney hold is refused (slot restriction).",
         "Passengers left waiting on a hold that will never happen.", "baseline", ec13_hold_rejected),
]
BY_ID = {c.id: c for c in CASES}


def run_case(case_id: str) -> dict:
    case = BY_ID[case_id]
    t0 = time.perf_counter()
    conn, path = _open(case.base)
    run = Run(conn)
    try:
        outcome, level = case.fn(run)
        if conn is not None:
            inv = db.check_invariants(conn)
            run.check("Database invariants clear (no double booking, no orphaned bag)", inv["all_clear"])
    except Exception as exc:  # noqa: BLE001 - a crash is reported as a failed case, never hidden
        run.check(f"Case ran to completion ({type(exc).__name__}: {exc})", False)
        outcome, level = f"Crashed: {exc}", "failed"
    finally:
        if conn is not None:
            conn.close()
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    passed = all(ch["passed"] for ch in run.checks)
    return {"id": case.id, "title": case.title, "category": case.category, "perturbation": case.perturbation,
            "risk": case.risk, "steps": run.steps, "checks": run.checks, "outcome": outcome,
            "level": level if passed else "failed", "passed": passed,
            "ms": int((time.perf_counter() - t0) * 1000)}


def run_all() -> list[dict]:
    return [run_case(c.id) for c in CASES]
