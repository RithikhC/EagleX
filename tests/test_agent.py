"""Agent loop tests: offline policy, and an LLM brain driven through a fake OpenAI-compatible server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from aeroturn import agent, db, faults, recovery
from aeroturn.llm import OpenAICompatClient


def test_offline_agent_completes_full_recovery(conn):
    faults.arm(conn, "SEAT_CONFLICT", 5)
    a = agent.AeroTurnAgent(conn, None)
    res = a.run()
    kinds = [e["kind"] for e in res["trace"]]
    assert "txn_rollback" in kinds and "txn_commit" in kinds and "guard_block" in kinds
    assert a.missing_steps() == []
    risk = recovery.connection_risk(conn)
    assert risk["at_risk"] == 0 and risk["awaiting_hold_decision"] == 4   # EK418 hold awaits the controller
    pending = {r["change_type"] for r in db.rows(conn, "SELECT change_type FROM schedule_changes WHERE status = 'PENDING'")}
    assert pending == {"GATE_REASSIGNMENT", "HOLD_FLIGHT", "CREW_SWAP", "RETIME"}
    assert db.one(conn, "SELECT COUNT(*) AS n FROM notifications")["n"] == 41
    assert res["brief"]["grounding"]["grounded"]
    assert db.check_invariants(conn)["all_clear"]


class _FakeLLM(BaseHTTPRequestHandler):
    script: list = []
    requests: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode())
        _FakeLLM.requests.append(body)
        if "tools" not in body:  # executive brief call
            msg = {"role": "assistant", "content": "**Situation** EK812 in-block 15:20. We saved EUR 99,999."}
        elif _FakeLLM.script:
            msg = _FakeLLM.script.pop(0)
        else:
            msg = {"role": "assistant", "content": "All done."}
        out = json.dumps({"choices": [{"message": msg}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def _call(name, args, i):
    return {"role": "assistant", "content": f"<think>step {i}</think>Calling {name}.",
            "tool_calls": [{"id": f"c{i}", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def test_llm_agent_is_contained_by_tools_and_guards(conn):
    crew_a = [r["crew_id"] for r in db.rows(conn, "SELECT crew_id FROM crew_assignments WHERE flight_id = 'EK812-1121'")]
    _FakeLLM.requests = []
    _FakeLLM.script = [
        _call("get_turnaround_and_crew_state", {}, 1),
        # a misbehaving model tries an override argument ...
        _call("propose_departure", {"flight_no": "EK813", "off_blocks": "16:35", "override": True}, 2),
        # ... then tries to dispatch with the illegal inbound crew
        _call("propose_departure", {"flight_no": "EK813", "off_blocks": "16:35", "crew_ids": crew_a}, 3),
        # ... then tries to approve its own change
        _call("approve_change", {"change_id": "CHG-1"}, 4),
        # ... then writes a notification template with hard-coded facts
        _call("send_passenger_notifications", {"templates": {"STANDARD": "Dear {first_name}, take EK372 at 18:25."}}, 5),
        _call("stage_controller_schedule_change", {"change_type": "GATE_REASSIGNMENT", "flight_no": "EK812",
                                                   "details": {"new_gate": "C31"}, "justification": "crew legal"}, 6),
    ]
    srv = HTTPServer(("127.0.0.1", 0), _FakeLLM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        client = OpenAICompatClient("fake", f"http://127.0.0.1:{srv.server_port}/v1", "k", "qwen3:fake")
        a = agent.AeroTurnAgent(conn, client, max_steps=12)
        res = a.run()
    finally:
        srv.shutdown()
    trace = res["trace"]
    titles = " | ".join(e["title"] for e in trace)
    assert any(e["kind"] == "thinking" for e in trace)                       # qwen3 <think> captured separately
    assert "REJECTED_INVALID_ARGS" in titles                                 # override argument refused
    assert any(e["kind"] == "guard_block" and "FTL-001" in e["title"] for e in trace)
    assert "approve_change: REJECTED" in titles                              # no approval tool exists
    assert any(e["kind"] == "autopilot" for e in trace)                      # model stalled -> code autopilot
    assert a.missing_steps() == []
    assert res["brief"]["grounding"]["ungrounded"] == ["99999"]              # fabricated number flagged
    # the model saw tool results and the qwen3 no-think switch
    first = _FakeLLM.requests[0]
    assert first["messages"][0]["content"].endswith("/no_think")
    assert any(m.get("role") == "tool" for m in _FakeLLM.requests[-2]["messages"])
    assert not any(t["function"]["name"].startswith("approve") for t in first["tools"])
    assert db.check_invariants(conn)["all_clear"]


class _FakePlanner(BaseHTTPRequestHandler):
    calls: list = []
    PLAN = {
        "analysis": "Crew FDP forbids holding for B14; C31 keeps them legal. EK813 needs a new captain.",
        "gate": {"new_gate": "C31", "why": "crew legal, fewest misconnects"},
        "holds": [{"flight_no": "EK418", "hold_min": 8, "why": "cheaper than rebooking 4 passengers"}],
        "crew_swap": {"remove_crew_id": "C-B01", "add_crew_id": "S-04", "why": "nearest legal captain"},
        "retime": {"new_etd": "16:30", "why": "as early as possible"},          # illegal: before EOBT 17:15
        "rebooking_objective": "earliest_arrival", "objective_why": "minimise delay",
        "templates": {"STANDARD": "Dear {first_name}, you now fly {new_flight} at {dep_time}.",
                      "PREMIUM": "Dear {first_name}, take EK372 at 18:25."},     # hard-coded facts: must be rejected
    }

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode())
        _FakePlanner.calls.append(body)
        if "response_format" in body:
            n = sum(1 for b in _FakePlanner.calls if "response_format" in b)
            payload = self.PLAN if n == 1 else {"retime": {"new_etd": "17:15", "why": "critical-path EOBT"}}
            msg = {"role": "assistant", "content": json.dumps(payload)}
        else:
            msg = {"role": "assistant", "content": "**Situation** EK812 in-block 15:20."}
        out = json.dumps({"choices": [{"message": msg}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def test_plan_and_execute_mode_replans_after_guard_block(conn):
    _FakePlanner.calls = []
    srv = HTTPServer(("127.0.0.1", 0), _FakePlanner)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        client = OpenAICompatClient("groq", f"http://127.0.0.1:{srv.server_port}/v1", "k", "openai/gpt-oss-fake")
        a = agent.AeroTurnAgent(conn, client)
        assert a.mode == "plan"
        res = a.run()
    finally:
        srv.shutdown()
    trace = res["trace"]
    assert any(e["kind"] == "guard_block" and "TURN-001" in e["title"] for e in trace)   # 16:30 refused
    staged = {(r["change_type"], r["status"]): r for r in db.rows(conn, "SELECT * FROM schedule_changes")}
    assert ("RETIME", "PENDING") in staged and '"17:15"' in staged[("RETIME", "PENDING")]["payload"]
    assert ("HOLD_FLIGHT", "PENDING") in staged and ("GATE_REASSIGNMENT", "PENDING") in staged
    assert sum(1 for b in _FakePlanner.calls if "response_format" in b) == 2              # plan + one replan
    assert any(e["kind"] == "error" and "Template validator" in e["title"] for e in trace)
    assert not any(e["kind"] == "autopilot" for e in trace)                               # LLM covered everything
    assert a.missing_steps() == []
    assert recovery.connection_risk(conn)["at_risk"] == 0 and db.check_invariants(conn)["all_clear"]
