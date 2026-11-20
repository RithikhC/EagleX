"""Render docs/round3/log_evidence.txt (the exact export the deck cites) as docs/round3/log_evidence.png."""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SRC, OUT = ROOT / "docs" / "round3" / "log_evidence.txt", ROOT / "docs" / "round3" / "log_evidence.png"
FONT = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 22)
BOLD = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", 22)
BG, INK, MUTED = (13, 27, 62), (226, 232, 240), (148, 163, 184)
COL = {"AUTO": (74, 222, 128), "PAUSED": (250, 204, 21), "BLOCKED": (248, 113, 113), "REJECTED": (248, 113, 113),
       "SAFE DEFAULT": (96, 165, 250), "EXPIRED": (96, 165, 250)}


def short(ln: str) -> str:
    ln = re.sub(r"\s{2,}", "  ", ln)
    ln = re.sub(r"  reason=(.{0,70}).*?(  hash=)", r"  reason=\1…\2", ln)
    return ln.replace("execute_atomic_passenger_rebook", "execute_rebook").replace(
        "stage_controller_schedule_change", "stage_change").replace(" (Operations Controller)", "")


lines = SRC.read_text(encoding="utf-8").splitlines()
keep = []
for ln in lines:
    if ln.startswith(("AeroTurn", "Generated", "THREE", "AUDIT", "  ", "     ")) or re.match(r"\d\d:\d\d:\d\d GST", ln):
        keep.append(short(ln) if re.match(r"\d\d:\d\d:\d\d GST", ln) else ln)
    elif ln.startswith("TRIGGER"):
        break
W = 40 + max(FONT.getlength(x) for x in keep)
H = 40 + 32 * len(keep)
img = Image.new("RGB", (int(min(W, 2600)), int(H)), BG)
d = ImageDraw.Draw(img)
y = 20
for ln in keep:
    head = ln.isupper() or ln.startswith(("AeroTurn", "THREE", "AUDIT"))
    color = next((c for k, c in COL.items() if f"  {k}" in ln or f" {k} " in ln), INK)
    d.text((20, y), ln, font=BOLD if head else FONT, fill=MUTED if ln.startswith("Generated") else (INK if head else color))
    y += 32
img.save(OUT, optimize=True)
print("wrote", OUT, img.size)
