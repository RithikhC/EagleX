"""
aeroturn.guards: IMMUTABLE LEGAL, MAINTENANCE AND PASSENGER-PROTECTION FLOORS
=============================================================================

Everything here is plain, deterministic Python: no I/O, no database, no
network, no LLM. The agent (LLM) never calls this module. Tools call it
before they touch state, and the human-approval gate (hitl.py) calls it again
at approval time, so a decision is never acted on with stale facts.

Immutability is enforced in three layers:
  1. Limits live in a frozen dataclass and in read-only MappingProxyType views.
  2. The module object is sealed: ``guards.X = ...`` raises GuardTamperError.
  3. This source file is SHA-256 pinned in ``guards.sha256``. The app shows the
     fingerprint and refuses to run the agent if the guard code was modified
     without re-pinning (scripts/pin_guards.py).

There is no override, force, or emergency parameter anywhere in this module.
That is deliberate.

Regulatory basis (simplified, for the hackathon scenario):
  * FDP table modelled on EASA ORO.FTL.205 Table 2 (acclimatised crew),
    with -30 min per sector above 2 and a 9h floor. Commander's discretion
    can never be planned. Standby per CS FTL.1.225: FDP counts from
    reporting; airport standby beyond 4h reduces the max FDP and airport
    standby + FDP <= 16h; home standby beyond 6h reduces the max FDP.
  * Minimum rest 12h at home base (ORO.FTL.235). Fatigue/sick reports are absolute.
  * Dispatch-blocking deferred defects need a CRS from an appropriately
    licensed (B1 for mechanical systems) and type-authorised engineer, signed
    no earlier than the end of the inspection task.
  * Positive Passenger-Bag Matching (ICAO Annex 17 PPBM): a bag may only be
    routed on a flight its owner is booked on. A bag that cannot make its
    owner's new connection needs an explicit plan (a later flight, screened
    as unaccompanied baggage, plus a delivery note) before the rebooking
    may commit.
  * A CRS from an outside system is validated, never trusted: the signatory
    must be on the licensed-engineer roster and the signature must come after
    the defect was raised and not in the future.
  * Duty limits are not a parameter. No message, request field or approval
    can extend them: the only legal path is a crew that is legal as rostered.
"""

from __future__ import annotations

import hashlib
import math
import sys
import types
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Final, Iterable, Mapping, Sequence


class GuardTamperError(RuntimeError):
    """Raised on any attempt to mutate guard constants or the sealed module."""


# ---------------------------------------------------------------------------
# Rule catalogue
# ---------------------------------------------------------------------------
RULES: Final[Mapping[str, str]] = MappingProxyType({
    "FTL-001": "Projected flight duty period exceeds the legal maximum FDP",
    "FTL-002": "Insufficient rest before duty",
    "FTL-003": "Crew member not type-rated on this aircraft",
    "FTL-004": "Crew member unfit / unavailable (fatigue or sick report is absolute)",
    "FTL-005": "Minimum crew complement not met",
    "FTL-006": "Crew member cannot reach the aircraft before the required report time",
    "MX-001": "Open dispatch-blocking maintenance item has no valid CRS",
    "MX-002": "CRS signatory lacks the required licence or type authorisation",
    "MX-003": "CRS cannot be signed before the inspection task can have been completed",
    "MX-004": "CRS signatory is not on the licensed-engineer roster",
    "MX-005": "CRS timestamp is impossible (before the defect was raised, or in the future)",
    "TURN-001": "Proposed off-blocks is earlier than the turnaround critical-path EOBT",
    "GATE-001": "Gate not available for the required time window",
    "NET-001": "Connection hold exceeds the network maximum hold",
    "PAX-001": "Vulnerable-passenger priority inversion",
    "PAX-002": "Rebooking breaks the passenger-specific minimum connection time",
    "PAX-003": "Unaccompanied minor: overnight, late-night or non-escort-carrier rebooking",
    "PAX-004": "Medical (MEDA) passenger moved off the MEDIF-cleared home carrier",
    "PAX-005": "Involuntary cabin downgrade",
    "PAX-006": "PNR group split across flights",
    "PAX-007": "Rebooked flight does not serve the passenger's destination",
    "PAX-008": "Passenger not permitted in an emergency-exit row",
    "PAX-009": "Passenger is not a disrupted passenger of this event (out of scope)",
    "PAX-010": "Rebooked flight departs before the inbound aircraft is on blocks",
    "BAG-001": "Bag not routed with its passenger (PPBM / orphaned bag)",
    "BAG-002": "Bag minimum transfer time not met",
    "BAG-003": "Bag cannot make its owner's new connection and has no forwarding plan",
    "HITL-001": "Gate / schedule / crew changes require Operations Controller approval",
})

