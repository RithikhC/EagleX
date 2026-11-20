# Round 1 submission form: answers to paste

## What does your AI agent do?

When a delayed aircraft lands at a hub, one late flight becomes a network crisis: in our scenario EK812 arrives at Dubai 75 minutes late, 45 of its 280 connecting passengers miss their onward flights, the arriving crew is 20 minutes from its legal duty limit, a hydraulic defect needs a licensed engineer's sign-off, and the next flight's captain has reported fatigue. AeroTurn helps airline operations controllers recover from this in under a minute instead of juggling separate systems by phone. On its own, the agent reads the live situation, picks a legal arrival stand, finds the nearest legal standby captain, retimes the departure to the turnaround's critical path, and rebooks all 45 passengers and their 48 bags in one all-or-nothing transaction, with children flying alone, wheelchair users and medical cases served first. It never breaks a safety rule: crew duty limits, maintenance sign-off and passenger priority are enforced by code it cannot change, and every network change waits for a human controller to approve. In the recorded live run it protects 10 of 10 vulnerable passengers, gets 45 of 45 to their destination the same day, and cuts compensation and care from AED 133,390 to AED 50,440.

## How does it work?

Agents and roles: one planning agent (an LLM) decides what to try: the stand, the replacement captain, the departure time, connection holds, how to rebook passengers and the wording of messages. Code does everything else: a tool dispatcher validates every call, sealed safety guards (25 rules in a SHA-256-pinned Python module) decide what is legal, and a re-validation step re-checks pending decisions when the world changes (an ATC hold, a second fatigue report, a leak found), withdrawing anything that became illegal or escalating it to a human.

Tools it calls (13, each classed read, propose or write): get_turnaround_and_crew_state, evaluate_gate_options, find_standby_crew (legal-crew matcher), get_turnaround_critical_path, evaluate_connection_holds, list_disrupted_passengers, plan_passenger_recovery, execute_atomic_passenger_rebook (one SQLite BEGIN / COMMIT / ROLLBACK transaction for seats and bags), stage_controller_schedule_change, propose_departure, send_passenger_notifications, compute_disruption_cost (EU261 and care in AED) and get_controller_queue. The planner's fact-gathering phase is locked to read-only tools; passenger free text is scanned and instruction-like text is withheld before it reaches the LLM.

Data: a synthetic but realistic, reproducible scenario database (seed 812): 342 passengers, 356 bags, 44 flights, 33 crew, 3 maintenance items and 11 turnaround tasks, with airport data from OurAirports and rules from EASA flight-time limitations, EASA Part-66, ICAO Annex 17 and EU Regulation 261/2004.

Human in the loop: the agent can only stage gate changes, crew swaps, retimes, holds and the departure release. A named operations controller approves or rejects each one, the guards run again at approval, decisions expire when their window closes, and a licensed engineer must sign the maintenance certificate. Approval is not one of the agent's tools. Every call, verdict and decision is written to a hash-chained audit log.

## Tech stack

Python 3.12+ with our own agent loop (no framework); Groq API with openai/gpt-oss-120b through an OpenAI-compatible client (Ollama or Google Gemini also supported, with a labelled offline policy when no key is set); SQLite with atomic transactions; Streamlit and Plotly for the dashboard; pytest (86 tests); hosted on Streamlit Community Cloud; code on GitHub.

## Links

| Field | Link |
|---|---|
| Working project (live demo) | https://aeroturn-eaglex.streamlit.app |
| Code (GitHub) | https://github.com/RithikhC/EagleX |
| Presentation (PDF, 8 slides) | https://github.com/RithikhC/EagleX/blob/main/docs/EagleX_Round1_Submission.pdf |
| Demo video (subtitled) | https://github.com/RithikhC/EagleX/blob/main/docs/demo/AeroTurn_demo.mp4 |
| Architecture / workflow diagram | https://github.com/RithikhC/EagleX/blob/main/docs/img/architecture.png |
