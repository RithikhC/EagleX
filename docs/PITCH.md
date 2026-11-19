# AeroTurn: pitch outline and judge Q&A

## Slide outline (8 slides, 3 minutes before the live demo)

1. **The 75-minute problem.** One late wide-body is a network event: gates, crew duty clocks, bags, 280
   connections. Today an OCC controller juggles 6 systems by phone.
2. **Why "just add AI" is dangerous.** An unconstrained optimiser rebooks commercially: premium first,
   one-size-fits-all connection time, children on partner carriers, families split. It also "gets the plane
   out" with an out-of-hours crew. We ran exactly that baseline: **15 guard violations.**
3. **AeroTurn's split.** *The LLM decides what to try. Code decides what is allowed. A human decides what
   changes the network.* (responsibility matrix)
4. **Immutable floors.** Sealed `guards.py` with SHA-256 pin and no override parameter:
   - FDP table, rest, rating, fatigue
   - Licensed CRS
   - P1–P4 vulnerable priority
   - Passenger-specific MCT
   - PPBM
5. **Atomic recovery.** One transaction for 45 passengers and 48 bags, with 4 protection layers. A mid-way
   failure leaves 0 double bookings, 0 orphaned bags and an identical state hash.
6. **Human in the loop that cannot be rubber-stamped.** Changes are staged with justification, guards re-run at
   approval, decisions have deadlines, and the agent cannot approve.
7. **Data & evidence.**
   - Synthetic, reproducible scenario (seed 812, as the brief requires).
   - Rules from EASA ORO.FTL.205 / CS FTL.1.225 / ORO.FTL.235, Part-66 and ICAO Annex 17 PPBM.
   - EU261 Art. 7/9 with *Sturgeon*, *Folkerts* and *Wegener*, plus *Gahan v Emirates* (Manchester → Dubai → Bangkok,
     missed connection, the same pattern as our scenario).
   - Full list: docs/DATA_SOURCES.md.
8. **Impact.**
   - 45/45 connections recovered the same day (41 rebooked, 4 saved by an 8-min hold)
   - 10/10 vulnerable passengers protected
   - Passenger compensation and care: EUR 33k → EUR 9.8k (−70%)
   - Network cost: EUR 52k → EUR 31k

## Numbers to remember

| Metric | Value |
|---|---|
| Passengers / connecting / broken | 342 / 280 / 45 |
| Vulnerable at risk (P1 critical) | 10 (6) |
| Inbound crew FDP limit / margin | 15:40 / 20 min |
| Holding for planned stand B14 | in-block 15:55 → FDP breach by 15 min |
| EK813 critical-path EOBT | 17:15 (+65), hydraulic inspection on critical path |
| Standby captain chosen | S-04, 9 min away, FDP margin 2h54 |
| Legacy vs AeroTurn passenger compensation + care | EUR 33,275 vs EUR 9,825 |
| Network cost (incl. EK813 delay, knock-on, hold) | EUR 51,959 vs EUR 30,746 |
| Connection hold staged | EK418 SYD +8 min: EUR 2,237 vs EUR 2,500 to rebook 4 pax ~6h later |
| Same-day arrivals | 45/45 (legacy 0/45) |
| Unconstrained plan | blocked: 15 violations across PAX-001/002/003/004/006 |
| Tests | 60 passing |

## Anticipated judge questions

**"Where does your data come from? Is it real?"**
The brief supplies no dataset and asks us to synthesise one. Ours is generated from a fixed seed, so it is byte-reproducible. The rules are real and sourced: EASA flight-time tables, CS FTL.1.225 standby, Part-66 licences, ICAO Annex 17 bag matching, EU261 and its case law. Every number we chose ourselves is listed as an assumption in docs/DATA_SOURCES.md.


**"What exactly does the LLM do, if code does all the work?"**
It owns the *judgement layer*:
- reading the situation
- deciding the order of actions
- choosing among legal options (gate, objective, which standby crew to stage)
- explaining trade-offs to the controller
- writing human-facing language

