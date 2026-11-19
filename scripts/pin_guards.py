"""Re-pin the SHA-256 fingerprint of aeroturn/guards.py.

Run this only after a reviewed, intentional change to the safety floors.
The app refuses to run the agent while the fingerprint does not match.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aeroturn import guards  # noqa: E402

if __name__ == "__main__":
    fp = guards.guard_source_fingerprint()
    pin = Path(guards.__file__).with_name("guards.sha256")
    pin.write_text(fp + "\n")
    print(f"pinned guards.py -> {fp}")
