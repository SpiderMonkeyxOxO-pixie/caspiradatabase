"""Caspira Solutions — Database Infrastructure Monitoring console.

Operations view of the database estate managed on behalf of Autofix Sdn Bhd:
server health, replication status, capacity, backups, alerts and scheduled
maintenance, sourced from telemetry.py.

Run with:  streamlit run app.py
"""

import base64
import random
import time
from pathlib import Path

import pandas as pd
import streamlit as st

import telemetry as tm
import store
import views

LOGO_PATH = Path(__file__).parent / "logo.png"
LOGO_DATA_URI = f"data:image/png;base64,{base64.b64encode(LOGO_PATH.read_bytes()).decode()}"

st.set_page_config(page_title="Caspira Solutions | Database Infrastructure Monitoring", page_icon=str(LOGO_PATH), layout="wide")

# ---------------------------------------------------------------------------
# Visual theme — GitHub-dark inspired: deep slate panels, hairline borders,
# pill-shaped labels with tinted fills, and the GitHub system font stack.
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Foundation ─────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
.block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1520px; }
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.09); border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.17); }

/* ── Top bar ─────────────────────────────────────────────────────── */
header[data-testid="stHeader"] {
    background: #070a14; border-bottom: 1px solid rgba(255,255,255,0.06);
    height: 2.6rem; min-height: 2.6rem;
}
header[data-testid="stHeader"] [data-testid="stToolbarActions"],
header[data-testid="stHeader"] [data-testid="stMainMenu"],
[data-testid="stDeployButton"] { display: none !important; }
header[data-testid="stHeader"] [data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"] { display: flex !important; visibility: visible !important; }

/* ── Type ─────────────────────────────────────────────────────────── */
h1 { font-size: 1.35rem !important; font-weight: 700 !important; letter-spacing: -0.02em !important; color: #f1f5f9 !important; }
h2 { font-size: 1.1rem !important; font-weight: 600 !important; letter-spacing: -0.015em; color: #e2e8f0 !important; }
h3 { font-size: 0.95rem !important; font-weight: 600 !important; color: #e2e8f0 !important; }
p, span, label, div { color: #94a3b8; }
hr { border: none; border-top: 1px solid rgba(255,255,255,0.07); margin: 10px 0; }
code, .gh-mono { font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace; font-size: 0.82em; color: #67e8f9; }

/* ── Sidebar ──────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: #070a14 !important; border-right: 1px solid rgba(255,255,255,0.06);
    min-width: 252px !important; max-width: 270px !important;
}
section[data-testid="stSidebar"] .block-container { padding-top: 0.75rem; padding-bottom: 1rem; }
section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #0d1120 !important; border-color: rgba(255,255,255,0.07) !important;
}

/* ── Sidebar: brand ───────────────────────────────────────────────── */
.sb-brand { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.sb-logo-img {
    width: 38px; height: 38px; object-fit: contain; flex-shrink: 0;
    border-radius: 8px; background: #0d1120; border: 1px solid rgba(255,255,255,0.08); padding: 4px;
}
.sb-brand-name { color: #e2e8f0; font-weight: 700; font-size: 0.94rem; line-height: 1.25; }
.sb-brand-tag { color: #2d3f55; font-size: 0.69rem; line-height: 1.3; }
.sb-section { color: #2d3f55; font-size: 0.64rem; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; margin: 20px 0 8px; }

/* ── Sidebar: client card ─────────────────────────────────────────── */
.sb-client-card { border: 1px solid rgba(255,255,255,0.07); border-radius: 9px; background: #0d1120; padding: 12px 14px; margin-top: 2px; }
.sb-client-head { margin-bottom: 8px; }
.sb-client-name { color: #e2e8f0; font-weight: 600; font-size: 0.86rem; line-height: 1.3; }
.sb-client-meta { color: #475569; font-size: 0.73rem; line-height: 1.3; }
.sb-client-rows { display: flex; flex-direction: column; gap: 2px; color: #475569; font-size: 0.73rem; padding-bottom: 10px; margin: 8px 0 10px; border-bottom: 1px solid rgba(255,255,255,0.06); }
.sb-client-rows .gh-mono { color: #22d3ee; }
.sb-tier-pill { display: inline-block; padding: 2px 9px; border-radius: 2em; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }
.tier-ent { background: rgba(34,211,238,0.12); color: #22d3ee; border: 1px solid rgba(34,211,238,0.28); }
.tier-mid { background: rgba(245,158,11,0.12); color: #f59e0b; border: 1px solid rgba(245,158,11,0.28); }
.tier-grw { background: rgba(34,197,94,0.12); color: #22c55e; border: 1px solid rgba(34,197,94,0.28); }

/* ── Sidebar: session ─────────────────────────────────────────────── */
.sb-session { border: 1px solid rgba(255,255,255,0.07); border-radius: 9px; background: #0d1120; padding: 11px 13px; display: flex; flex-direction: column; gap: 6px; }
.sb-session-row { display: flex; align-items: center; gap: 7px; color: #22c55e; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.02em; }
.sb-session-meta { color: #2d3f55; font-size: 0.73rem; }
.sb-session-meta b { color: #64748b; }

/* ── Live pulse ───────────────────────────────────────────────────── */
.live-indicator { display: inline-flex; align-items: center; gap: 6px; color: #22c55e; font-size: 0.73rem; font-weight: 600; letter-spacing: 0.05em; }
.live-dot { width: 6px; height: 6px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 0 0 rgba(34,197,94,0.5); animation: pulse-live 2.2s infinite; flex-shrink: 0; }
@keyframes pulse-live {
    0%   { box-shadow: 0 0 0 0 rgba(34,197,94,0.5); }
    70%  { box-shadow: 0 0 0 7px rgba(34,197,94,0); }
    100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
}

/* ── Top banner ───────────────────────────────────────────────────── */
.gh-banner {
    display: flex; align-items: center; justify-content: space-between;
    background: #0d1120; border: 1px solid rgba(255,255,255,0.07); border-radius: 10px;
    padding: 10px 16px; margin-bottom: 18px;
}
.gh-banner .left { display: flex; align-items: center; gap: 10px; }
.gh-banner .org { color: #475569; font-size: 0.82rem; }
.gh-banner .org b { color: #94a3b8; font-weight: 600; }
.gh-pill { display: inline-block; padding: 2px 10px; border-radius: 2em; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; background: rgba(34,211,238,0.12); color: #22d3ee; border: 1px solid rgba(34,211,238,0.28); }
.console-title { font-size: 1.38rem; font-weight: 700; letter-spacing: -0.02em; color: #f1f5f9; margin: 0; line-height: 1.3; }

/* ── Info card ────────────────────────────────────────────────────── */
.info-card { border: 1px solid rgba(34,211,238,0.16); border-left: 3px solid #22d3ee; border-radius: 8px; background: #08101c; padding: 11px 15px; margin-bottom: 16px; }
.info-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.info-card-dot { width: 6px; height: 6px; border-radius: 50%; background: #22d3ee; box-shadow: 0 0 8px rgba(34,211,238,0.7); flex-shrink: 0; }
.info-card-title { color: #67e8f9; font-weight: 700; font-size: 0.83rem; }
.info-card-desc { color: #475569; font-size: 0.78rem; line-height: 1.6; margin: 0; max-width: 100ch; }

/* ── Metric cards ─────────────────────────────────────────────────── */
div[data-testid="stMetric"] { background: #0d1120; border: 1px solid rgba(255,255,255,0.07); border-radius: 10px; padding: 16px 18px 14px; transition: border-color 0.2s, box-shadow 0.2s; }
div[data-testid="stMetric"]:hover { border-color: rgba(34,211,238,0.28); box-shadow: 0 0 18px rgba(34,211,238,0.05); }
div[data-testid="stMetric"] > div:first-child > label { color: #2d3f55 !important; font-size: 0.66rem !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 0.11em !important; }
div[data-testid="stMetricValue"] > div { color: #f1f5f9 !important; font-size: 1.55rem !important; font-weight: 700 !important; font-family: 'Inter', sans-serif !important; letter-spacing: -0.025em !important; line-height: 1.15 !important; }
div[data-testid="stMetricDelta"] span { font-size: 0.74rem; }

/* ── Containers / panels ──────────────────────────────────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] { border: 1px solid rgba(255,255,255,0.07) !important; border-radius: 10px !important; background: #090d1b; }
div[data-testid="stVerticalBlockBorderWrapper"] > div { gap: 0.9rem; }

/* ── Buttons ──────────────────────────────────────────────────────── */
.stButton > button {
    background: rgba(255,255,255,0.04) !important; border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 7px !important; color: #64748b !important; font-weight: 500 !important;
    font-size: 0.83rem !important; font-family: 'Inter', sans-serif !important; transition: all 0.15s !important;
}
.stButton > button:hover { background: rgba(255,255,255,0.08) !important; border-color: rgba(255,255,255,0.18) !important; color: #e2e8f0 !important; }
.stButton > button[kind="primary"], .stButton > button[kind="primaryFormSubmit"] {
    background: rgba(34,211,238,0.13) !important; border-color: rgba(34,211,238,0.38) !important;
    color: #22d3ee !important; font-weight: 600 !important;
}
.stButton > button[kind="primary"]:hover, .stButton > button[kind="primaryFormSubmit"]:hover {
    background: rgba(34,211,238,0.2) !important; border-color: rgba(34,211,238,0.55) !important;
    color: #67e8f9 !important; box-shadow: 0 0 14px rgba(34,211,238,0.14) !important;
}
.stButton > button[kind="tertiary"] { background: transparent !important; border-color: transparent !important; color: #475569 !important; }
.stButton > button[kind="tertiary"]:hover { background: rgba(255,255,255,0.05) !important; color: #94a3b8 !important; }

/* ── Forms ────────────────────────────────────────────────────────── */
div[data-testid="stForm"] { border: 1px solid rgba(255,255,255,0.07) !important; border-radius: 10px !important; background: #090d1b; }

/* ── Tabs ─────────────────────────────────────────────────────────── */
div[data-baseweb="tab-list"] { background: transparent !important; gap: 2px; }
button[data-baseweb="tab"] { font-family: 'Inter', sans-serif !important; font-size: 0.84rem !important; font-weight: 500 !important; color: #475569 !important; padding: 8px 14px !important; background: transparent !important; transition: color 0.15s !important; }
button[data-baseweb="tab"]:hover { color: #94a3b8 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: #f1f5f9 !important; font-weight: 600 !important; }
div[data-baseweb="tab-highlight"] { background: #22d3ee !important; height: 2px !important; }
div[data-baseweb="tab-border"] { background: rgba(255,255,255,0.07) !important; height: 1px !important; }

/* ── DataFrames ───────────────────────────────────────────────────── */
div[data-testid="stDataFrame"] { border: 1px solid rgba(255,255,255,0.07) !important; border-radius: 10px !important; overflow: hidden; }

/* ── Inputs & selects ─────────────────────────────────────────────── */
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {
    background: #070a14 !important; border-color: rgba(255,255,255,0.1) !important;
    border-radius: 7px !important; font-family: 'Inter', sans-serif !important;
}
div[data-baseweb="select"] > div:focus-within, div[data-baseweb="input"] > div:focus-within {
    border-color: rgba(34,211,238,0.5) !important; box-shadow: 0 0 0 3px rgba(34,211,238,0.1) !important;
}
span[data-baseweb="tag"] { background: rgba(34,211,238,0.13) !important; border: 1px solid rgba(34,211,238,0.3) !important; border-radius: 6px !important; }
span[data-baseweb="tag"] * { color: #67e8f9 !important; fill: #67e8f9 !important; }

/* ── Captions ─────────────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] { color: #2d3f55; font-size: 0.75rem; }

/* ── Expanders ────────────────────────────────────────────────────── */
div[data-testid="stExpander"] { border: 1px solid rgba(255,255,255,0.07) !important; border-radius: 10px !important; background: #090d1b; }
div[data-testid="stExpander"] summary { color: #94a3b8 !important; font-weight: 600 !important; font-size: 0.87rem !important; padding: 10px 14px !important; }

/* ── Donut ─────────────────────────────────────────────────────────── */
.donut-wrap { display: flex; align-items: center; gap: 22px; }
.donut { width: 112px; height: 112px; border-radius: 50%; flex-shrink: 0; position: relative; display: flex; align-items: center; justify-content: center; }
.donut::before { content: ""; position: absolute; inset: 14px; border-radius: 50%; background: #0d1120; }
.donut-center { position: relative; z-index: 1; text-align: center; }
.donut-center .donut-value { color: #f1f5f9; font-size: 1.5rem; font-weight: 700; line-height: 1.1; letter-spacing: -0.02em; }
.donut-center .donut-label { color: #2d3f55; font-size: 0.56rem; letter-spacing: 0.1em; text-transform: uppercase; margin-top: 2px; }
.donut-legend { display: flex; flex-direction: column; gap: 8px; }
.donut-legend-row { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: #64748b; }
.donut-legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.donut-legend-count { color: #334155; font-size: 0.75rem; margin-left: auto; padding-left: 16px; font-variant-numeric: tabular-nums; }

/* ── Topology ──────────────────────────────────────────────────────── */
.topo-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 12px; margin-top: 10px; margin-bottom: 18px; }
.topo-cluster { border: 1px solid rgba(255,255,255,0.07); border-radius: 9px; background: #0d1120; padding: 15px 17px; }
.topo-engine { color: #67e8f9; font-weight: 700; font-size: 0.79rem; letter-spacing: 0.02em; margin-bottom: 12px; text-transform: uppercase; }
.topo-row { display: flex; flex-wrap: wrap; gap: 12px; }
.topo-connector { width: 1px; height: 16px; margin: 0 0 0 20px; background: rgba(255,255,255,0.07); }
.topo-node { display: flex; flex-direction: column; gap: 4px; min-width: 172px; border: 1px solid rgba(255,255,255,0.07); border-left: 3px solid #334155; border-radius: 7px; background: #070a14; padding: 9px 13px; }
.topo-node.role-primary { border-left-color: #8b5cf6; }
.topo-node.role-replica { border-left-color: #22d3ee; }
.topo-node.role-cache { border-left-color: #34d399; }
.topo-node-head { display: flex; align-items: center; gap: 7px; }
.topo-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.topo-dot.st-healthy { background: #22c55e; box-shadow: 0 0 7px rgba(34,197,94,0.6); }
.topo-dot.st-warning { background: #f59e0b; box-shadow: 0 0 7px rgba(245,158,11,0.6); }
.topo-dot.st-critical { background: #ef4444; box-shadow: 0 0 7px rgba(239,68,68,0.6); }
.topo-role { color: #2d3f55; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.09em; text-transform: uppercase; }
.topo-name { color: #e2e8f0; font-size: 0.84rem; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
.topo-meta { color: #334155; font-size: 0.73rem; }

/* ── Toolkit ───────────────────────────────────────────────────────── */
.tool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; margin-top: 6px; }
.tool-card { border: 1px solid rgba(255,255,255,0.07); border-radius: 9px; background: #0d1120; padding: 13px 14px; transition: border-color 0.15s; }
.tool-card:hover { border-color: rgba(34,211,238,0.3); }
.tool-card .tool-name a { color: #22d3ee; text-decoration: none; font-weight: 600; font-size: 0.9rem; }
.tool-card .tool-name a:hover { text-decoration: underline; }
.tool-card .tool-cat { display: inline-block; margin-top: 4px; padding: 1px 8px; border-radius: 2em; font-size: 0.64rem; font-weight: 700; letter-spacing: 0.05em; background: rgba(148,163,184,0.09); color: #334155; border: 1px solid rgba(148,163,184,0.18); }
.tool-card .tool-desc { color: #334155; font-size: 0.78rem; margin-top: 7px; line-height: 1.45; }

/* ── Login ─────────────────────────────────────────────────────────── */
.login-brand { display: flex; flex-direction: column; align-items: center; gap: 10px; margin-bottom: 6px; }
.login-logo { width: 52px; height: 52px; border-radius: 12px; }
.login-title { color: #f1f5f9; font-size: 1.3rem; font-weight: 700; letter-spacing: -0.018em; }
.login-sub { color: #334155; font-size: 0.82rem; text-align: center; max-width: 360px; line-height: 1.55; }
.login-accounts { border: 1px solid rgba(255,255,255,0.07); border-radius: 9px; background: #0d1120; padding: 12px 16px; margin-top: 4px; }
.login-accounts-label { color: #2d3f55; font-size: 0.63rem; font-weight: 700; letter-spacing: 0.11em; text-transform: uppercase; margin-bottom: 7px; }
.login-account-row { color: #64748b; font-size: 0.8rem; padding: 3px 0; display: flex; justify-content: space-between; gap: 10px; }
.login-account-role { color: #22d3ee; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sign-in gate — demo accounts provisioned for the IT Operations team
# ---------------------------------------------------------------------------
ACCOUNTS = {
    "CSPR-Data Operation Specialist": "Data Operation Specialist",
    "CSPR-Monitoring": "Monitoring",
    "CSPR-I.T Assistant": "I.T Assistant",
    "CSPR-General Manager": "General Manager",
    "CSPR-Back-end Developer": "Back-end Developer",
    "CSPR-Dev-Ops": "Dev-Ops",
    "CSPR-Infrastructure Engineer": "Infrastructure Engineer",
    "CSPR-Customer Service": "Customer Service",
    "CSPR-Data Analyst": "Data Analyst",
}

ACCOUNT_PASSWORD = "@Tiger112211"

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if st.session_state.auth_user is None:
    _, login_col, _ = st.columns([1, 1.4, 1])
    with login_col:
        st.write("")
        st.write("")
        st.markdown(
            f"""
            <div class="login-brand">
                <img class="login-logo" src="{LOGO_DATA_URI}" alt="{tm.PROVIDER} logo" />
                <div class="login-title">{tm.PROVIDER}</div>
                <div class="login-sub">Database Infrastructure Monitoring &middot; sign in with your IT Operations account to access the managed-services console.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        with st.form("login_form", border=True):
            username = st.selectbox("Account", options=list(ACCOUNTS.keys()))
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", icon=":material/login:", width="stretch", type="primary")
            if submitted:
                if password == ACCOUNT_PASSWORD:
                    st.session_state.auth_user = username
                    st.rerun()
                else:
                    st.error("Incorrect password for this account. Check with your team lead and try again.")

        st.markdown(
            '<div class="login-accounts"><div class="login-accounts-label">Provisioned accounts</div>'
            + "".join(
                f'<div class="login-account-row"><span>{name}</span><span class="login-account-role">{role}</span></div>'
                for name, role in ACCOUNTS.items()
            )
            + "</div>",
            unsafe_allow_html=True,
        )
    st.stop()

@st.dialog("About this console")
def about_dialog():
    st.markdown(f"**{tm.PROVIDER} &middot; Database Infrastructure Monitoring**".replace("&middot;", "·"))
    st.write(
        "This console gives the managed-services team a single view into the health, performance and "
        "operational posture of every database host run on behalf of our clients. It brings together "
        "fleet inventory, live alerts, backup coverage and maintenance scheduling so issues can be "
        "spotted and resolved before they affect a client's business."
    )
    st.caption(
        "Switch clients from the dropdown above the navigation tabs — each account has its own "
        "isolated estate, alert history and maintenance calendar."
    )
    st.divider()
    st.caption(f"Build: {tm.PROVIDER} console &middot; v1.0".replace("&middot;", "·"))


@st.dialog("Keyboard shortcuts")
def shortcuts_dialog():
    st.write("These shortcuts work anywhere in the console:")
    shortcuts = [
        ("R", "Rerun the app and pull the latest telemetry"),
        ("C", "Clear the cache (developer use)"),
        ("Ctrl / ⌘ + Enter", "Submit the focused widget or form"),
        ("Esc", "Close this dialog or an open popover"),
        ("Tab", "Move between filters, tabs and table cells"),
    ]
    for key, desc in shortcuts:
        c1, c2 = st.columns([1, 3], vertical_alignment="center")
        with c1:
            st.markdown(f"`{key}`")
        with c2:
            st.caption(desc)


@st.dialog("Documentation")
def documentation_dialog():
    st.write("Quick orientation for each section of the console:")
    sections = [
        ("Fleet", "Real-time inventory and health snapshot of every managed database host."),
        ("Server detail", "Deep-dive metrics, latency, replication and capacity projections for one host."),
        ("Alerts & incidents", "Live monitoring event feed — filter, triage and track ownership."),
        ("Backups & maintenance", "Backup run history and the upcoming change-management calendar."),
        ("Toolkit", "Quick links to the external platforms the team uses day to day."),
    ]
    for name, desc in sections:
        st.markdown(f"**{name}**")
        st.caption(desc)
    st.divider()
    st.caption("For deeper platform documentation, contact the IT Operations team lead.")


@st.dialog("Report an issue")
def report_issue_dialog():
    st.write("Spotted something wrong with the console itself (not a database alert)? Let the team know.")
    st.selectbox("Type", ["Display issue", "Incorrect data", "Performance", "Feature request", "Other"])
    description = st.text_area("Description", placeholder="What happened, and what did you expect instead?")
    if st.button("Submit report", icon=":material/send:", type="primary"):
        if description.strip():
            st.success("Thanks — your report has been logged for the IT Operations team to review.")
        else:
            st.warning("Add a short description before submitting.")


# ---------------------------------------------------------------------------
# Session state / sidebar controls
# ---------------------------------------------------------------------------
if "jitter_seed" not in st.session_state:
    st.session_state.jitter_seed = 0

TIER_PILL_CLASS = {"Enterprise": "tier-ent", "Mid-Market": "tier-mid", "Growth": "tier-grw"}

with st.sidebar:
    st.markdown(
        f"""
        <div class="sb-brand">
            <img class="sb-logo-img" src="{LOGO_DATA_URI}" alt="{tm.PROVIDER} logo" />
            <div>
                <div class="sb-brand-name">{tm.PROVIDER}</div>
                <div class="sb-brand-tag">Database Infrastructure Monitoring &middot; Managed Services Console</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sb-section">Account</div>', unsafe_allow_html=True)
    client_name = st.selectbox(
        "Client account", options=[c["name"] for c in tm.CLIENTS], label_visibility="collapsed",
    )
    client = next(c for c in tm.CLIENTS if c["name"] == client_name)
    tier_class = TIER_PILL_CLASS.get(client["tier"], "tier-mid")

    st.markdown(
        f"""
        <div class="sb-client-card">
            <div class="sb-client-head">
                <div class="sb-client-name">{client['name']}</div>
                <div class="sb-client-meta">{client['industry']}</div>
            </div>
            <div class="sb-client-rows">
                <span>{client['hq']}</span>
                <span class="gh-mono">{client['domain']}</span>
            </div>
            <span class="sb-tier-pill {tier_class}">{client['tier']} tier</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sb-section">Controls</div>', unsafe_allow_html=True)
    if st.button("Refresh metrics", icon=":material/refresh:", width="stretch"):
        st.session_state.jitter_seed += 1

    live_mode = st.toggle(
        "Live mode", value=True, key="live_mode",
        help="Continuously stream the Server detail charts, redrawing every few seconds to simulate a live telemetry feed.",
    )

    window_hours = st.select_slider(
        ":material/history: History window (hours)", options=[6, 12, 24, 48, 72], value=24,
    )

    fleet_template = tm.build_fleet(client)
    region_filter = st.multiselect(
        ":material/public: Region",
        options=sorted({s["region"] for s in fleet_template}),
        default=sorted({s["region"] for s in fleet_template}),
    )

    st.markdown('<div class="sb-section">Session</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="sb-session">
            <div class="sb-session-row"><span class="live-dot"></span> All systems operational</div>
            <div class="sb-session-meta">Signed in as <b>{st.session_state.auth_user}</b> &middot; {ACCOUNTS.get(st.session_state.auth_user, "")}</div>
            <div class="sb-session-meta">Last refreshed {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Metrics refresh automatically every five minutes. Use \"Refresh metrics\" to pull the latest readings on demand.")

    st.write("")
    with st.popover("Console actions", icon=":material/more_vert:", width="stretch"):
        st.markdown("**Console actions**")
        if st.button("About this console", icon=":material/info:", width="stretch", type="tertiary"):
            about_dialog()
        if st.button("Keyboard shortcuts", icon=":material/keyboard:", width="stretch", type="tertiary"):
            shortcuts_dialog()
        if st.button("Documentation", icon=":material/menu_book:", width="stretch", type="tertiary"):
            documentation_dialog()
        if st.button("Report an issue", icon=":material/bug_report:", width="stretch", type="tertiary"):
            report_issue_dialog()
        st.divider()
        if st.button("Sign out", icon=":material/logout:", width="stretch", type="tertiary"):
            st.session_state.auth_user = None
            st.rerun()
        st.divider()
        st.caption(f"Build: {tm.PROVIDER} console &middot; v1.0".replace("&middot;", "·"))

# ---------------------------------------------------------------------------
# Pull current telemetry for the selected client
# ---------------------------------------------------------------------------
seed = f"{client['code']}-{st.session_state.jitter_seed}"
servers = [s for s in fleet_template if s["region"] in region_filter] or fleet_template
histories = {s["name"]: tm.generate_history(s, hours=window_hours, jitter_seed=seed) for s in servers}
snapshots = [tm.latest_snapshot(histories[s["name"]], s) for s in servers]
alerts = tm.generate_alerts(snapshots, jitter_seed=seed)
backups = tm.generate_backup_log(snapshots, jitter_seed=seed)
maintenance = tm.generate_maintenance_schedule(snapshots, jitter_seed=seed)
server_names = [s["name"] for s in snapshots]

# ---------------------------------------------------------------------------
# Header — repo-style breadcrumb banner with a live status pulse
# ---------------------------------------------------------------------------
st.markdown(
    f"""
<div class="gh-banner">
    <div class="left">
        <span class="org">{tm.PROVIDER} <span style="color:#1f2940">/</span> <b>{client['code']}-production</b></span>
        <span class="gh-pill">{client['tier'].upper()}</span>
    </div>
    <div class="left">
        <span class="live-indicator"><span class="live-dot"></span>LIVE</span>
        <span class="org">{client['hq']} &middot; synced {pd.Timestamp.now().strftime('%H:%M:%S')}</span>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(f'<div class="console-title">{client["name"]} — Database Infrastructure Monitoring</div>', unsafe_allow_html=True)
st.caption(
    f"Managed by {tm.PROVIDER} IT Operations  ·  {client['industry']}  ·  {client['hq']}  ·  {client['tier']} tier"
)
st.write("")

healthy = sum(1 for s in snapshots if s["status"] == "Healthy")
warning = sum(1 for s in snapshots if s["status"] == "Warning")
critical = sum(1 for s in snapshots if s["status"] == "Critical")
avg_latency = sum(s["query_latency_ms"] for s in snapshots) / len(snapshots)
avg_uptime = sum(s["uptime_pct_30d"] for s in snapshots) / len(snapshots)
open_incidents = int(((alerts["status"] != "Resolved") & (alerts["severity"] != "Info")).sum())

total_servers = len(snapshots)
healthy_pct = round(100 * healthy / total_servers) if total_servers else 0
warning_pct = round(100 * warning / total_servers) if total_servers else 0

hero_donut, hero_metrics = st.columns([1, 3], gap="large", vertical_alignment="center")
with hero_donut:
    st.markdown(
        f"""
        <div class="donut-wrap">
            <div class="donut" style="background: conic-gradient(#22c55e 0% {healthy_pct}%, #f59e0b {healthy_pct}% {healthy_pct + warning_pct}%, #ef4444 {healthy_pct + warning_pct}% 100%);">
                <div class="donut-center">
                    <div class="donut-value">{total_servers}</div>
                    <div class="donut-label">Hosts</div>
                </div>
            </div>
            <div class="donut-legend">
                <div class="donut-legend-row"><span class="donut-legend-dot" style="background-color:#22c55e;"></span> Healthy <span class="donut-legend-count">{healthy}</span></div>
                <div class="donut-legend-row"><span class="donut-legend-dot" style="background-color:#f59e0b;"></span> Warning <span class="donut-legend-count">{warning}</span></div>
                <div class="donut-legend-row"><span class="donut-legend-dot" style="background-color:#ef4444;"></span> Critical <span class="donut-legend-count">{critical}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hero_metrics:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Servers monitored", total_servers)
    m2.metric("Open incidents", open_incidents)
    m3.metric("Avg. query latency", f"{avg_latency:.1f} ms")
    m4.metric("Fleet uptime (sampled)", f"{avg_uptime:.2f}%")

st.write("")

# ---------------------------------------------------------------------------
# Role dispatch — each role gets its own purpose-built view
# ---------------------------------------------------------------------------
store.get()
_role = ACCOUNTS.get(st.session_state.auth_user, "")
_view_fn = views.ROLE_VIEW.get(_role)
if _view_fn:
    _view_fn(
        client=client, snapshots=snapshots, alerts=alerts,
        backups=backups, maintenance=maintenance, histories=histories,
        servers=servers, seed=seed, live_mode=live_mode,
        server_names=server_names, window_hours=window_hours,
    )
else:
    st.warning(f"No view configured for role '{_role}'. Contact your administrator.")

st.write("")
st.caption(
    f"{tm.PROVIDER} IT Operations — confidential. This console is for authorized internal use "
    f"by {tm.PROVIDER} and {client['name']} personnel only. Unauthorized access or distribution is prohibited."
)
