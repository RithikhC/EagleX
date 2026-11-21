"""📈 Dashboard: real performance of a real hub, and the KPI framework a pilot uses to compare it with AeroTurn."""
from __future__ import annotations

import json

import plotly.graph_objects as go
import streamlit as st

from aeroturn import config, realdata as R
from views import ui

ui.setup()
M = R.month_summary()
REC = R.recovery_days()
MEAS = json.loads((config.ROOT / "docs" / "round3" / "measurements.json").read_text(encoding="utf-8"))

ui.header("Disruption performance dashboard",
          f"Atlanta (ATL) · July 2024 · {M['departures']:,} departures, {M['airlines']} airlines · "
          "US DOT BTS on-time records",
          [("real", "Real data"), ("", "Source: BTS · OurAirports")])

c1, c2 = st.columns([1.2, 3], vertical_alignment="bottom")
stratum = c1.selectbox("Compare like with like", ["All days", "Normal", "Elevated", "Major disruption"],
                       help="Strata by the share of departures cancelled that day: Normal < 2%, Elevated 2–10%, "
                            "Major disruption ≥ 10%. Never compare an outage day with a normal day.")
c2.markdown("<div class='sub2'>The comparison is stratified, as a pilot must be: outage days (CrowdStrike, "
            "19–23 July) are kept apart from normal days.</div>", unsafe_allow_html=True)
S = None if stratum == "All days" else stratum

d = R.daily()
dd = d if S is None else d[d.stratum == S]
causes = R.cause_minutes(S)
tr = R.turn_recovery(S)
rot = R.rotations()
rot_s = rot[rot.date.isin(dd.date)]

k = st.columns(6, gap="small")
ui.kpi(k[0], "Departures", f"{int(dd.flights.sum()):,}", f"{len(dd)} days")
ui.kpi(k[1], "On-time departures", f"{100 - dd.delayed.sum() / dd.operated.sum() * 100:.1f}%",
       "left < 15 min late (BTS definition)")
ui.kpi(k[2], "Cancelled", f"{int(dd.cancelled.sum()):,}", f"{dd.cancelled.sum() / dd.flights.sum() * 100:.1f}% of departures")
ui.kpi(k[3], "Delay minutes", f"{causes.sum() / 1000:,.0f}k", "arrivals at ATL 15+ min late")
ui.kpi(k[4], "Late-aircraft share", f"{causes['Late-arriving aircraft'] / causes.sum() * 100:.1f}%",
       "of delay minutes: the turnaround chain")
ui.kpi(k[5], "Late turns recovered", f"{tr['rate']:.0f}%", f"{tr['recovered']:,} of {tr['late_inbound_turns']:,} late inbounds")
st.write("")

g1, g2 = st.columns([1.7, 1], gap="medium")
with g1.container(border=True):
    ui.section("Every day of July at ATL", "Departures that left on time, late, or not at all. The shaded band is the "
                                           "CrowdStrike outage and recovery.")
    fig = go.Figure()
    ontime = d.operated - d.delayed
    for name, y, color in (("On time", ontime, ui.BLUE), ("Delayed ≥ 15 min", d.delayed, ui.AMBER),
                           ("Cancelled", d.cancelled, ui.RED)):
        fig.add_bar(x=d.date, y=y, name=name, marker_color=color, marker_line_width=0,
                    hovertemplate="%{x|%d %b}: %{y:,} " + name.lower() + "<extra></extra>")
    fig.add_vrect(x0="2024-07-18 12:00", x1="2024-07-23 12:00", fillcolor="#fee2e2", opacity=0.6, line_width=0,
                  layer="below",
                  annotation_text="IT outage + recovery", annotation_position="top left",
                  annotation_font=dict(color=ui.RED, size=11))
    fig.update_layout(barmode="stack", bargap=0.15)
    st.plotly_chart(ui.layout(fig, 300), width="stretch", config={"displayModeBar": False})
