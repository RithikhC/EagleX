"""Crop live-demo captures (capture.mjs, 2x) into the images used by build_round1.js -> docs/img/round1/."""
import json
import sys
from pathlib import Path

from PIL import Image

SHOTS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()
S, MAXW, INSET, GAP, LEFT, RIGHT = 2, 2400, 17, 16, 80, 1520


def load(n):
    return Image.open(SHOTS / f"{n}.png").convert("RGB"), _fill(json.loads((SHOTS / f"{n}.json").read_text()))


def _fill(r):
    """Panels in the middle column share x/width with the critical-path panel (older captures lack 'ctrl')."""
    if r.get("ctrl") is None and r.get("gantt") and r.get("feed"):
        r["ctrl"] = [r["gantt"][0], r["feed"][1], r["gantt"][2], r["feed"][3]]
    return r


def save(img, rect, out, pad=6):
    x, y, w, h = rect
    c = img.crop((max(0, int((x - pad) * S)), max(0, int((y - pad) * S)),
                  min(img.width, int((x + w + pad) * S)), min(img.height, int((y + h + pad) * S))))
    if c.width > MAXW:
        c = c.resize((MAXW, round(c.height * MAXW / c.width)), Image.LANCZOS)
    c.save(OUT / f"{out}.png", optimize=True)
    print(f"{out:14} {c.width}x{c.height}")


def rows(r):
    a, b, c = r["map"][1] - INSET, r["flow"][1] - INSET, r["feed"][1] - INSET
    return {"A": (a, b - GAP), "B": (b, c - GAP), "C": (c, c + 432)}


def row(r, name, first, last):
    y0, y1 = rows(r)[name]
    x0, x1 = r[first][0] - INSET, r[last][0] + r[last][2] + INSET
    return [x0, y0, x1 - x0, y1 - y0]


def union(rs):
    x0 = min(q[0] for q in rs); y0 = min(q[1] for q in rs)
    return [x0, y0, max(q[0] + q[2] for q in rs) - x0, max(q[1] + q[3] for q in rs) - y0]


img, r = load("01_initial")
save(img, row(r, "A", "map", "map"), "map_before")
save(img, [LEFT, 18, RIGHT - LEFT, rows(r)["A"][1] - 18], "ux_1")
img, r = load("02_agent")
save(img, row(r, "A", "map", "map"), "map_after")
save(img, [LEFT, 18, RIGHT - LEFT, rows(r)["A"][1] - 18], "agent_run")
save(img, row(r, "C", "feed", "ctrl"), "ux_2")
img, r = load("09_release")
save(img, [LEFT, 18, RIGHT - LEFT, rows(r)["A"][1] - 18], "ux_3")
img, r = load("15_guard")
save(img, [LEFT, 18, RIGHT - LEFT, int(sys.argv[3]) if len(sys.argv) > 3 else 735], "guardrails")
img, r = load("16_curveballs")
save(img, r["kpis"], "curveballs_kpis")

img, r = load("11_edge")
save(img, r["kpis"], "edge_kpis")
save(img, [568, 360, 466, 424], "edge_ec02", pad=2)
save(img, [82, 1280, 466, 484], "edge_ec07", pad=2)
save(img, [1052, 1208, 466, 362], "edge_ec09", pad=2)
