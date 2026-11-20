"""Crop the Round 3 live captures (capture.mjs stage 'pilot', 2x) into docs/img/round3/*.png."""
import json
import sys
from pathlib import Path

from PIL import Image

SHOTS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
S, INSET, GAP, LEFT, RIGHT, MAXW = 2, 17, 16, 80, 1520, 2400


def load(n):
    return Image.open(SHOTS / f"{n}.png").convert("RGB"), json.loads((SHOTS / f"{n}.json").read_text())


def save(img, x0, y0, x1, y1, out):
    c = img.crop((int(x0 * S), int(y0 * S), int(x1 * S), int(y1 * S)))
    if c.width > MAXW:
        c = c.resize((MAXW, round(c.height * MAXW / c.width)), Image.LANCZOS)
    c.save(OUT / f"{out}.png", optimize=True)
    print(f"{out:14} {c.width}x{c.height}")


img, r = load("20_alert_run")
k = r["kpis"]
save(img, LEFT, 18, RIGHT, k[1] + k[3] + 10, "workflow")

img, r = load("21_pilot")
top = lambda key: r[key][1] - INSET  # noqa: E731
save(img, LEFT, top("burst"), RIGHT, top("cases") - GAP, "burst")
save(img, LEFT, top("cases"), RIGHT, top("audit") - GAP, "cases")
save(img, LEFT, top("audit"), RIGHT, top("cost") - GAP, "audit")
note = r.get("costNote") or r["costEnd"]
save(img, LEFT, top("cost"), RIGHT, note[1] + note[3] + INSET, "cost")
