"""💼 Business model: the problem in money, who already sells what, how AeroTurn is sold, and the economics.

Rule for this page: a number is either computed from real data / a published source (green), or it is an
assumption you can change (purple). Nothing in between.
"""
from __future__ import annotations

import json

import streamlit as st

from aeroturn import config, realdata as R
from views import ui

ui.setup()
ui.header("Business model",
          "Priced against the delay cost it removes, sold as a layer on top of the systems airlines already run",
          [("real", "Real data + published sources"), ("asm", "Assumptions are editable")])

M = R.month_summary()
MEAS = json.loads((config.ROOT / "docs" / "round3" / "measurements.json").read_text(encoding="utf-8"))
PRICE_MIN = config.A4A_COST_PER_MIN_USD
normal = R.daily()[R.daily().stratum == "Normal"]
late_min_day_normal = float(normal.LateAircraftDelay.mean())
annual_value_normal = late_min_day_normal * 365 * PRICE_MIN          # conservative: normal days only
july_value = M["late_aircraft_minutes"] * PRICE_MIN
knock_per_day = R.rotations()[R.rotations().knock_on].groupby("date").size().mean()
cost_per_recovery = MEAS["recovery"]["mean_cost_usd"]

# ---------------------------------------------------------------------------
# 1. the problem in money
# ---------------------------------------------------------------------------
k = st.columns(4, gap="small")
ui.kpi(k[0], "Late-aircraft delay, one hub", f"{M['late_aircraft_minutes'] / 1000:,.0f}k min",
       f"ATL, July 2024 · {M['late_aircraft_share']:.0f}% of all delay minutes")
ui.kpi(k[1], "Cost of that delay", f"${july_value / 1e6:,.1f}M / month", f"× ${PRICE_MIN} per minute (A4A 2025)")
ui.kpi(k[2], "Conservative yearly value pool", f"${annual_value_normal / 1e6:,.0f}M",
       "normal days only × 365 · one hub")
ui.kpi(k[3], "One bad week, one airline", "~7,000 cancellations", "Delta, five days from 19 Jul 2024: $380M revenue impact")
ui.source(f"BTS cause minutes × <a href='{config.A4A_SOURCE}'>A4A $98.41/min</a>. Delta figures: "
          "<a href='https://www.sec.gov/Archives/edgar/data/27904/000168316824005369/delta_8k.htm'>SEC 8-K, Aug "
          "2024</a>; the CEO said a crew-tracking tool could not process the volume of changes "
          "(<a href='https://cbsnews.com/news/delta-flight-cancellations-today-dot-investigation-crowdstrike-outage'>"
          "CBS</a>). In Europe the reference is €166/min (<a href='" + config.EUROCONTROL_SOURCE + "'>EUROCONTROL</a>).")
st.write("")

# ---------------------------------------------------------------------------
# 2. competitors and where AeroTurn fits
# ---------------------------------------------------------------------------
with st.container(border=True):
    ui.section("2 · Who already sells disruption tools, and where AeroTurn fits",
               "Strong products exist per domain. AeroTurn is the safety and orchestration layer across them: one "
               "decision that respects crew law, maintenance sign-off, passenger priority and bags at the same "
               "time, with a human approving every network change.")
    ui.table(["Vendor", "Products (from their sites)", "What it covers", "AeroTurn's relationship"], [
        ["<b>Amadeus</b>", "<a href='https://amadeus.com/en/airlines/products/passenger-recovery'>Passenger "
         "Recovery</a>, <a href='https://amadeus.com/en/airlines/products/airline-disruption-management'>Disruption "
         "Management</a>, <a href='https://amadeus.com/en/airlines/products/flight-operations-control'>Flight "
         "Operations Control</a>", "Automated passenger rebooking; ops control. Amadeus reports Air Canada's "
         "cancellation handling is ~90% automated", "Read/write through its APIs; AeroTurn adds crew-law, "
         "maintenance and bag checks before a rebooking commits"],
        ["<b>SITA</b>", "<a href='https://sita.aero/solutions/sita-at-airports/sita-baggage-management'>WorldTracer, "
         "Bag Journey</a>, <a href='https://sita.aero/solutions/sita-for-aircraft/applications/sita-mission-watch'>"
         "Mission Watch</a>", "Bag tracing and automatic bag reflight; flight watch", "Bag plans written back as "
         "messages; flight-watch alerts as triggers"],
        ["<b>Lufthansa Systems</b>", "<a href='https://lhsystems.com/product-brands/netline/netlineops'>NetLine/Ops "
         "++</a> (aiOCC assistant, 2024)", "AI-driven operations control", "Could host AeroTurn's guarded recovery "
         "as a module; same OCC users"],
        ["<b>Sabre</b>", "<a href='https://www.sabre.com/page/sabre-mosaic/'>SabreMosaic Disruption Management</a>",
         "Passenger reaccommodation suite", "Passenger side via its APIs"],
        ["<b>Jeppesen</b>", "<a href='https://ww2.jeppesen.com/network-and-operations-management/ops-control/'>Ops "
         "Control</a>, <a href='https://ww2.jeppesen.com/airline-crew-optimization-solutions/airline-crew-tracking/'>"
         "Crew Tracking</a>", "Aircraft recovery solver; crew recovery", "Crew legality inputs; AeroTurn re-checks "
         "duty limits in its own sealed rules"],
    ])
    ui.source("No vendor publishes its prices, so AeroTurn's price below is our assumption, set against the value "
              "it removes rather than copied from a competitor.")

