# Round 3: Make It Work in Practice (submission sheet)

Team EagleX · University Track · Domain 4: Aviation & Airport Operations. Built on our Round 2 solution (AeroTurn),
not a new project.

## What to submit

| Deliverable | Link / file |
|---|---|
| Updated working link | https://aeroturn-eaglex.streamlit.app (code and run steps: https://github.com/RithikhC/EagleX) |
| Round 3 presentation (official template, PDF) | https://github.com/RithikhC/EagleX/blob/main/docs/EagleX_Round3_Final.pdf · [PPTX](EagleX_Round3_Final.pptx) |
| Log evidence (three safety cases) | Screenshot: https://github.com/RithikhC/EagleX/blob/main/docs/round3/log_evidence.png · Export: https://github.com/RithikhC/EagleX/blob/main/docs/round3/log_evidence.txt (the same run; the deck cites these log IDs) |
| Proof of every number | [round3/NUMBERS_PROOF.md](round3/NUMBERS_PROOF.md) |
| Live pitch and demo (7 + 5 min) | Script: [PITCH_ROUND3.md](PITCH_ROUND3.md) |

## The app, in four pages

| Page | What it shows | Data |
|---|---|---|
| 📈 Dashboard | **Live operations:** the OCC screen on a real day at Atlanta, replayed to the minute: departures, cancellations, late aircraft on a map, arrival and departure boards, and the queue of turns AeroTurn would raise (with what really happened). **Month review:** July 2024 on-time, causes, knock-on turns, strata, KPI framework X (current) vs Y (AeroTurn) | Real: US DOT BTS, OurAirports, A4A |
| 🧪 Simulation | Six chapters: 1 recover the flight (alert → AI plan → rules → approval → outcome) · 2 under pressure (12 requests, one forced failure) · 3 safety & audit (three cases, audit trail, rogue-AI tests) · 4 the 5 curveballs · 5 our 13 edge cases · 6 cost & limits | Sample scenario (no real personal data) |
| 🔌 Implementation | Live connectors with checks; AeroTurn's alert rule on real flights (223 cases on 19 July); integration map; rollout; pilot design | Real + live (OpenSky) |
| 💼 Business model | Competitors (Amadeus, SITA, Lufthansa Systems, Sabre, Jeppesen), pricing, customer ROI, unit economics | Real + labelled assumptions |

## The one user journey

**User:** the duty operations controller in a hub OCC.
**Trigger:** a delay alert for the inbound EK812 ("new ETA 15:12"), typed or pasted into the *Incoming alert* box.
**Output:** a legal recovery plan waiting for approval (stand, captain, departure time, holds), 45 passengers
rebooked with their bags, passenger messages and the cost in AED.

1. **Trigger:** the alert. Code checks the flight, the new ETA and the text for injection
   (`aeroturn/alerts.py`). A bad alert is rejected and logged, and the agent does not run.
2. **Validate:** 6 read-only tools gather the facts, and 28 sealed rules decide what is legal.
3. **Agent acts:** the LLM plans. Every action goes through one of 13 guarded tools, and rebooking runs in
   atomic batches.
4. **Approve:** stand, crew, retime and hold changes wait for a named controller. The rules re-run at approval.
5. **Output:** the approval queue, the rebooking, messages and the AED cost.

## The four judged areas, and where to see each one live

| Area (weight) | What judges see | Where in the app |
|---|---|---|
| Workflow & resilience (30%) | Alert → plan in one run. 12 inbox requests back to back. A forced timeout on REQ-05 recovered by the backup model. | 🧪 Simulation › 1 · Recover the flight · 2 · Under pressure |
| Safety & audit (30%) | Safe auto-action, risky action paused (safe default: it expires and nothing changes), blocked attack, each with a log ID | 🧪 Simulation › 3 · Safety & audit |
| Deployment, cost & limits (25%) | Measured tokens, latency and cost; deployment plan; limitations | 🧪 Simulation › 6 · Cost & limits · 🔌 Implementation · slides 7–9 |
| Pitch & Q&A (15%) | Value and trade-offs | slide 10 · [PITCH_ROUND3.md](PITCH_ROUND3.md) |

## Resilience settings (`aeroturn/llm.py`)

| | Setting |
|---|---|
| Time limit | 20 s per model call (`AEROTURN_LLM_TIMEOUT`); 0.05 s in the failure test |
| Retries | at most 2, waiting 1 s then 2 s; a rate-limit error goes straight to the backup (no retry storm) |
| Fallback | openai/gpt-oss-120b (Groq) → openai/gpt-oss-20b (Groq; Gemini first if `GEMINI_API_KEY` is set) → local rule parser / offline policy (no network) |
| User messages | "Still working: retry 1/2 in 1 s", "Couldn't reach … Using … instead", "Answered by the backup model …" |

## Measured on real runs (`python scripts/round3_evidence.py` → `docs/round3/measurements.json`)

| Measure | Value |
|---|---|
| Inbox request | ≈ 308 tokens · ≈ US$ 0.00006 · median 0.56 s |
| Full recovery | 3 model calls · ≈ 5,200 input + 1,380 output tokens · ≈ US$ 0.0016 · 11.5–35 s, median 22.6 s over 5 back-to-back runs (model 3.6 s, rate-limit waits 11 s, our code 6.5 s; medians) |
| Burst | 12 requests in 10.6 s, 0 crashes, 3 timed-out calls recovered |
| Pilot month (assumed: 500 requests + 30 recoveries a day at one hub) | ≈ US$ 2.35 in tokens (≈ US$ 23 at 10×); about 351K tokens a day, above the free tier → paid tier |
| Our Groq account | 8,000 tokens/minute, 1,000 requests/day (read from Groq's response headers) |

Prices are from Groq's model pages (checked 21 Nov 2026): gpt-oss-120b US$ 0.15 / 0.60 and gpt-oss-20b
US$ 0.075 / 0.30 per million input / output tokens. Every number's source is in
[round3/NUMBERS_PROOF.md](round3/NUMBERS_PROOF.md).

## Final checklist (from the participant manual)

- [x] One complete user journey runs live from trigger (alert) to useful output (approved plan, rebooking, messages)
- [x] A batch of inputs (12) runs back to back, and one failure is handled gracefully (REQ-05 timeout → backup)
- [x] Every model call has a timeout, limited retries and a fallback
- [x] The three safety cases can be triggered on demand, and each appears in the logs with a log ID
- [x] Checks are in code; every change goes through one write function (`execute_atomic_passenger_rebook` for
      bookings, `stage_controller_schedule_change` → `hitl.approve` for the network)
- [x] API keys only in `.env` (git-ignored) or Streamlit Secrets, never on screen
- [x] Cost per request, cost per month, latency and limitations are on the slides
- [ ] Submit the working link, PDF and log evidence at the upload link before the deadline
- [ ] Test the demo on the presentation laptop and network; local fallback ready
      (`streamlit run app.py`; sidebar brain = offline if there is no network)
- [ ] Rehearse the 7 minutes with a timer