Code owns *facts and permissions*. That is the separation the brief asks for. The trace colours it: purple is
the LLM, blue is code, red is a guard, amber is a human.

**"How do you know the LLM can't bypass the guards?"**
1. The LLM can only call tools, through one dispatcher with strict JSON schemas.
2. No tool exposes an override or force argument, and unknown arguments are rejected.
3. Guards run inside the tools before any write, and again at approval.
4. `guards.py` is a sealed module (assignment raises), its limits are frozen, and its source is SHA-256 pinned.
5. Approval lives in `hitl.py`, which is not in the tool registry and rejects non-human identities.

A test drives a fake LLM through override arguments, an illegal crew, self-approval and fact-bearing
templates, and every attempt fails.

**"What if the LLM hallucinates a flight number in a passenger message?"**
It can't. Templates may only use placeholders such as `{new_flight}` and `{dep_time}`, and the validator
rejects any template containing a flight number, time, seat or gate. Code fills the facts from the database.
The executive brief gets a numeric grounding check, so any number not in the facts is flagged.

**"Why not just use database transactions? Why the extra layers?"**
- Transactions give atomicity.
- The guards give *correctness of intent*, for example priority inversion, which no constraint can express.
- The deferred foreign key gives a structural guarantee that a bag never travels without its passenger.
- The invariant scan catches anything we did not think of, before COMMIT.

**"Is the FTL model real?"**
It is modelled on EASA ORO.FTL.205 Table 2:
- The max FDP depends on report time, minus 30 min per sector above 2, with a 9h floor.
- Standby (CS FTL.1.225): the FDP counts from reporting; airport standby beyond 4h reduces the max FDP, and airport standby + FDP is capped at 16h. Home standby beyond 6h reduces the FDP.
- Home standby over 6h reduces the FDP.
- Minimum rest is 12h.
- Commander's discretion is never planned.

It is simplified and not a certified GCAA implementation, and the README says so.

**"Why EU261 for a flight into Dubai?"**
EK812 departed Larnaca, which is in the EU. Under CJEU *Wegener* (C-537/17), a single-booking journey starting
in the EU is covered to its final destination, and compensation follows the final-arrival delay. That is why
getting the Bangkok passengers onto the 18:25 (arriving under 3h late) instead of the 21:50 matters
financially, not just ethically.

**"Why hold one flight but not the others?"**
Hold cost = minutes × (aircraft cost + EUR 0.40 × every passenger on board), against the EU261 and care cost
of rebooking. Only EK418 (8 min, 4 passengers) is cheaper to hold. Holding the Bangkok flight 55 minutes would
cost EUR 15k to save EUR 2k, and is also above the 30-minute network cap (NET-001). The agent stages the hold,
the planner leaves those 4 passengers alone, and if the controller rejects it, one click rebooks them
atomically.

**"What happens when two controllers or two agents act at once?"**
`BEGIN IMMEDIATE` serialises writers. Plans carry their basis (in-block time), and a stale plan is refused. A
seat sold elsewhere between planning and execution is exactly the chaos case we demo. Changes are staged once:
duplicate staging returns the existing change.

**"How would this go to production?"**
- Swap SQLite for the airline's PSS/DCS APIs behind the same tool interface.
- Map the transaction to `SERIALIZABLE` plus an outbox for BHS and messaging.
- Keep `guards.py` as a reviewed, signed rules package.
- Feed the critical path from ground-handling milestones (A-CDM).

The agent and the guard contract do not change.

**"Why is the offline mode not cheating?"**
It is labelled "no LLM" everywhere. It exists so a demo cannot fail on Wi-Fi, and it runs the *same* tools and
guards. With Ollama qwen3, Groq or Gemini, the LLM drives the tool calls, and if it stalls a labelled code
autopilot completes the mandatory steps.
