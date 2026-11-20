"""The trigger of the main user journey: an incoming delay alert for the inbound aircraft.

An operations controller receives a delay message (the kind a flight-watch system or an ACARS/MVT feed sends).
AeroTurn reads it, checks it in code, applies the new arrival time to the scenario, and only then runs the agent.

Checks (all in code, never in the LLM):
  * size and characters: free text from outside, at most 600 characters;
  * prompt-injection scan (sanitize.scan): instruction-like text is rejected before anything else runs;
  * the flight must be an inbound arrival in today's schedule (this pilot handles late inbound aircraft);
  * the new ETA must be a real time, after the scheduled arrival, not in the past, and at most 6 hours late.
Every accepted or rejected alert is written to the audit log.
"""

from __future__ import annotations

import re
import sqlite3

from . import audit, config, db, sanitize
from .timeutil import fmt, hm, minutes, parse, plus

SAMPLE_ALERT = ("DELAY ALERT · EK812 LCA-DXB · A6-EQX · STA 14:05 · new ETA 15:12 · "
                "reason: ATC flow control and HYD SYS C LO PRESS caution after departure (MX-0412 raised)")
MAX_LEN = 600
MAX_DELAY_MIN = 6 * 60

_FLIGHT = re.compile(r"\b([A-Z]{2}\s?\d{2,4})\b")
_ETA = re.compile(r"\bETA\s*[:=]?\s*(\d{1,2})[:.h]?(\d{2})\b", re.I)


def parse_alert(text: str) -> dict:
    """Pure parsing: returns the fields found and the reasons the alert cannot be used (empty = usable)."""
    reasons: list[str] = []
    text = text or ""
    if not text.strip():
        return {"ok": False, "reasons": ["empty alert"]}
    if len(text) > MAX_LEN:
        reasons.append(f"alert longer than {MAX_LEN} characters")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in text):
        reasons.append("control characters in the alert")
    inj = sanitize.scan(text)
    if inj:
        return {"ok": False, "blocked": True, "reasons": [f"instruction-like text ({', '.join(inj)})"]}
    flights = [f.replace(" ", "") for f in _FLIGHT.findall(text.upper())]
    flight = flights[0] if flights else None
    m = _ETA.search(text)
    eta = f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
    if not flight:
        reasons.append("no flight number found")
    if not eta:
        reasons.append("no new ETA found (expected e.g. 'ETA 15:12')")
    elif not (0 <= int(eta[:2]) <= 23 and 0 <= int(eta[3:]) <= 59):
        reasons.append(f"ETA {eta} is not a valid time")
    return {"ok": not reasons, "flight": flight, "eta": eta, "reasons": reasons}


def accept_alert(conn: sqlite3.Connection, text: str, actor: str = "OCC_UI") -> dict:
    """Validate an alert against the schedule and apply its ETA. Returns the verdict; never raises."""
    p = parse_alert(text)
    inb = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))
    clock = db.now(conn)
    if p["ok"]:
        if p["flight"] != inb["flight_no"]:
            known = db.one(conn, "SELECT flight_no FROM flights WHERE flight_no = ?", (p["flight"],))
            p["reasons"].append(f"{p['flight']} is not a late inbound arrival at this hub today" if known
                                else f"unknown flight {p['flight']}")
        else:
            sta, old_eta = parse(inb["sta"]), parse(inb["eta"])
            new_eta = parse(p["eta"])
            if new_eta < sta:
                p["reasons"].append(f"ETA {p['eta']} is before the scheduled arrival {hm(sta)}: not a delay")
            elif minutes(sta, new_eta) > MAX_DELAY_MIN:
                p["reasons"].append(f"a delay of more than {MAX_DELAY_MIN // 60} h needs a cancellation plan, "
                                    f"not this workflow")
            elif new_eta < clock:
                p["reasons"].append(f"ETA {p['eta']} is already in the past (clock {hm(clock)})")
        p["ok"] = not p["reasons"]
    if not p["ok"]:
        status = "BLOCKED" if p.get("blocked") else "REJECTED"
        audit.log(conn, "GUARD", f"ALERT {status}", {"input": (text or "")[:120], "reasons": p["reasons"],
                                                    "tool": "none", "decision": status})
        return {"status": status, **p}
    shift = minutes(parse(inb["eta"]), parse(p["eta"]))
    if shift:
        conn.execute("UPDATE flights SET eta = ?, eibt = ? WHERE flight_id = ?",
                     (fmt(plus(parse(inb["eta"]), shift)), fmt(plus(parse(inb["eibt"]), shift)),
                      config.INBOUND_FLIGHT_ID))
    inb = db.one(conn, "SELECT * FROM flights WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))
    out = {"status": "ACCEPTED", **p, "eibt": hm(inb["eibt"]), "delay_min": minutes(parse(inb["sta"]), parse(inb["eibt"])),
           "shift_min": shift}
    audit.log(conn, actor, "ALERT ACCEPTED", {"input": text[:120], "flight": p["flight"], "eta": p["eta"],
                                             "on_blocks": out["eibt"], "shift_min": shift, "decision": "RUN AGENT"})
    return out
