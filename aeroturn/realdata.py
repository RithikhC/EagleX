"""Real-data analytics for the dashboard: US DOT BTS on-time data, Atlanta (ATL), July 2024.

Every number here is computed from the published records in data/real/ (see data/real/manifest.json for the URLs,
licences and SHA-256 of the raw files). Nothing is simulated. Definitions follow BTS:
  * a flight is "delayed" when it is 15 or more minutes late (BTS on-time definition);
  * delay causes (carrier, weather, NAS, security, late-arriving aircraft) are reported only for flights arriving
    15+ minutes late, in minutes;
  * "late-arriving aircraft" (reactionary) delay = the previous flight with the same aircraft arrived late, so this
    departure left late. That is the turnaround problem AeroTurn works on.
Passenger itineraries, crew rosters and maintenance records are not public (and must never be personal data), so
connection-level KPIs are measured in the pilot, not here.
"""

from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from .config import ROOT

REAL = ROOT / "data" / "real"
HUB = "ATL"
CAUSES = {"CarrierDelay": "Airline (carrier)", "LateAircraftDelay": "Late-arriving aircraft",
          "NASDelay": "Air traffic system (NAS)", "WeatherDelay": "Extreme weather", "SecurityDelay": "Security"}
CANCEL_CODES = {"A": "Airline", "B": "Weather", "C": "Air traffic system", "D": "Security"}


def manifest() -> dict:
    return json.loads((REAL / "manifest.json").read_text(encoding="utf-8"))


