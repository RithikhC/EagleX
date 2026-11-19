"""Small time helpers. All scenario times are naive hub-local (GST) datetimes."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .config import SCENARIO_DATE

FMT = "%Y-%m-%dT%H:%M"
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_BASE = datetime.strptime(SCENARIO_DATE, "%Y-%m-%d")


def parse(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    value = value.strip()
    if len(value) <= 8 and ":" in value:  # "15:20" or "03:05+1"
        return at(value)
    return datetime.strptime(value[:16], FMT)


def fmt(dt: datetime | None) -> str | None:
    return dt.strftime(FMT) if dt else None


def at(hhmm: str, day_offset: int = 0) -> datetime:
    """``at("15:20")`` -> scenario date 15:20; ``at("03:05+1")`` -> next day."""
    if "+" in hhmm:
        hhmm, extra = hhmm.split("+", 1)
        day_offset += int(extra)
    h, m = hhmm.split(":")
    return _BASE + timedelta(days=day_offset, hours=int(h), minutes=int(m))


def hm(dt: datetime | str | None) -> str:
    """Human label ``15:20`` / ``03:05+1`` relative to the scenario date."""
    dt = parse(dt)
    if dt is None:
        return "-"
    days = (dt.date() - _BASE.date()).days
    suffix = "" if days == 0 else (f"+{days}" if days > 0 else str(days))
    return dt.strftime("%H:%M") + suffix


def minutes(a: datetime, b: datetime) -> int:
    """Whole minutes from a to b (b - a)."""
    return int(round((b - a).total_seconds() / 60))


def plus(dt: datetime, mins: int) -> datetime:
    return dt + timedelta(minutes=mins)


def is_iso(value) -> bool:
    return isinstance(value, str) and bool(_ISO.match(value))


def dur(mins: int) -> str:
    sign = "-" if mins < 0 else ""
    mins = abs(int(mins))
    return f"{sign}{mins // 60}h{mins % 60:02d}"
