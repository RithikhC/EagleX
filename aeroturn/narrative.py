"""Executive recovery brief + notification templates + numeric grounding check.

The LLM writes prose. Facts come from the database. The brief is
grounding-checked: every number in the LLM's text must appear in the facts
it was given, and anything else is flagged for the controller.
"""

from __future__ import annotations

import json
import re
import sqlite3

from . import audit, config, costs, db, recovery
from .timeutil import hm, is_iso, parse

DEFAULT_TEMPLATES = {
    "UMNR_GUARDIAN": ("Dear guardian of {first_name}: the connection was missed because the inbound flight arrived late. "
                      "{first_name} is now booked on {new_flight} to {dest_city}, departing {dep_time} and arriving "
                      "{arr_time}, seat {seat}. {assistance}. Booking {pnr}."),
    "MEDICAL": ("Dear {first_name}, we have protected your onward journey: {new_flight} to {dest_city} departs "
                "{dep_time}, arriving {arr_time}, seat {seat}. {assistance}. Your {bag_count} bag(s) are transferred "
                "with you."),
    "PRM": ("Dear {first_name}, you are rebooked on {new_flight} to {dest_city} at {dep_time} (arrives {arr_time}), "
            "seat {seat}. {assistance}. Your {bag_count} bag(s) travel with you."),
    "FAMILY": ("Dear {first_name}, your party stays together on {new_flight} to {dest_city}, departing {dep_time}, "
               "arriving {arr_time}. Seat {seat}. {assistance}. Bags: {bag_count}, transferred automatically."),
    "PREMIUM": ("Dear {first_name}, we apologise for the missed connection. You are confirmed on {new_flight} to "
                "{dest_city}, departing {dep_time} from gate {gate}, seat {seat}. Lounge access is available."),
    "STANDARD": ("Dear {first_name}, due to the late arrival of your flight you are rebooked on {new_flight} to "
                 "{dest_city}, departing {dep_time} from gate {gate}, arriving {arr_time}. Seat {seat}. Your "
                 "{bag_count} bag(s) are transferred automatically. Booking {pnr}."),
}


def brief_facts(conn: sqlite3.Connection) -> dict:
    from .tools import get_turnaround_and_crew_state

    s = get_turnaround_and_crew_state(conn)
    changes = db.rows(conn, "SELECT change_type, status, payload, flight_id FROM schedule_changes ORDER BY staged_at")
    txns = db.rows(conn, "SELECT outcome, detail FROM txn_log ORDER BY started_at")
    blocks = db.rows(conn, "SELECT action, detail FROM audit_log WHERE actor = 'GUARD' AND action LIKE '%BLOCK%' "
                           "ORDER BY seq")
    interventions = []
    for b in blocks:
        d = json.loads(b["detail"] or "{}")
        interventions.append(f"{b['action']} {d.get('flight', '')} ({', '.join(d.get('rules', []))})".replace("  ", " "))
    notes = db.one(conn, "SELECT COUNT(*) AS n FROM notifications")["n"]
    rebooked = db.rows(conn, """
        SELECT p.first_name || ' ' || p.last_name AS name, p.ssr, f.flight_no, f.std, f.dest FROM bookings b
        JOIN passengers p ON p.pax_id = b.pax_id JOIN flights f ON f.flight_id = b.flight_id
        WHERE b.source = 'AEROTURN' ORDER BY p.pax_id""")
    vul = [r for r in rebooked if r["ssr"] and r["ssr"] not in ("",)]
    c = costs.disruption_cost(conn)
    return {
        "inbound": s["inbound"] | {"crew_fdp_limit": s["inbound_crew"]["fdp_limit"],
                                   "crew_margin_min": s["inbound_crew"]["margin_at_eibt_min"]},
        "outbound": s["outbound_rotation"],
        "maintenance": [m for m in s["maintenance"] if m["dispatch_blocking"]],
        "connections_initially_at_risk": len(recovery.disrupted_pax_ids(conn)),
        "connections_still_at_risk": s["connections"]["at_risk"],
        "rebooked": len(rebooked),
        "vulnerable_rebooked": [f"{r['name']} ({r['ssr']}) -> {r['flight_no']} {hm(r['std'])}" for r in vul],
        "controller_changes": [{"type": ch["change_type"], "status": ch["status"],
                                "details": {k: v for k, v in json.loads(ch["payload"]).items() if k != "crew_ids"}}
                               for ch in changes],
        "awaiting_controller": [f"{ch['change_type']} {_fmt_details(json.loads(ch['payload']))}"
                                for ch in changes if ch["status"] == "PENDING"],
        "executed_atomically": ([f"rebooked {len(rebooked)} passengers with their bags in one transaction "
                                 f"(transactions: {', '.join(t['outcome'] for t in txns)})"] if rebooked else [])
                               + ([f"{notes} passenger notifications sent"] if notes else []),
        "transactions": [t["outcome"] for t in txns],
        "guard_blocks": len(blocks),
        "guard_interventions": interventions,
        "cost_aed": {"legacy": c["legacy_auto_reprotect"]["total"], "aeroturn": c["aeroturn"]["total"],
                     "savings": c["savings"], "eu261_aeroturn": c["aeroturn"]["eu261"],
                     "eu261_legacy": c["legacy_auto_reprotect"]["eu261"],
                     "outbound_delay_cost": c["outbound_rotation"]["delay_cost"]},
        "same_day_arrivals": c["aeroturn"]["same_day"],
    }


