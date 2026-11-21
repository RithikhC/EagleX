# Every number in the Round 3 pitch and deck, and its proof

Each number has one of four kinds of proof:
- **Measured:** timed or counted on real runs. Source: `docs/round3/measurements.json`, written by
  `python scripts/round3_evidence.py` on 21 Nov 2026 01:44 GST.
- **Official source:** a provider page or regulation, linked.
- **Dataset:** the synthetic, reproducible scenario (seed 812, `python scripts/build_dataset.py`). It is visible in
  the app and explained in [../NUMBERS_EXPLAINED.md](../NUMBERS_EXPLAINED.md).
- **Assumption:** our estimate, stated as one, with how it would be validated.

Model outputs vary a little from run to run, and the provider's rate limits depend on load. Re-running the script
gives similar numbers, not identical ones.

## Real data (Dashboard, Implementation, Business pages)

All computed by `aeroturn/realdata.py` from `data/real/` (BTS on-time records for ATL, July 2024, SHA-256 in
`data/real/manifest.json`).

| Number | Proof |
|---|---|
| 30,072 departures, 13 airlines, 63.9% on time, 1,778 cancelled | Count of ATL departures; on time = left < 15 min late (BTS definition) |
| 921,161 delay minutes; 35.1% from late-arriving aircraft | Sum of BTS cause minutes for arrivals at ATL 15+ min late |
| 23,756 aircraft turns; 3,499 knock-on turns (91/day normal, 198/day outage) | Arrivals joined to the same tail number's next ATL departure; knock-on = inbound 15+ late, ate the buffer, outbound 15+ late |
| 5 days to recover after 19 July; 1,589 cancellations | Days until cancellations fell back under 2% |
| 223 recovery cases on 19 July | The alert rule applied to that day's turns |
| $31.8M late-aircraft delay cost (July); $254M/year value pool | Minutes × A4A $98.41/min; the pool uses normal days only × 365 |
| Break-even 0.12% at $300k/hub-year | **Assumption:** the price ($300k); real: the value pool |
| Model cost ≈ $65 per hub-year | Real case volume (113/day) × measured $0.0016 per recovery |
| ~7,000 cancellations, $380M | Delta SEC 8-K, Aug 2024 |
| Live board, 12 Jul 2024 at 17:00: 616 departures flown, 75% on time, 36 turn alerts (18 critical) | `realdata.board()`: departures due by 17:00 that had left; alert = inbound aircraft 15+ min late that leaves less than 30 min before its next departure (30 min is our stated minimum-turn assumption) |
| WN215 lands 237 min late; WN3275 (due 17:00) left 239 min late | Same BTS records (tail N287WN); "what really happened" is hindsight from the record |

## The scenario (Simulation page, sample data)

| Number | Proof |
|---|---|
| EK812 75 min late | Dataset: STA 14:05, on-blocks 15:20 (`flights` table; "EK812 at the stand" tile) |
| 280 connecting, 45 broken connections, 10 vulnerable | Dataset, computed by `recovery.connection_risk()`; "Connections at risk" and "Vulnerable" tiles |
| Crew 20 min from the legal limit | Reported 04:40, 2 sectors → max duty 11:00 (EASA ORO.FTL.205 Table 2, coded in `guards.py`) → limit 15:40; on-blocks 15:20 |
| 25-minute stand decision window | Clock 14:50; the C31 decision must be made by 15:15 (on-blocks − 5 min, `tools.evaluate_gate_options`) |
| Stand C31, Captain Mehta, departure 17:15 | Tool outputs: stand evaluator, legal-standby matcher, critical path ([NUMBERS_EXPLAINED §2–4](../NUMBERS_EXPLAINED.md)) |

## Results of a recovery run

