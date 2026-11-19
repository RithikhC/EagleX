# ✈️ AeroTurn: Autonomous Aircraft Turnaround & Atomic Disruption Recovery Agent

**Domain 4: Aviation & Airport Operations (University Track) · Team EagleX**

[![Open the live demo](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://aeroturn-eaglex.streamlit.app)

**Live demo: https://aeroturn-eaglex.streamlit.app**. The 📊 *Operations* dashboard opens first; each scenario is one button in the bar at the top. Every visitor gets
their own copy of the scenario, so click freely and use *↺ Reset scenario* to start over. If the app has been
asleep, the first load takes about a minute.

**Pitch deck: [PowerPoint](docs/AeroTurn_Deck.pptx) · [PDF](docs/AeroTurn_Deck.pdf)**. 17 slides built from real screenshots of the
demo: every scenario, the 13 edge cases, how AeroTurn plugs into an airline's systems, the rollout plan and
business case, and the datasets and sources on the thank-you slide. Rebuild it with `scripts/deck/`
(headless-Chrome capture, crop, pptxgenjs).

**Every number explained: [docs/NUMBERS_EXPLAINED.md](docs/NUMBERS_EXPLAINED.md)**: the formula, inputs and
arithmetic behind each figure on the dashboard (crew limits, stand choice, EU261, hold and network costs).

> A Boeing 777 lands 75 minutes late at Dubai with 280 connecting passengers. The inbound crew is 20 minutes
> from its legal duty limit, a hydraulic defect needs a licensed engineer's sign-off, and the outbound captain
> has just filed a fatigue report. AeroTurn lets an LLM reason about the cascade while plain Python makes the
> unsafe options impossible.

![AeroTurn OCC console after a recovery run](docs/img/demo/hero.png)

---

## The 30-second version

| | What AeroTurn does |
|---|---|
| 🧠 **LLM agent** | Reads the situation through tools, works out the cascade, decides which recovery action to try next, writes passenger messages and the executive brief. |
| 🔧 **Tools (code)** | Run the three required services: `get_turnaround_and_crew_state()`, `execute_atomic_passenger_rebook()` and `stage_controller_schedule_change()`. Also a standby crew matcher, a turnaround critical path, an EU261 cost model and a priority-protected rebooking planner. |
| 🛡️ **Guards (code)** | `guards.py` is pure Python and **sealed**: assigning to it raises, and its SHA-256 is pinned. It enforces crew FDP, rest, type rating, fatigue, maintenance CRS, vulnerable-passenger priority, passenger-specific MCT and bag-passenger matching. No tool has an `override` parameter. |
| ⚛️ **Atomic state** | Seat and bag rebooking run as **one** `BEGIN IMMEDIATE … COMMIT/ROLLBACK`. A mid-way failure leaves the state hash identical, with 0 double bookings and 0 orphaned bags. |
| 👤 **HITL** | Gate, retime, crew swap and departure release are only **staged**. A named human controller approves them, and the guards **run again** at approval time. The agent has no approval tool. |

**Results on the scenario:**
- 45/45 broken connections recovered: 41 rebooked atomically, and 4 kept on their flight by an 8-minute hold the
  controller approved.
- 10/10 vulnerable passengers protected, and all 45 arrive the same day.
- Passenger compensation and care fall from AED 133,390 (legacy +24h re-protection) to AED 40,200 (−70%);
  AED 50,440 if the controller rejects the hold and all 45 are rebooked.
- Network cost, including the EK813 delay, the knock-on and the hold, falls from AED 206k to AED 121k.
- All money is in UAE dirhams. EU261 amounts are fixed in EUR by law and converted at 1 EUR = 4.10 AED
  (`aeroturn/config.py`).
- 79 automated tests pass, including 13 edge cases where the world changes after the plan (all resolved or escalated, none broken).

---

## Quick start

```powershell
pip install -r requirements.txt
streamlit run app.py          # OCC dashboard at http://localhost:8501
python run_demo.py            # the same scenario in the terminal; you approve as the controller
python -m pytest -q           # 79 tests
```

### Choose the brain (optional)

AeroTurn works fully **offline**: a deterministic policy runs the same tool workflow and is clearly labelled as
"no LLM". To use a real LLM, copy `.env.example` to `.env`:

| Provider | Setting | Notes |
|---|---|---|
| **Ollama (local qwen3)** | `ollama pull qwen3:8b`, then `ollama serve` | Auto-detected on `localhost:11434`; uses `/no_think` for speed |
| **Groq** | `GROQ_API_KEY=...` | default `llama-3.3-70b-versatile` (`GROQ_MODEL` to change) |
| **Gemini Flash** | `GEMINI_API_KEY=...` | default `gemini-2.5-flash` (`GEMINI_MODEL` to change) |

`AEROTURN_LLM=auto|ollama|groq|gemini|offline` forces a provider. All three use the OpenAI-compatible
chat-completions API with native tool calling, through a stdlib HTTP client with no SDKs. If the model stalls or
skips a step, a labelled **code autopilot** finishes it, so a live demo never ends half-done.

---

## Architecture

```mermaid
flowchart LR
  subgraph BRAIN["🧠 LLM agent (qwen3 · Groq · Gemini · offline policy)"]
    A["Analyse cascade<br/>choose next tool<br/>write wording + brief"]
  end
  subgraph TOOLS["🔧 tools.dispatch: strict JSON schemas, no override args, audited"]
    T1["get_turnaround_and_crew_state"]
    T2["execute_atomic_passenger_rebook"]
    T3["stage_controller_schedule_change"]
    T4["evaluate_gate_options · find_standby_crew<br/>critical path · propose_departure · costs"]
  end
  subgraph GUARDS["🛡️ guards.py: sealed module, SHA-256 pinned"]
    G["FTL · MX CRS · priority · MCT · UMNR/MEDA · PPBM"]
  end
  subgraph DB["🗄️ SQLite"]
    D[("bookings · bag_routing · crew · MX<br/>schedule_changes · hash-chained audit")]
  end
  subgraph HUMAN["👤 Ops Controller · licensed engineer"]
    H["approve / reject · sign CRS"]
  end
  A -- "tool calls only" --> T1 & T2 & T3 & T4
  T2 & T3 & T4 -- "check before any write" --> G
  T2 -- "BEGIN IMMEDIATE → COMMIT / ROLLBACK" --> D
  T3 -- "PENDING only" --> D
  H -- "hitl.approve(): guards re-run" --> G
  H -- "apply atomically" --> D
```

### Four layers of protection against double booking and orphaned bags

1. **Guard pre-validation.** The whole batch is checked in pure Python before `BEGIN`: scope, destination,
   passenger-specific MCT, bag MCT, no downgrade, exit-row eligibility, UMNR/MEDA carrier rules, PNR integrity
   and priority inversion.
2. **Schema constraints during the transaction.** `UNIQUE(flight_id, seat_no)`, `UNIQUE(pax_id, leg_no)`, a
   seat-cabin trigger, and a bag-owner trigger for PPBM.
3. **Invariant scan inside the transaction.** Eight SQL invariants must all be zero before `COMMIT`.
4. **Deferred foreign key at COMMIT.** `bag_routing(pax_id, flight_id) → bookings DEFERRABLE INITIALLY DEFERRED`,
   so a bag can never be committed onto a flight its passenger is not booked on.

Any exception triggers a `ROLLBACK`, and the state fingerprint (SHA-256 over bookings, bag routing and history)
is shown to be identical before and after.

---

## Safety rules → where they are enforced → how they are tested

| Brief requirement | Enforcement | Test |
|---|---|---|
| Atomic state, mid-way rollback | `tools.execute_atomic_passenger_rebook` (4 layers above) | `test_atomic.py` (seat conflict at steps 7 and 30, bag-system fault, deferred FK, replay protection, stale plan) |
| Crew legal duty limits | `guards.check_crew_for_sector`, `check_inbound_crew_on_blocks`: EASA-style FDP table, sector reduction, standby rules per CS FTL.1.225 (airport standby >4h reduces FDP, standby+FDP ≤16h), rest, rating, fatigue, reachability | `test_guards.py`, `test_ops.py::test_standby_matcher…` |
| Mandatory maintenance sign-off | `guards.check_maintenance_release` + `check_crs_signature` (B1 licence, type authorisation, not before the task can finish) | `test_guards.py`, `test_hitl.py::test_full_departure_release_flow` |
| Vulnerable-passenger priority | `guards.pax_tier`, `_priority_inversions`, UMNR/MEDA/PRM rules; planner orders P1 → P4 | `test_priority.py` |
| LLM cannot bypass | Sealed module (`GuardTamperError`), frozen dataclasses, `MappingProxyType`, SHA-256 pin, strict arg schemas, no override params | `test_guards.py::test_guards_cannot_be_mutated`, `test_agent.py` (fake LLM tries override, illegal crew, self-approval, fact-bearing templates) |
| HITL for schedule / gate changes | `stage_controller_schedule_change` → `PENDING`; `hitl.approve()` is not in the tool registry, refuses non-human identities, re-runs the guards and enforces decision deadlines (gate 15:15, holds STD−5) | `test_hitl.py` (incl. hold approve, reject and expiry) |
| Decisions stay legal as facts change | `reconcile.reconcile`: re-checks every pending change, withdraws what became illegal, stages the next legal option or escalates | `test_edge_cases.py` (13 cases) |

## Core and stretch goals

- ✅ **Core 1: Late-aircraft recovery path.** Dataset of 342 passengers, 356 bags, 33 crew and 3 MX items;
  45 broken connections, all rebooked with vulnerable passengers first; a full staged recovery plan.
- ✅ **Core 2: Atomic rollback + immutable guards + controller gate.**
- ✅ **Stretch: standby crew pairing matcher.** Picks the nearest *legal* captain. The inbound captain, 0 min
  away, is rejected under FTL-001; the A380-only captain under FTL-003; the 9h-rest captain under FTL-002.
- ✅ **Stretch: below-wing critical-path tracker.** CPM over 11 tasks. The hydraulic inspection is on the
  critical path, giving EOBT 17:15 (+65 min).
- ✅ **Stretch: EU261 / cascade cost calculator.** Whole-journey EU261 because the flight departed Larnaca (EU),
  plus duty of care, the outbound delay and its knock-on to the return sector.
  - **Hold-or-rebook analysis:** for every broken connection, hold cost (aircraft plus passengers on board) is
    compared with rebooking cost.
  - The agent stages the one hold that pays off, EK418 to Sydney (+8 min), and the planner leaves those
    passengers alone until the controller decides.
- ➕ **Extras:**
  - Hash-chained, tamper-evident audit log (with a live tamper test)
  - Prompt-injection passenger remark that goes nowhere
  - Notification templates validated so the LLM can never state a flight, time, seat or gate itself
  - Numeric grounding check on the LLM brief
  - Gate decision deadline with expiry
  - Guard re-validation at approval
  - One-shot chaos injection, never reachable by the LLM

## Edge cases: when the world moves after the plan

A recovery plan is out of date the moment it is staged: a flight holds, a second captain reports fatigue, the
inspection finds a leak, the controller says no. AeroTurn re-validates continuously (`aeroturn/reconcile.py`).
It runs at the end of every agent run, after each world event, and on demand:

1. Every pending decision is re-run through the guards with fresh facts.
   - Expired decisions are marked EXPIRED.
   - Illegal ones are **WITHDRAWN** by the agent; they never sit in the controller's queue.
   - Still-legal ones whose facts moved, such as a new decision window, are re-staged with fresh numbers.
2. A legal replacement is staged when one exists: the next legal stand, the next legal captain, or a new
   critical-path ETD.
3. Short connection holds are re-assessed, then broken connections are re-planned in one atomic transaction.
4. Anything with no legal option is **escalated** to humans, with the reason and the options, and recorded in
   the audit chain. The model never solves a problem by breaking a floor.

`aeroturn/edge_cases.py` runs 13 cases. Each one uses a throw-away copy of the scenario, applies one
perturbation, and checks the outcome with readable assertions. **13/13 pass, 67/67 checks**: 9 cases are
resolved automatically and 4 are escalated to humans. Run them from the dashboard (🧪 Edge cases) or with
`pytest tests/test_edge_cases.py`.

| | The world changes | What AeroTurn does | Outcome |
|---|---|---|---|
| EC-01 | ATC holds EK812 +15 min after the plan | The 15:20 passenger plan is refused as stale. C31 is re-staged with the new 15:30 window (crew margin 5 min). Passengers are re-planned and committed | ✅ 45 rebooked; 1 with no legal seat today escalated |
| EC-02 | ATC hold +25 min: every stand breaches inbound crew FDP | C31 is withdrawn (FTL-001). Nothing relies on commander's discretion. Escalated with options | 🟧 escalated |
| EC-03 | The replacement captain reports fatigue | The controller's approval is blocked (FTL-004). The swap is withdrawn and the next legal captain is staged and approved | ✅ |
| EC-04 | Both legal standby captains drop out | No illegal captain is proposed. Departure is blocked (FTL-005). Crew control gets every candidate's blocking rule | 🟧 escalated |
| EC-05 | The last home-carrier seats for a UMNR and a MEDA passenger sell out | The child is never put on a partner, overnight or post-22:00 flight. The medical passenger is never put on an uncleared carrier. Both are escalated with their care protocol; the other 43 are rebooked | 🟧 escalated |
| EC-06 | One economy and one business seat left on the 18:25 to Bangkok | The UMNR gets the economy seat. The wheelchair passenger gets a protection upgrade to business. The family of three moves together to 21:50 | ✅ |
| EC-07 | The controller rejects C31 | C31 is never re-proposed; R205 is staged. After approval, the remote stand's +25 min MCT breaks more connections: AeroTurn proposes holding EK346 (last flight to Kuala Lumpur) for 3 min, which protects 10 passengers (AED 2,658 vs AED 31,100), and rebooks 6 more | ✅ |
| EC-08 | Nobody decides in time | C31 expires at 15:15. R205 is offered while its window is open (to 15:18), then expires and is escalated. A late approval returns EXPIRED | 🟧 escalated |
| EC-09 | The inspection finds a leak (+90 min) | The 17:15 retime is withdrawn (TURN-001) and re-staged at 18:45. C31 is withdrawn because the longer turn clashes with EK2350 at 18:45 (GATE-001); R205 is staged. The captain swap is re-checked and still legal | ✅ |
| EC-10 | The agent runs twice | No duplicate proposals, bookings or notifications | ✅ |
| EC-11 | The baggage system fails mid-commit | Rollback with an identical state fingerprint, then the retry commits all 45 passengers and their bags | ✅ |
| EC-12 | A diversion takes C31 | C31 is withdrawn (GATE-001) and R205 staged before anyone can approve a clash | ✅ |
| EC-13 | The controller rejects the EK418 hold | The 4 passengers waiting on it are rebooked at once; EK418 leaves on time | ✅ |

**What the edge cases changed in the model:**
- They found a cost bug. A passenger with no seat left today was costed at AED 0 in the hold analysis, so a
  hold for the last flight of the day never looked worthwhile. Stranded passengers are now costed as an
  overnight stay: hotel, meals and EU261.
- Hold length is now chosen per passenger. A 3-minute hold can protect 10 of 11 passengers even when the
  slowest would need 23 minutes. A hold must still save at least AED 1,000 net (`MIN_HOLD_NET_SAVING_AED`),
  because the delay estimate itself is uncertain. The main scenario's numbers are unchanged.
- The agent picks the best legal stand whose decision window is still open.
- If no legal stand or captain exists, the agent escalates instead of staging nothing.

## The scenario (synthetic, reproducible, seed 812)

All times are in GST (Dubai local) on 21 Nov 2026. The scenario clock starts at 14:50.

- **EK812 LCA→DXB**, B777-300ER A6-EQX: STA 14:05, in-block 15:20 (+75 min) after a HYD SYS C caution at Larnaca.
- **Inbound crew:** reported 04:40 for 2 sectors, so the max FDP is 11:00 and the limit is **15:40**. The planned
  stand B14 is blocked until 15:52, and holding for it would breach FDP by 15 min. C31 is legal.
- **MX-0412** (ATA 29, MEL 29-11-01 (M)): inspection plus CRS by a B1 engineer before the next departure.
- **EK813 DXB→CDG**: the rostered captain filed a fatigue report at 14:12.
- **45 broken connections:**
  - 2 unaccompanied minors (to BKK and SIN)
  - a WCHC passenger aged 78
  - a dialysis patient whose MEDIF is home-carrier only
  - a passenger 32 weeks pregnant
  - a blind passenger
  - WCHR and WCHS passengers
  - an 82-year-old travelling with her son
  - a family with a lap infant
  - 5 premium passengers
  - 30 standard passengers, one of whom carries a prompt-injection remark
- Re-accommodation inventory is deliberately scarce (2 to 4 seats on the next flights), so priority decisions
  actually matter.

Files: `data/aircraft_turnaround_disruption.sqlite` (pristine) and `data/scenario_snapshot.json`. Regenerate
them with `python scripts/build_dataset.py`.

## Repository layout

```
app.py                     Streamlit OCC console (guided demo + 9 deep-dive tabs)
run_demo.py                terminal version of the demo (presentation fallback)
aeroturn/
  guards.py                IMMUTABLE safety floors (sealed + SHA-256 pinned in guards.sha256)
  tools.py                 agent tools incl. the 3 required services; strict schemas; dispatcher
  hitl.py                  controller approval / rejection, engineer CRS, sim clock (NOT agent-callable)
  agent.py                 LLM loop + offline policy + completeness check + code autopilot
  reconcile.py             continuous re-validation: withdraw, re-stage, re-plan or escalate
  edge_cases.py            13 sandboxed what-if cases with readable checks
  llm.py                   Ollama / Groq / Gemini via OpenAI-compatible API (stdlib only)
  recovery.py              connection risk + priority-protected planner (+ unconstrained baseline)
  crew.py                  standby crew pairing matcher
  turnaround.py            critical-path (CPM) tracker
  costs.py                 EU261 / duty-of-care / delay / hold analysis
  narrative.py             executive brief, notification templates, grounding check
  db.py · audit.py         schema, invariants, fingerprint · hash-chained audit
  dataset.py               synthetic scenario generator
  faults.py · lab.py       chaos injection · sandboxed experiments
data/                      pristine SQLite + JSON snapshot
docs/                      DEMO_SCRIPT.md · PITCH.md · ARCHITECTURE.md
tests/                     79 pytest tests
```

## Deploying the live demo (Streamlit Community Cloud, free)

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with the GitHub account that owns this repo.
2. Click **Create app** and choose **Yup, I have an app**.
3. Enter repository `RithikhC/EagleX`, branch `main`, main file `app.py`. Under **App URL**, enter
   `aeroturn-eaglex`.
4. Optional: open **Advanced settings**, pick Python 3.12, and under **Secrets** add an LLM key so the hosted
   agent uses a real model instead of the offline policy:
   ```toml
   GROQ_API_KEY = "gsk_..."
   ```
5. Click **Deploy**. Pushing to `main` redeploys automatically.

## Data and sources

Every dataset, public source (EASA flight-time rules, Part-66, ICAO Annex 17, EU261 and its case law including *Gahan v Emirates*), and every modelling assumption is listed in **[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)**.

## Honest limitations

- The flight time limitations are a simplified, EASA-style model (ORO.FTL.205 table, standby and rest rules),
  not a certified UAE GCAA CAR-OPS implementation.
- EU261 treatment and cost rates are illustrative assumptions (`aeroturn/config.py`), not legal advice.
- All flights, people and numbers are synthetic. The flight number EK-812 comes from the problem statement.
  Partner carrier "IP" is fictional.
- Single-node SQLite. In production, the same pattern maps to `SERIALIZABLE` transactions in a reservation
  system, plus an outbox for BHS/DCS messages.

## The dashboard

One screen, with a scenario bar across the top. Each button runs one judged scenario against the live state,
and the panels update in place.

| Button | Scenario | What the dashboard shows |
|---|---|---|
| ▶ Run recovery agent (+ Chaos) | The LLM agent runs the full recovery; a seat is sold mid-batch | Incident banner, event feed (LLM ↔ tools ↔ guards), KPIs go 45 → 0 at risk, 0/10 → 10/10 vulnerable safe, map arcs turn green |
| ⛔ Duty breach | Rogue LLM dispatches EK813 with the inbound crew | Banner: BLOCKED, FTL-001 for every crew member + TURN-001 + MX-001 |
| ⛔ No CRS | Legal crew, but the hydraulic CRS is unsigned | Banner: BLOCKED, MX-001 |
| ⛔ Override | Tool call with `override=True` | Banner: REJECTED, no override exists |
| ⚛ Rollback | Seat conflict at step 7 on a sandbox copy | Banner: rolled back, 0 double bookings, 0 orphaned bags, state identical, retry committed |
| ⚖ Naive AI | Revenue-first optimiser vs the same guards | Banner: 15 violations (PAX-001/002/003/004/006), AeroTurn plan committed |
| ✅ Approve | The human controller approves the queue | Gate moves to C31, crew swap and retime applied |
| 🔧 Release | Clock to inspection end; B2 then B1 engineer sign; departure release | MX-002 refusal, CRS signed, EK813 released |
| 🌍 What if… | Inject a world event into this session (ATC hold +15 / +25, standby captain fatigued, leak found, diversion takes C31), or press Re-validate now | Banner lists what was withdrawn, re-staged, re-planned or escalated; the queue, KPIs and guard board update |
| ↺ | Reset | Back to 14:50 |

Panels:
- Connection network map (status per destination)
- EK813 critical-path timeline (now / STD / EOBT)
- Crew FDP legality: inbound crew per stand, standby captains
- Recovery flow, from missed connection to new flight, coloured by priority tier
- Priority queue in seat-allocation order
- Compensation & care, legacy vs AeroTurn
- Live event feed, rebuilt from the audit log after a reload
- Controller queue with Approve / Reject
- Guard interventions, withdrawals and escalations

The 🧪 **Edge cases** tab runs the 13 cases above (one at a time or all at once), each with its timeline and its ✓/✕ checks. Your live session is not touched.

Detail tabs cover passengers, crew & duty, turnaround & MX, cost & network, and the audit log with the data sources.

![recovery flow, priority queue and cost](docs/img/demo/agent_rowB.png)

See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for the presentation run-sheet and [docs/PITCH.md](docs/PITCH.md)
for the pitch and judge Q&A.
