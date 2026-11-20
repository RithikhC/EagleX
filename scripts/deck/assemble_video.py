"""Assemble screencast frames into an MP4 (long static stretches shortened) and write a matching SRT.

python assemble_video.py <recordDir> <out.mp4>
"""
import json
import subprocess
import sys
from pathlib import Path

REC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
CAP = 5.5        # longest a single unchanged frame may stay on screen (s): waiting is compressed
frames = json.loads((REC / "frames.json").read_text(encoding="utf-8"))
captions = json.loads((REC / "captions.json").read_text(encoding="utf-8"))

durs = [min(max(frames[i + 1]["ts"] - frames[i]["ts"], 1 / 60), CAP) for i in range(len(frames) - 1)] + [2.0]
starts, v = [], 0.0
for d in durs:
    starts.append(v)
    v += d
total = v


def video_time(t):
    """Map a wall-clock time to video time through the (compressed) frame timeline."""
    if t <= frames[0]["ts"]:
        return 0.0
    for i in range(len(frames) - 1):
        if frames[i]["ts"] <= t < frames[i + 1]["ts"]:
            return starts[i] + min(t - frames[i]["ts"], durs[i])
    return total


lst = REC / "list.txt"
with lst.open("w", encoding="utf-8") as f:
    for fr, d in zip(frames, durs):
        f.write(f"file 'frames/{fr['file']}'\nduration {d:.4f}\n")
    f.write(f"file 'frames/{frames[-1]['file']}'\n")

OUT.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-vf", "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                "-c:v", "libx264", "-preset", "medium", "-crf", "27", "-movflags", "+faststart", str(OUT)], check=True)


def ts(x):
    h, r = divmod(x, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)) % 1000:03d}"


srt = []
times = [video_time(c["t"]) for c in captions]
for i, c in enumerate(captions):
    a = times[i]
    b = times[i + 1] if i + 1 < len(captions) else total
    if b - a < 0.3:
        continue
    srt.append(f"{len(srt) + 1}\n{ts(a)} --> {ts(b)}\n{c['text']}\n")
OUT.with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")
print(f"video {total:.1f}s, {len(frames)} frames, {len(srt)} subtitles -> {OUT}")
