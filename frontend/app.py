"""Nightscout Cockpit v2 — Streamlit frontend with Live + Insights tabs."""

from __future__ import annotations

import base64
from datetime import datetime, time, timezone
from io import BytesIO
import os
import time as time_module
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

# ── Compat helpers ────────────────────────────────────────────────


def do_rerun() -> None:
    """Rerun the Streamlit app, compatible with old and new versions."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()  # type: ignore[attr-defined]


# ── API layer ─────────────────────────────────────────────────────


def api_request(
    method: str,
    path: str,
    token: Optional[str] = None,
    params: Optional[dict] = None,
    payload: Optional[dict] = None,
    timeout: int = 15,
) -> dict:
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(
        method,
        f"{BACKEND_URL}{path}",
        params=params,
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "Unknown error")
        except ValueError:
            detail = response.text or "Unknown error"
        raise RuntimeError(detail)
    return response.json()


# ── Unit conversion ───────────────────────────────────────────────


def mgdl_to_mmol(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value / 18.0


def format_glucose(value: Optional[float], units: str) -> Optional[float]:
    if value is None:
        return None
    return round(mgdl_to_mmol(value), 1) if units == "mmol/L" else round(value, 0)


def _trend_arrow(delta: Optional[float]) -> str:
    if delta is None:
        return "?"
    if delta > 30:
        return "\u2B06\u2B06"
    if delta > 15:
        return "\u2B06"
    if delta > 5:
        return "\u2197"
    if delta >= -5:
        return "\u2192"
    if delta >= -15:
        return "\u2198"
    if delta >= -30:
        return "\u2B07"
    return "\u2B07\u2B07"


# ── Charts ────────────────────────────────────────────────────────


def build_glucose_chart(
    points: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
    units: str,
) -> plt.Figure:
    """Glucose line with target band + gap shading."""
    df = pd.DataFrame(points)
    if df.empty:
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.text(0.5, 0.5, "Geen data", ha="center", va="center", transform=ax.transAxes)
        return fig
    df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df.sort_values("t", inplace=True)
    df.reset_index(drop=True, inplace=True)
    values = df["sgv"].astype(float)
    if units == "mmol/L":
        values = values / 18.0

    fig, ax = plt.subplots(figsize=(10, 3.5))

    lo, hi = (70, 180) if units == "mg/dL" else (70 / 18.0, 180 / 18.0)
    ax.axhspan(lo, hi, color="#d4edda", alpha=0.35, label="Target 70-180")

    # Gap shading
    for g in gaps:
        gs = pd.to_datetime(g["start"])
        ge = pd.to_datetime(g["end"])
        ax.axvspan(gs, ge, color="#ffcccc", alpha=0.3)

    # Plot segments (break at gaps > 12 min)
    gap_mask = df["t"].diff().dt.total_seconds() > 720
    seg_starts = [0] + list(df.index[gap_mask])
    seg_ends = list(df.index[gap_mask]) + [len(df)]
    for s, e in zip(seg_starts, seg_ends):
        ax.plot(df["t"].iloc[s:e], values.iloc[s:e], color="#1f77b4", linewidth=1.2)

    ax.set_ylabel(f"Glucose ({units})")
    ax.set_xlabel("")
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def build_basal_chart(series: List[Dict[str, Any]]) -> plt.Figure:
    """Temp-basal step chart."""
    df = pd.DataFrame(series)
    if df.empty:
        fig, ax = plt.subplots(figsize=(10, 2))
        ax.text(0.5, 0.5, "Geen basaal data", ha="center", va="center", transform=ax.transAxes)
        return fig
    df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df.sort_values("t", inplace=True)
    fig, ax = plt.subplots(figsize=(10, 2.2))
    ax.step(df["t"], df["rate"], where="post", color="#e67e22", linewidth=1.2)
    ax.fill_between(df["t"], df["rate"], step="post", color="#e67e22", alpha=0.15)
    ax.set_ylabel("Basal (U/hr)")
    ax.set_xlabel("")
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def build_hypo_heatmap(heatmap: Dict[str, Any], units: str) -> plt.Figure:
    """Hypo-minutes heatmap: days x hours."""
    days = heatmap.get("days", [])
    values = heatmap.get("values", [])
    if not days or not values:
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.text(0.5, 0.5, "Geen hypo data", ha="center", va="center", transform=ax.transAxes)
        return fig

    arr = np.array(values, dtype=float)
    fig, ax = plt.subplots(figsize=(12, max(3, len(days) * 0.35)))
    im = ax.imshow(arr, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7)
    ax.set_yticks(range(len(days)))
    ax.set_yticklabels(days, fontsize=7)
    ax.set_xlabel("Uur van de dag")
    ax.set_ylabel("Dag")
    ax.set_title(f"Hypo-minuten per uur (<{70 if units == 'mg/dL' else round(70/18, 1)} {units})")
    fig.colorbar(im, ax=ax, label="Minuten")
    fig.tight_layout()
    return fig


def build_agp_chart(agp: Dict[str, Any], units: str) -> plt.Figure:
    """AGP: median + p10/p90 band."""
    series = agp.get("series", [])
    df = pd.DataFrame(series)
    if df.empty:
        fig, ax = plt.subplots(figsize=(10, 3.5))
        ax.text(0.5, 0.5, "Geen AGP data", ha="center", va="center", transform=ax.transAxes)
        return fig

    df["hour"] = df["minute_of_day"] / 60.0
    for col in ["p10", "p25", "p50", "p75", "p90"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if units == "mmol/L":
            df[col] = df[col] / 18.0

    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.fill_between(df["hour"], df["p10"], df["p90"], color="#cce5ff", alpha=0.4, label="P10-P90")
    ax.fill_between(df["hour"], df["p25"], df["p75"], color="#99ccff", alpha=0.6, label="P25-P75")
    ax.plot(df["hour"], df["p50"], color="#1f77b4", linewidth=2, label="Mediaan")
    ax.set_xlabel("Uur van de dag")
    ax.set_ylabel(f"Glucose ({units})")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title("Ambulatory Glucose Profile (AGP)")
    fig.tight_layout()
    return fig


def build_loop_activity_charts(loop: Dict[str, Any]) -> tuple:
    """Two charts: % temp basal per hour + mean rate per hour."""
    hours = loop.get("hours", list(range(24)))
    pct = loop.get("percent_temp", [0] * 24)
    rate = loop.get("mean_rate", [0] * 24)

    fig1, ax1 = plt.subplots(figsize=(10, 2.5))
    ax1.bar(hours, pct, color="#2ecc71", alpha=0.7, width=0.8)
    ax1.set_xlabel("Uur")
    ax1.set_ylabel("% temp basal")
    ax1.set_xlim(-0.5, 23.5)
    ax1.set_xticks(range(0, 24, 3))
    ax1.set_title("Loop-activiteit: % tijd temp basal per uur")
    ax1.grid(True, alpha=0.25, axis="y")
    fig1.tight_layout()

    fig2, ax2 = plt.subplots(figsize=(10, 2.5))
    ax2.bar(hours, rate, color="#3498db", alpha=0.7, width=0.8)
    ax2.set_xlabel("Uur")
    ax2.set_ylabel("Gem. rate (U/hr)")
    ax2.set_xlim(-0.5, 23.5)
    ax2.set_xticks(range(0, 24, 3))
    ax2.set_title("Loop-activiteit: gemiddelde temp rate per uur")
    ax2.grid(True, alpha=0.25, axis="y")
    fig2.tight_layout()

    return fig1, fig2


def fig_to_base64(fig: plt.Figure) -> str:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ── Session / auth helpers ────────────────────────────────────────

def ensure_session_defaults() -> None:
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("email", None)
    st.session_state.setdefault("units", "mg/dL")


def validate_password_length_ui(password: str) -> Optional[str]:
    if len(password) > 128:
        return "Password too long. Max 128 characters."
    return None


# ── HTML tile helper ──────────────────────────────────────────────

_TILE_CSS = """
<style>
.ck-tile {
    background: #f8f9fa; border-radius: 8px; padding: 8px 12px;
    text-align: center; min-height: 60px;
}
.ck-tile .label { font-size: 0.65rem; color: #6c757d; text-transform: uppercase; margin-bottom: 2px; }
.ck-tile .value { font-size: 1.0rem; font-weight: 600; color: #212529; }
.ck-tile.stale .value { color: #dc3545; }
</style>
"""


def _tile(label: str, value: str, *, stale: bool = False) -> str:
    cls = "ck-tile stale" if stale else "ck-tile"
    return f'{_TILE_CSS}<div class="{cls}"><div class="label">{label}</div><div class="value">{value}</div></div>'


# ── Auth screens ──────────────────────────────────────────────────


def render_login() -> None:
    st.subheader("Login")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login"):
        error = validate_password_length_ui(password)
        if error:
            st.error(error)
            return
        try:
            result = api_request("POST", "/auth/login", payload={"email": email, "password": password})
            st.session_state["token"] = result["access_token"]
            st.session_state["email"] = email
            st.success("Logged in")
            do_rerun()
        except Exception as exc:
            st.error(str(exc))


def render_register() -> None:
    st.subheader("Register")
    email = st.text_input("Email", key="register_email")
    password = st.text_input("Password", type="password", key="register_password")
    if st.button("Create account"):
        error = validate_password_length_ui(password)
        if error:
            st.error(error)
            return
        try:
            result = api_request("POST", "/auth/register", payload={"email": email, "password": password})
            st.session_state["token"] = result["access_token"]
            st.session_state["email"] = email
            st.success("Account created")
            do_rerun()
        except Exception as exc:
            st.error(str(exc))


# ── Connection screen ─────────────────────────────────────────────


def render_connection(token: str) -> None:
    st.subheader("Nightscout koppelen")
    url = st.text_input("Nightscout URL")
    ns_token = st.text_input("Nightscout token", type="password")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Opslaan"):
            try:
                api_request("POST", "/me/nightscout", token=token, payload={"url": url, "token": ns_token})
                st.success("Opgeslagen")
            except Exception as exc:
                st.error(str(exc))
    with col2:
        if st.button("Opslaan en testen"):
            try:
                api_request("POST", "/me/nightscout", token=token, payload={"url": url, "token": ns_token})
                test = api_request("GET", "/me/nightscout/test", token=token)
                st.success(f"OK ({test['latency_ms']} ms)")
            except Exception as exc:
                st.error(str(exc))


# ── LIVE TAB ──────────────────────────────────────────────────────


def render_live(token: str, units: str) -> None:
    st.subheader("\U0001fa78 Live Cockpit")

    # Controls
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 2, 1, 1])
    with ctrl1:
        hours = st.select_slider("Window", options=[3, 6, 12, 24, 48], value=12, key="live_hours")
    with ctrl2:
        refresh = st.select_slider("Refresh (s)", options=[10, 15, 30, 60, 120, 300], value=60, key="live_refresh")
    with ctrl3:
        auto_refresh = st.toggle("Auto refresh", value=True, key="live_auto")
    with ctrl4:
        force = st.button("\u27F3 Refresh now")

    # Fetch cockpit data
    try:
        data = api_request("GET", "/me/cockpit", token=token, params={"hours": hours})
    except Exception as exc:
        st.error(str(exc))
        return

    cgm = data.get("cgm", {})
    basal = data.get("basal", {})
    metrics = cgm.get("metrics", {})
    points = cgm.get("points", [])
    gaps = cgm.get("gaps", [])
    cgm_status = cgm.get("status", "ok")

    # Metric values
    last_val = format_glucose(metrics.get("last"), units)
    delta_15 = metrics.get("delta_15m")
    delta_15_display = format_glucose(delta_15, units)
    arrow = _trend_arrow(delta_15)
    d15_sign = "+" if delta_15_display is not None and delta_15_display > 0 else ""
    data_age = metrics.get("data_age_seconds")
    data_age_min = round(data_age / 60, 1) if data_age is not None else None
    is_stale = cgm_status == "stale"
    coverage = metrics.get("coverage_percent")

    # Top metrics row
    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.markdown(_tile("Glucose", f"{last_val} {units}" if last_val is not None else "\u2014"), unsafe_allow_html=True)
    m2.markdown(_tile("\u039415 min", f"{d15_sign}{delta_15_display or '\u2014'} {arrow}"), unsafe_allow_html=True)
    m3.markdown(_tile("TIR", f"{metrics.get('tir', '\u2014')}%"), unsafe_allow_html=True)
    m4.markdown(_tile("TBR / TAR", f"{metrics.get('tbr', '\u2014')} / {metrics.get('tar', '\u2014')}%"), unsafe_allow_html=True)
    m5.markdown(_tile("CV", f"{metrics.get('cv', '\u2014')}%"), unsafe_allow_html=True)
    age_str = f"\u26A0 {data_age_min} min" if is_stale else (f"{data_age_min} min" if data_age_min is not None else "\u2014")
    m6.markdown(_tile("Data age", age_str, stale=is_stale), unsafe_allow_html=True)
    cov_str = f"{coverage}%" if coverage is not None else "\u2014"
    m7.markdown(_tile("Coverage", cov_str), unsafe_allow_html=True)

    # Glucose chart
    if points:
        fig = build_glucose_chart(points, gaps, units)
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.info("Geen CGM data in dit venster.")

    # Basal chart
    basal_series = basal.get("series", [])
    if basal_series:
        fig_b = build_basal_chart(basal_series)
        st.pyplot(fig_b)
        plt.close(fig_b)
    else:
        st.caption("Geen temp-basaal data in dit venster.")

    # Footer
    st.caption(f"Server: {data.get('server_time', '\u2014')} \u00B7 Status: {cgm_status}")

    # Refresh
    if force:
        do_rerun()
    if auto_refresh:
        time_module.sleep(refresh)
        do_rerun()


# ── INSIGHTS TAB ──────────────────────────────────────────────────


def render_insights(token: str, units: str) -> None:
    st.subheader("\U0001F4CA Insights")

    days = st.select_slider("Periode (dagen)", options=[7, 14, 21, 28], value=14, key="ins_days")

    try:
        data = api_request("GET", "/me/insights", token=token, params={"days": days})
    except Exception as exc:
        st.error(str(exc))
        return

    summary = data.get("summary", {})

    # Summary tiles
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    s1.markdown(_tile("Gemiddeld", f"{format_glucose(summary.get('mean'), units)} {units}" if summary.get("mean") else "\u2014"), unsafe_allow_html=True)
    s2.markdown(_tile("CV", f"{summary.get('cv_percent', '\u2014')}%"), unsafe_allow_html=True)
    s3.markdown(_tile("TIR", f"{summary.get('tir_percent', '\u2014')}%"), unsafe_allow_html=True)
    s4.markdown(_tile("TBR", f"{summary.get('tbr_percent', '\u2014')}%"), unsafe_allow_html=True)
    s5.markdown(_tile("TAR", f"{summary.get('tar_percent', '\u2014')}%"), unsafe_allow_html=True)
    s6.markdown(_tile("Coverage", f"{summary.get('coverage_percent', '\u2014')}%"), unsafe_allow_html=True)

    st.markdown("---")

    # 1) Hypo heatmap
    st.markdown("#### Hypo-heatmap")
    hypo = data.get("hypo_heatmap", {})
    if hypo.get("days"):
        fig_h = build_hypo_heatmap(hypo, units)
        st.pyplot(fig_h)
        plt.close(fig_h)
    else:
        st.info("Geen hypo-events in deze periode.")

    # 2) AGP
    st.markdown("#### AGP (Ambulatory Glucose Profile)")
    agp = data.get("agp", {})
    if agp.get("series"):
        fig_a = build_agp_chart(agp, units)
        st.pyplot(fig_a)
        plt.close(fig_a)
    else:
        st.info("Geen AGP data beschikbaar.")

    # 3) Dayparts
    st.markdown("#### Dagdelen (TIR/TBR/TAR)")
    dp = data.get("dayparts", {})
    _render_dayparts_tables(dp)

    # 4) Loop activity
    st.markdown("#### Loop-activiteit")
    loop = data.get("loop_activity", {})
    if any(v > 0 for v in loop.get("percent_temp", [])):
        fig_l1, fig_l2 = build_loop_activity_charts(loop)
        st.pyplot(fig_l1)
        plt.close(fig_l1)
        st.pyplot(fig_l2)
        plt.close(fig_l2)
    else:
        st.info("Geen loop-activiteit data in deze periode.")

    st.caption(f"Server: {data.get('server_time', '\u2014')}")


def _render_dayparts_tables(dp: Dict[str, Any]) -> None:
    """Render daypart tables: overall, weekday, weekend."""
    definition = dp.get("definition", [])
    if not definition:
        st.info("Geen dagdeel-analyse beschikbaar.")
        return

    tab_all, tab_wd, tab_we = st.tabs(["Totaal", "Werkdagen", "Weekend"])

    for tab, key, label in [(tab_all, "overall", "Totaal"), (tab_wd, "weekday", "Werkdagen"), (tab_we, "weekend", "Weekend")]:
        with tab:
            rows = dp.get(key, [])
            if rows:
                df = pd.DataFrame(rows)
                cols_display = ["name", "tir", "tbr", "tar", "mean", "cv"]
                cols_present = [c for c in cols_display if c in df.columns]
                rename = {"name": "Dagdeel", "tir": "TIR%", "tbr": "TBR%", "tar": "TAR%", "mean": "Gem.", "cv": "CV%"}
                st.dataframe(df[cols_present].rename(columns=rename), use_container_width=True, hide_index=True)
            else:
                st.info(f"Geen data voor {label}.")


# ── Account / Report screens ─────────────────────────────────────


def render_account() -> None:
    st.subheader("Account")
    st.write(f"Ingelogd als {st.session_state.get('email')}")
    if st.button("Uitloggen"):
        st.session_state["token"] = None
        st.session_state["email"] = None
        st.success("Uitgelogd")
        do_rerun()


# ── Main ──────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(page_title="Nightscout Cockpit", layout="wide")
    ensure_session_defaults()

    st.title("Nightscout Cockpit")

    if not st.session_state.get("token"):
        tab_login, tab_register = st.tabs(["Login", "Register"])
        with tab_login:
            render_login()
        with tab_register:
            render_register()
        return

    # Sidebar
    st.sidebar.header("Navigatie")
    st.session_state["units"] = st.sidebar.radio("Units", ["mg/dL", "mmol/L"])
    page = st.sidebar.radio("Ga naar", ["Koppelen", "Live", "Insights", "Account"])

    token = st.session_state["token"]
    units = st.session_state["units"]

    if page == "Koppelen":
        render_connection(token)
    elif page == "Live":
        render_live(token, units)
    elif page == "Insights":
        render_insights(token, units)
    else:
        render_account()


if __name__ == "__main__":
    main()
