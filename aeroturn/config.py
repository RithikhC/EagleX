"""Paths, scenario anchors and commercial assumptions.

Nothing in this file is a safety rule. Safety floors live in ``guards.py`` and
cannot be changed at runtime. The numbers below are commercial/simulation
assumptions and may be edited freely.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PRISTINE_DB = DATA_DIR / "aircraft_turnaround_disruption.sqlite"
SNAPSHOT_JSON = DATA_DIR / "scenario_snapshot.json"
RUNTIME_DIR = Path(os.environ.get("AEROTURN_RUNTIME_DIR", ROOT / "runtime"))
RUNTIME_DB = RUNTIME_DIR / "aeroturn.sqlite"

# Scenario anchors (all times are hub local time, Gulf Standard Time, UTC+4)
SCENARIO_DATE = "2026-11-21"
HUB = "DXB"
SCENARIO_START_CLOCK = "2026-11-21T14:50"
INBOUND_FLIGHT_ID = "EK812-1121"
OUTBOUND_FLIGHT_ID = "EK813-1121"
HOME_CARRIER = "EK"

# Commercial assumptions (illustrative, editable, NOT safety rules)
# Money is reported in UAE dirhams. EU261 amounts are fixed in EUR by law and are converted at EUR_TO_AED.
CURRENCY = "AED"
EUR_TO_AED = 4.10                 # reference mid-market rate (27 Oct 2026); set to the day's rate
# LLM prices for the cost report: Groq's official model pages (checked 21 Nov 2026)
#   https://console.groq.com/docs/model/openai/gpt-oss-120b : input $0.15 / 1M tokens, output $0.60 / 1M
#   https://console.groq.com/docs/model/openai/gpt-oss-20b  : input $0.075 / 1M tokens, output $0.30 / 1M
MODEL_PRICES = {"openai/gpt-oss-120b": (0.15, 0.60), "openai/gpt-oss-20b": (0.075, 0.30)}   # US$ per 1M in, out
PRICE_IN_PER_M, PRICE_OUT_PER_M = MODEL_PRICES["openai/gpt-oss-120b"]
PRICE_SOURCE = "Groq model pages, console.groq.com/docs/model/openai/gpt-oss-120b (checked 21 Nov 2026)"


def call_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = MODEL_PRICES.get(model, (PRICE_IN_PER_M, PRICE_OUT_PER_M))
    return (input_tokens * pin + output_tokens * pout) / 1e6

DELAY_COST_AED_PER_MIN = 400      # tactical delay cost, wide-body aircraft (assumption, ~EUR 100)
PAX_MINUTE_AED = 1.50             # value of one passenger-minute of delay for those on board (assumption)
MAX_RECOMMENDED_HOLD_MIN = 15     # commercial policy for suggesting a connection hold (the safety cap is in guards)
MIN_HOLD_NET_SAVING_AED = 1000    # a hold must beat re-accommodation by this margin: the delay estimate is uncertain
MEAL_VOUCHER_AED = 100            # right-to-care meal voucher per passenger
HOTEL_NIGHT_AED = 550             # overnight accommodation + transport per passenger
