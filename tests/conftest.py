import os
import sys
import tempfile
from pathlib import Path

os.environ["AEROTURN_RUNTIME_DIR"] = tempfile.mkdtemp(prefix="aeroturn_test_")
os.environ["AEROTURN_LLM"] = "offline"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from aeroturn import db  # noqa: E402


@pytest.fixture()
def conn():
    db.reset_runtime()
    c = db.connect()
    yield c
    c.close()
