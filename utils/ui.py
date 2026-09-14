"""Shared UI building blocks for the Streamlit views.

Before this module, every page in ``views/`` styled itself independently:
``app.py``'s own Overview page had a fairly polished "glass card" look
(hero header, card sections, metric tiles), but that pattern was
hand-rolled inline and never shared, so most of the other pages fell back
to bare ``st.header`` / ``st.subheader`` calls with no card treatment,
spacing, or icon language. The result was a workspace that looked like two
different apps depending on which page you were on.

This module is the fix: the same handful of primitives every page uses to
render a consistent header, section cards, metric tiles, and empty states,
plus a shared Plotly color theme so every chart in the app draws from one
palette instead of each view picking its own ad hoc colors.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, Sequence

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# The single source of truth for chart colors across the app. Views should
# pass this to Plotly Express calls (`color_discrete_sequence=CHART_COLORS`)
# for qualitative/categorical charts; sequential/continuous charts should
# use CHART_COLORSCALE. Picked to read clearly against the app's dark
# background and to stay distinguishable for common color-vision
# deficiencies (alternating cool/warm hues rather than adjacent ones).
CHART_COLORS: list[str] = [
    "#22c55e",  # green -- primary brand accent
    "#38bdf8",  # sky blue
    "#a78bfa",  # violet
    "#f59e0b",  # amber
    "#f472b6",  # pink
    "#2dd4bf",  # teal
    "#fb7185",  # rose
    "#94a3b8",  # slate (muted, for "other"/overflow categories)
]

CHART_COLORSCALE: str = "Tealgrn"

# Emoji icons used consistently for each workspace section, in both the
# sidebar nav and each page's own header -- so a user can match a sidebar
# item to the page it opens at a glance.
SECTION_ICONS: dict[str, str] = {
    "Overview": "\U0001f3e0",  # house
    "Portfolio Workspace": "\U0001f4bc",  # briefcase
    "Operations Center": "⚙️",  # gear
    "Governance Center": "\U0001f6e1️",  # shield
    "Integrations Hub": "\U0001f50c",  # plug
    "Team Workspace": "\U0001f465",  # people
    "Upload Analytics": "\U0001f4e5",  # inbox tray
    "Scenario Planner": "\U0001f9ed",  # compass
    "AI Forecast Studio": "\U0001f4c8",  # chart increasing
    "Executive Scorecards": "\U0001f3c6",  # trophy
}


def apply_chart_theme() -> None:
    """Register a shared Plotly template layered on top of ``plotly_dark``.

    Call once at app startup. Individual charts still work exactly as
    before (``px.bar(...)``, ``px.pie(...)``, etc.) -- this only changes
    the *defaults* they draw from, so every chart in the app picks up the
    same colorway, transparent background (so it sits on the page's own
    gradient instead of a plotly-gray box), and gridline styling without
    each view needing to repeat that configuration.
    """
    template = go.layout.Template()
    template.layout.colorway = CHART_COLORS
    template.layout.paper_bgcolor = "rgba(0,0,0,0)"
    template.layout.plot_bgcolor = "rgba(0,0,0,0)"
    template.layout.font = dict(color="#e8f1ff", family="'Source Sans Pro', sans-serif")
    template.layout.title = dict(font=dict(color="#f8fbff", size=17))
    template.layout.legend = dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#cbd5e1"))
    template.layout.xaxis = dict(
        gridcolor="rgba(148, 163, 184, 0.14)",
        zerolinecolor="rgba(148, 163, 184, 0.22)",
        linecolor="rgba(148, 163, 184, 0.22)",
    )
    template.layout.yaxis = dict(
        gridcolor="rgba(148, 163, 184, 0.14)",
        zerolinecolor="rgba(148, 163, 184, 0.22)",
        linecolor="rgba(148, 163, 184, 0.22)",
    )
    template.layout.hoverlabel = dict(bgcolor="#0f172a", font=dict(color="#f8fbff"))
    pio.templates["carbon_tracker"] = template
    pio.templates.default = "plotly_dark+carbon_tracker"


def page_header(title: str, subtitle: str, *, icon: str = "", eyebrow: str = "") -> None:
    """Render the shared hero header every page should open with.

    Reuses the ``.hero-shell`` styling already defined by
    ``app.py::inject_shell_styles`` (previously only used on the Overview
    and sign-in pages) so every page in the workspace gets the same
    polished top-of-page treatment instead of a bare ``st.header``.
    """
    eyebrow_html = f'<div class="page-eyebrow">{eyebrow}</div>' if eyebrow else ""
    icon_html = f'<span class="hero-icon">{icon}</span> ' if icon else ""
    st.markdown(
        f"""
        <div class="hero-shell">
            {eyebrow_html}
            <h2>{icon_html}{title}</h2>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def open_card(title: str = "", *, icon: str = "") -> None:
    """Open a ``.glass-card`` section without a context manager.

    Prefer the ``card()`` context manager below for new code -- this and
    its ``close_card()`` counterpart exist for retrofitting a card around
    an existing long, deeply-branching block (many buttons/forms/early
    returns) where reindenting the whole block under a ``with`` would be
    high-risk for little benefit. Every ``open_card`` must be paired with
    exactly one ``close_card()``.
    """
    header_html = f"<h3>{icon + ' ' if icon else ''}{title}</h3>" if title else ""
    st.markdown(f'<div class="glass-card">{header_html}', unsafe_allow_html=True)


