"""Repeatable experiments for the demo: sandboxed rollback, tamper evidence, immutability probes.

Each experiment runs on a fresh copy of the pristine scenario, so it can be
repeated any number of times without touching the live OCC state.
"""

from __future__ import annotations

import shutil
import sqlite3
import uuid
from pathlib import Path

from . import audit, config, db, faults, guards, recovery, tools


def sandbox_path(tag: str = "sandbox") -> Path:
    config.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return config.RUNTIME_DIR / f"{tag}.sqlite"


def fresh_sandbox(tag: str = "sandbox") -> sqlite3.Connection:
    p = sandbox_path(tag)
    db.reset_runtime(p)  # in-place restore, safe even if a stale handle is still open
    return db.connect(p)


def cleanup_runtime(max_age_hours: float = 12) -> int:
    """Delete per-visitor databases nobody has touched for a while (public hosting keeps disk bounded)."""
    import time
    if not config.RUNTIME_DIR.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for p in config.RUNTIME_DIR.glob("*.sqlite"):
        if p.name.startswith(("session_", "sb_", "tamper_", "inbox_")) and p.stat().st_mtime < cutoff:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass  # still open somewhere; try next time
    return removed


def _leg2(conn, pax_ids: list[str]) -> dict[str, str]:
    out = {}
    for pid in pax_ids:
        r = db.one(conn, "SELECT f.flight_no, b.seat_no FROM bookings b JOIN flights f ON f.flight_id = b.flight_id "
                         "WHERE b.pax_id = ? AND b.leg_no = 2", (pid,))
        out[pid] = f"{r['flight_no']} {r['seat_no'] or ''}".strip() if r else "-"
    return out


def _bags(conn, pax_ids: list[str]) -> dict[str, list[str]]:
    out = {}
    for pid in pax_ids:
        out[pid] = [f"{r['bag_tag']}->{r['flight_id'].split('-')[0]}" for r in db.rows(
            conn, "SELECT bag_tag, flight_id FROM bag_routing WHERE pax_id = ? AND leg_no = 2", (pid,))]
    return out


def rollback_experiment(kind: str = "SEAT_CONFLICT", at_step: int = 7, tag: str = "sandbox") -> dict:
    conn = fresh_sandbox(tag)
    try:
        plan = tools.plan_passenger_recovery(conn, actor="LAB")
        full = recovery.load_plan(conn, plan["plan_id"])
        probe_ids = [a["pax_id"] for a in full["assignments"][: max(1, at_step)]]
        before = {"leg2": _leg2(conn, probe_ids), "bags": _bags(conn, probe_ids),
                  "fingerprint": db.state_fingerprint(conn)[:16],
                  "invariants": {k: v["count"] for k, v in db.check_invariants(conn).items() if isinstance(v, dict)}}
        faults.arm(conn, kind, at_step)
        first = tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"], actor="LAB")
        after = {"leg2": _leg2(conn, probe_ids), "bags": _bags(conn, probe_ids),
                 "fingerprint": db.state_fingerprint(conn)[:16],
                 "invariants": {k: v["count"] for k, v in db.check_invariants(conn).items() if isinstance(v, dict)}}
        plan2 = tools.plan_passenger_recovery(conn, actor="LAB")
        retry = tools.execute_atomic_passenger_rebook(conn, plan_id=plan2["plan_id"], actor="LAB")
        final = {"leg2": _leg2(conn, probe_ids), "bags": _bags(conn, probe_ids),
                 "invariants": {k: v["count"] for k, v in db.check_invariants(conn).items() if isinstance(v, dict)},
                 "at_risk_remaining": recovery.connection_risk(conn)["at_risk"]}
        names = {a["pax_id"]: a["name"] for a in full["assignments"]}
        return {"plan_id": plan["plan_id"], "first": first, "retry": retry, "before": before, "after": after,
                "final": final, "probe": [{"pax_id": p, "name": names.get(p, p)} for p in probe_ids],
                "planned": {a["pax_id"]: f"{a['to_flight_no']} {a['seat_no'] or ''}".strip()
                            for a in full["assignments"][: max(1, at_step)]}}
    finally:
        conn.close()


def naive_vs_guarded(tag: str = "sandbox_naive") -> dict:
    """Run an unconstrained revenue-first plan and the AeroTurn plan through the same guard."""
    conn = fresh_sandbox(tag)
    try:
        naive = recovery.plan_naive(conn)
        naive_res = tools.execute_atomic_passenger_rebook(conn, plan_id=naive["plan_id"], actor="UNCONSTRAINED")
        plan = tools.plan_passenger_recovery(conn, actor="LAB")
        res = tools.execute_atomic_passenger_rebook(conn, plan_id=plan["plan_id"], actor="LAB")
        return {"naive_plan": naive, "naive_result": naive_res, "aeroturn_plan_id": plan["plan_id"],
                "aeroturn_result": res}
    finally:
        conn.close()


def tamper_demo(src: Path | None = None) -> dict:
    """Copy the live DB, edit one historic audit row, and show the hash chain detects it."""
    src = Path(src or config.RUNTIME_DB)
    dst = sandbox_path(f"tamper_{uuid.uuid4().hex[:6]}")
    shutil.copyfile(src, dst)
    conn = db.connect(dst)
    try:
        before = audit.verify_chain(conn)
        row = db.one(conn, "SELECT seq, action FROM audit_log WHERE actor = 'GUARD' ORDER BY seq LIMIT 1") or \
            db.one(conn, "SELECT seq, action FROM audit_log ORDER BY seq LIMIT 1")
        if not row:
            return {"before": before, "note": "audit log empty - run the agent first"}
        conn.execute("UPDATE audit_log SET detail = '{\"rules\": []}', action = 'GATE PASS' WHERE seq = ?",
                     (row["seq"],))
        after = audit.verify_chain(conn)
        return {"before": before, "edited_seq": row["seq"], "edited_action": row["action"], "after": after}
    finally:
        conn.close()
        try:
            dst.unlink()
        except OSError:
            pass


def immutability_probe() -> list[dict]:
    """Try to weaken the guards at runtime the way a compromised tool or prompt-injected code might."""
    attempts = [
        ("guards.LIMITS.min_rest_min = 0", lambda: setattr(guards.LIMITS, "min_rest_min", 0)),
        ("guards.LIMITS = SafetyLimits(base_mct_min=0)", lambda: setattr(guards, "LIMITS", None)),
        ("guards.max_fdp_minutes = lambda *a: 9999", lambda: setattr(guards, "max_fdp_minutes", lambda *a: 9999)),
        ("guards.RULES['FTL-001'] = 'ignored'", lambda: guards.RULES.__setitem__("FTL-001", "ignored")),
        ("guards.FDP_TABLE[0] = (0, 1439, 2400)", lambda: guards.FDP_TABLE.__setitem__(0, (0, 1439, 2400))),
        ("del guards.check_departure", lambda: delattr(guards, "check_departure")),
        ("guards.CONTROLLER_GATED_CHANGES.discard('GATE_REASSIGNMENT')",
         lambda: guards.CONTROLLER_GATED_CHANGES.discard("GATE_REASSIGNMENT")),
    ]
    out = []
    for label, fn in attempts:
        try:
            fn()
            out.append({"attempt": label, "result": "SUCCEEDED (!)", "blocked": False})
        except Exception as exc:  # noqa: BLE001
            out.append({"attempt": label, "result": f"{type(exc).__name__}: {str(exc)[:80]}", "blocked": True})
    return out
