"""Terminal demo: the full judged scenario without a browser (presentation fallback).

    python run_demo.py            # interactive: you approve as the Operations Controller
    python run_demo.py --yes      # non-interactive, auto-approve as a named controller
    python run_demo.py --offline  # force the offline policy brain
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

# The terminal demo uses its own runtime DB so it never disturbs the Streamlit console's state.
os.environ.setdefault("AEROTURN_RUNTIME_DIR", str(Path(__file__).resolve().parent / "runtime" / "cli"))

from aeroturn import agent, audit, config, db, faults, hitl, lab, llm, tools, turnaround  # noqa: E402

os.system("")  # enable ANSI colours on Windows terminals
C = {"llm": "\033[95m", "tool": "\033[94m", "guard": "\033[91m", "hitl": "\033[93m", "ok": "\033[92m",
     "dim": "\033[90m", "b": "\033[1m", "x": "\033[0m"}
LANE = {"llm": ("llm", "LLM"), "policy": ("llm", "POLICY"), "thinking": ("dim", "THINK"), "tool_call": ("tool", "TOOL"),
        "guard_block": ("guard", "GUARD"), "hitl": ("hitl", "HITL"), "txn_commit": ("ok", "COMMIT"),
        "txn_rollback": ("guard", "ROLLBACK"), "autopilot": ("dim", "AUTO"), "system": ("tool", "SYSTEM"),
        "error": ("guard", "ERROR"), "brief": ("llm", "BRIEF")}


def h(title: str) -> None:
    print(f"\n{C['b']}{'=' * 78}\n  {title}\n{'=' * 78}{C['x']}")


def lane(kind: str, text: str) -> None:
    col, tag = LANE.get(kind, ("dim", kind.upper()))
    body = textwrap.fill(text, 100, subsequent_indent=" " * 11)
    print(f"{C[col]}[{tag:^8}]{C['x']} {body}")


def verdict(title: str, r: dict) -> None:
    st = r.get("status")
    col = "guard" if st in ("BLOCKED", "REJECTED_INVALID_ARGS", "REFUSED", "REJECTED", "BLOCKED_AT_APPROVAL") else (
        "hitl" if st == "PENDING" else "ok")
    print(f"  {C[col]}{st}{C['x']}  {title}")
    seen = set()
    for v in (r.get("guard") or {}).get("violations", []):
        if v["rule"] in seen:
            continue
        seen.add(v["rule"])
        print(f"     {C['guard']}{v['rule']}{C['x']} {v['message']}")
    for e in r.get("errors", []) or []:
        print(f"     {C['guard']}ARGS{C['x']} {e}")


def ask(q: str, auto: bool) -> bool:
    if auto:
        print(f"  {q} [auto: yes]")
        return True
    return input(f"  {q} [y/N] ").strip().lower().startswith("y")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    if args.offline:
        os.environ["AEROTURN_LLM"] = "offline"

    db.reset_runtime()
    c = db.connect()
    s = tools.get_turnaround_and_crew_state(c)
    h("AeroTurn: EK812 late-aircraft disruption, DXB hub, 14:50 GST")
    print(f"  EK812 {s['inbound']['route']} in-block {s['inbound']['eibt']} (+{s['inbound']['delay_min']} min), "
          f"{s['inbound']['passengers']} pax, {s['inbound']['connecting']} connecting")
    print(f"  Inbound crew FDP limit {s['inbound_crew']['fdp_limit']}: margin {s['inbound_crew']['margin_at_eibt_min']} min")
    print(f"  {s['connections']['at_risk']} connections break ({s['connections']['vulnerable_at_risk']} vulnerable). "
          f"MX-0412 hydraulic item OPEN. EK813 captain unfit.")

    h("1. Agent run (seat conflict will be injected at rebooking step 7)")
    info = llm.detect()
    print(f"  Brain: {llm.describe(info)}")
    faults.arm(c, "SEAT_CONFLICT", 7)
    res = agent.AeroTurnAgent(c, llm.make_client(info),
                              on_event=lambda e: e.kind != "tool_result" and lane(
                                  e.kind, e.title if e.kind != "tool_call" else f"{e.title}({str(e.detail)[:90]})")).run()
    print()
    print(textwrap.indent(res["brief"]["markdown"], "  "))
    print(f"  {C['dim']}grounding: {res['brief']['grounding']}{C['x']}")

    h("2. Guards vs. a rogue LLM")
    crew_a = [r["crew_id"] for r in db.rows(c, "SELECT crew_id FROM crew_assignments WHERE flight_id = 'EK812-1121'")]
    verdict("EK813 off-blocks 16:35 with the inbound crew",
            tools.dispatch(c, "propose_departure", {"flight_no": "EK813", "off_blocks": "16:35", "crew_ids": crew_a},
                           actor="ROGUE_LLM"))
    verdict("propose_departure(..., override=True)",
            tools.dispatch(c, "propose_departure", {"flight_no": "EK813", "off_blocks": "16:35", "override": True},
                           actor="ROGUE_LLM"))
    nv = lab.naive_vs_guarded()  # fresh sandbox copy of the scenario
    verdict(f"unconstrained revenue-first plan ({len(nv['naive_plan']['assignments'])} passengers)", nv["naive_result"])
    print(f"  same guard, AeroTurn plan: {C['ok']}{nv['aeroturn_result']['status']}{C['x']}")

    h("3. Atomic rollback evidence")
    for t in db.rows(c, "SELECT txn_id, outcome, detail FROM txn_log ORDER BY started_at"):
        print(f"  {C['ok'] if t['outcome'] == 'COMMITTED' else C['guard']}{t['outcome']:<12}{C['x']} {t['txn_id']} {t['detail'][:120]}")
    inv = db.check_invariants(c)
    print(f"  Invariants: " + ", ".join(f"{k}={v['count']}" for k, v in inv.items() if isinstance(v, dict)))

    h("4. Priority order of the committed rebooking (first 12)")
    from aeroturn import guards
    from aeroturn.facts import pax_facts
    rows = db.rows(c, """SELECT p.*, f.flight_no, f.std FROM bookings b JOIN passengers p ON p.pax_id = b.pax_id
                          JOIN flights f ON f.flight_id = b.flight_id WHERE b.source = 'AEROTURN' ORDER BY b.booking_id""")
    group = {}
    for r in rows:
        group[r["pnr"]] = min(group.get(r["pnr"], 4), guards.pax_tier(pax_facts(r)))
    for i, r in enumerate(rows[:13], 1):
        t, own = group[r["pnr"]], guards.pax_tier(pax_facts(r))
        label = guards.TIER_LABELS[t] + (" (group)" if own != t else "")
        name = f"{r['first_name']} {r['last_name']}"
        print(f"  {i:>2}. {label:<32} {name:<22} {r['ssr'] or '-':<5} -> {r['flight_no']} {r['std'][-5:]}")

    h("5. You are the Operations Controller")
    who = hitl.ControllerIdentity(os.environ.get("OCC_NAME", "Duty Ops Controller"), os.environ.get("OCC_ID", "OCC-2611"))
    for ch in hitl.pending(c):
        d = {k: v for k, v in ch["payload"].items() if not k.startswith("_")}
        print(f"  {C['hitl']}{ch['change_type']}{C['x']} {ch['flight_no']} {d}\n    agent: {ch['justification'][:110]}")
        if ask("Approve?", args.yes):
            verdict(ch["change_type"], hitl.approve(c, ch["change_id"], who, "terminal demo"))

    h("6. Engineer CRS and departure release")
    end = next(t["end_hm"] for t in turnaround.critical_path(c, config.OUTBOUND_FLIGHT_ID)["tasks"] if t["task_id"] == "MXI")
    hitl.advance_clock(c, end)
    verdict("CRS by B2 avionics engineer", hitl.sign_crs(c, "MX-0412", "E-02"))
    verdict("CRS by B1 engineer", hitl.sign_crs(c, "MX-0412", "E-01"))
    eobt = turnaround.critical_path(c, config.OUTBOUND_FLIGHT_ID)["eobt_hm"]
    r = tools.propose_departure(c, "EK813", eobt, actor="OCC")
    verdict(f"EK813 departure release at {eobt}", r)
    if r["status"] == "PENDING" and ask("Release EK813?", args.yes):
        verdict("EK813 release", hitl.approve(c, r["change_id"], who, "released"))

    h("Done")
    print(f"  Audit chain: {audit.verify_chain(c)}")
    print(f"  Invariants all clear: {db.check_invariants(c)['all_clear']}")
    print(f"  Open the console: streamlit run app.py")


if __name__ == "__main__":
    sys.exit(main())
