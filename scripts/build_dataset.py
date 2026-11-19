"""Regenerate the pristine scenario dataset (SQLite + JSON snapshot)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aeroturn import config  # noqa: E402
from aeroturn.dataset import build_dataset  # noqa: E402

if __name__ == "__main__":
    summary = build_dataset(config.PRISTINE_DB, config.SNAPSHOT_JSON)
    print(json.dumps(summary, indent=2))
    print(f"wrote {config.PRISTINE_DB}")
    print(f"wrote {config.SNAPSHOT_JSON}")
