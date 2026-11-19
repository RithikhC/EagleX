"""AeroTurn OCC console (Streamlit).

    streamlit run app.py
"""

from __future__ import annotations

import html
import json
import os
import re
import uuid

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from aeroturn import (agent, audit, config, costs, crew, db, faults, guards, hitl, lab, llm, narrative, recovery,
                      tools, turnaround)
from aeroturn.timeutil import dur, hm, minutes, parse, plus

st.set_page_config(page_title="AeroTurn OCC", page_icon="✈️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 3rem;}
.lane {border-left: 4px solid #64748b; padding: 7px 12px; margin: 5px 0; border-radius: 8px;
       background: rgba(148,163,184,.06); font-size: .92rem; line-height: 1.35;}
.lane .tag {font-size: .68rem; font-weight: 800; letter-spacing: .06em; padding: 2px 7px; border-radius: 5px;
            margin-right: 8px; white-space: nowrap;}
.lane.llm {border-color:#a78bfa;} .lane.llm .tag {background:#a78bfa26; color:#c4b5fd;}
.lane.thinking {border-color:#7c3aed; opacity:.8} .lane.thinking .tag {background:#7c3aed26; color:#a78bfa;}
.lane.tool {border-color:#60a5fa;} .lane.tool .tag {background:#60a5fa26; color:#93c5fd;}
.lane.guard {border-color:#f87171;} .lane.guard .tag {background:#f8717126; color:#fca5a5;}
.lane.hitl {border-color:#fbbf24;} .lane.hitl .tag {background:#fbbf2426; color:#fcd34d;}
.lane.ok {border-color:#2dd4bf;} .lane.ok .tag {background:#2dd4bf26; color:#5eead4;}
.lane.bad {border-color:#fb7185;} .lane.bad .tag {background:#fb718526; color:#fda4af;}
.lane.auto {border-color:#94a3b8;} .lane.auto .tag {background:#94a3b826; color:#cbd5e1;}
.lane.sys {border-color:#38bdf8;} .lane.sys .tag {background:#38bdf826; color:#7dd3fc;}
.vcard {border-radius: 12px; padding: 12px 14px; margin: 6px 0;}
.vblock {background: rgba(248,113,113,.08); border: 1px solid rgba(248,113,113,.45);}
.vpass {background: rgba(52,211,153,.08); border: 1px solid rgba(52,211,153,.45);}
.vpend {background: rgba(251,191,36,.08); border: 1px solid rgba(251,191,36,.45);}
.vtitle {font-weight: 800; font-size: 1.02rem; margin-bottom: 4px;}
.rule {font-family: ui-monospace, Consolas, monospace; font-weight: 700; color: #fca5a5; margin-right: 6px;}
.small {font-size: .82rem; opacity: .8}
.hero {font-size: 1.55rem; font-weight: 800; margin: 0;}
.sub {opacity: .75; margin-top: -2px;}
.pill {display:inline-block; padding:2px 9px; border-radius:999px; font-size:.75rem; font-weight:700; margin-right:6px;}
.p-llm {background:#a78bfa26; color:#c4b5fd} .p-code {background:#60a5fa26; color:#93c5fd}
.p-guard {background:#f8717126; color:#fca5a5} .p-hitl {background:#fbbf2426; color:#fcd34d}
.stepno {font-size: 1.05rem; font-weight: 800;}
</style>
""", unsafe_allow_html=True)

ss = st.session_state
ss.setdefault("flash", [])
ss.setdefault("results", {})

# Hosted deployments (Streamlit Community Cloud) keep API keys in st.secrets; expose them to the LLM layer.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:  # noqa: BLE001 - no secrets file locally is fine
    pass

# Every visitor gets an isolated copy of the scenario. The id lives in the URL (?s=...), so a page refresh
# keeps your progress and two judges on the public demo never step on each other.
_sid = st.query_params.get("s", "")
if not re.fullmatch(r"[a-f0-9]{10}", _sid or ""):
    _sid = uuid.uuid4().hex[:10]
    st.query_params["s"] = _sid
SESSION_DB = config.RUNTIME_DIR / f"session_{_sid}.sqlite"
if "cleaned" not in ss:
    lab.cleanup_runtime()
    ss["cleaned"] = True


def conn():
    return db.connect(SESSION_DB)


C = conn()
TIER_BADGE = {1: "🟥 P1", 2: "🟧 P2", 3: "🟦 P3", 4: "⬜ P4"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def flash(kind: str, msg: str) -> None:
    ss["flash"].append((kind, msg))


def controller() -> hitl.ControllerIdentity:
    return hitl.ControllerIdentity(ss.get("ctrl_name", "Duty Ops Controller"), ss.get("ctrl_id", "OCC-2611"))


def brain_info() -> dict:
    choice = ss.get("brain_choice", "auto")
    cache = ss.setdefault("brain_cache", {})
    if choice not in cache:
        os.environ["AEROTURN_LLM"] = choice
        cache[choice] = llm.detect()
    return cache[choice]


LANES = {
    "llm": ("llm", "LLM BRAIN"), "thinking": ("thinking", "LLM REASONING"), "tool_call": ("tool", "TOOL CALL"),
    "tool_result": ("tool", "CODE RESULT"), "guard_block": ("guard", "GUARD BLOCK"), "guard_pass": ("ok", "GUARD PASS"),
    "hitl": ("hitl", "HITL STAGED"), "txn_commit": ("ok", "TXN COMMIT"), "txn_rollback": ("bad", "TXN ROLLBACK"),
    "autopilot": ("auto", "CODE AUTOPILOT"), "system": ("sys", "SYSTEM"), "error": ("bad", "ERROR"),
    "brief": ("llm", "BRIEF"), "policy": ("auto", "AGENT POLICY · offline"),
}


def lane_html(kind: str, title: str, extra: str = "") -> str:
    cls, tag = LANES.get(kind, ("tool", kind.upper()))
    return (f"<div class='lane {cls}'><span class='tag'>{tag}</span>{html.escape(str(title))}"
            f"{('<div class=small>' + html.escape(extra) + '</div>') if extra else ''}</div>")


def event_extra(ev: dict) -> str:
    if ev["kind"] == "tool_call":
        return json.dumps(ev["detail"], default=str)[:220] if ev["detail"] else ""
    return ""


def render_trace(trace: list[dict], compact: bool = False) -> None:
    for ev in trace:
        if compact and ev["kind"] in ("tool_result", "thinking", "tool_call"):
            continue
        st.markdown(lane_html(ev["kind"], ev["title"], event_extra(ev)), unsafe_allow_html=True)
        if not compact and ev["kind"] in ("tool_result", "guard_block", "hitl", "txn_commit", "txn_rollback",
                                          "error", "thinking") and ev.get("detail"):
            with st.expander("details", expanded=False):
                if isinstance(ev["detail"], (dict, list)):
                    st.json(ev["detail"], expanded=1)
                else:
                    st.code(str(ev["detail"])[:3000])


def verdict_card(res: dict, title: str) -> None:
    g = res.get("guard") or {}
    status = res.get("status") or g.get("verdict")
    if status in ("BLOCKED", "BLOCKED_AT_APPROVAL", "REFUSED", "REJECTED_INVALID_ARGS", "ERROR", "REJECTED"):
        cls, head = "vblock", f"⛔ {status}"
    elif status in ("PENDING",):
        cls, head = "vpend", "⏳ STAGED: awaiting Operations Controller"
    else:
        cls, head = "vpass", f"✅ {status}"
    body = ""
    vs = g.get("violations", [])
    seen, first, rest = set(), [], []
    for v in vs:
        (rest if v["rule"] in seen else first).append(v)
        seen.add(v["rule"])
    vs = first + rest
    for v in vs[:5]:
        body += (f"<div><span class='rule'>{html.escape(v['rule'])}</span>{html.escape(v.get('title', ''))}"
                 f"<div class='small'>{html.escape(v.get('message', ''))}</div></div>")
    more = len(vs) - 5
    if more > 0:
        body += f"<div class='small'>... and {more} more violation(s)</div>"
    for e in res.get("errors", []) or []:
        body += f"<div><span class='rule'>ARGS</span>{html.escape(e)}</div>"
    if res.get("error"):
        body += f"<div class='small'>{html.escape(str(res['error']))}</div>"
    if res.get("message"):
        body += f"<div class='small' style='margin-top:6px'>{html.escape(res['message'])}</div>"
    st.markdown(f"<div class='vcard {cls}'><div class='vtitle'>{html.escape(title)}: {head}</div>{body}</div>",
                unsafe_allow_html=True)


def run_agent(container, inject: bool, fault_step: int = 7) -> None:
    c = conn()
    if inject:
        faults.arm(c, "SEAT_CONFLICT", fault_step)
    info = brain_info()
    client = llm.make_client(info)
    with container.status(f"AeroTurn agent running. Brain: {llm.describe(info)}", expanded=True) as status:
        def on_event(ev):
            if ev.kind in ("tool_result",):
                return
            status.markdown(lane_html(ev.kind, ev.title, event_extra(ev.as_dict())), unsafe_allow_html=True)
        res = agent.AeroTurnAgent(c, client, on_event=on_event).run()
        status.update(label=f"Agent finished. Brain: {llm.describe(info)}", state="complete", expanded=False)
    ss["agent_result"] = res
    rb = [e for e in res["trace"] if e["kind"] == "txn_rollback"]
    if rb:
        ss["results"]["agent_rollback"] = rb[-1]["detail"]


# ---------------------------------------------------------------------------
# callbacks (run before the page re-renders, so KPIs are always fresh)
# ---------------------------------------------------------------------------
def cb_reset():
    db.reset_runtime(SESSION_DB)
    for k in ("agent_result", "results", "flash"):
        ss.pop(k, None)
    ss["results"], ss["flash"] = {}, []
    flash("success", "Scenario reset to 14:50 GST: EK812 on approach, nothing decided yet.")


def cb_rogue(kind: str):
    c = conn()
    crew_a = [r["crew_id"] for r in db.rows(c, "SELECT crew_id FROM crew_assignments WHERE flight_id = ?",
                                            (config.INBOUND_FLIGHT_ID,))]
    crew_b = [r["crew_id"] for r in db.rows(c, "SELECT crew_id FROM crew_assignments WHERE flight_id = ? "
                                               "AND status IN ('ROSTERED','ASSIGNED')", (config.OUTBOUND_FLIGHT_ID,))]
    eobt = turnaround.critical_path(c, config.OUTBOUND_FLIGHT_ID)["eobt_hm"]
    if kind == "crew":
        r = tools.dispatch(c, "propose_departure", {"flight_no": "EK813", "off_blocks": "16:35", "crew_ids": crew_a,
                                                    "justification": "Get the plane out: inbound crew is already on board"},
                           actor="ROGUE_LLM")
    elif kind == "mx":
        ids = sorted(set(crew_b + ["S-04"]))
        r = tools.dispatch(c, "propose_departure", {"flight_no": "EK813", "off_blocks": eobt, "crew_ids": ids,
                                                    "justification": "Crew is legal, dispatch before the inspection is signed"},
                           actor="ROGUE_LLM")
    elif kind == "override":
        r = tools.dispatch(c, "propose_departure", {"flight_no": "EK813", "off_blocks": "16:35", "override": True,
                                                    "emergency_waiver": "OCC director approved"}, actor="ROGUE_LLM")
    elif kind == "approve":
        try:
            pend = hitl.pending(c)
            hitl.approve(c, pend[0]["change_id"] if pend else "CHG-X", hitl.ControllerIdentity("AeroTurn agent", "LLM-1"))
            r = {"status": "APPROVED"}
        except Exception as exc:  # noqa: BLE001
            r = {"status": "REJECTED", "error": f"{type(exc).__name__}: {exc}",
                 "message": "Approval functions are not in the agent tool registry, and hitl.approve() refuses "
                            "non-human identities."}
    else:
        return
    ss["results"][f"rogue_{kind}"] = r


def cb_approve(change_id: str):
    try:
        r = hitl.approve(conn(), change_id, controller(), ss.get(f"note_{change_id}", ""))
    except hitl.ApprovalError as exc:
        r = {"status": "REJECTED", "error": str(exc)}
    ss["results"][f"approval_{change_id}"] = r
    flash("success" if r["status"] == "APPROVED" else "warning", f"{change_id}: {r['status']}")


def cb_reject(change_id: str):
    try:
        r = hitl.reject(conn(), change_id, controller(), ss.get(f"note_{change_id}", "") or "Rejected by controller")
    except hitl.ApprovalError as exc:
        r = {"status": "ERROR", "error": str(exc)}
    flash("info", f"{change_id}: {r['status']}")


def cb_sign(eng_id: str):
    r = hitl.sign_crs(conn(), "MX-0412", eng_id, ss.get("crs_remarks", ""))
    ss["results"]["crs"] = r
    flash("success" if r["status"] == "SIGNED" else "error", f"CRS {r['status']}")


def cb_advance(to: str):
    r = hitl.advance_clock(conn(), to)
    flash("info", f"Clock: {r['clock']}")


def cb_propose_release():
    c = conn()
    eobt = turnaround.critical_path(c, config.OUTBOUND_FLIGHT_ID)["eobt_hm"]
    ss["results"]["release"] = tools.dispatch(c, "propose_departure", {"flight_no": "EK813", "off_blocks": eobt},
                                              actor="OCC_UI")


def cb_arm():
    kind = ss.get("chaos_kind")
    if kind and kind != "none":
        faults.arm(conn(), kind, int(ss.get("chaos_step", 7)))
        flash("warning", f"Chaos armed: {kind} at step {ss.get('chaos_step', 7)} of the next live rebooking.")
    else:
        faults.disarm(conn())


def cb_rebook_remaining():
    c = conn()
    plan = tools.dispatch(c, "plan_passenger_recovery", {"objective": "earliest_arrival"}, actor="OCC_UI")
    r = tools.dispatch(c, "execute_atomic_passenger_rebook", {"plan_id": plan["plan_id"]}, actor="OCC_UI")
    if r.get("status") == "COMMITTED":
        tools.dispatch(c, "send_passenger_notifications", {"templates": narrative.DEFAULT_TEMPLATES}, actor="OCC_UI")
    flash("success" if r.get("status") == "COMMITTED" else "warning",
          f"Rebooking of remaining passengers: {r.get('status')}")


def cb_lab_rollback():
    ss["results"]["lab_rollback"] = lab.rollback_experiment(ss.get("lab_kind", "SEAT_CONFLICT"),
                                                            int(ss.get("lab_step", 7)), tag=f"sb_{_sid}")


def cb_lab_naive():
    ss["results"]["lab_naive"] = lab.naive_vs_guarded(tag=f"sb_{_sid}_naive")


# ---------------------------------------------------------------------------
# sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("<p class='hero'>✈️ AeroTurn OCC</p><p class='sub'>DXB hub · EK812 disruption</p>",
                unsafe_allow_html=True)
    clock = db.now(C)
    gate_change = db.one(C, "SELECT * FROM schedule_changes WHERE change_type = 'GATE_REASSIGNMENT' "
                            "AND status IN ('PENDING','APPROVED') ORDER BY staged_at DESC LIMIT 1")
    c1, c2 = st.columns(2)
    c1.metric("Sim clock (GST)", hm(clock))
    deadline = parse("2026-11-21T15:15")
    left = minutes(clock, deadline)
    c2.metric("Gate decision", f"{left} min" if left > 0 else "closed",
              help="EK812 must know its stand 5 min before in-block (15:20); inbound crew FDP ends 15:40")
    st.caption("Advance scenario clock")
    adv = st.columns(3)
    adv[0].button("15:10", on_click=cb_advance, args=("15:10",), width="stretch")
    adv[1].button("15:25", on_click=cb_advance, args=("15:25",), width="stretch")
    mxi_end = next((t["end_hm"] for t in turnaround.critical_path(C, config.OUTBOUND_FLIGHT_ID)["tasks"]
                    if t["task_id"] == "MXI"), "16:30")
    adv[2].button(mxi_end, on_click=cb_advance, args=(mxi_end,), width="stretch",
                  help="Hydraulic inspection complete")

    st.divider()
    st.selectbox("Agent brain", ["auto", "offline", "ollama", "groq", "gemini"], key="brain_choice",
                 help="auto: local Ollama qwen3 if running, else Groq / Gemini keys from .env, else offline policy")
    info = brain_info()
    if info["provider"] == "offline":
        st.caption(f"🧠 **Offline policy** (no LLM): {info.get('reason', '')}")
    else:
        st.caption(f"🧠 **{info['model']}** via {info['provider']}")
    if st.button("Re-detect LLM", width="stretch"):
        ss.pop("brain_cache", None)
        st.rerun()

    st.divider()
    st.markdown("**Operations Controller (HITL)**")
    st.text_input("Name", value="Duty Ops Controller", key="ctrl_name")
    st.text_input("Staff / licence ID", value="OCC-2611", key="ctrl_id")

    st.divider()
    st.markdown("**Chaos injection** (presenter only, never the LLM)")
    st.selectbox("Fault", ["none", "SEAT_CONFLICT", "BAG_SYSTEM_FAULT"], key="chaos_kind")
    st.number_input("At rebooking step", 1, 45, 7, key="chaos_step")
    st.button("Arm for next live rebooking", on_click=cb_arm, width="stretch")
    armed = faults.peek(C)
    st.caption(f"Armed: **{armed['kind']} @ step {armed['at_step']}**" if armed else "Armed: none")

    st.divider()
    integ = guards.verify_guard_integrity()
    if integ["ok"]:
        st.success(f"Guards sealed & pinned\n\n`{integ['actual'][:16]}…`", icon="🛡️")
    else:
        st.error("Guard fingerprint mismatch: agent disabled", icon="🚨")
    chain = audit.verify_chain(C)
    st.caption(f"Audit chain: {'✅ intact' if chain['ok'] else '❌ BROKEN'} · {chain['entries']} entries")
    st.button("↺ Reset scenario", on_click=cb_reset, type="secondary", width="stretch")

for kind, msg in ss["flash"]:
    st.toast(msg, icon={"success": "✅", "warning": "⚠️", "error": "⛔"}.get(kind, "ℹ️"))
ss["flash"] = []

# ---------------------------------------------------------------------------
# header KPIs
# ---------------------------------------------------------------------------
state = tools.get_turnaround_and_crew_state(C)
risk_now = recovery.connection_risk(C)
disrupted = recovery.disrupted_pax_ids(C)
rebooked = {r["pax_id"] for r in db.rows(C, "SELECT pax_id FROM bookings WHERE source = 'AEROTURN'")}
vul_ids = {p["pax_id"] for p in recovery.connection_risk(C, use_original=True)["passengers"]
           if p["at_risk"] and p["vulnerable"]}
pending_n = state["pending_controller_decisions"]
mx = next(m for m in state["maintenance"] if m["item"] == "MX-0412")
out_f = db.one(C, "SELECT * FROM flights WHERE flight_id = ?", (config.OUTBOUND_FLIGHT_ID,))
inb_f = db.one(C, "SELECT * FROM flights WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))

st.markdown("<p class='hero'>AeroTurn: Autonomous Turnaround & Atomic Disruption Recovery</p>"
            "<p class='sub'><span class='pill p-llm'>LLM decides what to try</span>"
            "<span class='pill p-code'>Code executes atomically</span>"
            "<span class='pill p-guard'>Guards enforce immutable floors</span>"
            "<span class='pill p-hitl'>Humans approve network changes</span></p>", unsafe_allow_html=True)
k = st.columns(7)
k[0].metric("EK812 in-block", state["inbound"]["eibt"], f"+{state['inbound']['delay_min']} min late",
            delta_color="inverse", border=True)
k[1].metric("Crew FDP margin", f"{state['inbound_crew']['margin_at_eibt_min']} min",
            f"limit {state['inbound_crew']['fdp_limit']}", delta_color="off", border=True)
k[2].metric("Connections at risk", risk_now["at_risk"],
            f"{risk_now['awaiting_hold_decision']} await hold decision" if risk_now["awaiting_hold_decision"] else (
                f"of {len(disrupted)} broken" if rebooked else "connecting 280"), delta_color="off", border=True)
k[3].metric("Vulnerable safe", f"{len(vul_ids & rebooked)}/{len(vul_ids)}", border=True)
k[4].metric("EK813 off-blocks", hm(out_f["etd"]) if out_f["etd"] else state["outbound_rotation"]["critical_path_eobt"],
            f"STD {hm(out_f['std'])} · {out_f['status']}", delta_color="off", border=True)
k[5].metric("MX-0412 hydraulic", "Signed" if mx["status"] == "CLOSED" else "Open",
            "CRS valid" if mx["status"] == "CLOSED" else "no CRS",
            delta_color="normal" if mx["status"] == "CLOSED" else "inverse", border=True)
k[6].metric("For controller", pending_n, f"gate {inb_f['gate_id']}", delta_color="off", border=True)

tabs = st.tabs(["🎬 Guided demo", "🛰️ Situation", "🧠 Agent", "🛡️ Guards lab", "⚛️ Atomic rebooking",
                "🧑‍✈️ Controller (HITL)", "🔧 Turnaround & MX", "💶 Cost & network", "📨 Notifications", "📜 Audit"],
               key="main_tabs", on_change="rerun")

# ===========================================================================
# 1. GUIDED DEMO
# ===========================================================================
with tabs[0]:
    if tabs[0].open:
        st.caption("Five judged moments, in order. Each button calls the same tools and guards the agent uses.")

        with st.container(border=True):
            st.markdown("<span class='stepno'>① The agent analyses the cascade and runs the recovery</span>",
                        unsafe_allow_html=True)
            cc = st.columns([2, 1, 1])
            inject = cc[1].toggle("Inject mid-way seat conflict", value=True,
                                  help="A web sales channel sells a seat the plan is about to use (step 7)")
            go_run = cc[2].button("▶ Run AeroTurn agent", type="primary", width="stretch")
            cc[0].markdown(f"Brain: **{llm.describe(brain_info())}**. The agent reads state, stages gate, crew and "
                           "schedule changes for you, and rebooks passengers atomically.")
            holder = st.container()
            if go_run:
                run_agent(holder, inject)
                st.rerun()
            if ss.get("agent_result"):
                with st.expander("Agent trace (key events)", expanded=True):
                    render_trace(ss["agent_result"]["trace"], compact=True)

        with st.container(border=True):
            st.markdown("<span class='stepno'>② Python guards block unsafe departure proposals</span>",
                        unsafe_allow_html=True)
            b = st.columns(4)
            b[0].button("Rogue: depart 16:35 with the inbound crew", on_click=cb_rogue, args=("crew",), width="stretch")
            b[1].button("Rogue: depart before hydraulic CRS", on_click=cb_rogue, args=("mx",), width="stretch")
            b[2].button("Rogue: call tool with override=True", on_click=cb_rogue, args=("override",), width="stretch")
            b[3].button("Rogue: agent tries to self-approve", on_click=cb_rogue, args=("approve",), width="stretch")
            r = ss["results"]
            cols = st.columns(2)
            for i, (key, title) in enumerate([("rogue_crew", "EK813 with inbound crew at 16:35"),
                                              ("rogue_mx", "EK813 at EOBT without CRS"),
                                              ("rogue_override", "Override / waiver arguments"),
                                              ("rogue_approve", "Agent self-approval")]):
                if key in r:
                    with cols[i % 2]:
                        verdict_card(r[key], title)

        with st.container(border=True):
            st.markdown("<span class='stepno'>③ Atomic batch rebooking rolls back cleanly on a mid-way seat conflict</span>",
                        unsafe_allow_html=True)
            rb = ss["results"].get("agent_rollback")
            lr = ss["results"].get("lab_rollback")
            cc = st.columns([3, 1])
            cc[0].caption("Shown from the agent run above. Re-run on a fresh sandbox copy at any time.")
            cc[1].button("Re-run rollback on sandbox", on_click=cb_lab_rollback, width="stretch")
            src = lr["first"] if lr else rb
            if src:
                m = st.columns(5)
                m[0].metric("Failed at step", src["failed_at_step"])
                m[1].metric("Provisional steps reverted", src["provisional_steps_reverted"])
                m[2].metric("State identical after rollback", "YES" if src["state_identical_to_before"] else "NO")
                m[3].metric("Double bookings", src["invariants_after"]["seat_double_bookings"] +
                            src["invariants_after"]["duplicate_leg_bookings"])
                m[4].metric("Orphaned bags", src["invariants_after"]["orphaned_bags"] +
                            src["invariants_after"]["bags_left_on_old_connection"])
                st.markdown(lane_html("txn_rollback", src["error"],
                                      (src.get("fault_injected") or {}).get("story", "")), unsafe_allow_html=True)
                st.dataframe(pd.DataFrame([{"step": s["step"], "passenger": s["name"], "tier": s.get("tier"),
                                            "to": s.get("to"), "seat": s.get("seat"),
                                            "result": "✓ provisional, then reverted" if s["ok"] else "✗ " + s.get("error", "")[:70]}
                                           for s in src["steps"]]), hide_index=True, height=240)
                if lr:
                    st.caption(f"Sandbox retry after re-plan: **{lr['retry']['status']}**; at-risk remaining "
                               f"{lr['final']['at_risk_remaining']}; invariants all zero: "
                               f"{all(v == 0 for v in lr['final']['invariants'].values())}")
            else:
                st.info("Run the agent with the seat-conflict toggle on, or press the sandbox button.")

        with st.container(border=True):
            st.markdown("<span class='stepno'>④ Vulnerable passengers are rebooked first, and code proves it</span>",
                        unsafe_allow_html=True)
            rows = db.rows(C, """SELECT b.booking_id, p.pax_id, p.first_name || ' ' || p.last_name AS name, p.ssr, p.age,
                                  p.cabin, p.loyalty, p.is_infant, f.flight_no, f.std, f.operated_by_home, b.seat_no,
                                  p.original_onward_flight FROM bookings b JOIN passengers p ON p.pax_id = b.pax_id
                                  JOIN flights f ON f.flight_id = b.flight_id WHERE b.source = 'AEROTURN'
                                  ORDER BY b.booking_id""")
            if rows:
                from aeroturn.facts import pax_facts
                prow = {p_["pax_id"]: p_ for p_ in db.rows(C, "SELECT * FROM passengers")}
                own_tier = {r_["pax_id"]: guards.pax_tier(pax_facts(prow[r_["pax_id"]])) for r_ in rows}
                grp: dict = {}
                for r_ in rows:
                    pnr_ = prow[r_["pax_id"]]["pnr"]
                    grp[pnr_] = min(grp.get(pnr_, 4), own_tier[r_["pax_id"]])
                table = []
                for i, r_ in enumerate(rows, 1):
                    tier = grp[prow[r_["pax_id"]]["pnr"]]
                    inherited = " · group" if tier != own_tier[r_["pax_id"]] else ""
                    table.append({"#": i, "tier": TIER_BADGE[tier] + inherited, "passenger": r_["name"], "SSR": r_["ssr"],
                                  "missed": r_["original_onward_flight"].split("-")[0], "new flight": r_["flight_no"],
                                  "dep": hm(r_["std"]), "seat": r_["seat_no"] or "lap infant",
                                  "carrier": "home" if r_["operated_by_home"] else "partner"})
                first_non_vul = next((t["#"] for t in table if t["tier"].startswith(("🟦", "⬜"))), None)
                ok = all(t["tier"].startswith(("🟥", "🟧")) for t in table[: (first_non_vul or 1) - 1]) and                 all(t["tier"].startswith(("🟦", "⬜")) for t in table[(first_non_vul or len(table) + 1) - 1:])
                st.success(f"Committed in priority order: the first {first_non_vul - 1 if first_non_vul else len(table)} "
                           f"seats went to P1/P2 passengers. UMNR stayed on home-carrier flights before 22:00, the MEDA "
                           f"passenger stayed on the MEDIF carrier, PRM got +20 min MCT. Pre-transaction priority-inversion "
                           f"check: PASS." if ok else "Priority order check failed")
                st.dataframe(pd.DataFrame(table), hide_index=True, height=300)
            else:
                st.info("No AeroTurn rebookings yet. Run step ①.")
            st.button("Compare: unconstrained revenue-first optimiser vs guards", on_click=cb_lab_naive)
            if "lab_naive" in ss["results"]:
                ln = ss["results"]["lab_naive"]
                verdict_card(ln["naive_result"], "Unconstrained revenue-first plan (sandbox)")
                st.caption(f"Same guard, AeroTurn plan: **{ln['aeroturn_result']['status']}**")

        with st.container(border=True):
            st.markdown("<span class='stepno'>⑤ The human Operations Controller approves the gate reassignment "
                        "(and the connection hold)</span>", unsafe_allow_html=True)
            if risk_now["at_risk"] and ss.get("agent_result"):
                st.button(f"Rebook the {risk_now['at_risk']} passenger(s) still at risk (e.g. after a rejected hold)",
                          on_click=cb_rebook_remaining, type="primary")
            pend = [p for p in hitl.pending(C)]
            if not pend:
                st.info("Nothing awaiting approval. Run step ① first.")
            for ch in sorted(pend, key=lambda x: x["change_type"] != "GATE_REASSIGNMENT"):
                d = {k_: v for k_, v in ch["payload"].items() if not k_.startswith("_")}
                drv = ch["guard_report"].get("derived", {})
                with st.container(border=True):
                    cc = st.columns([3, 1, 1])
                    cc[0].markdown(f"**{ch['change_type']}** · {ch['flight_no']} · `{json.dumps(d)}`  \n"
                                   f"<span class='small'>Agent: {html.escape(ch['justification'][:220])}</span>  \n"
                                   f"<span class='small'>Guard re-check at approval · "
                                   f"{'valid until ' + hm(ch['valid_until']) if ch['valid_until'] else 'no expiry'}"
                                   f"{' · crew margin ' + str(drv.get('crew_margin_min')) + ' min' if 'crew_margin_min' in drv else ''}"
                                   f"</span>", unsafe_allow_html=True)
                    cc[1].button("✅ Approve", key=f"g_ap_{ch['change_id']}", on_click=cb_approve, args=(ch["change_id"],),
                                 type="primary", width="stretch")
                    cc[2].button("✖ Reject", key=f"g_rj_{ch['change_id']}", on_click=cb_reject, args=(ch["change_id"],),
                                 width="stretch")
            for key_, val in ss["results"].items():
                if key_.startswith("approval_") and val.get("status") != "APPROVED":
                    verdict_card(val, key_.replace("approval_", ""))

        with st.container(border=True):
            st.markdown("<span class='stepno'>⑥ Bonus: engineer CRS, then guarded departure release</span>",
                        unsafe_allow_html=True)
            cc = st.columns(4)
            cc[0].button(f"⏩ Clock to {mxi_end} (inspection done)", on_click=cb_advance, args=(mxi_end,), width="stretch")
            cc[1].button("B2 avionics engineer signs CRS", on_click=cb_sign, args=("E-02",), width="stretch")
            cc[2].button("B1 engineer signs CRS", on_click=cb_sign, args=("E-01",), width="stretch")
            cc[3].button("Propose EK813 departure release", on_click=cb_propose_release, type="primary", width="stretch")
            if "crs" in ss["results"]:
                verdict_card(ss["results"]["crs"], "CRS MX-0412")
            if "release" in ss["results"]:
                verdict_card(ss["results"]["release"], "EK813 departure release")

# ===========================================================================
# 2. SITUATION
# ===========================================================================
with tabs[1]:
    if tabs[1].open:
        a, b = st.columns(2)
        with a:
            st.subheader("Inbound EK812 LCA → DXB")
            ib = state["inbound"]
            st.markdown(f"**{ib['aircraft']}** · STA {ib['sta']} · landing {ib['eta_landing']} · in-block **{ib['eibt']}** "
                        f"(+{ib['delay_min']}) · {ib['passengers']} pax, {ib['connecting']} connecting  \n"
                        f"Assigned stand **{ib['assigned_gate']}** "
                        f"{'⚠️ ' + ', '.join(ib['gate_conflict']) if ib['gate_conflict'] else ''}")
            cr = state["inbound_crew"]
            st.markdown(f"Inbound crew: {cr['members']} members, report {cr['report']}, {cr['sectors']} sectors → "
                        f"**FDP limit {cr['fdp_limit']}**, margin at in-block **{cr['margin_at_eibt_min']} min**")
        with b:
            st.subheader("Outbound rotation EK813 DXB → CDG")
            ob = state["outbound_rotation"]
            st.markdown(f"STD {ob['std']} · critical-path EOBT **{ob['critical_path_eobt']}** (+{ob['projected_delay_min']}) "
                        f"· critical path `{' → '.join(ob['critical_path'])}`  \n"
                        + "  \n".join("⚠️ " + x for x in ob["crew_issues"]))
            st.markdown("  \n".join(f"{'⛔' if m['dispatch_blocking'] and m['status'] != 'CLOSED' else '🟢'} "
                                    f"**{m['item']}** ATA {m['ata']} {m['title']}: {m['status']} · {m['requirement']} · "
                                    f"CRS {m['crs']}" for m in state["maintenance"]))

        st.subheader("Arrival stand options for EK812")
        go_ = tools.evaluate_gate_options(C)
        gcols = st.columns([3, 2])
        with gcols[0]:
            st.dataframe(pd.DataFrame([{"stand": o["gate"], "type": o["kind"], "in-block": o["eibt"],
                                        "hold for stand": f"{o['hold_for_stand_min']} min",
                                        "crew FDP margin": f"{o['crew_fdp_margin_min']} min", "misconnects": o["misconnects"],
                                        "vulnerable misconnects": o["vulnerable_misconnects"],
                                        "guard": "✅ PASS" if o["legal"] else "⛔ " + ", ".join(sorted({v['rule'] for v in o['violations']}))}
                                       for o in go_["options"]]), hide_index=True)
            st.caption(f"Recommended: **{go_['recommended']}**, decide by **{go_['decision_deadline']}**. Needs controller approval.")
        with gcols[1]:
            fig = go.Figure(go.Bar(x=[o["gate"] for o in go_["options"]], y=[o["crew_fdp_margin_min"] for o in go_["options"]],
                                   marker_color=["#34d399" if o["legal"] else "#f87171" for o in go_["options"]],
                                   text=[f"{o['crew_fdp_margin_min']} min" for o in go_["options"]], textposition="outside"))
            fig.add_hline(y=0, line_color="#f87171", line_dash="dash")
            fig.update_layout(title="Inbound crew FDP margin at in-block", height=260, margin=dict(l=10, r=10, t=40, b=10),
                              yaxis_title="minutes", template="plotly_dark")
            st.plotly_chart(fig)

        st.subheader("Connections of EK812 passengers")
        only = st.toggle("Only connections at risk now", value=False)
        view = risk_now["passengers"] if not only else [p for p in risk_now["passengers"] if p["at_risk"]]
        base_risk = {p["pax_id"]: p for p in recovery.connection_risk(C, use_original=True)["passengers"]}
        st.dataframe(pd.DataFrame([{"tier": TIER_BADGE[p["tier"]], "pax": p["pax_id"], "name": p["name"], "SSR": p["ssr"],
                                    "cabin": p["cabin"], "dest": p["dest"],
                                    "original": base_risk[p["pax_id"]]["onward_flight"],
                                    "now on": p["onward_flight"], "dep": p["onward_std"], "MCT": p["mct_min"],
                                    "slack": p["slack_min"], "status": "⚠️ AT RISK" if p["at_risk"] else (
                                        "⏸ hold pending" if p["hold_pending"] else
                                        "🔁 rebooked" if p["pax_id"] in rebooked else "OK"), "bags": p["bags"]}
                                   for p in view]), hide_index=True, height=360)

# ===========================================================================
# 3. AGENT
# ===========================================================================
with tabs[2]:
    if tabs[2].open:
        st.subheader("Who does what")
        st.dataframe(pd.DataFrame([
            {"Responsibility": "Analyse the cascade, choose next action, explain trade-offs", "LLM agent": "✅", "Python code": "provides facts"},
            {"Responsibility": "Read state, compute options, CPM, crew legality, costs", "LLM agent": "-", "Python code": "✅ tools"},
            {"Responsibility": "Crew FDP / rest / ratings, MX CRS, vulnerable priority, MCT, PPBM", "LLM agent": "cannot touch", "Python code": "✅ sealed guards.py"},
            {"Responsibility": "Seat + bag rebooking (BEGIN / COMMIT / ROLLBACK)", "LLM agent": "requests it", "Python code": "✅ atomic transaction"},
            {"Responsibility": "Gate, retime, crew swap, departure release", "LLM agent": "stages it", "Python code": "✅ guard check · 👤 human approves"},
            {"Responsibility": "Notification wording, executive brief", "LLM agent": "✅ writes words", "Python code": "✅ injects facts, grounding check"},
        ]), hide_index=True)
        cc = st.columns([1, 1, 2])
        inj2 = cc[0].toggle("Inject seat conflict", value=True, key="inj2")
        run2 = cc[1].button("▶ Run agent", type="primary", key="run2")
        holder2 = st.container()
        if run2:
            run_agent(holder2, inj2)
            st.rerun()
        res = ss.get("agent_result")
        if res:
            if res.get("brief"):
                with st.container(border=True):
                    st.markdown(res["brief"]["markdown"])
                    g = res["brief"]["grounding"]
                    st.caption(f"Source: {res['brief']['source']} · numeric grounding: "
                               f"{'✅ all ' + str(g['numbers_checked']) + ' numbers traced to facts' if g['grounded'] else '⚠️ ungrounded: ' + ', '.join(g['ungrounded'])}")
            st.subheader(f"Full trace · brain: {res.get('brain')}")
            render_trace(res["trace"])
        else:
            st.info("Run the agent to see the reasoning, tool calls, guard verdicts and transactions as colour-coded lanes.")

# ===========================================================================
# 4. GUARDS LAB
# ===========================================================================
with tabs[3]:
    if tabs[3].open:
        st.subheader("Departure proposal builder (EK813)")
        crew_sets = {
            "Inbound crew of EK812 (already on board)": [r["crew_id"] for r in db.rows(
                C, "SELECT crew_id FROM crew_assignments WHERE flight_id = ?", (config.INBOUND_FLIGHT_ID,))],
            "Rostered crew B incl. unfit captain": [r["crew_id"] for r in db.rows(
                C, "SELECT crew_id FROM crew_assignments WHERE flight_id = ?", (config.OUTBOUND_FLIGHT_ID,))],
            "Rostered crew B (fit) + standby S-04": sorted({r["crew_id"] for r in db.rows(
                C, "SELECT crew_id FROM crew_assignments WHERE flight_id = ? AND status IN ('ROSTERED','ASSIGNED')",
                (config.OUTBOUND_FLIGHT_ID,))} | {"S-04"}),
            "Crew B (fit) + standby S-01 (Becker)": sorted({r["crew_id"] for r in db.rows(
                C, "SELECT crew_id FROM crew_assignments WHERE flight_id = ? AND status IN ('ROSTERED','ASSIGNED')",
                (config.OUTBOUND_FLIGHT_ID,))} - {"S-04"} | {"S-01"}),
        }
        cc = st.columns([2, 1, 1])
        which = cc[0].selectbox("Crew", list(crew_sets))
        off = cc[1].text_input("Off-blocks (HH:MM)", value=state["outbound_rotation"]["critical_path_eobt"])
        if cc[2].button("Validate & propose", type="primary", width="stretch"):
            ss["results"]["builder"] = tools.dispatch(C, "propose_departure", {"flight_no": "EK813", "off_blocks": off,
                                                                             "crew_ids": crew_sets[which]}, actor="OCC_UI")
        if "builder" in ss["results"]:
            verdict_card(ss["results"]["builder"], f"EK813 off-blocks {off}")
            fx = (ss["results"]["builder"].get("guard") or {}).get("facts", {}).get("crew", {})
            if fx:
                with st.expander("Per-crew FDP computation"):
                    st.dataframe(pd.DataFrame([{"crew": k_, **v} for k_, v in fx.items()]), hide_index=True)

        st.subheader("Standby crew pairing matcher (EK813 captain)")
        sc = crew.find_standby_crew(C, flight_id=config.OUTBOUND_FLIGHT_ID, rank="CPT")
        st.caption(sc["summary"])
        st.dataframe(pd.DataFrame([{"crew": c_["crew_id"], "name": c_["name"], "status": c_["status"], "rating": c_["type_ratings"],
                                    "location": c_["location"], "away": f"{c_['proximity_min']} min",
                                    "can report": c_["can_report"], "FDP limit": c_["fdp_limit"], "margin": c_["margin"],
                                    "verdict": "✅ legal" if c_["legal"] else "⛔ " + ", ".join(v["rule"] + " " + v["message"][:60]
                                                                                           for v in c_["violations"])}
                                   for c_ in sc["candidates"]]), hide_index=True)

        a, b = st.columns(2)
        with a:
            st.subheader("Try to weaken the guards at runtime")
            if st.button("Run immutability probe"):
                ss["results"]["probe"] = lab.immutability_probe()
            if "probe" in ss["results"]:
                st.dataframe(pd.DataFrame(ss["results"]["probe"]), hide_index=True)
            st.caption(f"guards.py SHA-256 pinned: `{guards.verify_guard_integrity()['actual']}`")
        with b:
            st.subheader("Prompt injection in passenger data")
            inj = db.one(C, "SELECT pax_id, first_name || ' ' || last_name AS name, remarks FROM passengers "
                            "WHERE remarks LIKE '%AI AGENT%'")
            if inj:
                st.code(inj["remarks"], language=None)
                st.caption(f"{inj['name']} ({inj['pax_id']}). Remarks reach the LLM as data. Even if a model obeyed, "
                           f"no tool accepts an override, departure needs CRS + legal crew, and cabin upgrades are a "
                           f"tier-1 protection only.")
        with st.expander("Rule catalogue (immutable)"):
            st.dataframe(pd.DataFrame([{"rule": k_, "meaning": v} for k_, v in guards.RULES.items()]), hide_index=True)
            st.json({f: str(getattr(guards.LIMITS, f)) for f in guards.LIMITS.__dataclass_fields__}, expanded=False)

# ===========================================================================
# 5. ATOMIC
# ===========================================================================
with tabs[4]:
    if tabs[4].open:
        st.subheader("Rollback experiment (fresh sandbox copy of the scenario)")
        cc = st.columns([1, 1, 1])
        cc[0].selectbox("Fault", list(faults.KINDS), key="lab_kind")
        cc[1].number_input("Fail at step", 1, 45, 7, key="lab_step")
        cc[2].button("Run experiment", on_click=cb_lab_rollback, type="primary", width="stretch")
        lr = ss["results"].get("lab_rollback")
        if lr:
            f1 = lr["first"]
            verdict_card({"status": f1["status"], "message": f1.get("message"), "error": f1.get("error")},
                         f"Batch of {len(f1['steps']) - 1} provisional + 1 failing step")
            st.markdown(f"**Fault:** {(f1.get('fault_injected') or {}).get('story', '-')}")
            probe = [{"passenger": p["name"], "planned": lr["planned"][p["pax_id"]],
                      "before batch": lr["before"]["leg2"][p["pax_id"]], "after ROLLBACK": lr["after"]["leg2"][p["pax_id"]],
                      "bags after rollback": ", ".join(lr["after"]["bags"][p["pax_id"]]) or "-",
                      "after retry COMMIT": lr["final"]["leg2"][p["pax_id"]]} for p in lr["probe"]]
            st.dataframe(pd.DataFrame(probe), hide_index=True)
            m = st.columns(3)
            m[0].metric("State fingerprint before", lr["before"]["fingerprint"])
            m[1].metric("After rollback", lr["after"]["fingerprint"],
                        "identical" if lr["before"]["fingerprint"] == lr["after"]["fingerprint"] else "DIFFERENT",
                        delta_color="off")
            m[2].metric("Retry", lr["retry"]["status"], f"{lr['final']['at_risk_remaining']} still at risk", delta_color="off")
            st.markdown("**Invariants after rollback** (all must be 0)")
            st.dataframe(pd.DataFrame([lr["after"]["invariants"]]), hide_index=True)
        st.subheader("Live database invariants")
        inv = db.check_invariants(C)
        st.dataframe(pd.DataFrame([{k_: v["count"] for k_, v in inv.items() if isinstance(v, dict)}]), hide_index=True)
        st.caption("Protection layers: guard pre-validation → UNIQUE(flight, seat) / UNIQUE(pax, leg) / triggers → "
                   "in-transaction invariant scan → DEFERRABLE foreign key (bag ↔ booking) at COMMIT.")
        st.subheader("Transaction log")
        st.dataframe(pd.DataFrame(db.rows(C, "SELECT * FROM txn_log ORDER BY started_at DESC")), hide_index=True)

# ===========================================================================
# 6. CONTROLLER
# ===========================================================================
with tabs[5]:
    if tabs[5].open:
        st.subheader("Awaiting your decision")
        pend = hitl.pending(C)
        if not pend:
            st.info("Queue empty.")
        for ch in pend:
            with st.container(border=True):
                d = {k_: v for k_, v in ch["payload"].items() if not k_.startswith("_")}
                st.markdown(f"**{ch['change_type']}** · {ch['flight_no']} · `{json.dumps(d)}` · staged by "
                            f"`{ch['staged_by']}` at {hm(ch['staged_at'])}"
                            f"{' · valid until **' + hm(ch['valid_until']) + '**' if ch['valid_until'] else ''}")
                st.markdown(f"> {ch['justification']}")
                gr = ch["guard_report"]
                st.caption("Guard checks at staging: " + " · ".join(gr.get("checks", [])))
                cc = st.columns([3, 1, 1])
                cc[0].text_input("Decision note", key=f"note_{ch['change_id']}", label_visibility="collapsed",
                                 placeholder="Decision note (optional)")
                cc[1].button("✅ Approve", key=f"ap_{ch['change_id']}", on_click=cb_approve, args=(ch["change_id"],),
                             type="primary", width="stretch")
                cc[2].button("✖ Reject", key=f"rj_{ch['change_id']}", on_click=cb_reject, args=(ch["change_id"],),
                             width="stretch")
        st.subheader("Decision history")
        hist = hitl.history(C)
        st.dataframe(pd.DataFrame([{"change": h["change_id"], "type": h["change_type"], "flight": h["flight_no"],
                                    "details": json.dumps({k_: v for k_, v in h["payload"].items() if not k_.startswith("_")}),
                                    "status": h["status"], "guard": ", ".join(h["guard_report"].get("rules_violated", [])) or "PASS",
                                    "staged by": h["staged_by"], "decided by": h["decided_by"] or "-"} for h in hist]),
                     hide_index=True)

# ===========================================================================
# 7. TURNAROUND & MX
# ===========================================================================
with tabs[6]:
    if tabs[6].open:
        cpm = turnaround.critical_path(C, config.OUTBOUND_FLIGHT_ID)
        m = st.columns(4)
        m[0].metric("EK812 in-block", cpm["eibt_hm"])
        m[1].metric("EK813 STD", cpm["std_hm"])
        m[2].metric("Critical-path EOBT", cpm["eobt_hm"], f"+{cpm['delay_vs_std_min']} min", delta_color="inverse")
        m[3].metric("Turn time", dur(cpm["turn_min"]))
        df = pd.DataFrame([{"Task": t["name"], "Start": parse(t["start"]), "Finish": parse(t["end"]),
                            "Path": "Critical path" if t["critical"] else "Has slack", "Slack": f"{t['slack_min']} min",
                            "Resource": t["resource"]} for t in cpm["tasks"] if t["duration_min"] > 0]).sort_values("Start")
        fig = px.timeline(df, x_start="Start", x_end="Finish", y="Task", color="Path", hover_data=["Resource", "Slack"],
                          color_discrete_map={"Critical path": "#f87171", "Has slack": "#60a5fa"})
        fig.update_yaxes(autorange="reversed")
        for x, label, color in ((parse(out_f["std"]), "STD", "#fbbf24"), (parse(cpm["eobt"]), "EOBT", "#f87171")):
            fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper", line=dict(color=color, dash="dash"))
            fig.add_annotation(x=x, y=1.04, yref="paper", text=f"{label} {hm(x)}", showarrow=False, font=dict(color=color))
        fig.update_layout(height=420, template="plotly_dark", margin=dict(l=10, r=10, t=30, b=10), legend_title=None)
        st.plotly_chart(fig)
        st.dataframe(pd.DataFrame([{"task": t["task_id"], "name": t["name"], "start": t["start_hm"], "end": t["end_hm"],
                                    "min": t["duration_min"], "slack": t["slack_min"], "critical": "🔴" if t["critical"] else "",
                                    "depends on": ", ".join(t["depends_on"]), "note": t["note"]} for t in cpm["tasks"]]),
                     hide_index=True)
        st.subheader("Maintenance sign-off (licensed engineer)")
        engs = db.rows(C, "SELECT * FROM engineers")
        cc = st.columns([2, 2, 1])
        eng = cc[0].selectbox("Engineer", [e["eng_id"] for e in engs],
                              format_func=lambda x: next(f"{e['name']} ({e['licence']}, {e['type_auth']})" for e in engs if e["eng_id"] == x))
        cc[1].text_input("Remarks", key="crs_remarks", placeholder="Inspection and leak check satisfactory")
        cc[2].button("Sign CRS", on_click=cb_sign, args=(eng,), type="primary", width="stretch")
        if "crs" in ss["results"]:
            verdict_card(ss["results"]["crs"], "CRS MX-0412")
        st.dataframe(pd.DataFrame(db.rows(C, "SELECT item_id, ata, title, category, status, blocks_dispatch, mel_ref, "
                                             "est_task_min, crs_eng_id, crs_signed_at FROM maintenance_items")), hide_index=True)

# ===========================================================================
# 8. COST
# ===========================================================================
with tabs[7]:
    if tabs[7].open:
        cst = costs.disruption_cost(C)
        leg, aer = cst["legacy_auto_reprotect"], cst["aeroturn"]
        m = st.columns(4)
        m[0].metric("Legacy auto-reprotect", f"€{leg['total']:,}")
        m[1].metric("AeroTurn", f"€{aer['total']:,}", f"-€{cst['savings']:,}" if rebooked else "run the agent",
                    delta_color="inverse")
        m[2].metric("Same-day arrivals", f"{aer['same_day']}/{cst['scope_passengers']}", f"legacy {leg['same_day']}",
                    delta_color="off")
        m[3].metric("Arrive < 3h late (no EU261)", aer["under_3h"])
        fig = go.Figure()
        for comp, color in (("eu261", "#f87171"), ("hotel", "#fbbf24"), ("meals", "#60a5fa")):
            fig.add_bar(name=comp.upper() if comp == "eu261" else comp.title(), x=["Legacy +24h", "AeroTurn"],
                        y=[leg[comp], aer[comp]], marker_color=color)
        fig.update_layout(barmode="stack", height=320, template="plotly_dark", margin=dict(l=10, r=10, t=30, b=10),
                          title="Passenger compensation & care (EUR)")
        a, b = st.columns([3, 2])
        a.plotly_chart(fig)
        ob = cst["outbound_rotation"]
        b.markdown(f"**Outbound rotation {ob['flight']}**: delay {ob['delay_min']} min × (€{cst['assumptions']['delay_cost_eur_per_min']} "
                   f"aircraft + €0.40 × {ob['pax']} pax) per min = **€{ob['delay_cost']:,}**. {ob['eu261_note']}.  \n"
                   f"Knock-on to the return sector: {ob['knock_on_return_delay_min']} min (€{ob['knock_on_cost']:,}) after "
                   f"{cst['assumptions']['rotation_buffer_min']} min CDG buffer.  \n\n"
                   f"Connection holds: {', '.join(cst['connection_holds']['flights']) or 'none approved'} "
                   f"(€{cst['connection_holds']['cost']:,}).  \n\n"
                   f"**Network total**: AeroTurn €{cst['network_total_aeroturn']:,} vs legacy €{cst['network_total_legacy']:,}.")
        st.subheader("Hold a departing connection, or rebook its passengers?")
        st.dataframe(pd.DataFrame([{"flight": h["flight"], "dest": h["dest"], "STD": h["std"], "pax protected": h["pax_protected"],
                                    "hold needed": f"{h['hold_needed_min']} min",
                                    "safety cap ≤30": "✅" if h["allowed"] else "⛔ NET-001",
                                    "hold cost": f"€{h['hold_cost']:,}", "rebook cost": f"€{h['rebook_cost']:,}",
                                    "net saving": f"€{h['net_saving']:,}",
                                    "verdict": "✅ HOLD" if h["recommended"] else "rebook", "status": h["hold_status"],
                                    "pax on board delayed": h["onboard_pax_delayed"]}
                                   for h in costs.hold_analysis(C)]), hide_index=True)
        st.caption("Hold cost = minutes × (€100 aircraft + €0.40 × passengers on board). Recommended only if ≤ 15 min "
                   "and cheaper than rebooking. A hold is a network change: the controller decides.")
        st.subheader("Per passenger")
        st.dataframe(pd.DataFrame(cst["per_passenger"]), hide_index=True, height=320)
        st.caption("EU261: EK812 departed Larnaca (EU), so whole-journey compensation applies on final-arrival delay ≥3h "
                   "(Wegener C-537/17). Rates are illustrative assumptions in aeroturn/config.py, not legal advice.")

# ===========================================================================
# 9. NOTIFICATIONS
# ===========================================================================
with tabs[8]:
    if tabs[8].open:
        notes = db.rows(C, """SELECT n.category, n.pax_id, p.first_name || ' ' || p.last_name AS name, n.message,
                              n.template_source FROM notifications n JOIN passengers p ON p.pax_id = n.pax_id
                              ORDER BY CASE n.category WHEN 'UMNR_GUARDIAN' THEN 0 WHEN 'MEDICAL' THEN 1 WHEN 'PRM' THEN 2
                              WHEN 'FAMILY' THEN 3 WHEN 'PREMIUM' THEN 4 ELSE 5 END, n.pax_id""")
        st.caption("The LLM writes the wording as templates. Code rejects any template containing a flight number, "
                   "time, seat or gate, then fills those facts in from the database.")
        if notes:
            st.dataframe(pd.DataFrame(notes), hide_index=True, height=460)
        else:
            st.info("No notifications yet.")
        st.subheader("Template validator")
        t = st.text_area("Try a template", value="Dear {first_name}, you are now on EK372 at 18:25, seat 24K.")
        probs = tools.validate_template(t)
        (st.error if probs else st.success)("; ".join(probs) if probs else "Template accepted")

# ===========================================================================
# 10. AUDIT
# ===========================================================================
with tabs[9]:
    if tabs[9].open:
        ch_ = audit.verify_chain(C)
        st.markdown(f"Hash chain: {'✅ **intact**' if ch_['ok'] else '❌ **broken at ' + str(ch_.get('broken_at_seq')) + '**'} "
                    f"· {ch_['entries']} entries · head `{ch_.get('head', '')[:20]}`")
        if st.button("Tamper test: edit one historic entry in a copy"):
            ss["results"]["tamper"] = lab.tamper_demo(SESSION_DB)
        if "tamper" in ss["results"]:
            t_ = ss["results"]["tamper"]
            if "after" in t_:
                st.error(f"Edited seq {t_['edited_seq']} ('{t_['edited_action']}' → 'GATE PASS'): chain verification now "
                         f"fails at seq {t_['after'].get('broken_at_seq')}. Tampering is detectable.")
            else:
                st.info(t_.get("note"))
        st.dataframe(pd.DataFrame(audit.recent(C, 400)), hide_index=True, height=520)
