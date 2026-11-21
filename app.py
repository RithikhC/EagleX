"""AeroTurn web app: a real-data performance dashboard, the live simulation, the implementation view and the
business model, each on its own page.

    streamlit run app.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import streamlit as st


def _fresh_package() -> None:
    """Streamlit re-runs app.py on every interaction but keeps imported modules. After a deploy (git pull) the
    package source changes on disk; drop the old aeroturn modules so this run imports the new code."""
    root = Path(__file__).parent
    files = sorted(root.joinpath("aeroturn").glob("*.py")) + sorted(root.joinpath("views").glob("*.py"))
    stamp = hashlib.sha1("".join(f"{p.name}:{p.stat().st_mtime_ns}:{p.stat().st_size}" for p in files).encode()
                         ).hexdigest()
    old = sys.modules.get("aeroturn")
    if old is not None and getattr(old, "_code_stamp", None) != stamp:
        for name in [m for m in sys.modules if m.split(".")[0] in ("aeroturn", "views")]:
            del sys.modules[name]
    import aeroturn
    aeroturn._code_stamp = stamp


_fresh_package()

st.set_page_config(page_title="AeroTurn · Disruption Recovery", page_icon="✈️", layout="wide",
                   initial_sidebar_state="collapsed")

pages = [
    st.Page("views/dashboard.py", title="Dashboard", icon="📈", url_path="dashboard", default=True),
    st.Page("views/simulation.py", title="Simulation", icon="🧪", url_path="simulation"),
    st.Page("views/implementation.py", title="Implementation", icon="🔌", url_path="implementation"),
    st.Page("views/business.py", title="Business model", icon="💼", url_path="business"),
]
st.navigation(pages, position="top").run()