with g2.container(border=True):
    ui.section("Where the delay minutes come from", f"{stratum.lower()} · reported by airlines to BTS")
    cs = causes.sort_values()
    fig = go.Figure(go.Bar(x=cs.values, y=cs.index, orientation="h",
                           marker_color=[ui.CAUSE_COLORS.get(i, ui.SLATE) for i in cs.index],
                           text=[f"{v / cs.sum() * 100:.0f}%" for v in cs.values], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x:,.0f} min<extra></extra>"))
    fig.update_xaxes(title=None, showgrid=False, showticklabels=False, range=[0, cs.max() * 1.18])
    st.plotly_chart(ui.layout(fig, 300, legend=False), width="stretch", config={"displayModeBar": False})

g3, g4 = st.columns([1.7, 1], gap="medium")
with g3.container(border=True):
    ui.section("Knock-on turns per day",
               "A late inbound ate the planned turn and the next departure of the same aircraft also left late: each "
               "one is a decision AeroTurn would raise and plan for.")
    colors = d.stratum.map({"Normal": ui.BLUE_L, "Elevated": ui.AMBER, "Major disruption": ui.RED})
    fig = go.Figure(go.Bar(x=d.date, y=d.knock_ons, marker_color=colors, marker_line_width=0,
                           hovertemplate="%{x|%d %b}: %{y} knock-on turns<extra></extra>"))
    st.plotly_chart(ui.layout(fig, 250, legend=False), width="stretch", config={"displayModeBar": False})
with g4.container(border=True):
    ui.section("Stratified baseline", "Same measures, by kind of day")
    st_ = R.strata_table()
    ui.table(["Stratum", "Days", "On-time", "Cancelled", "Knock-ons / day"],
             [[f"<b>{r.Stratum}</b>", r.Days, f"{r['On-time %']:.0f}%", f"{r['Cancelled %']:.1f}%",
               f"{r['Knock-on turns / day']:.0f}"] for _, r in st_.iterrows()])
    if REC:
        ui.source(f"After the 19 July outage, ATL needed <b>{REC['days']} days</b> to get back under 2% cancellations "
                  f"({REC['cancelled']:,} departures cancelled). Delta reported ~7,000 cancellations over five days "
                  f"network-wide (<a href='https://www.sec.gov/Archives/edgar/data/27904/000168316824005369/delta_8k.htm'>"
                  f"8-K, Aug 2024</a>).")

# ---------------------------------------------------------------------------
# KPI framework: baseline (X) vs AeroTurn (Y)
# ---------------------------------------------------------------------------
st.write("")
with st.container(border=True):
    ui.section("KPI framework · current workflow (X) vs AeroTurn (Y)",
               f"{ui.pill('real', 'Real data')} measured from BTS records &nbsp; {ui.pill('sim', 'Simulation')} "
               f"measured on AeroTurn's sample scenario and test suite &nbsp; {ui.pill('pilot', 'Pilot')} needs the "
               f"airline's own data, measured in shadow mode")
    rmed = MEAS["recovery"]["seconds_total"]
    ops = [
        ["Time to recovery plan", "Minutes from disruption alert to a validated plan",
         f"{ui.pill('real', 'Real')} hub back to normal <b>{REC.get('days', '?')} days</b> after the 19 Jul outage",
         f"{ui.pill('sim', 'Sim')} <b>{rmed['min']:.0f}–{rmed['max']:.0f} s</b> per plan ({MEAS['recovery']['runs']} runs)",
         "Alert timestamp → plan staged (audit log)"],
        ["Same-day recovery rate", "Same-day arrivals ÷ disrupted passengers", f"{ui.pill('pilot', 'Pilot')} passenger itineraries are not public",
         f"{ui.pill('sim', 'Sim')} <b>45 / 45</b>", "Reservation system, matched disruptions"],
        ["Connection preservation", "Connections preserved ÷ connections at risk",
         f"{ui.pill('real', 'Real proxy')} late turns recovered: <b>{tr['rate']:.0f}%</b> of {tr['late_inbound_turns']:,}",
         f"{ui.pill('sim', 'Sim')} <b>45 / 45</b> broken connections re-protected", "PNR-level in the pilot"],
        ["Vulnerable protection rate", "Vulnerable recovered correctly ÷ affected vulnerable", f"{ui.pill('pilot', 'Pilot')} not public",
         f"{ui.pill('sim', 'Sim')} <b>10 / 10</b>", "SSR codes in the reservation system"],
        ["Bag integrity", "Bags with a valid routing or forwarding plan ÷ affected bags", f"{ui.pill('pilot', 'Pilot')} not public",
         f"{ui.pill('sim', 'Sim')} <b>48 / 48</b> (46 with owner, 2 forwarded)", "Baggage messages (BSM/BPM)"],
        ["Plan acceptance rate", "Controller-approved plans ÷ plans presented", f"{ui.pill('pilot', 'Pilot')} —",
         f"{ui.pill('pilot', 'Pilot')} —", "Approval log"],
        ["Manual workload", "Staff minutes per disruption", f"{ui.pill('pilot', 'Pilot')} time-and-motion study",
         f"{ui.pill('pilot', 'Pilot')} —", "Shadow-mode timing"],
        ["Rule violations", "Committed prohibited actions", f"{ui.pill('pilot', 'Pilot')} —",
         f"{ui.pill('sim', 'Sim')} <b>0</b> in 116 tests, 13 edge cases, 5 curveballs", "Guard log"],
        ["Rollback correctness", "Failed transactions with no partial state ÷ failed transactions", "—",
         f"{ui.pill('sim', 'Sim')} <b>100%</b> (state fingerprint identical)", "Transaction log"],
        ["Escalation rate", "Unresolved cases escalated ÷ affected cases", "—",
         f"{ui.pill('sim', 'Sim')} <b>4 / 13</b> edge cases escalated (no legal option)", "Escalation log"],
    ]
    ui.table(["Operational KPI", "Formula", "X · current (baseline)", "Y · AeroTurn", "How the pilot measures it"], ops)
    st.write("")
    cost_all = causes.sum() * config.A4A_COST_PER_MIN_USD
    cost_late = causes["Late-arriving aircraft"] * config.A4A_COST_PER_MIN_USD
    fin = [
        ["Aircraft delay cost", "Delay minutes × cost per minute",
         f"{ui.pill('real', 'Real × published')} <b>${cost_all / 1e6:,.1f}M</b> ({causes.sum():,.0f} min × "
         f"${config.A4A_COST_PER_MIN_USD})", "Measured in the pilot", "A4A 2025 cost per block minute"],
        ["…of which late-aircraft", "Late-aircraft minutes × cost per minute",
         f"{ui.pill('real', 'Real × published')} <b>${cost_late / 1e6:,.1f}M</b>", "The value AeroTurn targets",
         "Same cause codes, before vs after"],
        ["Net savings · savings %", "Baseline cost − AeroTurn cost · ÷ baseline", "—",
         f"{ui.pill('pilot', 'Pilot')} measured, not assumed", "Matched strata, X vs Y"],
        ["Passenger care cost", "Compensation + hotel + meal + transport", f"{ui.pill('pilot', 'Pilot')} airline finance data",
         f"{ui.pill('sim', 'Sim')} EU261 model: AED 133,390 → 50,440", "Claims and vouchers issued"],
    ]
    ui.table(["Financial KPI", "Formula", "X · current (baseline)", "Y · AeroTurn", "How it is measured"], fin)
    ui.source(f"Delay minutes are BTS cause minutes for flights arriving at ATL 15+ min late ({stratum.lower()}). "
              f"Cost per minute: <a href='{config.A4A_SOURCE}'>Airlines for America, US passenger carrier delay cost, "
              f"$98.41 per block minute (2025)</a>. Simulation values: docs/round3/NUMBERS_PROOF.md.")

with st.expander("Data sources and how to reproduce"):
    man = R.manifest()
    ui.table(["Source", "Publisher · licence", "Rows used", "SHA-256 (raw file)"],
             [[f"<a href='{s['url']}'>{s['name']}</a>", f"{s['publisher']} · {s['licence']}",
               f"{s.get('rows_processed') or '—':,}" if isinstance(s.get("rows_processed"), int) else "live",
               (s.get("raw_sha256") or "—")[:16]] for s in man["sources"]])
    ui.source("Re-create the processed files with <code>python scripts/fetch_real_data.py</code> "
              f"(fetched {man['fetched_at']}).")
