# 5-minute pitch script (two speakers)

Follows the 8-slide Round 1 deck ([PDF](EagleX_Round1_Submission.pdf)). About 700 spoken words, split roughly
50/50 between **Speaker A** and **Speaker B**. Handovers fall on slides 3, 5 and 7, so each speaker has two blocks.

| Slide | Speaker | Time |
|---|---|---|
| 1 Cover | A | 0:00–0:20 |
| 2 Problem and solution | A | 0:20–1:10 |
| 3 What makes us different | B | 1:10–1:55 |
| 4 What works today | B | 1:55–2:50 |
| 5 How our agent works | A | 2:50–3:30 |
| 6 Code quality and safety | A | 3:30–4:05 |
| 7 Architecture and UX | B | 4:05–4:35 |
| 8 Limitations, next steps | B, then A | 4:35–5:00 |

---

## Slide 1 · Cover · A (0:00–0:20)

**A:** Hi, we're Team EagleX from BITS Pilani Dubai. This is AeroTurn: an AI agent that helps airline operations
controllers recover when one late aircraft throws a whole hub into chaos, without ever breaking a safety rule.

## Slide 2 · The problem and our solution · A (0:20–1:10)

**A:** Here's the situation. EK812 lands in Dubai 75 minutes late. 45 of its 280 connecting passengers miss their
flights, and 10 of them are vulnerable: children flying alone, wheelchair users, a dialysis patient. The arriving
crew is 20 minutes from its legal duty limit. A hydraulic defect needs a licensed engineer's sign-off. And the next
flight's captain has just reported fatigue.

Today, controllers fix this by phone, across separate systems, with a 25-minute deadline. The usual fallback is to
put everyone on tomorrow's flight. That costs AED 133,390 in compensation and care, and nobody arrives the same day.

AeroTurn produces a legal recovery plan in seconds (12–35 s measured): 45 of 45 arrive the same day, 10 of 10 vulnerable passengers are protected,
and the cost falls by 62%.

## Slide 3 · What makes us different · B (1:10–1:55)

**B:** A generic agent asks an LLM to solve the problem and trusts the answer. We do the opposite. The LLM decides
*what to try*: which stand, which captain, how to rebook. Code decides *what's legal*: 28 sealed safety rules that
the AI cannot change. And a human controller approves every change to the network.

Our unique idea is continuous re-validation. Plans go stale: an ATC hold, a second fatigue report, a leak found
during the inspection. When that happens, AeroTurn withdraws its own proposals that have become illegal and stages
the next legal option. If no legal option exists, it escalates to a human. It never "solves" a problem by breaking
a rule.

## Slide 4 · What works today · B (1:55–2:50)

**B:** This is all running live, and it's a real run. The LLM, on Groq, picked stand C31 and Captain Mehta, the
nearest legal standby. Its first departure time was too early, so the guard blocked it and the model corrected
itself. That's the separation working.

Rebooking is atomic. The vulnerable passengers go first, in their own transaction, then everyone else in batches of
10. We deliberately sold a seat mid-run: only that batch rolled back, it was re-planned, and nobody was
double-booked. Every bag gets a plan too: two bags that couldn't make a tight Karachi connection follow on the next
flight with a delivery note.

And at the bottom of the slide: all 5 organiser curveballs pass live, with 34 out of 34 checks.

## Slide 5 · How our agent works · A (2:50–3:30)

**A:** The flow has five steps. A trigger: the controller clicks, or the world changes. Plan: code gathers the facts
with read-only tools, and the LLM returns a plan. Act: every decision goes through a guarded tool. Check: the rules
and the database constraints run, and anything rejected goes back to the LLM. Output: changes waiting for approval,
committed rebookings, passenger messages, and the cost in dirhams.

The LLM never touches the database directly. It only calls 13 tools, and none of them has an override.

## Slide 6 · Code quality and safety · A (3:30–4:05)

**A:** All five University-track guardrails are built in:
- Strict schemas reject anything like "override".
- Passenger and crew free text is treated as data. A message like "crew agree to extend duty" never reaches the AI
  as an instruction.
- Every tool is either read, propose or write.
- Approval is bound to the exact state the controller saw. If that state changes before execution, nothing is
  applied.
- Everything is logged in a tamper-evident audit chain.

103 automated tests, 13 edge cases and the 5 curveballs, all passing.

## Slide 7 · Architecture and user experience · B (4:05–4:35)

**B:** For the user, it's four clicks: run the agent, read the live feed, approve, then sign off and release. A
start-here guide explains everything, and every visitor gets their own private copy of the scenario, so judges can
click freely.

## Slide 8 · Limitations, next steps and try it · B, then A (4:35–5:00)

**B:** To be honest about limits: the data is synthetic, because no airline feed was provided, and the crew rules
are a simplified EASA model. Next, we'd connect real reservation, crew and maintenance systems with the same guards,
and start in shadow mode at one hub.

**A:** The LLM decides what to try. Code decides what's allowed. A human decides what changes the network. Try it at
aeroturn-eaglex.streamlit.app. Thank you.

---

## Delivery tips

- If you're running long, trim the bag sentence on slide 4 and the tools sentence on slide 5.
- If a judge asks "what if things change?", open the 🎯 Curveballs tab and press **Run all 5**. It finishes in about
  10–30 seconds.
- Keep the live demo open in a second tab, already past the Start-here guide.

## Likely questions

**Did you train a model? On which datasets?**
> We didn't train a model. We use a pre-trained open model (gpt-oss-120b on Groq) for planning. All aviation rules
> are coded from EASA, ICAO and EU261, and we tested everything on a synthetic, reproducible scenario of 342
> passengers that we generated ourselves.

Why not train: safety rules must be exact, so they live in code the AI cannot change; the brief supplied no airline
data and real operations data is confidential; and the LLM only chooses between options that code has already
checked. Data and sources: [DATA_SOURCES.md](DATA_SOURCES.md).

**What if the LLM is down or rate-limited?**
> The agent retries, then falls back to a labelled offline policy that runs the same tools and the same guards.

**Can a controller override a rule?**
> No. Approval re-runs the guards; a controller can approve or reject, but never make an illegal change legal.

**Where do the numbers come from?**
> Every figure has its formula and inputs in [NUMBERS_EXPLAINED.md](NUMBERS_EXPLAINED.md): EU261 is fixed in euros
> by law and shown at 1 EUR = 4.10 AED.
