"""Crop the 2x dashboard captures into slide-ready images (docs/img/demo/*.png)."""
import json
import sys
from pathlib import Path

from PIL import Image

SHOTS = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()
S = 2            # device scale factor used for capture
MAXW = 2600      # px
INSET = 17       # css px between a card's border and its section heading
GAP = 16         # css px between rows
LEFT, RIGHT = 80, 1520   # content column of the dashboard (css px)


def load(name):
    return Image.open(SHOTS / f"{name}.png").convert("RGB"), _fill(json.loads((SHOTS / f"{name}.json").read_text()))


def _fill(r):
    """Panels in the middle column share x/width with the critical-path panel (older captures lack 'ctrl')."""
    if r.get("ctrl") is None and r.get("gantt") and r.get("feed"):
        r["ctrl"] = [r["gantt"][0], r["feed"][1], r["gantt"][2], r["feed"][3]]
    return r


def save(img, rect, out, pad=6):
    x, y, w, h = rect
    box = (max(0, int((x - pad) * S)), max(0, int((y - pad) * S)),
           min(img.width, int((x + w + pad) * S)), min(img.height, int((y + h + pad) * S)))
    c = img.crop(box)
    if c.width > MAXW:
        c = c.resize((MAXW, round(c.height * MAXW / c.width)), Image.LANCZOS)
    c.save(OUT / f"{out}.png", optimize=True)
    print(f"{out:22} {c.width}x{c.height}")


def rows(r):
    a = r["map"][1] - INSET
    b = r["flow"][1] - INSET
    c = r["feed"][1] - INSET
    return {"A": (a, b - GAP), "B": (b, c - GAP), "C": (c, c + 432)}


def row(r, name, first="map", last="crew"):
    y0, y1 = rows(r)[name]
    x0 = r[first][0] - INSET
    x1 = r[last][0] + r[last][2] + INSET
    return [x0, y0, x1 - x0, y1 - y0]


def union(rects):
    x0 = min(q[0] for q in rects); y0 = min(q[1] for q in rects)
    x1 = max(q[0] + q[2] for q in rects); y1 = max(q[1] + q[3] for q in rects)
    return [x0, y0, x1 - x0, y1 - y0]


# overview before anything happens: header, scenario bar, KPIs, row A
img, r = load("01_initial")
save(img, [LEFT, 18, RIGHT - LEFT, rows(r)["A"][1] - 18], "overview")

# after the agent run
img, r = load("02_agent")
save(img, [LEFT, 18, RIGHT - LEFT, rows(r)["A"][1] - 18], "hero")
save(img, union([r["banner"], r["kpis"]]), "agent_banner_kpis")
save(img, row(r, "A"), "agent_rowA")
save(img, row(r, "B", "flow", "cost"), "agent_rowB")
save(img, row(r, "C", "feed", "guard"), "agent_rowC")

for n, o in (("b_duty", "duty_breach"), ("b_nocrs", "no_crs"), ("b_override", "override"),
             ("06_rollback", "rollback"), ("b_naive", "naive")):
    img, r = load(n)
    save(img, r["banner"], o)

img, r = load("07_naive")
save(img, row(r, "B", "flow", "queue"), "priority")
for n, o in (("08_approve", "approve"), ("09_release", "release")):
    img, r = load(n)
    save(img, union([r["banner"], r["kpis"]]), o)

img, r = load("10_whatif")
save(img, r["banner"], "whatif_banner")
save(img, row(r, "C", "ctrl", "guard"), "whatif_queue_guard")

# edge cases tab: KPI strip and three cards (positions read off the 2x capture)
img, r = load("11_edge")
save(img, r["kpis"], "edge_kpis")
save(img, [568, 360, 466, 424], "edge_ec02", pad=2)
save(img, [82, 1280, 466, 484], "edge_ec07", pad=2)
save(img, [1052, 1208, 466, 362], "edge_ec09", pad=2)