def template_brief(f: dict) -> str:
    pend = [x for x in f["controller_changes"] if x["status"] == "PENDING"]
    appr = [x for x in f["controller_changes"] if x["status"] == "APPROVED"]
    blocked = [x for x in f["controller_changes"] if x["status"] == "BLOCKED"]
    inb, out = f["inbound"], f["outbound"]
    lines = [
        f"### Executive turnaround recovery brief: {inb['flight']} / {out['flight']}",
        "",
        f"**Situation.** {inb['flight']} {inb['route']} in-block {inb['eibt']} ({inb['delay_min']} min late). "
        f"Inbound crew FDP limit {inb['crew_fdp_limit']}, margin {inb['crew_margin_min']} min at on-blocks. "
        f"Outbound {out['flight']} critical-path EOBT {out['critical_path_eobt']} "
        f"(+{out['projected_delay_min']} min).",
        "",
        "**Decisions awaiting the Operations Controller.** " + (
            "; ".join(f"{x['type']} {_fmt_details(x['details'])}" for x in pend) if pend else "none"),
        "",
        "**Approved.** " + ("; ".join(f"{x['type']} {_fmt_details(x['details'])}" for x in appr) if appr else "none yet"),
        "",
        f"**Passengers.** {f['connections_initially_at_risk']} connections broke; {f['rebooked']} passengers rebooked "
        f"atomically with bags; {f['connections_still_at_risk']} still at risk. Vulnerable passengers were processed "
        f"first: " + (", ".join(f["vulnerable_rebooked"][:6]) or "n/a") + ".",
        "",
        f"**Safety guards.** {f['guard_blocks']} unsafe proposals blocked in code" +
        (f" (e.g. {', '.join(x['type'] for x in blocked[:3])})" if blocked else "") +
        f". Transactions: {', '.join(f['transactions']) or 'none'}.",
        "",
        f"**Maintenance.** " + "; ".join(f"{m['item']} {m['title']}: {m['crs']}" for m in f["maintenance"]),
        "",
        f"**Cost.** AeroTurn AED {f['cost_aed']['aeroturn']:,} vs legacy auto-reprotect AED {f['cost_aed']['legacy']:,} "
        f"(saves AED {f['cost_aed']['savings']:,}; EU261 AED {f['cost_aed']['eu261_aeroturn']:,} vs "
        f"AED {f['cost_aed']['eu261_legacy']:,}). {f['same_day_arrivals']} passengers still travel today.",
    ]
    return "\n".join(lines)


def _fmt_details(d: dict) -> str:
    d = {k: v for k, v in d.items() if not k.startswith("_")}
    return "(" + ", ".join(f"{k}={hm(v) if is_iso(v) else v}" for k, v in d.items()) + ")"


BRIEF_PROMPT = """You are the AeroTurn disruption agent writing for the human Operations Controller.
Write an executive turnaround recovery brief in Markdown, at most 220 words, with these bold headings:
Situation, Decisions awaiting you, Executed (atomic), Safety guard interventions, Passenger impact, Cost.
"Decisions awaiting you" lists ONLY awaiting_controller. "Executed (atomic)" lists ONLY executed_atomically
(staged changes are NOT executed). "Safety guard interventions" lists ONLY guard_interventions, verbatim in meaning.
Use ONLY facts and numbers from the JSON below. Do not invent any number, time, flight or name.
All money is in UAE dirhams: write amounts like AED 50,532.
Be direct and specific; the controller must decide quickly.

FACTS:
{facts}"""


def executive_brief(conn: sqlite3.Connection, client=None) -> dict:
    facts = brief_facts(conn)
    if client is None:
        md = template_brief(facts)
        return {"markdown": md, "source": "template (offline)", "grounding": grounding_check(md, facts)}
    try:
        prompt = BRIEF_PROMPT.format(facts=json.dumps(facts, default=str))
        sys = "You write concise, factual operations briefs." + (" /no_think" if getattr(client, "is_qwen3", False) else "")
        resp = client.chat([{"role": "system", "content": sys}, {"role": "user", "content": prompt}],
                           temperature=0.2, max_tokens=700)
        md = resp.content.strip() or template_brief(facts)
        g = grounding_check(md, facts)
        audit.log(conn, "AGENT", "EXECUTIVE_BRIEF", {"source": client.label, "ungrounded": g["ungrounded"]})
        return {"markdown": md, "source": client.label, "grounding": g}
    except Exception as exc:  # noqa: BLE001
        md = template_brief(facts)
        return {"markdown": md, "source": f"template (LLM error: {exc})", "grounding": grounding_check(md, facts)}


_NUM = re.compile(r"(?<![A-Za-z])(\d{1,2}:\d{2}|\d[\d,]*(?:\.\d+)?)")


def _numbers(obj) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out |= _numbers(k) | _numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _numbers(v)
    else:
        for m in _NUM.findall(str(obj)):
            out.add(m.replace(",", ""))
    return out


def grounding_check(text: str, facts: dict) -> dict:
    """Every number in the narrative must exist in the facts the model was given."""
    allowed = _numbers(facts) | {str(i) for i in range(0, 11)} | {"261"}
    # models write 33,275 / 33 275 / 33\u202f275 / 33.275: join digit groups before checking
    joined = re.sub(r"(?<=\d)[ ,.\u00a0\u202f\u2009](?=\d{3}\b)", "", text)
    found = [m.replace(",", "") for m in _NUM.findall(re.sub(r"\b(?:EU|EK|IP|MX|FL|P)[- ]?(\d+)", "", joined))]
    ungrounded = sorted({n for n in found if n not in allowed})
    return {"numbers_checked": len(found), "ungrounded": ungrounded, "grounded": not ungrounded}
