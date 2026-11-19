# AeroTurn architecture notes

## 1. Control flow of an agent run

```
AeroTurnAgent.run()
 ├─ verify_guard_integrity()            refuse to run if guards.py != pinned SHA-256
 ├─ LLM loop (≤ 24 steps)               OpenAI-compatible chat + native tool calls
 │    └─ tools.dispatch(name, args)     schema check → audit → tool → guards → state
 ├─ missing_steps()                     checks DB state, not what the model claims
 ├─ autopilot (code) for any missing    clearly labelled in the trace
 └─ narrative.executive_brief()         LLM prose + numeric grounding check
```

## 2. State machine of a network change

```
          stage_controller_schedule_change / propose_departure
                               │
                     guards (fresh facts)
                   ┌───────────┴───────────┐
                BLOCKED                 PENDING ──── valid_until passes ──→ EXPIRED
             (never queued)                │
                              hitl.approve(ControllerIdentity)
                                           │
                                 guards re-run (fresh)
                              ┌────────────┴────────────┐
                    BLOCKED_AT_APPROVAL         APPROVED → applied atomically
                    (stays PENDING)
                                     hitl.reject → REJECTED
```

## 3. Atomic rebooking transaction

```
pre-check (guards.check_rebooking_batch)  ── violations → BLOCKED, no transaction
fault injection (presenter only, one-shot)
fingerprint_before = sha256(bookings, bag_routing, booking_history)
BEGIN IMMEDIATE
  for each assignment in priority order:
    SAVEPOINT pax_i
      history CANCEL · DELETE old leg-2 booking
      INSERT new booking          ← UNIQUE(flight, seat), UNIQUE(pax, leg), cabin trigger
      history BOOK
      UPDATE bag_routing (each bag) ← PPBM owner trigger
    RELEASE pax_i
  check_invariants() == all zero  ← else raise
COMMIT                            ← deferred FK bag_routing → bookings
on any exception: ROLLBACK; fingerprint_after == fingerprint_before
```

## 4. Priority model

| Tier | Who | Protection |
|---|---|---|
| P1 Critical-vulnerable | UMNR, MEDA, WCHC, BLND/DEAF/DPNA, PREG | first seats, may be upgraded, UMNR home carrier only and no departure after 22:00, MEDA home carrier only |
| P2 Protected | WCHR, WCHS, lap infants, age ≥ 75, and their PNR group | before P3/P4, +20 min MCT for PRM |
| P3 Premium | F/J cabins, Gold/Platinum | before P4 |
| P4 Standard | everyone else | |

A PNR group takes the best tier of its members and always travels together. A priority inversion is when a
lower-tier group holds an earlier flight that a higher-tier group was legally eligible for and would have fit
on. Any inversion blocks the whole batch.

## 5. Data model (SQLite)

`flights` · `seats` · `bookings` (externals have `pax_id NULL`) · `booking_history` · `passengers` · `bags` ·
`bag_routing` · `crew` · `crew_assignments` · `engineers` · `maintenance_items` · `turnaround_tasks` · `gates` ·
`gate_allocations` · `schedule_changes` · `plans` · `txn_log` · `notifications` · `audit_log` (hash chain) ·
`meta` (sim clock, chaos).