# Change types that may never be executed without a human Operations Controller.
CONTROLLER_GATED_CHANGES: Final[frozenset[str]] = frozenset({
    "GATE_REASSIGNMENT", "RETIME", "CREW_SWAP", "HOLD_FLIGHT",
    "DEPARTURE_RELEASE", "AIRCRAFT_SWAP", "CANCELLATION",
})


@dataclass(frozen=True, slots=True)
class SafetyLimits:
    # Flight time limitations
    fdp_sector_reduction_min: int = 30
    fdp_floor_min: int = 9 * 60
    min_rest_min: int = 12 * 60
    home_standby_free_min: int = 6 * 60
    airport_standby_free_min: int = 4 * 60
    airport_standby_plus_fdp_max_min: int = 16 * 60
    planned_discretion_min: int = 0          # commander's discretion is never planned
    callout_response_min: int = 10           # time to acknowledge a standby call-out
    report_before_off_blocks_min: int = 45   # crew must be at the aircraft this early
    cabin_crew_seats_per_member: int = 50
    # Passenger protection
    base_mct_min: int = 60
    prm_mct_extra_min: int = 20
    meda_mct_extra_min: int = 20
    umnr_mct_extra_min: int = 15
    remote_stand_mct_extra_min: int = 25
    bag_mct_min: int = 45
    umnr_latest_departure: time = time(22, 0)
    umnr_max_wait_min: int = 8 * 60
    elderly_age: int = 75
    child_exit_row_age: int = 15
    # Network
    max_connection_hold_min: int = 30


LIMITS: Final[SafetyLimits] = SafetyLimits()

# EASA-style max daily FDP for acclimatised crew, 1-2 sectors.
# (band start minute-of-day, band end minute-of-day inclusive, max FDP minutes)
FDP_TABLE: Final[tuple[tuple[int, int, int], ...]] = (
    (6 * 60, 13 * 60 + 29, 13 * 60),
    (13 * 60 + 30, 13 * 60 + 59, 12 * 60 + 45),
    (14 * 60, 14 * 60 + 29, 12 * 60 + 30),
    (14 * 60 + 30, 14 * 60 + 59, 12 * 60 + 15),
    (15 * 60, 15 * 60 + 29, 12 * 60),
    (15 * 60 + 30, 15 * 60 + 59, 11 * 60 + 45),
    (16 * 60, 16 * 60 + 29, 11 * 60 + 30),
    (16 * 60 + 30, 16 * 60 + 59, 11 * 60 + 15),
    (17 * 60, 23 * 60 + 59, 11 * 60),
    (0, 4 * 60 + 59, 11 * 60),
    (5 * 60, 5 * 60 + 14, 12 * 60),
    (5 * 60 + 15, 5 * 60 + 29, 12 * 60 + 15),
    (5 * 60 + 30, 5 * 60 + 44, 12 * 60 + 30),
    (5 * 60 + 45, 5 * 60 + 59, 12 * 60 + 45),
)

CABIN_RANK: Final[Mapping[str, int]] = MappingProxyType({"Y": 1, "J": 2, "F": 3})
CRITICAL_SSR: Final[frozenset[str]] = frozenset({"UMNR", "MEDA", "WCHC", "BLND", "DEAF", "DPNA", "PREG"})
PROTECTED_SSR: Final[frozenset[str]] = frozenset({"WCHR", "WCHS", "INFT"})
PRM_SSR: Final[frozenset[str]] = frozenset({"WCHR", "WCHS", "WCHC", "BLND", "DEAF", "DPNA"})
EXIT_ROW_BANNED_SSR: Final[frozenset[str]] = frozenset(
    {"UMNR", "MEDA", "WCHR", "WCHS", "WCHC", "BLND", "DEAF", "DPNA", "PREG", "INFT"})
