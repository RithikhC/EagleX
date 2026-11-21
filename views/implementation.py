"""🔌 Implementation: how AeroTurn plugs into a real airline, shown live on real data feeds."""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from aeroturn import config, realdata as R
from views import ui

ui.setup()
ss = st.session_state
ui.header("How AeroTurn goes live",
          "Connectors to real data, the alert rule running on real flights, the systems it plugs into, and the pilot",
          [("real", "Live + real data"), ("", "Rollout: shadow → advisor → supervised")])

OPENSKY = "https://opensky-network.org/api/states/all?lamin=24.7&lomin=54.9&lamax=25.6&lomax=55.8"


def fetch_opensky() -> dict:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(OPENSKY, headers={"User-Agent": "aeroturn-research/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        return {"mode": "live", "data": data, "ms": int((time.perf_counter() - t0) * 1000),
                "at": dt.datetime.utcfromtimestamp(data["time"]).strftime("%H:%M:%S UTC")}
    except Exception as exc:  # noqa: BLE001 - the connector degrades to the cached snapshot, never crashes
        data = json.loads((R.REAL / "opensky_dxb_snapshot.json").read_text(encoding="utf-8"))
        return {"mode": "cache", "data": data, "ms": int((time.perf_counter() - t0) * 1000),
                "at": dt.datetime.utcfromtimestamp(data["time"]).strftime("%d %b %H:%M UTC"),
                "error": f"{type(exc).__name__}: {str(exc)[:80]}"}


# ---------------------------------------------------------------------------
# 1. connectors
# ---------------------------------------------------------------------------
with st.container(border=True):
    ui.section("1 · Data connectors, running now",
               "Each source is read, checked in code and mapped to AeroTurn's schema. In a pilot the same "
               "connector slots take the airline's own feeds.")
    f = R.flights()
    man = {s["name"]: s for s in R.manifest()["sources"]}
    bts = man["BTS Reporting Carrier On-Time Performance, July 2024"]
    need = {"FlightDate", "Tail_Number", "CRSDepTime", "DepDelay", "ArrDelay", "LateAircraftDelay"}
    checks_bts = [("required columns present", need <= set(f.columns)),
                  ("dates inside July 2024", f.date.min() >= pd.Timestamp("2024-07-01") and
                   f.date.max() <= pd.Timestamp("2024-07-31")),
                  ("tail numbers on operated flights", f[f.Cancelled == 0].Tail_Number.notna().mean() > 0.99)]
    if ss.get("opensky") is None:
        ss["opensky"] = fetch_opensky()
    osk = ss["opensky"]
    states = osk["data"].get("states") or []
    c = st.columns(3, gap="small")
    with c[0]:
        st.markdown(f"<div class='card'><h4>Flight movements and delays {ui.pill('real', 'loaded')}</h4>"
                    f"<p>US DOT BTS on-time records · public domain</p><p><b>{len(f):,}</b> ATL flights from "
                    f"{bts['rows_all_us_flights']:,} US flights</p>"
                    + "".join(f"<p>{'✓' if ok else '✕'} {t}</p>" for t, ok in checks_bts)
                    + f"<div class='src'>SHA-256 {bts['raw_sha256'][:16]}… · "
                      f"<a href='{bts['url']}'>source</a></div></div>", unsafe_allow_html=True)
    with c[1]:
        ap = pd.read_csv(R.REAL / "airports.csv")
        st.markdown(f"<div class='card'><h4>Airports {ui.pill('real', 'loaded')}</h4><p>OurAirports · public "
                    f"domain</p><p><b>{len(ap)}</b> airports in ATL's network, with coordinates</p>"
                    f"<p>{'✓' if ap.latitude_deg.between(-90, 90).all() else '✕'} coordinates valid</p>"
                    f"<p>{'✓' if set(f.Dest) - set(ap.iata_code) <= {'XWA'} else '◆'} every destination resolved</p>"
                    f"<div class='src'><a href='{man['OurAirports airports.csv']['url']}'>source</a></div></div>",
                    unsafe_allow_html=True)
    with c[2]:
        mode = ui.pill("live", f"live · {osk['ms']} ms") if osk["mode"] == "live" else ui.pill("cache", "cached fallback")
        st.markdown(f"<div class='card'><h4>Live aircraft around Dubai {mode}</h4><p>OpenSky Network ADS-B · "
                    f"research licence</p><p><b>{len(states)}</b> aircraft in the DXB area at {osk['at']}</p>"
                    + (f"<p>✕ live call failed ({osk.get('error', '')}): cached snapshot shown, the page did not "
                       f"stop</p>" if osk["mode"] == "cache" else "<p>✓ 8 s timeout · fallback to cached snapshot</p>")
                    + "<div class='src'>Production: the airline's own ADS-B/ACARS feed or an OpenSky commercial "
                      "licence.</div></div>", unsafe_allow_html=True)
        if st.button("↻ Call OpenSky again", width="stretch"):
            ss["opensky"] = fetch_opensky()
            st.rerun()
    if states:
        df = pd.DataFrame(states).iloc[:, [1, 2, 5, 6, 7, 9]]
        df.columns = ["callsign", "country", "lon", "lat", "alt_m", "speed_ms"]
        df = df.dropna(subset=["lat", "lon"])
        fig = go.Figure(go.Scattergeo(lon=df.lon, lat=df.lat, text=df.callsign.str.strip(), mode="markers+text",
                                      textposition="top center", textfont=dict(size=9, color=ui.INK2),
                                      marker=dict(size=7, color=ui.BLUE)))
        fig.update_geos(lonaxis_range=[54.8, 55.9], lataxis_range=[24.6, 25.7], showland=True,
                        landcolor="#f1f5f9", showocean=True, oceancolor="#ffffff", showcountries=True,
                        countrycolor="#cbd5e1", showcoastlines=True, coastlinecolor="#94a3b8", resolution=50)
        st.plotly_chart(ui.layout(fig, 260, legend=False), width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# 2. the alert rule on real flights
# ---------------------------------------------------------------------------
with st.container(border=True):
    ui.section("2 · AeroTurn's trigger, replayed on real flights",
               "Rule (in code): a late inbound uses up the planned turn and the same aircraft's next departure is at "
               "risk → open a recovery case. Pick any day in July 2024 at ATL.")
    day = st.date_input("Day", value=dt.date(2024, 7, 19), min_value=dt.date(2024, 7, 1),
                        max_value=dt.date(2024, 7, 31), format="DD/MM/YYYY")
    rot = R.rotations()
    today = rot[rot.date == pd.Timestamp(day)]
    hit = today[today.knock_on]
    drow = R.daily()[R.daily().date == pd.Timestamp(day)].iloc[0]
    k = st.columns(4, gap="small")
    ui.kpi(k[0], "Aircraft turns at ATL", f"{len(today):,}", "inbound linked to next departure (tail number)")
    ui.kpi(k[1], "Recovery cases opened", f"{len(hit):,}", "late inbound ate the planned turn")
    ui.kpi(k[2], "Departures cancelled", f"{int(drow.cancelled):,}", f"{drow.cancel_pct:.1f}% · {drow.stratum.lower()} day")
    ui.kpi(k[3], "Late-aircraft delay", f"{drow.LateAircraftDelay:,.0f} min", "arrivals at ATL that day (BTS)")
    st.write("")
    a1, a2 = st.columns([1, 1.6], gap="medium")
    with a1:
        by_h = hit.sched_dep.dt.hour.value_counts().reindex(range(5, 24), fill_value=0)
        fig = go.Figure(go.Bar(x=[f"{h:02d}" for h in by_h.index], y=by_h.values, marker_color=ui.BLUE,
                               hovertemplate="%{x}:00 · %{y} cases<extra></extra>"))
        fig.update_xaxes(title="Scheduled departure hour")
        st.plotly_chart(ui.layout(fig, 250, legend=False), width="stretch", config={"displayModeBar": False})
    with a2:
        st.dataframe(R.alerts_for_day(str(day), 200), height=250, hide_index=True, width="stretch")
    ui.source("Each row is a real aircraft (tail number) and two real flights from the BTS records. In a pilot the "
              "same rule runs on the airline's live movement messages (MVT/ACARS), and each case goes to the agent "
              "with passengers, crew, maintenance and stands from the airline's systems.")

# ---------------------------------------------------------------------------
# 3. integration map
# ---------------------------------------------------------------------------
with st.container(border=True):
    ui.section("3 · What AeroTurn connects to at an airline",
               "Only the connector layer changes. The guards, transactions, approvals and audit trail stay the same.")
    rows = [
        ["Flight movements, delays", "Flight operations / movement messages (IATA MVT, ACARS); today: BTS + OpenSky",
         "alert trigger · get_turnaround_and_crew_state", "read"],
        ["Bookings, seats, special needs", "Passenger service system, e.g. Amadeus Altéa or Sabre (APIs, IATA NDC)",
         "list_disrupted_passengers · execute_atomic_passenger_rebook", "read + write"],
        ["Bags", "SITA WorldTracer / Bag Journey, IATA BSM/BPM messages", "bag plans in the same transaction",
         "read + write"],
        ["Crew duty and standby", "Crew tracking, e.g. Jeppesen Crew Tracking or Lufthansa Systems NetLine/Crew",
         "find_standby_crew (legal-crew matcher)", "read; swaps staged"],
        ["Maintenance", "Tech log / MRO system (deferred defects, CRS)", "maintenance sign-off check", "read"],
        ["Stands and turnaround", "Airport AODB / A-CDM (stand plan, TOBT)", "evaluate_gate_options · critical path",
         "read; changes staged"],
        ["Decisions", "Ops control, e.g. Amadeus Flight Operations Control or NetLine/Ops ++",
         "stage_controller_schedule_change → controller approves", "staged, human approves"],
    ]
    ui.table(["Data", "Airline system it comes from", "AeroTurn tool", "Access"], rows)
    ui.source("Vendor products are named as examples of systems AeroTurn reads from and writes back to; it does not "
              "replace them. Product names from the vendors' sites (amadeus.com, sita.aero, lhsystems.com, "
              "jeppesen.com).")

# ---------------------------------------------------------------------------
# 4. rollout + pilot design
# ---------------------------------------------------------------------------
r1, r2 = st.columns([1, 1.15], gap="medium")
with r1.container(border=True):
    ui.section("4 · Rollout, with exit criteria")
    ui.table(["Phase", "What runs", "Moves on when (set with the airline)"], [
        ["<b>0 · Data check</b> (2–4 wks)", "Connectors read-only; data quality measured", "Feeds complete and on time"],
        ["<b>1 · Shadow</b> (8–12 wks)", "AeroTurn plans every case; controllers work as today",
         "Plans legal in every case; KPIs measured X vs Y"],
        ["<b>2 · Advisor</b>", "Plans shown in the controller console; one-click approval", "Acceptance rate agreed"],
        ["<b>3 · Supervised</b>", "Passenger and bag rebooking run inside the guards; network changes stay human",
         "Safety board sign-off"],
    ])
with r2.container(border=True):
    ui.section("5 · Pilot design: current workflow (X) vs AeroTurn (Y)")
    st.markdown("<div class='card'><h4>X · current workflow</h4><p>Manual recovery, the existing decision process, "
                "existing costs and staff time, measured on the same disruptions.</p></div>"
                "<div class='card'><h4>Y · AeroTurn</h4><p>Validated AI-assisted recovery: time to plan, actual or "
                "estimated recovery cost, staff time.</p></div>", unsafe_allow_html=True)
    ui.table(["Stratify by", "Why"], [
        ["Severity (cancellations, delay)", "An outage day is not a normal day (see the Dashboard strata)"],
        ["Duration", "A 2-hour disruption is not a 5-day recovery"],
        ["Passengers affected", "Workload scales with people, not flights"],
        ["Airport conditions", "Weather, ATC flow control, stand availability"],
        ["Flight availability", "Spare seats decide what recovery is possible"],
    ])
