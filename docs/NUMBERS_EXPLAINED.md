# Every number in the demo, and where it comes from

This is a presenter's cheat sheet, not part of the demo. Every figure below is computed by the code from the
scenario data and a small set of stated inputs. Nothing is typed into the dashboard by hand. Each section gives
the formula, the inputs, the arithmetic, and what to say if a judge challenges it.

Three kinds of input:
- **Law or regulation**: EU261 amounts, EASA crew-duty tables. Not ours to choose.
- **Scenario facts**: from the problem statement, e.g. 75 minutes late and crew 20 minutes from the limit.
- **Our assumptions**: commercial rates and buffers. Listed in `aeroturn/config.py` and `aeroturn/guards.py`,
  and in [DATA_SOURCES.md](DATA_SOURCES.md). Change them and every number updates.

Times are Dubai local (GST). Money is in UAE dirhams (AED).

---

## 1. The disruption (top row of KPIs)

| Number on screen | Where it comes from |
|---|---|
| **EK812 in-block 15:20, +75 min** | Scheduled arrival 14:05; the aircraft lands at 15:12 and taxis 8 minutes to stand C31. 15:20 − 14:05 = 75 minutes, as in the brief |
| **Inbound crew FDP 20 min, limit 15:40** | The crew reported at 04:40 and flew 2 sectors. The EASA table gives 11:00 for a duty starting between 00:00 and 04:59 (the night hours count against you). 04:40 + 11:00 = **15:40**. On blocks at 15:20 leaves **20 min** |
| **45 connections at risk (of 280)** | A connection breaks when in-block time + the passenger's minimum connection time (MCT) is later than the onward departure, or when bags have less than 45 min. With in-block 15:20, 45 of the 280 connecting passengers fail that test |
| **10 vulnerable** | Of the 45, 10 are tier P1/P2: unaccompanied minors, medical case, wheelchair users, blind, pregnant, infant |
| **EK813 off-blocks 17:15 (+65)** | Critical path, section 4. Scheduled 16:10, so 65 minutes late |
| **MX-0412 Open / NO-GO** | The hydraulic defect blocks dispatch until a B1 engineer signs the certificate of release to service |

**Minimum connection time per passenger** (`guards.pax_mct_minutes`):