PREMIUM_LOYALTY: Final[frozenset[str]] = frozenset({"GOLD", "PLATINUM"})
TIER_LABELS: Final[Mapping[int, str]] = MappingProxyType({
    1: "P1 Critical-vulnerable",
    2: "P2 Protected",
    3: "P3 Premium",
    4: "P4 Standard",
})
CRS_LICENCE_FOR_ATA: Final[Mapping[str, frozenset[str]]] = MappingProxyType({
    # Mechanical systems need B1; avionics B2; default B1.
    "29": frozenset({"B1"}),   # hydraulic power
    "32": frozenset({"B1"}),   # landing gear
    "34": frozenset({"B2"}),   # navigation
    "23": frozenset({"B2"}),   # communications
})


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Violation:
    rule: str
    subject: str
    message: str

    def as_dict(self) -> dict:
        return {"rule": self.rule, "title": RULES[self.rule], "subject": self.subject,
                "message": self.message}


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    violations: tuple[Violation, ...] = ()
    checks: tuple[str, ...] = ()
    facts: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "verdict": "PASS" if self.ok else "BLOCKED",
            "violations": [v.as_dict() for v in self.violations],
            "rules_violated": sorted({v.rule for v in self.violations}),
            "checks": list(self.checks),
            "facts": self.facts,
        }


def _verdict(violations: Iterable[Violation], checks: Iterable[str], facts: dict | None = None) -> Verdict:
    vs = tuple(violations)
    return Verdict(ok=not vs, violations=vs, checks=tuple(checks), facts=dict(facts or {}))


# ---------------------------------------------------------------------------
# Flight-time limitations
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class CrewFacts:
    crew_id: str
    name: str
    rank: str                      # CPT / FO / PUR / CC
    type_ratings: tuple[str, ...]
    fitness: str                   # FIT / UNFIT
    duty_kind: str                 # ON_DUTY / ROSTERED / AIRPORT_STANDBY / HOME_STANDBY / OFF
    duty_start: datetime | None    # report time (ON_DUTY/ROSTERED) or standby start
    sectors_flown: int = 0
    rest_before_duty_min: int = 24 * 60
    proximity_min: int = 0
    standby_kind: str | None = None        # AIRPORT / HOME when an ON_DUTY crew member was called from standby
    standby_start: datetime | None = None  # when that standby began


def max_fdp_minutes(fdp_start: datetime, sectors: int) -> int:
    """Maximum FDP for an acclimatised crew starting at ``fdp_start``."""
    minute_of_day = fdp_start.hour * 60 + fdp_start.minute
    base = None
    for lo, hi, value in FDP_TABLE:
        if lo <= minute_of_day <= hi:
            base = value
            break
    if base is None:  # pragma: no cover - table covers 00:00-23:59
        raise GuardTamperError("FDP table incomplete")
    extra_sectors = max(0, int(sectors) - 2)
    return max(LIMITS.fdp_floor_min, base - LIMITS.fdp_sector_reduction_min * extra_sectors)


