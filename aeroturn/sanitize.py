"""Prompt-injection defence for untrusted free text.

Passenger remarks, crew notes and similar fields come from outside the system (a booking channel, a check-in
agent, a passenger). They are data, never instructions. Before any tool result reaches the LLM, every such field
is scanned; text that looks like an instruction aimed at an AI or an operator is withheld and the event is logged.

This is a second line of defence. Even if an instruction got through, the LLM can only call guarded tools, cannot
approve anything and cannot change a safety rule.
"""

from __future__ import annotations

import re
import sqlite3

# Free-text fields that originate outside AeroTurn
UNTRUSTED_KEYS = frozenset({"remarks", "notes", "remark", "note", "comment", "free_text"})

PATTERNS = [
    (r"\b(system|developer)\s*(note|prompt|message|instruction)s?\b", "fake system message"),
    (r"\b(note|message|instruction)s?\s+to\s+(the\s+)?(ai|agent|assistant|model|llm|bot)\b", "addressed to the AI"),
    (r"\bignore\b.{0,40}\b(previous|prior|above|all|crew|duty|rule|limit|instruction|maintenance|guard)", "ignore rules"),
    (r"\b(disregard|bypass|override|disable|skip)\b.{0,40}\b(rule|limit|guard|check|safety|instruction|hold|approval)",
     "bypass a control"),
    (r"\byou\s+(are|must|should|will)\s+now\b", "role change"),
    (r"\b(dispatch|release|approve|upgrade)\b.{0,30}\b(immediately|now|without)\b", "unauthorised action"),
    (r"\bthis\s+is\s+the\s+(occ\s+)?(director|captain|controller|admin|ceo)\b", "claims authority"),
    (r"\b(extend|extending|extension|stretch|exceed)\w*\b.{0,30}\b(duty|fdp|limit|hours)\b", "asks to change a duty limit"),
    (r"\b(duty|fdp)\b.{0,30}\b(extend|extension|waive|ignore|over)\b", "asks to change a duty limit"),
    (r"\bdiscretion\b", "invokes discretion by message"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), why) for p, why in PATTERNS]
WITHHELD = "[withheld by AeroTurn: this free text looked like an instruction or a rule change]"


def scan(text: str) -> list[str]:
    """Reasons this text looks like an injected instruction (empty list = clean)."""
    if not isinstance(text, str) or not text:
        return []
    return sorted({why for rx, why in _COMPILED if rx.search(text)})


def scrub(obj, hits: list[dict] | None = None, _owner: str | None = None):
    """Return a copy of ``obj`` with injected instructions in untrusted fields withheld. ``hits`` collects findings."""
    if isinstance(obj, dict):
        owner = obj.get("pax_id") or obj.get("crew_id") or obj.get("msg_id") or _owner
        out = {}
        for k, v in obj.items():
            if k in UNTRUSTED_KEYS and isinstance(v, str):
                reasons = scan(v)
                if reasons:
                    if hits is not None:
                        hits.append({"owner": owner, "field": k, "reasons": reasons})
                    out[k] = WITHHELD
                    continue
            out[k] = scrub(v, hits, owner)
        return out
    if isinstance(obj, list):
        return [scrub(v, hits, _owner) for v in obj]
    return obj


def log_hits(conn: sqlite3.Connection, hits: list[dict], tool: str) -> int:
    """Record each blocked injection once per owner and field (the audit log stays readable)."""
    from . import audit, db
    new = 0
    for h in hits:
        if db.one(conn, "SELECT 1 FROM audit_log WHERE action = 'INJECTION_BLOCKED' AND detail LIKE ? AND detail LIKE ?",
                  (f'%"field": "{h["field"]}"%', f'%"owner": "{h["owner"]}"%')):
            continue
        audit.log(conn, "GUARD", "INJECTION_BLOCKED", {"owner": h["owner"], "field": h["field"], "tool": tool,
                                                       "reasons": h["reasons"]})
        new += 1
    return new
