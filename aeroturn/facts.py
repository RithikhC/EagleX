"""Convert database rows into the immutable fact objects the guards consume.

The guards never read the database themselves. This module is the only
bridge, which keeps the guards pure and makes every verdict reproducible
from its inputs.
"""

from __future__ import annotations

import sqlite3

from . import db, guards
from .timeutil import parse


def ssr_tuple(ssr: str | None) -> tuple[str, ...]:
    return tuple(x.strip() for x in (ssr or "").split(",") if x.strip())


def crew_facts(row: dict) -> guards.CrewFacts:
    return guards.CrewFacts(
        crew_id=row["crew_id"], name=row["name"], rank=row["rank"],
        type_ratings=tuple(x.strip() for x in row["type_ratings"].split(",")),
        fitness=row["fitness"], duty_kind=row["duty_kind"], duty_start=parse(row["duty_start"]),
        sectors_flown=row["sectors_flown"], rest_before_duty_min=row["rest_before_duty_min"],
        proximity_min=row["proximity_min"], standby_kind=row.get("standby_kind"),
        standby_start=parse(row.get("standby_start")))


def pax_facts(row: dict, bag_count: int | None = None) -> guards.PaxFacts:
    return guards.PaxFacts(
        pax_id=row["pax_id"], pnr=row["pnr"], name=f"{row['first_name']} {row['last_name']}", age=row["age"],
        cabin=row["cabin"], loyalty=row["loyalty"], ssr=ssr_tuple(row["ssr"]), final_dest=row["final_dest"],
        is_infant=bool(row["is_infant"]), bag_count=int(bag_count if bag_count is not None else row.get("bag_count", 0)))


def option_facts(row: dict) -> guards.OptionFacts:
    return guards.OptionFacts(
        flight_id=row["flight_id"], flight_no=row["flight_no"], dest=row["dest"],
        std=parse(row["etd"] or row["std"]), sta=parse(row["eta"] or row["sta"]),
        operated_by_home=bool(row["operated_by_home"]))


def mx_facts(conn: sqlite3.Connection, row: dict, task_earliest_complete=None) -> guards.MxFacts:
    eng = db.one(conn, "SELECT * FROM engineers WHERE eng_id = ?", (row["crs_eng_id"],)) if row["crs_eng_id"] else None
    return guards.MxFacts(
        item_id=row["item_id"], ata=row["ata"], title=row["title"], blocks_dispatch=bool(row["blocks_dispatch"]),
        status=row["status"], crs_licence=eng["licence"] if eng else None,
        crs_type_auth=tuple(eng["type_auth"].split(",")) if eng else (),
        crs_signed_at=parse(row["crs_signed_at"]), task_earliest_complete=task_earliest_complete)


def bag_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {r["pax_id"]: r["n"] for r in conn.execute("SELECT pax_id, COUNT(*) AS n FROM bags GROUP BY pax_id")}