| Number | Proof |
|---|---|
| 0 connections at risk, 10/10 vulnerable protected | KPI tiles after the run (screenshot `docs/img/round3/workflow.png`); also asserted in the tests |
| AED 133,390 legacy vs AED 50,440 AeroTurn (−62%) | Cost model. EU261 amounts are set by law (EUR 250/400/600, Art. 7) at 1 EUR = 4.10 AED; care and delay rates are stated assumptions in `aeroturn/config.py`. Arithmetic in [NUMBERS_EXPLAINED §5](../NUMBERS_EXPLAINED.md) |
| AED 82,950 saved | 133,390 − 50,440, shown on the "Passenger cost saved" tile. When the LLM also proposes the Sydney hold, the figure is AED 93,190 instead: it is the figure of that run |
| 45/45 arrive the same day | Dataset plus plan: every rebooked flight lands on 21 Nov ([NUMBERS_EXPLAINED §5](../NUMBERS_EXPLAINED.md)) |
| 118 tests, 13 edge cases, 5 curveballs; no rule broken | `python -m pytest -q` → 118 passed (includes the edge-case and curveball suites). "No rule broken" means no guard violation was ever committed in these tests; it does not mean the rules are certified |

## Round 3: measured on real calls (`measurements.json`)

| Number | Value | How it was measured |
|---|---|---|
| Burst | 12 requests in 10.6 s, 0 crashes | Wall clock around the 12 requests |
| Decisions | 4 auto, 3 paused, 4 blocked, 1 rejected | Counted from the 12 results (stable across 3 extra runs) |
| Time per request | 0.56 s median; model call 0.22 s median | Timer per request and per model call |
| Failure handled | 3 timed-out calls recovered (REQ-05: 2 retries, then the backup) | Call log statuses |
| Requests needing no model | 2 (both attacks, stopped by code) | Count |
| Tokens per inbox request | 308 (319 in + 51 out per call; 13 calls for 12 requests) | Groq's own `usage` counts in each response |
| Tokens per recovery | 6,579 (5,200 in + 1,379 out), 3 model calls | Groq `usage` counts, mean of 5 runs |
| Cost per request / per recovery | US$ 0.000062 / US$ 0.0016 | Tokens × price per model (below), each call at its own model |
| Recovery time | 11.5–35 s, median 22.6 s (5 runs back to back) | Wall clock per run |
| Recovery time breakdown (medians) | model answering 3.6 s · rate-limit waits 11 s · our code 6.5 s | Call timers; seconds actually slept on HTTP 429; remainder. Waits appear because 5 back-to-back runs at ~6,600 tokens each exceed 8,000 tokens/minute. The first run's 27 s of code time is a cold start |

## Prices and limits (official sources)

| Number | Proof |
|---|---|
| gpt-oss-120b: US$ 0.15 / 1M input, US$ 0.60 / 1M output | https://console.groq.com/docs/model/openai/gpt-oss-120b (checked 21 Nov 2026) |
| gpt-oss-20b (backup): US$ 0.075 / 1M input, US$ 0.30 / 1M output | https://console.groq.com/docs/model/openai/gpt-oss-20b (checked 21 Nov 2026) |
| Our account: 8,000 tokens/minute, 1,000 requests/day | Read from the `x-ratelimit-limit-tokens` / `x-ratelimit-limit-requests` headers of a live Groq response (in `measurements.json`) |
| 200,000 tokens/day | Groq's rate-limit table for openai/gpt-oss-120b (30 RPM, 1K RPD, 8K TPM, 200K TPD): https://console.groq.com/docs/rate-limits |

## Assumptions (stated as such on the slides)

| Number | Why it is an assumption | How a pilot would check it |
|---|---|---|
| 500 inbox requests + 30 recoveries a day at one hub | No airline data was supplied | Count them in shadow mode |
| → US$ 2.35 a month in tokens (US$ 23 at 10× the volume) | Measured cost per request × the assumed volume × 30 | The same formula with the real counts |
| Pilot day ≈ 351,000 tokens → needs a paid tier | Assumed volume × measured tokens; above the 200K/day in Groq's table | The Groq usage dashboard |
| Team size of the OCC | Not stated: "to be confirmed with the airline" | Airline roster |
| "One small server" for hosting | Not priced: depends on the airline's cloud contract | Airline IT quote |

## Log IDs on the safety slide

| Slide | Proof |
|---|---|
| Safe auto-action #34 · paused #37 → expired #40 · blocked attack #38 | `docs/round3/log_evidence.txt` and `log_evidence.png` (the same run). `log_evidence_live_app.png` is a screenshot of the live app from another run, so its IDs differ |

## How to reproduce everything

```powershell
python -m pytest -q                    # 118 tests
python scripts/round3_evidence.py      # re-measures and rewrites measurements.json + log_evidence.txt
python scripts/deck/render_log_png.py  # log_evidence.png from the text export
```
