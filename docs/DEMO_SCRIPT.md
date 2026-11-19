# AeroTurn: live demo run-sheet (about 6 minutes)

**Before you go on stage**

Read [NUMBERS_EXPLAINED.md](NUMBERS_EXPLAINED.md): how every number on the dashboard is calculated, with
answers for judges who challenge them.


1. Open the live demo (https://aeroturn-eaglex.streamlit.app) or run `streamlit run app.py`, in full screen.
   The 📊 **Operations** dashboard opens first.
2. Press **↺** (right end of the scenario bar). The clock should read 14:50, the KPIs 45 at risk / 0/10 vulnerable,
   and the controller queue 0.
3. Check the 🧠 badge in the header:
   - It should show a model, e.g. `openai/gpt-oss-120b · groq · plan-and-execute`.
   - If it says "offline policy", the Wi-Fi or the key is down. Everything still works, labelled "no LLM".
4. Optional: the sidebar (› at top left) holds the controller name, the agent-brain choice and the clock.
5. Backup if the browser dies: `python run_demo.py` in a terminal.

The scenario bar, left to right:
**▶ Run recovery agent · Chaos · ⛔ Duty breach · ⛔ No CRS · ⛔ Override · ⚛ Rollback · ⚖ Naive AI · ✅ Approve · 🔧 Release · 🌍 What if… · ↺**

---

## 0:00 · The hook (30 s): just point at the dashboard

> "EK812 from Larnaca blocks in at 15:20, 75 minutes late. 280 passengers connect here, and 45 of those
> connections just broke. Look at the red arcs on the map. The crew has 20 minutes of legal duty left. A
> hydraulic defect needs a licensed engineer's signature. The outbound captain just filed a fatigue report."

KPIs: **15:20 LATE · 20 min TIGHT · 45 AT RISK · 0/10 EXPOSED · MX-0412 NO-GO**.

## 0:30 · ▶ Run recovery agent, with Chaos on (60 s)

Talk over the incident banner and the event feed:

- "The LLM reads a digest of the situation and decides: gate C31, the nearest legal standby captain, a retime,
  and how to rebook."
- On the **crew duty chart**: "Holding for gate B14 puts the crew 15 minutes over. That's the red bar. Captain
  Okafor is 0 minutes away but illegal, and Captain Becker's long airport standby cuts her FDP to 6h54."
- "Watch: the model proposed retiming to 16:30. The guard blocked it, TURN-001, because that's earlier than the
  critical path. The model corrected itself to 17:20. That's the separation: the LLM proposes, code decides
  what's legal."
- "Chaos sold a seat mid-batch. Rollback, re-plan, commit: 45 passengers and 48 bags in one transaction."

KPIs flip to **0 CLEAR · 10/10 SAFE · 3 PENDING · about AED 83k SAVED**, and the map arcs turn green.

## 1:30 · Guards vs a rogue AI (60 s)

Click **⛔ Duty breach**, then **⛔ No CRS**, then **⛔ Override**. Each one produces a red banner:
- FTL-001 for all 13 crew, plus TURN-001 and MX-001
- MX-001 on its own
- "unknown argument 'override': no overrides exist"

> "These rules are plain Python in a sealed module. Assigning to it raises an error, the file is SHA-256
> pinned, and the agent refuses to start if anyone edits it. There is no override parameter anywhere."

## 2:30 · ⚛ Rollback (40 s)

Banner: **step 7 · 6 reverted · state identical YES · 0 double bookings · 0 orphaned bags · retry COMMITTED**.

> "Four layers: a guard pre-check, UNIQUE constraints, an invariant scan inside the transaction, and a deferred
> foreign key from bags to bookings at COMMIT. A bag cannot be committed onto a flight its owner is not on."

## 3:10 · Vulnerable priority (50 s)

Point at the **priority queue** (P1 UMNR, UMNR, MEDA, WCHC, BLND, PREG, then P2) and the **recovery flow**,
whose lightest bands are P1.

> "Lina, 10, flying alone, gets the 18:25 to Bangkok: unaccompanied minors stay on our metal and never leave
> after 22:00. Mr Qureshi in a wheelchair needs 80 minutes to connect, so the 16:35 Karachi flight is illegal
> for him, though legal for others."

Click **⚖ Naive AI**: "An unconstrained revenue-first optimiser gets **15 violations**. The same guard
blocks it."

## 4:00 · The controller (45 s)

In the **Operations Controller queue**, press **Approve** on GATE_REASSIGNMENT (or **✅ Approve** for all).

> "Approval re-runs the guards with fresh facts, and decisions expire: wait past 15:15 and the gate change
> is dead, because the crew would be illegal by then. The agent has no way to approve anything."

### Optional · 🌍 What if… (30 s, if a judge asks "what if things change?")

After the agent run, open **🌍 What if…** and click **Medical diversion takes stand C31**.

> "Stand C31 just went to a diversion. AeroTurn withdrew its own C31 proposal (GATE-001) and staged R205
> before anyone could approve a clash."

For the full catalogue, open the **🧪 Edge cases** tab and press **▶ Run all 13** (about 20 s): 13/13, 67/67
checks, 9 resolved automatically, 4 escalated to humans. Open the EC-07 timeline to show the 3-minute EK346 hold
that protects 10 passengers.

## 4:45 · 🔧 Release (40 s)

The banner shows, in order:
1. Clock → 16:30
2. **B2 avionics engineer REFUSED (MX-002)**: wrong licence for a hydraulic system
3. B1 engineer SIGNED
4. Departure release PENDING → APPROVED

KPIs: **MX-0412 Signed · EK813 RELEASED**.

## 5:25 · Close (35 s)

Point at **Compensation & care**: legacy AED 133k against AeroTurn AED 50k, with 45/45 still arriving today. (EU261 is set in euros by law; the dashboard converts at 1 EUR = 4.10 AED.) Then the
**Guard interventions** board and the **event feed**.

> "The LLM decides what to try. Code decides what is allowed. A human decides what changes the network."

---

### If something goes wrong

| Problem | Fix |
|---|---|
| Header says "offline policy" | Fine: same workflow, deterministic, labelled honestly. Or fix the key in Settings |
| "rate limit, waiting Ns" in the feed | Groq free tier; it retries automatically within seconds |
| Clicked out of order | **↺** resets instantly |
| Gate approval says EXPIRED | The clock passed 15:15 (🔧 Release moves it to 16:30). Press ↺ and approve the gate before releasing |
| Browser dies | `python run_demo.py` |
| You injected a world event by mistake | **↺** resets; edge cases never touch the live session |