def fdp_window(crew: CrewFacts, *, report_time: datetime | None, sectors_total: int) -> dict:
    """Legal FDP window for a crew member. Returns start, limit and basis.

    Standby (CS FTL.1.225): the FDP counts from reporting. Airport standby: max FDP reduced by standby time
    beyond 4h, and airport standby + FDP <= 16h. Home standby: max FDP reduced by standby time beyond 6h.
    """
    kind = crew.duty_kind
    if kind in ("ON_DUTY", "ROSTERED"):
        start = crew.duty_start
        sb_kind, sb_start = crew.standby_kind, crew.standby_start
    elif kind == "AIRPORT_STANDBY":
        start, sb_kind, sb_start = report_time or crew.duty_start, "AIRPORT", crew.duty_start
    elif kind == "HOME_STANDBY":
        start, sb_kind, sb_start = report_time or crew.duty_start, "HOME", crew.duty_start
    else:
        return {"start": None, "limit": None, "max_min": 0, "basis": "not on duty or standby"}
    reduction, cap, basis = 0, None, f"report {start:%H:%M}"
    if sb_kind and sb_start:
        standby_min = max(0, int((start - sb_start).total_seconds() // 60))
        free = LIMITS.airport_standby_free_min if sb_kind == "AIRPORT" else LIMITS.home_standby_free_min
        reduction = max(0, standby_min - free)
        basis = (f"{sb_kind.lower()} standby from {sb_start:%H:%M}, report {start:%H:%M}"
                 + (f", -{reduction}m for standby >{free // 60}h" if reduction else ""))
        if sb_kind == "AIRPORT":
            cap = sb_start + timedelta(minutes=LIMITS.airport_standby_plus_fdp_max_min)
    max_min = max_fdp_minutes(start, sectors_total) - reduction + LIMITS.planned_discretion_min
    limit = start + timedelta(minutes=max_min)
    if cap is not None and cap < limit:
        limit, max_min = cap, int((cap - start).total_seconds() // 60)
        basis += f", capped at standby+FDP {LIMITS.airport_standby_plus_fdp_max_min // 60}h"
    return {"start": start, "limit": limit, "max_min": max_min,
            "basis": f"{basis}; {sectors_total} sector(s) -> max FDP {max_min // 60}h{max_min % 60:02d}"}


def check_crew_for_sector(crew: CrewFacts, *, aircraft_type: str, off_blocks: datetime,
                          block_min: int, report_time: datetime | None = None) -> Verdict:
    """Can this crew member legally operate a sector departing at ``off_blocks``?"""
    v: list[Violation] = []
    checks = [f"{crew.crew_id}: fitness, type rating, rest, FDP, reachability"]
    if crew.fitness != "FIT":
        v.append(Violation("FTL-004", crew.crew_id, f"{crew.name} is {crew.fitness} (report is absolute)"))
    if aircraft_type not in crew.type_ratings:
        v.append(Violation("FTL-003", crew.crew_id,
                           f"{crew.name} rated {'/'.join(crew.type_ratings)}, aircraft is {aircraft_type}"))
    if crew.rest_before_duty_min < LIMITS.min_rest_min:
        v.append(Violation("FTL-002", crew.crew_id,
                           f"{crew.name} rest {crew.rest_before_duty_min // 60}h{crew.rest_before_duty_min % 60:02d}"
                           f" < {LIMITS.min_rest_min // 60}h minimum"))
    if crew.duty_kind == "OFF":
        v.append(Violation("FTL-004", crew.crew_id, f"{crew.name} is off duty, not on standby"))
        return _verdict(v, checks)
    if crew.duty_kind in ("AIRPORT_STANDBY", "HOME_STANDBY") and report_time is not None:
        latest_report = off_blocks - timedelta(minutes=LIMITS.report_before_off_blocks_min)
        if report_time > latest_report:
            v.append(Violation("FTL-006", crew.crew_id,
                               f"{crew.name} can report {report_time:%H:%M}, needed by {latest_report:%H:%M}"))
    win = fdp_window(crew, report_time=report_time or crew.duty_start, sectors_total=crew.sectors_flown + 1)
    on_blocks = off_blocks + timedelta(minutes=block_min)
    facts = {"fdp_basis": win["basis"], "fdp_limit": win["limit"], "projected_fdp_end": on_blocks}
    if win["limit"] is not None:
        margin = int((win["limit"] - on_blocks).total_seconds() // 60)
        facts["margin_min"] = margin
        if margin < 0:
            v.append(Violation("FTL-001", crew.crew_id,
                               f"{crew.name}: FDP would end {on_blocks:%H:%M}{_day(on_blocks, off_blocks)}, legal limit "
                               f"{win['limit']:%H:%M}{_day(win['limit'], off_blocks)} ({-margin} min over)"))
    return _verdict(v, checks, facts)


def check_inbound_crew_on_blocks(crew: Sequence[CrewFacts], *, eibt: datetime) -> Verdict:
    """FDP ends at on-blocks: the crew operating the inbound sector must block in legally."""
    v: list[Violation] = []
    margins = {}
    for c in crew:
        if c.duty_kind != "ON_DUTY" or c.duty_start is None:
            continue
        limit = c.duty_start + timedelta(minutes=max_fdp_minutes(c.duty_start, c.sectors_flown))
        margin = int((limit - eibt).total_seconds() // 60)
        margins[c.crew_id] = margin
        if margin < 0:
            v.append(Violation("FTL-001", c.crew_id,
                               f"{c.name}: on-blocks {eibt:%H:%M} is after FDP limit {limit:%H:%M} ({-margin} min over)"))
    facts = {"min_margin_min": min(margins.values()) if margins else None, "margins": margins}
    return _verdict(v, [f"inbound crew FDP at on-blocks {eibt:%H:%M}"], facts)


def check_crew_complement(crew: Sequence[CrewFacts], *, seats_total: int) -> list[Violation]:
    ranks = [c.rank for c in crew]
    need_cc = math.ceil(seats_total / LIMITS.cabin_crew_seats_per_member)
    have_cc = sum(1 for r in ranks if r in ("PUR", "CC"))
    v = []
    if ranks.count("CPT") < 1:
        v.append(Violation("FTL-005", "flight deck", "no legal commander (CPT) assigned"))
    if ranks.count("FO") < 1:
        v.append(Violation("FTL-005", "flight deck", "no legal first officer (FO) assigned"))
    if have_cc < need_cc:
        v.append(Violation("FTL-005", "cabin", f"{have_cc} cabin crew < {need_cc} required for {seats_total} seats"))
    return v


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MxFacts:
    item_id: str
    ata: str
    title: str
    blocks_dispatch: bool
    status: str                      # OPEN / CLOSED
    crs_licence: str | None = None   # licence type of signatory
    crs_type_auth: tuple[str, ...] = ()
    crs_signed_at: datetime | None = None
    task_earliest_complete: datetime | None = None


def required_licences(ata: str) -> frozenset[str]:
    return CRS_LICENCE_FOR_ATA.get(str(ata)[:2], frozenset({"B1"}))


def check_crs_signature(item: MxFacts, *, licence: str, type_auth: Sequence[str], aircraft_type: str,
                        signed_at: datetime, on_roster: bool = True, raised_at: datetime | None = None,
                        now: datetime | None = None, eng_id: str = "") -> Verdict:
    """Validate a Certificate of Release to Service before it is recorded.

    An "OK" from an inspection record is not enough: who signed and when are checked independently.
    """
    v = []
    if not on_roster:
        v.append(Violation("MX-004", item.item_id,
                           f"engineer ID '{eng_id}' is not on the licensed-engineer roster"))
    if raised_at and signed_at <= raised_at:
        v.append(Violation("MX-005", item.item_id,
                           f"signed {signed_at:%H:%M}, but the defect was only raised at {raised_at:%H:%M}"))
    if now and signed_at > now:
        v.append(Violation("MX-005", item.item_id, f"signature time {signed_at:%H:%M} is in the future"))
    need = required_licences(item.ata)
    if licence not in need:
        v.append(Violation("MX-002", item.item_id,
                           f"ATA {item.ata} needs licence {'/'.join(sorted(need))}; signatory holds {licence}"))
    if aircraft_type not in type_auth:
        v.append(Violation("MX-002", item.item_id, f"signatory not type-authorised on {aircraft_type}"))
    if item.task_earliest_complete and signed_at < item.task_earliest_complete:
        v.append(Violation("MX-003", item.item_id,
                           f"inspection cannot be complete before {item.task_earliest_complete:%H:%M}; "
                           f"signature attempted at {signed_at:%H:%M}"))
    return _verdict(v, [f"CRS validity for {item.item_id}: roster, licence, type, defect time, task time"])


def check_maintenance_release(items: Sequence[MxFacts], *, aircraft_type: str) -> list[Violation]:
    v = []
    for it in items:
        if not it.blocks_dispatch:
            continue
        if it.status != "CLOSED":
            v.append(Violation("MX-001", it.item_id, f"{it.title}: open, CRS not signed"))
            continue
        need = required_licences(it.ata)
        if it.crs_licence not in need or aircraft_type not in it.crs_type_auth:
            v.append(Violation("MX-002", it.item_id, f"{it.title}: CRS signatory not authorised"))
    return v


# ---------------------------------------------------------------------------
# Departure proposal (dispatch release)
# ---------------------------------------------------------------------------
def check_departure(*, flight_no: str, aircraft_type: str, seats_total: int, off_blocks: datetime,
                    block_min: int, crew: Sequence[CrewFacts], report_times: Mapping[str, datetime],
                    mx_items: Sequence[MxFacts], critical_path_eobt: datetime | None) -> Verdict:
    v: list[Violation] = []
    crew_facts = {}
    for c in crew:
        cv = check_crew_for_sector(c, aircraft_type=aircraft_type, off_blocks=off_blocks, block_min=block_min,
                                   report_time=report_times.get(c.crew_id))
        v.extend(cv.violations)
        crew_facts[c.crew_id] = {k: (val.strftime("%H:%M") if isinstance(val, datetime) else val)
                                 for k, val in cv.facts.items()}
    v.extend(check_crew_complement(crew, seats_total=seats_total))
    v.extend(check_maintenance_release(mx_items, aircraft_type=aircraft_type))
    if critical_path_eobt and off_blocks < critical_path_eobt:
        v.append(Violation("TURN-001", flight_no,
                           f"off-blocks {off_blocks:%H:%M} < critical-path EOBT {critical_path_eobt:%H:%M}"))
    checks = [
        f"{len(crew)} crew x (fitness, type rating, rest, FDP, reachability)",
        "minimum complement (CPT, FO, 1 cabin crew per 50 seats)",
        f"{sum(1 for m in mx_items if m.blocks_dispatch)} dispatch-blocking MX item(s) need valid CRS",
        "off-blocks >= turnaround critical-path EOBT",
    ]
    return _verdict(v, checks, {"crew": crew_facts})


# ---------------------------------------------------------------------------
# Passengers & bags
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PaxFacts:
    pax_id: str
    pnr: str
    name: str
    age: int
    cabin: str
    loyalty: str
    ssr: tuple[str, ...]
    final_dest: str
    is_infant: bool = False
    bag_count: int = 0


@dataclass(frozen=True, slots=True)
class OptionFacts:
    flight_id: str
    flight_no: str
    dest: str
    std: datetime
    sta: datetime
    operated_by_home: bool


@dataclass(frozen=True, slots=True)
class Assignment:
    pax: PaxFacts
    flight_id: str | None          # None = unresolved (no legal option)
    cabin: str | None
    seat_is_exit: bool = False


def pax_tier(p: PaxFacts) -> int:
    ssr = set(p.ssr)
    if ssr & CRITICAL_SSR:
        return 1
    if ssr & PROTECTED_SSR or p.is_infant or p.age >= LIMITS.elderly_age:
        return 2
    if p.cabin in ("F", "J") or p.loyalty.upper() in PREMIUM_LOYALTY:
        return 3
    return 4


def is_vulnerable(p: PaxFacts) -> bool:
    return pax_tier(p) <= 2


def group_tier(members: Sequence[PaxFacts]) -> int:
    return min(pax_tier(m) for m in members)


def pax_mct_minutes(p: PaxFacts, *, remote_arrival: bool = False) -> int:
    ssr = set(p.ssr)
    extra = 0
    if ssr & PRM_SSR:
        extra = max(extra, LIMITS.prm_mct_extra_min)
    if "MEDA" in ssr:
        extra = max(extra, LIMITS.meda_mct_extra_min)
    if "UMNR" in ssr:
        extra = max(extra, LIMITS.umnr_mct_extra_min)
    return LIMITS.base_mct_min + extra + (LIMITS.remote_stand_mct_extra_min if remote_arrival else 0)


def exit_row_permitted(p: PaxFacts) -> bool:
    if set(p.ssr) & EXIT_ROW_BANNED_SSR or p.is_infant:
        return False
    return LIMITS.child_exit_row_age <= p.age < LIMITS.elderly_age


def check_pax_option(p: PaxFacts, opt: OptionFacts, *, cabin: str, eibt: datetime, remote_arrival: bool,
                     seat_is_exit: bool = False) -> list[Violation]:
    """Is ``opt`` a legal re-accommodation for passenger ``p``?"""
    v: list[Violation] = []
    ssr = set(p.ssr)
    if opt.dest != p.final_dest:
        v.append(Violation("PAX-007", p.pax_id, f"{opt.flight_no} goes to {opt.dest}, passenger to {p.final_dest}"))
    if opt.std <= eibt:
        v.append(Violation("PAX-010", p.pax_id, f"{opt.flight_no} departs {opt.std:%H:%M} before on-blocks"))
    mct = pax_mct_minutes(p, remote_arrival=remote_arrival)
    ready = eibt + timedelta(minutes=mct)
    if opt.std < ready:
        v.append(Violation("PAX-002", p.pax_id,
                           f"{opt.flight_no} {opt.std:%H:%M} < on-blocks {eibt:%H:%M} + MCT {mct}m"))
    if p.bag_count and opt.std < eibt + timedelta(minutes=LIMITS.bag_mct_min):
        v.append(Violation("BAG-002", p.pax_id, f"bags need {LIMITS.bag_mct_min}m to transfer"))
    if "UMNR" in ssr:
        if not opt.operated_by_home:
            v.append(Violation("PAX-003", p.pax_id, f"{opt.flight_no} partner carrier has no UMNR escort agreement"))
        wait = (opt.std - eibt).total_seconds() / 60
        if opt.std.date() != eibt.date() or opt.std.time() > LIMITS.umnr_latest_departure or wait > LIMITS.umnr_max_wait_min:
            v.append(Violation("PAX-003", p.pax_id,
                               f"{opt.flight_no} {opt.std:%H:%M}: UMNR cannot wait overnight / depart after "
                               f"{LIMITS.umnr_latest_departure:%H:%M}"))
    if "MEDA" in ssr and not opt.operated_by_home:
        v.append(Violation("PAX-004", p.pax_id, f"{opt.flight_no}: MEDIF clearance is home-carrier only"))
    if CABIN_RANK.get(cabin, 0) < CABIN_RANK.get(p.cabin, 0):
        v.append(Violation("PAX-005", p.pax_id, f"downgrade {p.cabin}->{cabin} not permitted"))
    if seat_is_exit and not exit_row_permitted(p):
        v.append(Violation("PAX-008", p.pax_id, f"{p.name} may not sit in an exit row"))
    return v


def check_rebooking_batch(assignments: Sequence[Assignment], *, options: Mapping[str, OptionFacts],
                          free_seats: Mapping[str, Mapping[str, int]], eibt: datetime, remote_arrival: bool,
                          disrupted_pax_ids: frozenset[str] | set[str]) -> Verdict:
    """Pre-flight validation of a whole rebooking batch, before any transaction starts.

    ``free_seats`` is free inventory per flight/cabin *before* this batch.
    """
    v: list[Violation] = []
    # 1. scope + per-passenger legality
    for a in assignments:
        if a.pax.pax_id not in disrupted_pax_ids:
            v.append(Violation("PAX-009", a.pax.pax_id, f"{a.pax.name} is not a disrupted passenger"))
            continue
        if a.flight_id is None:
            continue
        opt = options.get(a.flight_id)
        if opt is None:
            v.append(Violation("PAX-007", a.pax.pax_id, f"unknown flight {a.flight_id}"))
            continue
        v.extend(check_pax_option(a.pax, opt, cabin=a.cabin or a.pax.cabin, eibt=eibt,
                                  remote_arrival=remote_arrival, seat_is_exit=a.seat_is_exit))
    # 2. PNR integrity
    by_pnr: dict[str, set] = {}
    for a in assignments:
        by_pnr.setdefault(a.pax.pnr, set()).add(a.flight_id)
    for pnr, flights in by_pnr.items():
        if len(flights) > 1:
            v.append(Violation("PAX-006", pnr, f"PNR {pnr} split across {sorted(str(f) for f in flights)}"))
    # 3. priority protection
    v.extend(_priority_inversions(assignments, options=options, free_seats=free_seats, eibt=eibt,
                                  remote_arrival=remote_arrival))
    checks = [
        f"{len(assignments)} passengers in scope of this disruption",
        "destination, MCT (passenger-specific), bag MCT, cabin (no downgrade), exit-row eligibility",
        "UMNR: home carrier, no overnight, no departure after 22:00",
        "MEDA: MEDIF-cleared home carrier only",
        "PNR groups kept together",
        "no lower-priority passenger takes a seat a higher-priority passenger could legally use",
    ]
    return _verdict(v, checks)


def _priority_inversions(assignments: Sequence[Assignment], *, options: Mapping[str, OptionFacts],
                         free_seats: Mapping[str, Mapping[str, int]], eibt: datetime,
                         remote_arrival: bool) -> list[Violation]:
    groups: dict[str, list[Assignment]] = {}
    for a in assignments:
        groups.setdefault(a.pax.pnr, []).append(a)

    used: dict[tuple[str, str], int] = {}
    for a in assignments:
        if a.flight_id and not a.pax.is_infant:
            key = (a.flight_id, a.cabin or a.pax.cabin)
            used[key] = used.get(key, 0) + 1

    def arrival(g: list[Assignment]) -> datetime:
        fid = g[0].flight_id
        return options[fid].sta if fid in options else datetime.max

    v: list[Violation] = []
    glist = list(groups.values())
    for gh in glist:
        th = group_tier([a.pax for a in gh])
        for gl in glist:
            if gl is gh or not gl[0].flight_id or gl[0].flight_id not in options:
                continue
            tl = group_tier([a.pax for a in gl])
            if th >= tl:
                continue
            f = options[gl[0].flight_id]
            if f.dest != gh[0].pax.final_dest or not (f.sta < arrival(gh)):
                continue
            # Would every member of the higher-priority group be legal on the lower group's flight?
            legal = all(not check_pax_option(a.pax, f, cabin=a.pax.cabin, eibt=eibt, remote_arrival=remote_arrival)
                        for a in gh)
            if not legal:
                continue
            need: dict[str, int] = {}
            for a in gh:
                if not a.pax.is_infant:
                    need[a.pax.cabin] = need.get(a.pax.cabin, 0) + 1
            freed: dict[str, int] = {}
            for a in gl:
                if not a.pax.is_infant:
                    c = a.cabin or a.pax.cabin
                    freed[c] = freed.get(c, 0) + 1
            fits = True
            for cabin, n in need.items():
                remaining = free_seats.get(f.flight_id, {}).get(cabin, 0) - used.get((f.flight_id, cabin), 0)
                if n > remaining + freed.get(cabin, 0):
                    fits = False
            if fits:
                names_h = ", ".join(a.pax.name for a in gh)
                names_l = ", ".join(a.pax.name for a in gl)
                v.append(Violation("PAX-001", gh[0].pax.pnr,
                                   f"{TIER_LABELS[tl]} [{names_l}] holds {f.flight_no} while {TIER_LABELS[th]} "
                                   f"[{names_h}] is placed later/unresolved"))
    return v


def bag_connection_minutes(*, bag_ready: datetime, std: datetime) -> int:
    """Minutes a transfer bag has between reaching the transfer belt and the onward departure."""
    return int((std - bag_ready).total_seconds() // 60)


def check_bag_connection(bag_tag: str, *, bag_ready: datetime, std: datetime, flight_no: str) -> list[Violation]:
    """Can this bag make the onward flight? (Its owner may still make it: passengers walk, bags are sorted.)"""
    have = bag_connection_minutes(bag_ready=bag_ready, std=std)
    if have < LIMITS.bag_mct_min:
        return [Violation("BAG-003", bag_tag,
                          f"bag on the belt {bag_ready:%H:%M}, {flight_no} leaves {std:%H:%M}: {have} min "
                          f"< bag MCT {LIMITS.bag_mct_min} min")]
    return []


def check_bag_routing(bag_owner: Mapping[str, str], bag_flight: Mapping[str, str],
                      pax_flights: Mapping[str, set[str]]) -> list[Violation]:
    """PPBM: every routed bag must travel on a flight its owner is booked on."""
    v = []
    for tag, flight in bag_flight.items():
        owner = bag_owner.get(tag)
        if owner is None or flight not in pax_flights.get(owner, set()):
            v.append(Violation("BAG-001", tag, f"bag {tag} routed on {flight} without its passenger"))
    return v


# ---------------------------------------------------------------------------
# Gates & network
# ---------------------------------------------------------------------------
def check_gate_window(*, gate_id: str, need_from: datetime, need_to: datetime,
                      busy: Sequence[tuple[datetime, datetime, str]]) -> list[Violation]:
    v = []
    for start, end, who in busy:
        if start < need_to and need_from < end:
            v.append(Violation("GATE-001", gate_id,
                               f"{gate_id} occupied by {who} {start:%H:%M}-{end:%H:%M}"))
    return v


def check_connection_hold(*, hold_min: int, flight_no: str) -> list[Violation]:
    if hold_min > LIMITS.max_connection_hold_min:
        return [Violation("NET-001", flight_no, f"hold {hold_min}m > max {LIMITS.max_connection_hold_min}m")]
    return []


def requires_controller_approval(change_type: str) -> bool:
    return change_type in CONTROLLER_GATED_CHANGES


def _day(dt: datetime, ref: datetime) -> str:
    d = (dt.date() - ref.date()).days
    return f"+{d}" if d > 0 else ""


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------
def guard_source_fingerprint() -> str:
    src = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(src).hexdigest()


def verify_guard_integrity() -> dict:
    pin_file = Path(__file__).with_name("guards.sha256")
    actual = guard_source_fingerprint()
    pinned = pin_file.read_text().strip() if pin_file.exists() else None
    return {"ok": pinned == actual, "actual": actual, "pinned": pinned}


# ---------------------------------------------------------------------------
# Seal the module. After this line, `guards.ANYTHING = value` raises.
# ---------------------------------------------------------------------------
class _SealedModule(types.ModuleType):
    def __setattr__(self, name, value):
        raise GuardTamperError(f"aeroturn.guards is sealed: cannot set '{name}'")

    def __delattr__(self, name):
        raise GuardTamperError(f"aeroturn.guards is sealed: cannot delete '{name}'")


sys.modules[__name__].__class__ = _SealedModule