| Passenger | MCT | Why |
|---|---:|---|
| Standard | 60 min | Generic international transfer (our assumption, not DXB's published figure) |
| Wheelchair / blind / deaf (PRM) | 60 + 20 = **80 min** | Assistance hand-over takes longer |
| Medical (MEDA) | 60 + 20 = 80 min | Medical hand-over |
| Unaccompanied minor | 60 + 15 = 75 min | Escort hand-over |
| Remote stand arrival | +25 min on top | Bus from the aircraft to the terminal |
| Checked bags | at least 45 min | Bag transfer time |

> *"Mr Qureshi in a wheelchair needs 80 minutes: 15:20 + 80 = 16:40, so the 16:35 Karachi flight is illegal for
> him but fine for a standard passenger, who needs only until 16:20."*

---

## 2. The stand decision (B14 vs C31 vs R205)

| Stand | Taxi | In-block | Inbound crew margin (limit 15:40) | Connections broken |
|---|---:|---|---:|---:|
| B14 (planned) | 6 min | **15:55**: EK2104 occupies B14 until 15:52, plus 3 min to clear | **−15 min: illegal** | 56 |
| **C31** | 8 min | 15:12 + 8 = **15:20** | **+20 min** | **45** |
| R205 (remote) | 11 min | 15:12 + 11 = 15:23 | +17 min | 56: everyone needs +25 min for the bus |

C31 wins: the crew stays legal and it breaks the fewest connections.

**Decision deadline 15:15** = C31 in-block 15:20 minus 5 minutes. The stand must be confirmed before the
aircraft turns off the runway (our assumption). After 15:15 the change expires and cannot be approved.

---

## 3. The replacement captain (crew chart)

EK813 leaves at 17:15 and the flight to Paris takes 7 hours, so duty ends at **00:15**. A captain is legal only if
their limit is later than that.

| Captain | Report time | Max duty and why | Limit | Margin |
|---|---|---|---|---:|
| **S-04 Mehta** (chosen) | 14:50 + 10 min call-out + 9 min away = **15:09** | Airport standby since 14:00 is only 1h09, under 4h, so no reduction. Table for a 15:00–15:29 start, 1 sector: **12:00** | 03:09 | **+2h54** |
| S-02 Farouk | 14:50 + 10 + 35 = 15:35 | Home standby since 12:00 is 3h35, under 6h, so no reduction. Table for 15:30–15:59: 11:45 | 03:20 | +3h05 (legal, but further away) |
| C-A01 Okafor (inbound captain) | already on duty since 04:40 | 11:00 − 30 min for a 3rd sector = **10:30** | 15:10 | **−9h05: FTL-001** |
| S-01 Becker | 15:06 | Airport standby since 06:00 = 9h06. Every minute over 4h comes off: 546 − 240 = **306 min**. 12:00 − 5:06 = **6h54**. Airport standby + duty is also capped at 16h: 06:00 + 16h = 22:00 | 22:00 | **−2h15: FTL-001** |
| S-03 Romano | | Rated on the A380 only, aircraft is a 777 | | **FTL-003** |
| S-05 Lindqvist | | Only 9h rest since the last duty, minimum 12h | | **FTL-002** |

> *"Okafor is 0 minutes away but would end his duty 9 hours over the limit. Becker is 6 minutes away, but she's
> been on airport standby since 6 am, and the rules take that time off her duty limit. Mehta is the nearest legal
> captain."*

---

## 4. EK813 critical path (17:15)

| Task | Start | Duration | End | Why it starts then |
|---|---|---:|---|---|
| Hydraulic inspection + CRS (B1 engineer) | 15:35 | 55 min | 16:30 | Not before on-blocks + 15 min for chocks and safety (15:20 + 15) |
| Boarding | 16:30 | 35 min | 17:05 | Can't board until the aircraft is certified |
| Doors, load sheet, pushback | 17:05 | 10 min | **17:15** | |

Everything else (deplaning, cleaning, catering, fuel, bags) fits in the slack around these. Scheduled 16:10, so
the delay is **+65 min**. A retime earlier than 17:15 is refused by guard TURN-001: that's the correction the
LLM makes in the demo.

---

## 5. Passenger costs: legacy vs AeroTurn

### The rules (EU261 and duty of care)

EK812 left from Larnaca (EU) on one booking, so EU261 covers each passenger's **whole journey to the final
destination** (Wegener C-537/17; applied to an Emirates connection via Dubai in *Gahan v Emirates*).

| Final-arrival delay | Distance ≤ 1,500 km | ≤ 3,500 km | > 3,500 km |
|---|---:|---:|---:|
| Under 3 h | €0 | €0 | €0 |
| 3 to 4 h | €250 | €400 | **€300** (halved, Art. 7(2)(c)) |
| 4 h or more | €250 | €400 | **€600** |

- Distance is great-circle from Larnaca to the final destination. Every destination except Karachi (3,399 km) is
  over 3,500 km.
- The lap infant flies free, so no compensation (Art. 3(3)).
- Meals: AED 100 when the wait for the new flight is 2 h or more.
- Hotel: AED 550 when the new flight is the next day.
- EUR is converted at 1 EUR = 4.10 AED. EU261 is fixed in euros by law.

### Legacy: rebook everyone on the same flight tomorrow (+24 h)

| Item | Arithmetic | AED |
|---|---|---:|
| EU261 | 39 passengers × €600 + 5 Karachi × €400 = €25,400 (the infant gets nothing) × 4.10 | 104,140 |
| Hotel | 45 × 550 | 24,750 |
| Meals | 45 × 100 | 4,500 |
| **Total** | | **133,390** |

Nobody arrives the same day (0/45).

### AeroTurn: rebook the same day (the recorded demo run, no hold)

| Group | Passengers | Arrival delay | EU261 each | |
|---|---:|---|---:|---|
| Arrive under 3 h late | 21 | e.g. Bangkok 18:25 flight: 160 min | €0 | Bangkok 6, Mumbai 7, Delhi 3, Karachi 5 |
| 3–4 h late, long-haul | 10 | e.g. Johannesburg 235 min | €300 | Johannesburg 4, Manila 3, Singapore 3 |
| 4 h+ late | 14 | e.g. Sydney 353 min | €600 | Bangkok 3, Delhi 2, Manila 3, Singapore 2, Sydney 4 |

| Item | Arithmetic | AED |
|---|---|---:|
| EU261 | 14 × €600 + 10 × €300 = €11,400 × 4.10 | 46,740 |
| Meals | 37 passengers wait 2 h or more × 100 | 3,700 |
| Hotel | Nobody overnight | 0 |
| **Total** | | **50,440** |

**Saving: 133,390 − 50,440 = AED 82,950 (−62%)**, and 45/45 arrive the same day.

### With the EK418 hold (the offline-policy run, and the README figure)

The 4 Sydney passengers stay on EK418, which waits 8 minutes, so their cost falls from 4 × (2,460 + 100) =
**10,240** to 0. 50,440 − 10,240 = **AED 40,200 (−70%)**.

> *"Why does AeroTurn sometimes show 62% and sometimes 70%? The difference is one decision: whether to hold the
> Sydney flight 8 minutes. The LLM didn't propose it in that run; the offline policy did. Both are valid; the
> controller decides."*

---

## 6. The hold-or-rebook decision (EK418 to Sydney)

| | Arithmetic | AED |
|---|---|---:|
| Hold needed | In-block 15:20 + 60 min MCT = 16:20; EK418 leaves 16:12, so **8 min** | |
| **Cost to hold** | 8 min × (AED 400 aircraft + AED 1.50 × 449 people on board) = 8 × 1,073.50 | **8,588** |
| **Cost to rebook** | 4 passengers onto EK414 at 22:05 (353 min late): 4 × (€600 × 4.10 + AED 100 meal) | **10,240** |
| Net saving | 10,240 − 8,588 | 1,652 |

A hold is recommended only if:
- it's 15 minutes or less (commercial policy; the hard safety cap is 30, guard NET-001);
- it saves at least **AED 1,000** net, because the delay estimate itself is uncertain.

EK418 passes both, so it is staged for the controller. Other flights don't pass. Example: holding the Delhi flight
for 25 minutes would cost AED 22,412 to save AED 5,120.

**Hold length is chosen per passenger.** In edge case EC-07, holding the last flight to Kuala Lumpur for all 11
passengers would take 23 minutes. A 3-minute hold protects 10 of them: 3 × (400 + 1.50 × 324) = **AED 2,658**,
instead of **AED 31,100** to put them up overnight. A passenger with no seat today is costed as stranded until
tomorrow: hotel, meals and full EU261.

---

## 7. Network cost (bottom of the cost panel)

| Item | Arithmetic | AED |
|---|---|---:|
| EK813 delay | 65 min × (AED 400 + AED 1.50 × 334 on board) = 65 × 901 | 58,565 |
| Knock-on to the return flight | 65 min delay − 30 min spare ground time at Paris = 35 min × AED 400 | 14,000 |
| **AeroTurn network total** (no hold) | 50,440 + 58,565 + 14,000 | **123,005** ("AED 123k") |
| AeroTurn with the EK418 hold | 40,200 + 58,565 + 14,000 + 8,588 | 121,353 |
| **Legacy network total** | 133,390 + 58,565 + 14,000 | **205,955** ("AED 206k") |

EK813 itself pays no EU261: it departs Dubai on a non-EU airline (Art. 3(1)).

---

## 8. Our assumptions, and how to defend them

| Input | Value | How to defend it |
|---|---|---|
| Aircraft delay cost | AED 400/min (≈ €100) | EUROCONTROL's reference values for tactical delay at the gate are higher (around €166/min reported), so ours is **conservative**: it makes holds look more expensive, not cheaper |
| Passenger time on a held flight | AED 1.50 per person per minute (≈ €22/hour) | An illustrative value of passengers' time. It's why holding a full 777 is expensive: 449 people × 8 min |
| Meal voucher | AED 100 | EU261 Art. 9 requires meals "in reasonable relation to the waiting time". We pay from 2 h, which is generous for long-haul (the law's threshold rises with distance) |
| Hotel + transport | AED 550 per person per night | An airport-hotel rate assumption for Dubai |
| Exchange rate | 1 EUR = 4.10 AED | The AED is pegged to the US dollar, so EUR→AED follows EUR/USD. 4.10 is the mid-market reference used (27 Oct 2026); change `EUR_TO_AED` to the day's rate |
| Base MCT | 60 min | Generic. Not DXB's published figure |
| Extra MCT | +20 PRM / medical, +15 minor, +25 remote stand, bags ≥ 45 | Hand-over and bussing time |
| Gate decision buffer | 5 min before in-block | Time to tell the crew and stand before arrival |
| Stand clearance | 3 min after the previous aircraft leaves | Pushback and stand check |
| Standby call-out | 10 min + travel time | |
| Paris spare ground time | 30 min | Absorbs part of the delay on the return flight |
| Hold policy | ≤ 15 min recommended, ≥ AED 1,000 net, hard cap 30 min | Network stability: holds spread delay to everyone on board |

**If a judge says "your numbers are made up":**

> *"The legal amounts are from EU261 and the crew limits are from the EASA tables. Those aren't ours. The
> commercial rates are assumptions, listed in one file, and deliberately conservative. Change any of them and
> every number on the dashboard recalculates. The comparison holds because both strategies use the same
> rates."*

---

## 9. Other numbers you may be asked about

| Number | Meaning |
|---|---|
| 342 / 280 / 45 / 10 | Passengers on EK812 / connecting / broken connections / vulnerable among them (dataset designed to match the brief) |
| 334 and 449 | People on board EK813 and EK418 (used in the delay and hold costs) |
| 15 violations | The naive revenue-first plan: 11 vulnerable passengers served after less vulnerable ones (PAX-001), and one each of the minor, medical, connection-time and family-split rules |
| 6 reverted, step 7 | In the rollback demo, the injected seat conflict hits the 7th booking; the 6 already written are undone |
| 13 / 67 | Edge cases / checks; 9 resolved automatically, 4 escalated |
| 86 | Automated tests |

Regenerate any of this yourself: `python run_demo.py --yes` prints every verdict, and the 💶 *Cost & network* tab
shows the per-passenger table behind sections 5 and 6.
