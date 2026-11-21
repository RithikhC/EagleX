"""The real-data numbers quoted in the pitch and on the Dashboard are reproducible from data/real/."""
import pandas as pd

from aeroturn import realdata as R


def test_month_summary_matches_proof():
    m = R.month_summary()
    assert m["departures"] == 30072 and m["cancelled"] == 1778
    assert round(m["late_aircraft_share"], 1) == 35.1


def test_live_board_on_a_real_day():
    b = R.board("2024-07-12", pd.Timestamp("2024-07-12 17:00"))
    assert b["flown"] == 616 and round(b["ontime_pct"]) == 75
    a = b["alerts"]
    assert len(a) == 36 and (a.Severity == "Critical").sum() == 18
    top = a.iloc[0]
    assert (top.Aircraft, top.Inbound, top.Outbound) == ("N287WN", "WN215", "WN3275")
    assert top["Late by"] == 237 and top["Actually left"] == 239
    # the alert uses only what is known at 17:00: every alerted turn has less than the minimum turn left
    assert (a["Turn left"] < R.MIN_TURN_MIN).all()
    # boards list only flights that have not yet left or landed
    assert not b["deps"].Status.str.startswith("Departed").any()
    assert not b["arrs"].Status.str.startswith("Landed").any()
