"""Fetch the real, open datasets AeroTurn's dashboard runs on, and write small processed copies to data/real/.

    python scripts/fetch_real_data.py

Sources (all open; nothing personal):
  1. US DOT Bureau of Transportation Statistics (BTS), Reporting Carrier On-Time Performance, July 2024.
     Every US domestic flight: scheduled and actual times, delay minutes by cause, cancellations, tail numbers.
     Public domain (US Government work). https://www.transtats.bts.gov/
     We keep the flights touching one hub: Atlanta (ATL), the world's busiest airport and Delta's main hub. July 2024
     includes the CrowdStrike IT outage (19 July) and the multi-day recovery that followed.
  2. OurAirports airports.csv: airport names, cities, coordinates. Public domain. https://ourairports.com/data/
  3. OpenSky Network live state vectors around Dubai (DXB): real aircraft positions, used to show a live connector.
     Free for research and non-commercial use. https://opensky-network.org/ (a cached snapshot is kept as fallback)

Raw downloads go to data/raw/ (git-ignored). data/real/manifest.json records URL, licence, size, SHA-256 and row
counts, so anyone can verify the processed files came from the published sources.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW, REAL = ROOT / "data" / "raw", ROOT / "data" / "real"
RAW.mkdir(parents=True, exist_ok=True)
REAL.mkdir(parents=True, exist_ok=True)

HUB = "ATL"
BTS_URL = ("https://transtats.bts.gov/PREZIP/"
           "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2024_7.zip")
OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OPENSKY_URL = "https://opensky-network.org/api/states/all?lamin=24.7&lomin=54.9&lamax=25.6&lomax=55.8"

BTS_COLS = ["FlightDate", "Reporting_Airline", "Tail_Number", "Flight_Number_Reporting_Airline", "Origin", "Dest",
            "CRSDepTime", "DepTime", "DepDelay", "CRSArrTime", "ArrTime", "ArrDelay", "Cancelled",
            "CancellationCode", "Diverted", "CRSElapsedTime", "Distance", "CarrierDelay", "WeatherDelay", "NASDelay",
            "SecurityDelay", "LateAircraftDelay"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> Path:
    if not dest.exists():
        print("downloading", url)
        req = urllib.request.Request(url, headers={"User-Agent": "aeroturn-research/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
            f.write(r.read())
    return dest


def main() -> None:
    manifest = {"fetched_at": time.strftime("%Y-%m-%d %H:%M"), "sources": []}

    # 1. BTS on-time performance, July 2024 -> flights touching ATL
    z = download(BTS_URL, RAW / "bts_ontime_2024_07.zip")
    with zipfile.ZipFile(z) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv"))
        with zf.open(name) as f:
            df = pd.read_csv(f, usecols=BTS_COLS, dtype={"Tail_Number": str, "CancellationCode": str},
                             low_memory=False)
    total_us = len(df)
    hub = df[(df.Origin == HUB) | (df.Dest == HUB)].copy()
    out = REAL / "bts_atl_2024_07.csv.gz"
    hub.to_csv(out, index=False, compression="gzip")
    manifest["sources"].append({
        "name": "BTS Reporting Carrier On-Time Performance, July 2024", "url": BTS_URL,
        "publisher": "US DOT Bureau of Transportation Statistics", "licence": "Public domain (US Government work)",
        "raw_bytes": z.stat().st_size, "raw_sha256": sha256(z), "rows_all_us_flights": total_us,
        "processed_file": str(out.relative_to(ROOT)).replace("\\", "/"), "rows_processed": len(hub),
        "filter": f"Origin == {HUB} or Dest == {HUB}"})
    print(f"BTS: {total_us:,} US flights, {len(hub):,} touching {HUB}")

    # 2. OurAirports -> airports that appear in the hub data (+ DXB for the live connector)
    ap_raw = download(OURAIRPORTS_URL, RAW / "ourairports_airports.csv")
    ap = pd.read_csv(ap_raw, usecols=["iata_code", "name", "municipality", "iso_country", "latitude_deg",
                                      "longitude_deg", "type"])
    codes = set(hub.Origin) | set(hub.Dest) | {"DXB"}
    ap = ap[ap.iata_code.isin(codes) & ap.type.isin(["large_airport", "medium_airport", "small_airport"])]
    ap = ap.drop_duplicates("iata_code")
    ap_out = REAL / "airports.csv"
    ap.to_csv(ap_out, index=False)
    manifest["sources"].append({
        "name": "OurAirports airports.csv", "url": OURAIRPORTS_URL, "publisher": "OurAirports",
        "licence": "Public domain", "raw_bytes": ap_raw.stat().st_size, "raw_sha256": sha256(ap_raw),
        "processed_file": str(ap_out.relative_to(ROOT)).replace("\\", "/"), "rows_processed": len(ap)})
    print(f"OurAirports: {len(ap)} airports")

    # 3. OpenSky live snapshot around DXB (cached fallback for the live connector)
    try:
        req = urllib.request.Request(OPENSKY_URL, headers={"User-Agent": "aeroturn-research/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            snap = json.loads(r.read().decode())
        (REAL / "opensky_dxb_snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
        n = len(snap.get("states") or [])
    except Exception as exc:  # noqa: BLE001
        print("OpenSky not reachable:", exc)
        n = None
    manifest["sources"].append({
        "name": "OpenSky Network live state vectors (DXB area)", "url": OPENSKY_URL,
        "publisher": "OpenSky Network", "licence": "Free for research and non-commercial use (OpenSky terms)",
        "processed_file": "data/real/opensky_dxb_snapshot.json", "rows_processed": n,
        "note": "The dashboard calls the live API; this snapshot is the fallback when it is unreachable"})

    (REAL / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("wrote", REAL / "manifest.json")


if __name__ == "__main__":
    main()