def close_card() -> None:
    """Close a card opened with ``open_card()``."""
    st.markdown("</div>", unsafe_allow_html=True)


@contextmanager
def card(title: str = "", *, icon: str = ""):
    """Context manager for a ``.glass-card`` section, optionally titled.

    Usage::

        with card("Priority Actions", icon="⚡"):
            st.write(...)

    Equivalent to the inline ``st.markdown('<div class="glass-card">...')``
    /``st.markdown('</div>')`` pairs already used throughout
    ``app.py::show_overview`` -- pulled out into a reusable helper so every
    other view can get the same card treatment without repeating the raw
    HTML (and without an easy-to-miss unclosed ``</div>``).
    """
    open_card(title, icon=icon)
    try:
        yield
    finally:
        close_card()


def render_metric_card(label: str, value: str, meta: str = "") -> None:
    """Render a single ``.metric-card`` tile (label / big value / meta line)."""
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            <div class="meta">{meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_row(items: Sequence[tuple[str, str, str]], columns: int | None = None) -> None:
    """Render a row of metric cards from ``(label, value, meta)`` tuples.

    ``columns`` defaults to ``len(items)`` (one column per metric, the
    common case); pass a smaller number to wrap onto multiple rows.
    """
    items = list(items)
    if not items:
        return
    n_cols = columns or len(items)
    cols = st.columns(n_cols)
    for index, (label, value, meta) in enumerate(items):
        with cols[index % n_cols]:
            render_metric_card(label, value, meta)


def tag_row(tags: Iterable[str]) -> None:
    """Render a row of small pill-shaped tags (``.tag`` / ``.tag-row``)."""
    tags_html = "".join(f'<span class="tag">{tag}</span>' for tag in tags)
    st.markdown(f'<div class="tag-row">{tags_html}</div>', unsafe_allow_html=True)


def empty_state(message: str, *, icon: str = "\U0001f4ed") -> None:
    """A friendlier "nothing here yet" box than a bare ``st.info`` call.

    Used for pages/sections where there's genuinely no data yet (no
    projects, no reports, no alerts) -- a large icon plus muted copy,
    instead of the same blue info banner used for every hint and caption
    throughout the app, so an intentional empty state reads differently
    from an informational aside.
    """
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-state-icon">{icon}</div>
            <div class="empty-state-message">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def soft_divider() -> None:
    """A subtler in-card divider than ``st.markdown("---")``.

    ``st.markdown("---")`` renders Streamlit's default ``<hr>``, which is a
    hard, high-contrast rule -- fine between page sections but visually
    heavy when used repeatedly to separate list rows inside a card (recent
    activity, saved reports, recommendations). This renders a thinner,
    low-contrast rule instead.
    """
    st.markdown('<hr class="soft-divider" />', unsafe_allow_html=True)
