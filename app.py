"""
app.py — POTS (PreOff Trading System)
======================================
Streamlit web application. Run locally with:
    streamlit run app.py

Then open on any device on your network:
    http://<your-pc-ip>:8501
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import streamlit as st

from auth import CredentialStore
from core.api_connector import BetfairConnector
from analysis.engine import AnalysisEngine, Signal

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="POTS — PreOff Trading System",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Clean light-on-dark theme */
    .stApp { background-color: #1c1f26; color: #f0f0f0; }
    .block-container { padding-top: 0.5rem; max-width: 1200px; }

    /* Header */
    .pots-header {
        background: linear-gradient(90deg, #0a3d62 0%, #1a5276 50%, #0a3d62 100%);
        border-bottom: 3px solid #f39c12;
        padding: 12px 24px;
        margin-bottom: 12px;
        text-align: center;
        border-radius: 6px;
    }
    .pots-title {
        font-size: 2.2rem;
        font-weight: 900;
        color: #f39c12;
        letter-spacing: 6px;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
    }
    .pots-subtitle {
        font-size: 0.75rem;
        color: #aed6f1;
        letter-spacing: 3px;
        margin-top: 2px;
    }

    /* Verdict cards */
    .verdict-back {
        background: #1a3a2a;
        border-left: 4px solid #27ae60;
        border-radius: 6px;
        padding: 10px 14px;
        margin: 5px 0;
        color: #f0f0f0;
    }
    .verdict-lay {
        background: #3a1a1a;
        border-left: 4px solid #e74c3c;
        border-radius: 6px;
        padding: 10px 14px;
        margin: 5px 0;
        color: #f0f0f0;
    }
    .verdict-scalp {
        background: #1a2a3a;
        border-left: 4px solid #3498db;
        border-radius: 6px;
        padding: 10px 14px;
        margin: 5px 0;
        color: #f0f0f0;
    }
    .verdict-none {
        background: #262932;
        border-left: 4px solid #555;
        border-radius: 6px;
        padding: 10px 14px;
        margin: 5px 0;
        color: #aaa;
    }

    /* Countdown */
    .countdown-green  { color: #2ecc71; font-size: 1.3rem; font-weight: bold; }
    .countdown-yellow { color: #f39c12; font-size: 1.3rem; font-weight: bold; }
    .countdown-red    { color: #e74c3c; font-size: 1.3rem; font-weight: bold; }

    /* Confidence bar */
    .conf-bar-wrap { background: #333; border-radius: 4px; height: 10px; width: 100%; margin-top: 3px; }
    .conf-bar-fill-high { background: #27ae60; height: 10px; border-radius: 4px; }
    .conf-bar-fill-med  { background: #f39c12; height: 10px; border-radius: 4px; }
    .conf-bar-fill-low  { background: #e74c3c; height: 10px; border-radius: 4px; }

    /* WOM bar */
    .wom-container { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
    .wom-label { font-size: 0.8rem; color: #ccc; width: 130px; overflow: hidden; white-space: nowrap; }
    .wom-bar-wrap { flex: 1; background: #333; border-radius: 4px; height: 16px; position: relative; }
    .wom-lay-fill  { background: #c0392b; height: 16px; border-radius: 4px 0 0 4px; position: absolute; left: 0; }
    .wom-back-fill { background: #27ae60; height: 16px; border-radius: 0 4px 4px 0; position: absolute; right: 0; }
    .wom-pct { font-size: 0.8rem; color: #eee; width: 60px; text-align: right; font-weight: bold; }

    /* Odds */
    .odds-back { color: #2ecc71; font-weight: bold; font-size: 1.1rem; }
    .odds-lay  { color: #e74c3c; font-weight: bold; font-size: 1.1rem; }
    .odds-lpt  { color: #f39c12; font-size: 1rem; }

    /* Smart money badge */
    .smart-money { background: #f39c12; color: #000; border-radius: 4px;
                   padding: 2px 7px; font-size: 0.7rem; font-weight: bold; }

    hr { border-color: #444; }

    /* Streamlit overrides */
    .stTextInput input { background: #262932; color: #f0f0f0; border: 1px solid #444; }
    .stButton button { font-weight: bold; }
    h1, h2, h3, h4 { color: #f0f0f0 !important; }
    label { color: #ccc !important; }
    .stMetric { background: #262932; border-radius: 6px; padding: 8px; }

    /* Mobile responsive */
    @media (max-width: 768px) {
        .pots-title { font-size: 1.5rem; letter-spacing: 3px; }
        .pots-subtitle { font-size: 0.65rem; }
        .pots-header { padding: 10px 12px; }
        .block-container { padding: 0.5rem 0.5rem !important; }
        .wom-label { width: 80px; font-size: 0.7rem; }
        .wom-pct { width: 40px; font-size: 0.7rem; }
        .verdict-back, .verdict-lay, .verdict-scalp, .verdict-none {
            padding: 8px 10px;
            font-size: 0.85rem;
        }
        .countdown-green, .countdown-yellow, .countdown-red {
            font-size: 1rem;
        }
    }
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "authenticated":  False,
        "connector":      None,
        "engine":         None,
        "market_id":      "",
        "market_data":    None,
        "signals":        [],
        "last_fetch":     0.0,
        "error":          "",
        "master_pw":      "",
        "price_histories": {},   # runner_name -> list of prices
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()
store = CredentialStore()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_market_id(raw: str) -> str:
    raw = raw.strip()
    if "betfair.com" in raw:
        parts = raw.split("market/")
        if len(parts) > 1:
            mid = parts[-1].split("?")[0].strip("/")
            return mid if mid.startswith("1.") else f"1.{mid}"
    if raw.isdigit():
        return f"1.{raw}"
    return raw


def _countdown_html(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    text = f"{mins}m {secs:02d}s"
    if seconds > 300:
        cls = "countdown-green"
    elif seconds > 120:
        cls = "countdown-yellow"
    else:
        cls = "countdown-red"
    return f'<span class="{cls}">⏱ {text} to Off</span>'


def _conf_bar_html(score: int) -> str:
    pct = score * 10
    if score >= 7:
        cls = "conf-bar-fill-high"
    elif score >= 4:
        cls = "conf-bar-fill-med"
    else:
        cls = "conf-bar-fill-low"
    return (
        f'<div class="conf-bar-wrap">'
        f'<div class="{cls}" style="width:{pct}%"></div>'
        f'</div>'
        f'<small style="color:#888">{score}/10</small>'
    )


def _wom_bar_html(name: str, wom: float, delta: float) -> str:
    lay_pct  = int((1 - wom) * 100)
    back_pct = int(wom * 100)
    delta_str = ""
    if delta > 0.05:
        delta_str = f'<span style="color:#00ff88;font-size:0.7rem"> ↑+{delta:.0%}</span>'
    elif delta < -0.05:
        delta_str = f'<span style="color:#ff4444;font-size:0.7rem"> ↓{delta:.0%}</span>'
    return (
        f'<div class="wom-container">'
        f'<span class="wom-label">{name[:18]}</span>'
        f'<div class="wom-bar-wrap">'
        f'<div class="wom-lay-fill"  style="width:{lay_pct}%"></div>'
        f'<div class="wom-back-fill" style="width:{back_pct}%"></div>'
        f'</div>'
        f'<span class="wom-pct">{wom:.0%}{delta_str}</span>'
        f'</div>'
    )


def _verdict_card_html(sig: Signal) -> str:
    cls_map = {"BACK": "verdict-back", "LAY": "verdict-lay",
               "SCALP": "verdict-scalp", "NONE": "verdict-none"}
    cls = cls_map.get(sig.verdict_code, "verdict-none")
    sm  = '<span class="smart-money">⚡ Smart Money</span>' if sig.smart_money else ""

    # Diagnostics line — shows why signal is what it is
    diag = []
    diag.append(f"WOM {sig.wom:.0%}")
    if sig.wom_delta:
        diag.append(f"delta {sig.wom_delta:+.0%}/60s")
    if sig.total_matched >= 1000:
        diag.append(f"£{sig.total_matched/1000:.1f}k matched")
    else:
        diag.append(f"£{sig.total_matched:.0f} matched")
    if not sig.spread_ok:
        diag.append("⚠ Wide spread")
    diag_str = " · ".join(diag)

    return (
        f'<div class="{cls}">'
        f'<strong style="font-size:1rem">{sig.runner_name}</strong> {sm}<br>'
        f'<span style="font-size:0.85rem;color:#ccc">{sig.verdict}</span><br>'
        f'<span style="font-size:0.72rem;color:#777">{diag_str}</span>'
        f'</div>'
    )


# ── Login / setup screen ──────────────────────────────────────────────────────

def _login_from_secrets() -> bool:
    """Try to login using Streamlit cloud secrets. Returns True on success."""
    try:
        secrets = st.secrets
        username = secrets["BETFAIR_USERNAME"]
        password = secrets["BETFAIR_PASSWORD"]
        app_key  = secrets["BETFAIR_APP_KEY"]
    except Exception:
        return False  # No secrets configured

    connector = BetfairConnector(
        username=username,
        password=password,
        app_key=app_key,
        demo=False,
    )
    if connector.login():
        st.session_state.authenticated = True
        st.session_state.connector     = connector
        st.session_state.engine        = AnalysisEngine()
        return True

    # Show diagnostic info if login fails
    st.warning(f"Cloud auto-login attempted for {username} — failed. "
               f"Check secrets and Betfair account settings.")
    return False


def render_login():
    st.markdown("""
    <div class="pots-header">
        <p class="pots-title">🏇 POTS</p>
        <p class="pots-subtitle">PREOFF TRADING SYSTEM</p>
    </div>
    """, unsafe_allow_html=True)

    # Try cloud secrets first (Streamlit Cloud deployment)
    if _login_from_secrets():
        st.rerun()
        return

    if store.exists():
        st.markdown("### 🔐 Enter Master Password")
        pw = st.text_input("Master Password", type="password", key="login_pw")
        if st.button("Unlock", use_container_width=True, type="primary"):
            creds = store.load(pw)
            if creds:
                connector = BetfairConnector(
                    username=creds["username"],
                    password=creds["password"],
                    app_key=creds["app_key"],
                    demo=False,
                )
                if connector.login():
                    st.session_state.authenticated = True
                    st.session_state.connector     = connector
                    st.session_state.engine        = AnalysisEngine()
                    st.session_state.master_pw     = pw
                    st.rerun()
                else:
                    st.error("Betfair login failed — check your stored credentials.")
            else:
                st.error("Wrong master password.")

        st.markdown("---")
        with st.expander("Update stored credentials"):
            render_setup_form()
    else:
        st.markdown("### ⚙️ First-Time Setup")
        st.info("Enter your Betfair credentials and choose a master password. "
                "They will be stored encrypted on this device.")
        render_setup_form()


def render_setup_form():
    with st.form("setup_form"):
        master  = st.text_input("Choose a Master Password", type="password")
        master2 = st.text_input("Confirm Master Password",  type="password")
        uname   = st.text_input("Betfair Username (email)")
        pw      = st.text_input("Betfair Password", type="password")
        key     = st.text_input("Betfair App Key (Delay key)")
        submit  = st.form_submit_button("Save & Login", use_container_width=True)

        if submit:
            if master != master2:
                st.error("Passwords do not match.")
            elif not all([master, uname, pw, key]):
                st.error("All fields are required.")
            else:
                store.save(master, uname, pw, key)
                connector = BetfairConnector(
                    username=uname, password=pw, app_key=key, demo=False
                )
                if connector.login():
                    st.session_state.authenticated = True
                    st.session_state.connector     = connector
                    st.session_state.engine        = AnalysisEngine()
                    st.session_state.master_pw     = master
                    st.success("Credentials saved. Logging in...")
                    st.rerun()
                else:
                    st.error("Betfair login failed — check your credentials.")


# ── Main trading dashboard ────────────────────────────────────────────────────

def render_dashboard():
    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="pots-header">
        <p class="pots-title">🏇 POTS</p>
        <p class="pots-subtitle">PREOFF TRADING SYSTEM — LIVE</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Market input ───────────────────────────────────────────────────────────
    col_url, col_btn, col_logout = st.columns([5, 1, 1])
    with col_url:
        raw_url = st.text_input(
            "Betfair Race URL or Market ID",
            placeholder="https://www.betfair.com/exchange/plus/horse-racing/market/1.XXXXXXXXX",
            label_visibility="collapsed",
        )
    with col_btn:
        load_btn = st.button("▶ Load", use_container_width=True, type="primary")
    with col_logout:
        if st.button("Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.connector     = None
            st.rerun()

    if load_btn and raw_url:
        st.session_state.market_id     = _parse_market_id(raw_url)
        st.session_state.market_data   = None
        st.session_state.signals       = []
        st.session_state.error         = ""
        st.session_state.price_histories = {}

    if not st.session_state.market_id:
        st.info("👆 Paste a Betfair race URL above and press Load to begin.")
        return

    # ── Fetch data ─────────────────────────────────────────────────────────────
    now = time.time()
    if now - st.session_state.last_fetch >= 5:
        data = st.session_state.connector.fetch_market(st.session_state.market_id)
        if data and "_error" not in data:
            st.session_state.market_data = data
            signals = st.session_state.engine.analyse(data)
            # Persist price histories across Streamlit reruns
            for sig in signals:
                name = sig.runner_name
                if name not in st.session_state.price_histories:
                    st.session_state.price_histories[name] = []
                mid = ((sig.back_price or 0) + (sig.lay_price or 0)) / 2
                if mid > 0:
                    st.session_state.price_histories[name].append(mid)
                    # Keep last 120 points (10 mins at 5s intervals)
                    if len(st.session_state.price_histories[name]) > 120:
                        st.session_state.price_histories[name].pop(0)
                # Inject persisted history into signal
                sig.price_history = list(st.session_state.price_histories[name])
            st.session_state.signals = signals
            st.session_state.error   = ""
        else:
            st.session_state.error = data.get("_error", "Unknown error") if data else "No data returned"
        st.session_state.last_fetch = now

    if st.session_state.error:
        st.error(f"⚠ {st.session_state.error}")
        return

    data    = st.session_state.market_data
    signals = st.session_state.signals

    if not data:
        st.info("Loading market data...")
        time.sleep(1)
        st.rerun()
        return

    secs = data.get("seconds_to_start", 0)

    # Pre-off lockout
    if secs <= 60:
        st.warning("⚑ Race is within 60 seconds of the off — trading suspended.")
        return

    # Outside window
    if secs > 600:
        mins = int(secs // 60)
        st.info(f"⏳ Race is {mins} minutes away. Signals activate inside 10 minutes.")

    # ── Market bar ─────────────────────────────────────────────────────────────
    col_name, col_time, col_ts = st.columns([3, 2, 2])
    with col_name:
        st.markdown(f"**{data.get('market_name', '')}**")
    with col_time:
        st.markdown(_countdown_html(secs), unsafe_allow_html=True)
    with col_ts:
        ts = data.get("fetched_at", "")[:19].replace("T", " ")
        st.markdown(f'<small style="color:#555">Updated: {ts} UTC</small>',
                    unsafe_allow_html=True)

    st.markdown("---")

    # ── Runner table (compact, mobile-friendly) ───────────────────────────────
    st.markdown("#### 📊 Runners")

    # Build a single HTML table — much more mobile-friendly than st.columns
    rows = ""
    for sig in signals:
        trend_colour = {"Steaming": "#2ecc71", "Drifting": "#e74c3c"}.get(sig.price_trend, "#f39c12")
        trend_arrow  = {"Steaming": "▼", "Drifting": "▲"}.get(sig.price_trend, "─")
        conf_colour  = "#27ae60" if sig.confidence >= 7 else "#f39c12" if sig.confidence >= 4 else "#e74c3c"
        vol = sig.total_matched
        if vol >= 1000:
            vol_str = f"£{vol/1000:.1f}k"
        else:
            vol_str = f"£{vol:.0f}"
        rows += f"""
        <tr>
            <td style="color:#fff;font-weight:bold;padding:6px 4px">{sig.runner_name[:16]}</td>
            <td style="color:#2ecc71;font-weight:bold;text-align:center">{sig.back_price or "—"}</td>
            <td style="color:#e74c3c;font-weight:bold;text-align:center">{sig.lay_price or "—"}</td>
            <td style="color:#f39c12;text-align:center">{sig.lpt or "—"}</td>
            <td style="color:{trend_colour};text-align:center">{trend_arrow}</td>
            <td style="color:#aed6f1;text-align:center">{vol_str}</td>
            <td style="color:{conf_colour};text-align:center;font-weight:bold">{sig.confidence}/10</td>
        </tr>"""

    table_html = f"""
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:0.85rem">
        <thead>
            <tr style="border-bottom:1px solid #444;color:#888;font-size:0.75rem">
                <th style="text-align:left;padding:4px">Runner</th>
                <th>Back</th><th>Lay</th><th>LPT</th><th>Trend</th><th>Matched</th><th>Conf</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    </div>"""
    st.markdown(table_html, unsafe_allow_html=True)

    st.markdown("---")

    # ── WOM bars ───────────────────────────────────────────────────────────────
    st.markdown("#### 💰 Weight of Money")
    wom_html = "".join(
        _wom_bar_html(s.runner_name, s.wom, s.wom_delta) for s in signals
    )
    st.markdown(wom_html, unsafe_allow_html=True)

    st.markdown("---")

    # ── Price history micro charts ─────────────────────────────────────────────
    st.markdown("#### 📈 Live Odds History")

    # Build chart data from price_history stored in signals
    chart_signals = [s for s in signals if len(s.price_history) >= 2]
    if not chart_signals:
        st.caption("Accumulating price history — charts appear after a few polls...")
    else:
        import json
        # Pick top 4 runners by matched volume for the chart
        top_runners = sorted(chart_signals, key=lambda s: s.total_matched, reverse=True)[:4]

        for sig in top_runners:
            history = sig.price_history[-60:]  # Last 60 data points max
            if len(history) < 2:
                continue

            # Determine chart colour based on trend
            line_colour = {"Steaming": "#2ecc71", "Drifting": "#e74c3c"}.get(
                sig.price_trend, "#f39c12"
            )

            # Build sparkline as SVG
            min_p = min(history)
            max_p = max(history)
            price_range = max_p - min_p if max_p != min_p else 0.1
            w, h = 300, 50
            points = []
            for i, p in enumerate(history):
                x = int(i / (len(history) - 1) * w)
                y = int(h - ((p - min_p) / price_range) * (h - 4) - 2)
                points.append(f"{x},{y}")
            polyline = " ".join(points)

            # Current price vs start — show direction
            price_change = history[-1] - history[0]
            change_str = f"{'▼' if price_change < 0 else '▲' if price_change > 0 else '─'} {abs(price_change):.2f}"
            change_col = "#2ecc71" if price_change < 0 else "#e74c3c" if price_change > 0 else "#888"

            svg = f"""
            <div style="margin:6px 0;background:#262932;border-radius:6px;padding:8px 12px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                    <span style="color:#fff;font-weight:bold;font-size:0.85rem">{sig.runner_name[:20]}</span>
                    <span style="color:#f39c12;font-weight:bold">{sig.back_price or "—"}</span>
                    <span style="color:{change_col};font-size:0.8rem">{change_str}</span>
                    <span style="color:#888;font-size:0.75rem">{len(history)} pts</span>
                </div>
                <svg viewBox="0 0 {w} {h}" width="100%" height="40" preserveAspectRatio="none"
                     style="display:block">
                    <polyline points="{polyline}"
                        fill="none" stroke="{line_colour}" stroke-width="2"
                        stroke-linejoin="round" stroke-linecap="round"/>
                    <circle cx="{points[-1].split(',')[0]}" cy="{points[-1].split(',')[1]}"
                        r="3" fill="{line_colour}"/>
                </svg>
                <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:#555;margin-top:2px">
                    <span>10 min ago</span><span>Now</span>
                </div>
            </div>"""
            st.markdown(svg, unsafe_allow_html=True)

    st.markdown("---")

    # ── Trade verdicts ─────────────────────────────────────────────────────────
    st.markdown("#### 🎯 Trade Verdicts")
    for sig in signals:
        st.markdown(_verdict_card_html(sig), unsafe_allow_html=True)

    # ── Top signal detail ──────────────────────────────────────────────────────
    if signals:
        top = signals[0]
        if top.verdict_code != "NONE":
            st.markdown("---")
            st.markdown(f"#### 🔍 Top Signal: {top.runner_name}")
            col_a, col_b = st.columns(2)
            col_a.metric("Back", f"{top.back_price or '—'}")
            col_b.metric("Lay",  f"{top.lay_price  or '—'}")
            col_a.metric("LPT",  f"{top.lpt or '—'}")
            col_b.metric("EMA-20", f"{top.ema_20:.2f}" if top.ema_20 else "—")
            if top.resistance_lvl:
                st.metric("Resistance Wall", f"{top.resistance_lvl:.2f}")
            if top.reasons:
                st.markdown("**Signal Evidence:**")
                for r in top.reasons:
                    st.markdown(f"- {r}")

    # ── Auto-refresh ───────────────────────────────────────────────────────────
    st.markdown("---")
    refresh_col, _ = st.columns([1, 4])
    with refresh_col:
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.session_state.last_fetch = 0
            st.rerun()

    # Auto-refresh every 6 seconds
    time.sleep(6)
    st.rerun()


# ── Router ────────────────────────────────────────────────────────────────────

if st.session_state.authenticated:
    render_dashboard()
else:
    render_login()