# ---------------------------------------------------------------------------
# 3. how it is sold + customer ROI
# ---------------------------------------------------------------------------
b1, b2 = st.columns([1, 1.25], gap="medium")
with b1.container(border=True):
    ui.section("3 · How AeroTurn is sold")
    st.markdown(
        "<div class='card'><h4>Annual subscription per hub</h4><p>Priced against the late-aircraft delay cost at that "
        "hub. Covers the agent, guards, audit trail and updates to the rule file.</p></div>"
        "<div class='card'><h4>One-time integration</h4><p>Connectors to the airline's reservation, crew, maintenance, "
        "baggage and airport systems; the shadow-mode pilot.</p></div>"
        "<div class='card'><h4>Deployment choice</h4><p>Cloud, or on-premise with an open-weight model (gpt-oss) when "
        "data must stay in the country.</p></div>"
        "<div class='card'><h4>Go to market</h4><p>1) a shadow pilot at one hub; 2) integrations listed with the "
        "platforms airlines already run (Amadeus, SITA, Lufthansa Systems); 3) ground handlers and A-CDM airports.</p>"
        "</div>", unsafe_allow_html=True)
with b2.container(border=True):
    ui.section("4 · Customer ROI (one hub)", f"{ui.pill('real', 'value pool')} from real data &nbsp; "
                                             f"{ui.pill('asm', 'assumptions')} are the two sliders")
    price = st.slider("Subscription per hub per year (US$, assumption)", 50_000, 1_000_000, 300_000, 25_000)
    cut = st.slider("Share of late-aircraft delay minutes AeroTurn removes (%, assumption; measured in the pilot)",
                    0.0, 5.0, 1.0, 0.1)
    saving = annual_value_normal * cut / 100
    breakeven = price / annual_value_normal * 100
    k2 = st.columns(3, gap="small")
    ui.kpi(k2[0], "Saving per year", f"${saving / 1e6:,.2f}M", f"{cut:.1f}% of ${annual_value_normal / 1e6:,.0f}M")
    ui.kpi(k2[1], "Customer ROI", f"{(saving - price) / price * 100:,.0f}%" if price else "—",
           "(saving − price) ÷ price")
    ui.kpi(k2[2], "Break-even", f"{breakeven:.2f}%", "of late-aircraft minutes removed")
    ui.source(f"Value pool = {late_min_day_normal:,.0f} late-aircraft minutes per normal day at ATL (BTS, July 2024) "
              f"× 365 × ${PRICE_MIN}/min. Payback months = price ÷ monthly saving. The share removed is not claimed: "
              f"it is what the shadow pilot measures, X vs Y.")

# ---------------------------------------------------------------------------
# 5. AeroTurn's own unit economics
# ---------------------------------------------------------------------------
with st.container(border=True):
    ui.section("5 · AeroTurn's unit economics",
               f"{ui.pill('real', 'measured')} model cost per recovery and real case volume &nbsp; "
               f"{ui.pill('asm', 'assumptions')} everything you can type in")
    i = st.columns(5, gap="small")
    hubs = i[0].number_input("Hubs live (assumption)", 1, 200, 5)
    hosting = i[1].number_input("Hosting per hub / yr, US$ (assumption)", 0, 500_000, 24_000, 1_000)
    support = i[2].number_input("Support per hub / yr, US$ (assumption)", 0, 1_000_000, 60_000, 5_000)
    cac = i[3].number_input("CAC per airline, US$ (assumption)", 0, 2_000_000, 150_000, 10_000)
    churn = i[4].number_input("Churn per year, % (assumption)", 0.0, 100.0, 10.0, 1.0)
    llm_year = knock_per_day * 365 * cost_per_recovery
    arr = hubs * price
    delivery = hubs * (hosting + support + llm_year)
    gm = (arr - delivery) / arr * 100 if arr else 0
    gp_month = (price - (hosting + support + llm_year)) / 12
    k3 = st.columns(5, gap="small")
    ui.kpi(k3[0], "ARR", f"${arr / 1e6:,.2f}M", "hubs × subscription")
    ui.kpi(k3[1], "Gross margin", f"{gm:.0f}%", "(revenue − delivery cost) ÷ revenue")
    ui.kpi(k3[2], "Model cost per hub", f"${llm_year:,.0f} / yr",
           f"{knock_per_day:.0f} cases/day × ${cost_per_recovery:.4f}")
    ui.kpi(k3[3], "Payback on CAC", f"{cac / gp_month:,.1f} months" if gp_month > 0 else "—",
           "CAC ÷ monthly gross profit per hub")
    ui.kpi(k3[4], "Churn", f"{churn:.0f}% / yr", "lost customers ÷ customer base")
    ui.source(f"Real inputs: {knock_per_day:.0f} recovery cases per day = knock-on turns at ATL (BTS, July 2024); "
              f"${cost_per_recovery:.4f} per recovery measured on real Groq calls (docs/round3/measurements.json) at "
              "Groq's published price. Everything else is an assumption you set.")
