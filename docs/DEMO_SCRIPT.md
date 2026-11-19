# AeroTurn: live demo run-sheet (about 6 minutes)

**Before you go on stage**

1. `streamlit run app.py`, then open http://localhost:8501 in full screen and pick the **🎬 Guided demo** tab.
2. Sidebar: press **↺ Reset scenario**. The clock should read 14:50, the gate decision 25 min, and *For controller* 0.
3. Sidebar → **Agent brain**:
   - `auto` if Ollama qwen3 is running locally or a Groq/Gemini key is in `.env`.
   - Otherwise `offline`, which is labelled "no LLM" and is fully deterministic.
4. Sidebar → Operations Controller: type the name of the team member who will play the controller.
5. Backup: `python run_demo.py` runs the same story in a terminal, and you approve with `y`.

---

## 0:00 · The hook (Situation tab, 30 s)

> "EK812 from Larnaca is landing 75 minutes late. 280 passengers connect in Dubai, and 45 of those connections
> just broke, including two unaccompanied children and a dialysis patient. The crew has 20 minutes left before
> breaching legal duty time. A hydraulic defect needs a licensed engineer's signature. And the outbound
> captain just filed a fatigue report."

Point at the KPI strip: **15:20 / +75**, **crew margin 20 min**, **45 at risk**, **MX-0412 Open**.

## 0:30 · ① Agent run (60 s)

Leave the **Inject mid-way seat conflict** toggle on and press **▶ Run AeroTurn agent**. Talk over the lanes as they stream:

- **Purple, LLM brain:** "The agent reasons. It notices that holding for the planned gate B14 breaches crew duty time."
- **Amber, HITL staged:** "It *stages* C31 for me. It cannot move a gate itself."
- "It weighs holding departing connections. Holding the Sydney flight 8 minutes saves 4 connections for less
  than rebooking them 6 hours later; every other hold costs more than it saves. That is staged too."
- "It finds the nearest legal standby captain. Note what it rejected: the inbound captain is 0 minutes away
  but would be 9 hours over duty, and another captain's airport standby since 06:00 counts against her."
- **Red, guard block:** "It even asks for a departure release, and code says no: no legal captain yet, and no
  maintenance sign-off."
- **Red, rollback:** "Now we sabotage it. A web sales channel sells a seat mid-batch. Watch."
- **Green, commit:** "Full rollback, re-plan on fresh inventory, commit. 45 passengers and 48 bags in one transaction."

KPIs now show **0 at risk (4 await hold decision)**, **10/10 vulnerable safe**, **4 for controller**.

## 1:30 · ② Guards block unsafe departures (60 s)

Click the four **Rogue** buttons, left to right:

1. *Depart 16:35 with the inbound crew*: **FTL-001** ×13, plus TURN-001 and MX-001.
2. *Depart before hydraulic CRS*: legal crew, but **MX-001** blocks it.
3. *override=True*: **REJECTED_INVALID_ARGS**. "There is no override parameter anywhere. The concept does not exist."
4. *Agent self-approval*: **ApprovalError**. "Approval is not even in the agent's tool list."

> "These floors are plain Python in a sealed module. Try `guards.LIMITS = ...` and it raises. The file is
> SHA-256 pinned, and the agent refuses to start if anyone edits it."

## 2:30 · ③ Atomic rollback (45 s)

Point at the metrics: **failed at step 7 · 6 provisional steps reverted · state identical YES · double
bookings 0 · orphaned bags 0**. Optionally press **Re-run rollback on sandbox** to show it is repeatable. The
*⚛️ Atomic rebooking* tab shows, passenger by passenger, *planned → before → after rollback → after retry*.

> "Four layers: a guard pre-check, UNIQUE constraints, an invariant scan inside the transaction, and a
> deferred foreign key between bags and bookings at COMMIT. A bag physically cannot be committed onto a flight
> its owner is not on."

## 3:15 · ④ Vulnerable priority (45 s)

The table lists the first 13 seats: P1 UMNR, UMNR, MEDA, WCHC, BLND, PREG, then P2.

> "Lina, 10, flying alone, gets the 18:25 Bangkok flight, not the 21:50, because unaccompanied minors may
> not depart after 22:00 and must stay on our metal. The dialysis patient keeps a carrier his medical
> clearance covers. Mr Qureshi in a wheelchair needs 80 minutes to connect, so the 16:35 Karachi flight is
> illegal for him even though it is legal for others."

Press **Compare: unconstrained revenue-first optimiser**: **BLOCKED** with PAX-001, -002, -003, -004 and -006.
"That is what an unconstrained AI would have done."

## 4:00 · ⑤ Controller approves the gate (45 s)

The controller presses **✅ Approve** on GATE_REASSIGNMENT → C31, then HOLD_FLIGHT EK418 +8 (watch "4 await
hold decision" disappear), then CREW_SWAP and RETIME. Optional: *reject* the hold instead, then press **Rebook
the 4 passengers still at risk** to show the planner picking them up atomically.

> "Approval is not a rubber stamp. The guards run again with fresh facts. If I wait past 15:15 this decision
> expires, because by then the aircraft is holding and the crew is going illegal."

## 4:45 · ⑥ Bonus: maintenance → release (45 s)

1. **⏩ Clock to 16:30**
2. **B2 avionics engineer signs CRS**: **MX-002**, wrong licence for a hydraulic system.
3. **B1 engineer signs CRS**: SIGNED.
4. **Propose EK813 departure release**: PASS → staged → the controller approves → EK813 RELEASED.

## 5:30 · Close (30 s)

Open **💶 Cost & network**: passenger compensation **EUR 33.3k → EUR 9.8k**, network **EUR 52k → EUR 31k**,
45/45 same-day arrivals, and the hold-or-rebook table. Then **📜 Audit**: the chain is intact. Press **Tamper test** and the chain breaks at the edited row.

> "The LLM decides what to try. Code decides what is allowed. A human decides what changes the network.
> That is AeroTurn."

---

### If something goes wrong

| Problem | Fix |
|---|---|
| LLM slow or offline | Sidebar → Agent brain = `offline`; same workflow, deterministic |
| Clicked out of order | Sidebar → **↺ Reset scenario** (instant) |
| Browser dies | `python run_demo.py` in a terminal |
| Gate approval says EXPIRED | The clock passed 15:15. Reset, and approve the gate before advancing the clock |
