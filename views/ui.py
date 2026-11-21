"""Shared light-mode look for the Dashboard, Implementation and Business pages."""
from __future__ import annotations

import html

import plotly.graph_objects as go
import streamlit as st

INK, INK2, MUTED, LINE, PAGE, CARD = "#0f172a", "#334155", "#64748b", "#e2e8f0", "#f5f7fb", "#ffffff"
BLUE, BLUE_L, GREEN, AMBER, RED, SLATE = "#2563eb", "#93c5fd", "#15803d", "#d97706", "#dc2626", "#94a3b8"
CAUSE_COLORS = {"Late-arriving aircraft": BLUE, "Airline (carrier)": "#64748b", "Air traffic system (NAS)": "#94a3b8",
                "Extreme weather": "#cbd5e1", "Security": "#e2e8f0"}

CSS = f"""
<style>
.stApp {{background:{PAGE};}}
.block-container {{padding-top:1rem; max-width:1400px;}}
.pg-h {{display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin:4px 0 14px 0;}}
.pg-h h1 {{font-size:1.55rem; font-weight:800; color:{INK}; margin:0; letter-spacing:-.01em;}}
.pg-h p {{color:{MUTED}; margin:2px 0 0 0; font-size:.92rem;}}
.tag {{display:inline-block; font-size:.72rem; font-weight:700; padding:3px 10px; border-radius:999px;
  border:1px solid {LINE}; color:{INK2}; background:#fff; margin-left:6px; white-space:nowrap;}}
.tag.real {{border-color:#bbf7d0; color:{GREEN}; background:#f0fdf4;}}
.tag.sim {{border-color:#fde68a; color:#92400e; background:#fffbeb;}}
.tag.asm {{border-color:#e9d5ff; color:#6b21a8; background:#faf5ff;}}
.kc {{background:{CARD}; border:1px solid {LINE}; border-radius:12px; padding:12px 14px; height:100%;
  box-shadow:0 1px 2px rgba(15,23,42,.05);}}
.kc .l {{font-size:.72rem; font-weight:700; color:{MUTED}; text-transform:uppercase; letter-spacing:.05em;}}
.kc .v {{font-size:1.6rem; font-weight:800; color:{INK}; line-height:1.2; margin-top:2px;}}
.kc .s {{font-size:.78rem; color:{INK2}; margin-top:2px;}}
.sec2 {{font-size:1.02rem; font-weight:800; color:{INK}; margin:6px 0 2px 0;}}
.sub2 {{font-size:.84rem; color:{MUTED}; margin:0 0 8px 0;}}
.card {{background:{CARD}; border:1px solid {LINE}; border-radius:12px; padding:14px 16px; margin-bottom:10px;
  box-shadow:0 1px 2px rgba(15,23,42,.05);}}
.card h4 {{margin:0 0 4px 0; font-size:.98rem; color:{INK};}}
.card p, .card li {{color:{INK2}; font-size:.86rem; margin:2px 0;}}
.src {{font-size:.74rem; color:{MUTED}; margin-top:6px;}}
.src a {{color:{MUTED};}}
table.t {{width:100%; border-collapse:collapse; font-size:.84rem; background:#fff; border:1px solid {LINE};
  border-radius:10px; overflow:hidden;}}
table.t th {{background:#f8fafc; color:{INK2}; text-align:left; font-weight:700; padding:8px 10px;
  border-bottom:1px solid {LINE};}}
table.t td {{padding:7px 10px; border-bottom:1px solid #f1f5f9; color:{INK2}; vertical-align:top;}}
table.t td b {{color:{INK};}}
.pill {{display:inline-block; font-size:.7rem; font-weight:700; padding:1px 8px; border-radius:999px;}}
.pill.real {{background:#dcfce7; color:#166534;}} .pill.sim {{background:#fef3c7; color:#92400e;}}
.pill.pilot {{background:#e0e7ff; color:#3730a3;}} .pill.asm {{background:#f3e8ff; color:#6b21a8;}}
.pill.live {{background:#dcfce7; color:#166534;}} .pill.cache {{background:#fef3c7; color:#92400e;}}
div[data-testid="stVerticalBlockBorderWrapper"] {{background:#fff; border-color:{LINE}!important; border-radius:12px;}}
</style>
"""


def setup() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header(title: str, subtitle: str, tags: list[tuple[str, str]] = ()) -> None:
    t = "".join(f"<span class='tag {k}'>{html.escape(v)}</span>" for k, v in tags)
    st.markdown(f"<div class='pg-h'><div><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>"
                f"<div>{t}</div></div>", unsafe_allow_html=True)


def kpi(col, label: str, value: str, sub: str = "") -> None:
    col.markdown(f"<div class='kc'><div class='l'>{html.escape(label)}</div><div class='v'>{html.escape(value)}</div>"
                 f"<div class='s'>{html.escape(sub)}</div></div>", unsafe_allow_html=True)


def section(title: str, sub: str = "") -> None:
    st.markdown(f"<div class='sec2'>{html.escape(title)}</div>"
                + (f"<div class='sub2'>{sub}</div>" if sub else ""), unsafe_allow_html=True)


def table(headers: list[str], rows: list[list[str]], raw: bool = True) -> None:
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c if raw else html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    st.markdown(f"<table class='t'><tr>{th}</tr>{tr}</table>", unsafe_allow_html=True)


def pill(kind: str, text: str) -> str:
    return f"<span class='pill {kind}'>{html.escape(text)}</span>"


def layout(fig: go.Figure, height: int = 300, legend: bool = True) -> go.Figure:
    fig.update_layout(height=height, template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                      margin=dict(l=8, r=8, t=10, b=8), showlegend=legend,
                      font=dict(family="Inter, Segoe UI, system-ui, sans-serif", color=INK2, size=12),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, bgcolor="rgba(0,0,0,0)"),
                      hoverlabel=dict(bgcolor="#ffffff", font=dict(color=INK)))
    fig.update_xaxes(gridcolor="#f1f5f9", linecolor=LINE)
    fig.update_yaxes(gridcolor="#f1f5f9", linecolor=LINE)
    return fig


def source(text: str) -> None:
    st.markdown(f"<div class='src'>{text}</div>", unsafe_allow_html=True)
