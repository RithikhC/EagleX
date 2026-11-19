"""AeroTurn: Autonomous Aircraft Turnaround & Atomic Disruption Recovery Agent.

Package layout (agent vs. code separation):

    guards.py      immutable legal / maintenance / passenger-protection floors (pure Python)
    db.py          SQLite schema, constraints, invariants, state fingerprint
    dataset.py     synthetic EK-812 late-aircraft disruption dataset generator
    tools.py       the services the agent may call (incl. the 3 required services)
    hitl.py        human Operations Controller approval gate (never exposed to the LLM)
    recovery.py    connection-risk analysis + priority-protected rebooking planner
    crew.py        standby crew pairing matcher
    turnaround.py  below-wing turnaround critical-path (CPM) tracker
    costs.py       EU261 / duty-of-care / delay cost calculator
    llm.py         LLM providers (Ollama qwen3, Groq, Gemini, offline)
    agent.py       the agent loop: LLM decides *what* to do, tools decide *whether it is allowed*
"""

__version__ = "1.0.0"