def _hhmm(date: pd.Series, hhmm: pd.Series) -> pd.Series:
    v = pd.to_numeric(hhmm, errors="coerce")
    h, m = (v // 100) % 24, v % 100
    return pd.to_datetime(date) + pd.to_timedelta(h, unit="h") + pd.to_timedelta(m, unit="m")


@lru_cache(maxsize=1)
def flights() -> pd.DataFrame:
    df = pd.read_csv(REAL / "bts_atl_2024_07.csv.gz", dtype={"Tail_Number": str, "CancellationCode": str})
    df["date"] = pd.to_datetime(df.FlightDate)
    df["sched_dep"] = _hhmm(df.FlightDate, df.CRSDepTime)
    df["sched_arr"] = _hhmm(df.FlightDate, df.CRSArrTime)
    overnight = df.sched_arr < df.sched_dep
    df.loc[overnight, "sched_arr"] += pd.Timedelta(days=1)
    df["flight"] = df.Reporting_Airline + df.Flight_Number_Reporting_Airline.astype(str)
    return df


def departures() -> pd.DataFrame:
    return flights()[flights().Origin == HUB]


def arrivals() -> pd.DataFrame:
    return flights()[flights().Dest == HUB]


def day_type(cancel_pct: float) -> str:
    """Stratum for like-for-like comparison: never compare an outage day with a normal day."""
    if cancel_pct >= 10:
        return "Major disruption"
    if cancel_pct >= 2:
        return "Elevated"
    return "Normal"


@lru_cache(maxsize=1)
def daily() -> pd.DataFrame:
    d = departures()
    out = d.groupby("date").agg(flights=("Cancelled", "size"), cancelled=("Cancelled", "sum"),
                                delayed=("DepDelay", lambda s: int((s >= 15).sum())),
                                mean_delay=("DepDelay", "mean")).reset_index()
    late_min = arrivals()[arrivals().ArrDelay >= 15].groupby("date")[list(CAUSES)].sum().reset_index()
    out = out.merge(late_min, on="date", how="left").fillna(0)
    out["cancel_pct"] = out.cancelled / out.flights * 100
    out["operated"] = out.flights - out.cancelled
    out["delayed_pct"] = out.delayed / out.operated.clip(lower=1) * 100
    out["ontime_pct"] = 100 - out.delayed_pct
    out["stratum"] = out.cancel_pct.map(day_type)
    rot = rotations()
    knock = rot[rot.knock_on].groupby("date").size().rename("knock_ons").reset_index()
    out = out.merge(knock, on="date", how="left").fillna({"knock_ons": 0})
    return out


@lru_cache(maxsize=1)
def rotations() -> pd.DataFrame:
    """Aircraft turns at ATL: each arrival linked to the same tail number's next departure from ATL (same day).

    buffer   = scheduled departure - scheduled arrival (the planned turn)
    knock_on = the inbound arrived 15+ min late AND it ate more than the planned buffer allowed, AND the outbound
               then left 15+ min late: the late-aircraft chain AeroTurn is built to break.
    """
    f = flights()
    f = f[f.Tail_Number.notna() & (f.Cancelled == 0)]
    a = f[f.Dest == HUB][["Tail_Number", "date", "flight", "Origin", "sched_arr", "ArrDelay"]]
    d = f[f.Origin == HUB][["Tail_Number", "date", "flight", "Dest", "sched_dep", "DepDelay", "LateAircraftDelay"]]
    a = a.sort_values("sched_arr")
    d = d.sort_values("sched_dep")
    m = pd.merge_asof(a, d, left_on="sched_arr", right_on="sched_dep", by="Tail_Number",
                      direction="forward", suffixes=("_in", "_out"), tolerance=pd.Timedelta(hours=8))
    m = m.dropna(subset=["flight_out"])
    m["buffer_min"] = (m.sched_dep - m.sched_arr).dt.total_seconds() / 60
    m["date"] = m.date_in
    m["knock_on"] = (m.ArrDelay >= 15) & (m.DepDelay >= 15) & (m.ArrDelay > m.buffer_min - 30)
    return m.rename(columns={"flight_in": "inbound", "flight_out": "outbound", "Origin": "from", "Dest": "to",
                             "ArrDelay": "inbound_delay", "DepDelay": "outbound_delay"})


def cause_minutes(stratum: str | None = None) -> pd.Series:
    a = arrivals()
    a = a[a.ArrDelay >= 15]
    if stratum:
        days = daily()[daily().stratum == stratum].date
        a = a[a.date.isin(days)]
    return a[list(CAUSES)].sum().rename(index=CAUSES)


def strata_table() -> pd.DataFrame:
    d = daily()
    rot = rotations()
    rows = []
    for s in ("Normal", "Elevated", "Major disruption"):
        x = d[d.stratum == s]
        if x.empty:
            continue
        days = x.date
        r = rot[rot.date.isin(days)]
        rows.append({"Stratum": s, "Days": len(x), "Departures": int(x.flights.sum()),
                     "Cancelled %": x.cancelled.sum() / x.flights.sum() * 100,
                     "On-time %": 100 - x.delayed.sum() / x.operated.sum() * 100,
                     "Late-aircraft min / day": x.LateAircraftDelay.mean(),
                     "Turns / day": len(r) / len(x), "Knock-on turns / day": r.knock_on.sum() / len(x)})
    return pd.DataFrame(rows)


def recovery_days(threshold_pct: float = 2.0) -> dict:
    """How long the hub took to get back to normal after the outage (cancellations back under threshold)."""
    d = daily().sort_values("date")
    bad = d[d.cancel_pct >= 10]
    if bad.empty:
        return {}
    start = bad.date.min()
    after = d[(d.date > start) & (d.cancel_pct < threshold_pct)]
    end = after.date.min() if not after.empty else d.date.max()
    lost = d[(d.date >= start) & (d.date < end)]
    return {"start": start.date().isoformat(), "back_to_normal": end.date().isoformat(),
            "days": int((end - start).days), "cancelled": int(lost.cancelled.sum()),
            "departures": int(lost.flights.sum())}


def month_summary() -> dict:
    d = daily()
    late = arrivals()[arrivals().ArrDelay >= 15]
    causes = late[list(CAUSES)].sum()
    rot = rotations()
    return {"departures": int(d.flights.sum()), "arrivals": int(len(arrivals())), "cancelled": int(d.cancelled.sum()),
            "cancel_pct": d.cancelled.sum() / d.flights.sum() * 100,
            "ontime_pct": 100 - d.delayed.sum() / d.operated.sum() * 100,
            "delay_minutes": float(causes.sum()), "late_aircraft_minutes": float(causes.LateAircraftDelay),
            "late_aircraft_share": float(causes.LateAircraftDelay / causes.sum() * 100),
            "turns": int(len(rot)), "knock_ons": int(rot.knock_on.sum()),
            "airlines": int(flights().Reporting_Airline.nunique()),
            "first": d.date.min().date().isoformat(), "last": d.date.max().date().isoformat()}


def alerts_for_day(day: str, limit: int = 40) -> pd.DataFrame:
    """The AeroTurn trigger rule run on a real day: every turn where a late inbound ate the planned buffer."""
    r = rotations()
    r = r[(r.date == pd.Timestamp(day)) & r.knock_on].sort_values("sched_arr")
    out = pd.DataFrame({
        "Aircraft": r.Tail_Number, "Inbound": r.inbound, "From": r["from"],
        "Sched. arrival": r.sched_arr.dt.strftime("%H:%M"), "Arrived late (min)": r.inbound_delay.astype(int),
        "Planned turn (min)": r.buffer_min.astype(int), "Outbound": r.outbound, "To": r["to"],
        "Sched. departure": r.sched_dep.dt.strftime("%H:%M"), "Departed late (min)": r.outbound_delay.astype(int)})
    return out.head(limit).reset_index(drop=True)


def turn_recovery(stratum: str | None = None) -> dict:
    """Of the aircraft turns whose inbound arrived 15+ min late, how many still left on time (< 15 min late)?
    A real, public proxy for 'connection preservation' at aircraft level."""
    r = rotations()
    if stratum:
        r = r[r.date.isin(daily()[daily().stratum == stratum].date)]
    late = r[r.inbound_delay >= 15]
    ok = int((late.outbound_delay < 15).sum())
    return {"late_inbound_turns": int(len(late)), "recovered": ok,
            "rate": ok / len(late) * 100 if len(late) else 0.0}


def days_in(stratum: str | None) -> pd.Series:
    d = daily()
    return d.date if not stratum else d[d.stratum == stratum].date


# ---------------------------------------------------------------------------
# OCC live board: a real day replayed minute by minute (what a controller sees at a given local time)
# ---------------------------------------------------------------------------
MIN_TURN_MIN = 30    # same threshold as the knock-on rule above: a turn shorter than this cannot be done on time


@lru_cache(maxsize=1)
def airports() -> pd.DataFrame:
    return pd.read_csv(REAL / "airports.csv").dropna(subset=["iata_code"]).set_index("iata_code")


def _day(day: str) -> pd.DataFrame:
    f = flights()
    f = f[f.date == pd.Timestamp(day)].copy()
    f["dep_act"] = f.sched_dep + pd.to_timedelta(f.DepDelay.fillna(0), unit="m")
    f["arr_act"] = f.sched_arr + pd.to_timedelta(f.ArrDelay.fillna(0), unit="m")
    return f


def board(day: str, now: pd.Timestamp, ahead_min: int = 120) -> dict:
    """Everything the live board shows at local time `now` on a real day.

    Known at `now` (as in an operations centre): flights already flown, cancellations so far, and the ETA of
    inbound aircraft (in operation it comes from ATC/ADS-B feeds; in this replay it is the arrival time in the
    record). The turn alert uses only those facts; the outbound's real outcome is shown separately, as hindsight.
    """
    f = _day(day)
    dep, arr = f[f.Origin == HUB], f[f.Dest == HUB]
    horizon = now + pd.Timedelta(minutes=ahead_min)

    due = dep[dep.sched_dep <= now]
    flown = due[(due.Cancelled == 0) & (due.dep_act <= now)]
    cancelled_so_far = int(due.Cancelled.sum())
    ontime = int((flown.DepDelay < 15).sum())

    # departure board: next departures, with what is known now
    nxt = dep[(dep.sched_dep > now - pd.Timedelta(minutes=30)) & (dep.sched_dep <= horizon)].sort_values("sched_dep")

    def dep_status(r) -> str:
        if r.Cancelled:
            return "Cancelled"
        if r.dep_act <= now:
            return "Departed" + (f" +{int(r.DepDelay)}" if r.DepDelay >= 15 else "")
        return f"Delayed {r.dep_act:%H:%M}" if r.DepDelay >= 15 else "On time"

    deps = pd.DataFrame({"Flight": nxt.flight, "To": nxt.Dest, "Aircraft": nxt.Tail_Number.fillna("—"),
                         "Sched.": nxt.sched_dep.dt.strftime("%H:%M"),
                         "Status": [dep_status(r) for r in nxt.itertuples()]})
    deps = deps[~deps.Status.str.startswith("Departed")]

    # inbound aircraft in the window, with their ETA
    inb = arr[(arr.sched_arr > now - pd.Timedelta(minutes=30)) & (arr.sched_arr <= horizon)].sort_values("sched_arr")

    def arr_status(r) -> str:
        if r.Cancelled:
            return "Cancelled"
        if r.Diverted:
            return "Diverted"
        if r.arr_act <= now:
            return "Landed" + (f" +{int(r.ArrDelay)}" if r.ArrDelay >= 15 else "")
        return f"ETA {r.arr_act:%H:%M} (+{int(r.ArrDelay)})" if r.ArrDelay >= 15 else f"ETA {r.arr_act:%H:%M}"

    arrs = pd.DataFrame({"Flight": inb.flight, "From": inb.Origin, "Aircraft": inb.Tail_Number.fillna("—"),
                         "Sched.": inb.sched_arr.dt.strftime("%H:%M"),
                         "Status": [arr_status(r) for r in inb.itertuples()]})
    arrs = arrs[~arrs.Status.str.startswith("Landed")]
    late_inbound = inb[(inb.Cancelled == 0) & (inb.ArrDelay >= 15) & (inb.arr_act > now)]

    # turn alerts: a late inbound leaves less than the minimum turn before the same aircraft's next departure
    rot = rotations()
    rot = rot[rot.date == pd.Timestamp(day)].copy()
    rot["eta"] = rot.sched_arr + pd.to_timedelta(rot.inbound_delay, unit="m")
    rot["turn_left"] = (rot.sched_dep - rot.eta).dt.total_seconds() / 60
    open_ = rot[(rot.inbound_delay >= 15) & (rot.turn_left < MIN_TURN_MIN) & (rot.sched_arr <= horizon)
                & (rot.sched_dep + pd.to_timedelta(rot.outbound_delay, unit="m") > now)
                & (rot.eta > now - pd.Timedelta(minutes=60))].sort_values("turn_left")
    alerts = pd.DataFrame({
        "Severity": ["Critical" if t < 0 else "At risk" for t in open_.turn_left],
        "Aircraft": open_.Tail_Number, "Inbound": open_.inbound, "From": open_["from"],
        "ETA": open_.eta.dt.strftime("%H:%M"), "Late by": open_.inbound_delay.astype(int),
        "Outbound": open_.outbound, "To": open_["to"], "Sched. dep.": open_.sched_dep.dt.strftime("%H:%M"),
        "Planned turn": open_.buffer_min.astype(int), "Turn left": open_.turn_left.astype(int),
        "Actually left": open_.outbound_delay.astype(int)}).reset_index(drop=True)

    # hour by hour: flown hours in colour, the rest as scheduled
    hrs = dep.assign(h=dep.sched_dep.dt.floor("h"))
    hourly = []
    for h, g in hrs.groupby("h"):
        if h + pd.Timedelta(hours=1) <= now:
            ok = g[(g.Cancelled == 0) & (g.DepDelay < 15)]
            hourly.append({"hour": h, "On time": len(ok), "Delayed ≥ 15 min": int(((g.Cancelled == 0) & (g.DepDelay >= 15)).sum()),
                           "Cancelled": int(g.Cancelled.sum()), "Scheduled": 0})
        else:
            hourly.append({"hour": h, "On time": 0, "Delayed ≥ 15 min": 0, "Cancelled": 0, "Scheduled": len(g)})

    return {"departures_due": int(len(due)), "flown": int(len(flown)), "ontime": ontime,
            "ontime_pct": ontime / len(flown) * 100 if len(flown) else 0.0, "cancelled": cancelled_so_far,
            "delay_minutes": float(flown.DepDelay.clip(lower=0).sum()),
            "late_aircraft_minutes": float(arr[(arr.arr_act <= now) & (arr.ArrDelay >= 15)].LateAircraftDelay.sum()),
            "total_departures": int(len(dep)), "deps": deps, "arrs": arrs, "late_inbound": late_inbound,
            "alerts": alerts, "hourly": pd.DataFrame(hourly)}
