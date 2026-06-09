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
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
}
.block-container {
    padding-top: 1.6rem;
    padding-bottom: 3rem;
    max-width: 1480px;
}
header[data-testid="stHeader"] {
    background-color: #0a0e1a;
    border-bottom: 1px solid #1f2940;
    height: 2.75rem;
    min-height: 2.75rem;
}
header[data-testid="stHeader"] [data-testid="stToolbarActions"],
header[data-testid="stHeader"] [data-testid="stMainMenu"] {
    display: none;
}
header[data-testid="stHeader"] [data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
}
h1 { font-weight: 600; letter-spacing: -0.015em; color: #e2e8f0; }
h2, h3 { font-weight: 600; letter-spacing: -0.01em; color: #e2e8f0; }
p, span, label, div { color: #cbd5e1; }

/* Top banner strip evoking a repo header */
.gh-banner {
    display: flex; align-items: center; justify-content: space-between;
    border: 1px solid #1f2940; border-radius: 6px;
    background: linear-gradient(180deg, #121729 0%, #0d1224 100%);
    padding: 10px 16px; margin-bottom: 18px;
}
.gh-banner .left { display: flex; align-items: center; gap: 10px; }
.gh-banner .org { color: #94a3b8; font-size: 0.84rem; }
.gh-banner .org b { color: #cbd5e1; }
.gh-pill {
    display: inline-block; padding: 2px 10px; border-radius: 2em;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.03em;
    background-color: rgba(34,211,238,0.15); color: #22d3ee; border: 1px solid rgba(34,211,238,0.4);
}
.console-title {
    font-size: 1.5rem; font-weight: 600; letter-spacing: -0.01em;
    color: #e2e8f0; margin: 0 0 2px 0; line-height: 1.3;
}

/* Section importance notes — short callouts on why a view matters */
.info-card {
    border: 1px solid rgba(34,211,238,0.22); border-left: 3px solid #22d3ee; border-radius: 8px;
    background-color: #121729;
    padding: 12px 16px; margin-bottom: 14px;
}
.info-card-head { display: flex; align-items: center; gap: 9px; margin-bottom: 5px; }
.info-card-dot {
    width: 7px; height: 7px; border-radius: 50%; background-color: #22d3ee; flex-shrink: 0;
    box-shadow: 0 0 9px 1px rgba(34,211,238,0.65);
}
.info-card-title { color: #67e8f9; font-weight: 700; font-size: 0.86rem; letter-spacing: 0.005em; }
.info-card-desc { color: #94a3b8; font-size: 0.81rem; line-height: 1.6; margin: 0; max-width: 100ch; }

.live-indicator {
    display: inline-flex; align-items: center; gap: 6px;
    color: #22c55e; font-size: 0.76rem; font-weight: 600; letter-spacing: 0.04em;
}
.live-dot {
    width: 7px; height: 7px; border-radius: 50%; background-color: #22c55e;
    box-shadow: 0 0 0 0 rgba(34,197,94,0.55);
    animation: pulse-live 2s infinite;
}
@keyframes pulse-live {
    0%   { box-shadow: 0 0 0 0 rgba(34,197,94,0.55); }
    70%  { box-shadow: 0 0 0 7px rgba(34,197,94,0); }
    100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
}

/* Metric cards — GitHub "Insights" style tiles */
div[data-testid="stMetric"] {
    background-color: #121729;
    border: 1px solid #1f2940;
    border-radius: 6px;
    padding: 14px 16px 10px 16px;
}
div[data-testid="stMetric"]:hover { border-color: #22d3ee; transition: border-color 0.15s ease-in-out; }
div[data-testid="stMetric"] label { color: #94a3b8 !important; font-size: 0.8rem; }
div[data-testid="stMetricValue"] { font-weight: 600; color: #e2e8f0; font-family: "JetBrains Mono", monospace; }

/* Bordered content panels — GitHub "Box" component */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 6px !important;
    border: 1px solid #1f2940 !important;
    background-color: #0a0e1a;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div { gap: 0.85rem; }

/* Dataframes / tables */
div[data-testid="stDataFrame"] {
    border: 1px solid #1f2940;
    border-radius: 6px;
    overflow: hidden;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #0a0e1a;
    border-right: 1px solid #1f2940;
}
section[data-testid="stSidebar"] .block-container { padding-top: 0.6rem; }
section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #121729;
}

/* Sidebar — brand lockup */
.sb-brand { display: flex; align-items: center; gap: 11px; margin-bottom: 4px; }
.sb-logo-img {
    width: 40px; height: 40px; object-fit: contain; flex-shrink: 0;
    border-radius: 9px; background-color: #121729; border: 1px solid #1f2940; padding: 4px;
}
.sb-brand-name { color: #e2e8f0; font-weight: 700; font-size: 0.98rem; line-height: 1.25; }
.sb-brand-tag { color: #94a3b8; font-size: 0.74rem; line-height: 1.3; }

/* Sidebar — section eyebrow labels */
.sb-section {
    color: #64748b; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; margin: 18px 0 8px 0;
}

/* Sidebar — selected client summary card */
.sb-client-card {
    border: 1px solid #1f2940; border-radius: 8px; background-color: #121729;
    padding: 13px 14px 14px 14px; margin-top: 2px;
}
.sb-client-head { margin-bottom: 10px; }
.sb-client-name { color: #e2e8f0; font-weight: 600; font-size: 0.88rem; line-height: 1.3; }
.sb-client-meta { color: #94a3b8; font-size: 0.76rem; line-height: 1.3; }
.sb-client-rows {
    display: flex; flex-direction: column; gap: 3px; color: #94a3b8; font-size: 0.76rem;
    padding-bottom: 11px; margin-bottom: 11px; border-bottom: 1px solid #1a2338;
}
.sb-client-rows .gh-mono { color: #67e8f9; }
.sb-tier-pill {
    display: inline-block; padding: 2px 10px; border-radius: 2em;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.03em;
}
.tier-ent { background-color: rgba(34,211,238,0.15); color: #22d3ee; border: 1px solid rgba(34,211,238,0.4); }
.tier-mid { background-color: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.4); }
.tier-grw { background-color: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.4); }

/* Sidebar — session / system status block */
.sb-session {
    border: 1px solid #1f2940; border-radius: 8px; background-color: #121729;
    padding: 12px 14px; display: flex; flex-direction: column; gap: 7px;
}
.sb-session-row {
    display: flex; align-items: center; gap: 8px;
    color: #22c55e; font-size: 0.78rem; font-weight: 600;
}
.sb-session-meta { color: #94a3b8; font-size: 0.76rem; }
.sb-session-meta b { color: #cbd5e1; }

/* Buttons — GitHub primary/secondary button look */
.stButton > button {
    border: 1px solid #1f2940; border-radius: 6px; background-color: #1a2338;
    color: #cbd5e1; font-weight: 500; font-size: 0.85rem;
}
.stButton > button:hover { background-color: #1f2940; border-color: #94a3b8; color: #e2e8f0; }

/* Tabs — underline style like GitHub PR tabs */
button[data-baseweb="tab"] { font-weight: 500; color: #cbd5e1; }
button[data-baseweb="tab"]:hover { color: #67e8f9; }
button[data-baseweb="tab"][aria-selected="true"] { color: #e2e8f0; font-weight: 600; }
div[data-baseweb="tab-highlight"] { background-color: #8b5cf6 !important; height: 2px; }
div[data-baseweb="tab-border"] { background-color: #1a2338 !important; }

/* Inputs */
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {
    background-color: #0a0e1a; border-color: #1f2940; border-radius: 6px;
}

/* Multiselect chips — translucent cyan fill with bright, readable text */
span[data-baseweb="tag"] {
    background-color: rgba(34,211,238,0.16) !important;
    border: 1px solid rgba(34,211,238,0.45) !important;
    border-radius: 5px !important;
}
span[data-baseweb="tag"] * { color: #67e8f9 !important; fill: #67e8f9 !important; }

/* Captions / muted text */
.stCaption, [data-testid="stCaptionContainer"] { color: #94a3b8; }

/* Toolkit link cards */
.tool-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 12px; margin-top: 6px;
}
.tool-card {
    border: 1px solid #1f2940; border-radius: 6px; background-color: #121729;
    padding: 13px 15px; transition: border-color 0.15s ease-in-out;
}
.tool-card:hover { border-color: #22d3ee; }
.tool-card .tool-name a {
    color: #22d3ee; text-decoration: none; font-weight: 600; font-size: 0.95rem;
}
.tool-card .tool-name a:hover { text-decoration: underline; }
.tool-card .tool-cat {
    display: inline-block; margin-top: 5px; padding: 1px 9px; border-radius: 2em;
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.03em;
    background-color: rgba(148,163,184,0.15); color: #94a3b8; border: 1px solid rgba(148,163,184,0.35);
}
.tool-card .tool-desc { color: #94a3b8; font-size: 0.8rem; margin-top: 7px; line-height: 1.4; }

/* Fleet health donut */
.donut-wrap { display: flex; align-items: center; gap: 20px; }
.donut {
    width: 108px; height: 108px; border-radius: 50%; flex-shrink: 0; position: relative;
    display: flex; align-items: center; justify-content: center;
}
.donut::before {
    content: ""; position: absolute; inset: 13px; border-radius: 50%; background-color: #121729;
}
.donut-center { position: relative; z-index: 1; text-align: center; }
.donut-center .donut-value { color: #e2e8f0; font-size: 1.4rem; font-weight: 700; line-height: 1.1; }
.donut-center .donut-label { color: #64748b; font-size: 0.62rem; letter-spacing: 0.06em; text-transform: uppercase; }
.donut-legend { display: flex; flex-direction: column; gap: 7px; }
.donut-legend-row { display: flex; align-items: center; gap: 8px; font-size: 0.84rem; color: #cbd5e1; }
.donut-legend-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.donut-legend-count { color: #64748b; font-size: 0.78rem; margin-left: auto; padding-left: 18px; }

/* Replication topology diagram */
.topo-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 14px; margin-top: 10px; margin-bottom: 18px;
}
.topo-cluster {
    border: 1px solid #1f2940; border-radius: 8px; background-color: #121729;
    padding: 16px 18px;
}
.topo-engine { color: #67e8f9; font-weight: 700; font-size: 0.82rem; letter-spacing: 0.01em; margin-bottom: 12px; }
.topo-row { display: flex; flex-wrap: wrap; gap: 14px; }
.topo-connector { width: 1px; height: 18px; margin: 0 0 0 22px; background-color: #1f2940; }
.topo-node {
    display: flex; flex-direction: column; gap: 4px; min-width: 172px;
    border: 1px solid #1f2940; border-left: 3px solid #64748b; border-radius: 6px;
    background-color: #0a0e1a; padding: 9px 13px;
}
.topo-node.role-primary { border-left-color: #8b5cf6; }
.topo-node.role-replica { border-left-color: #22d3ee; }
.topo-node.role-cache { border-left-color: #34d399; }
.topo-node-head { display: flex; align-items: center; gap: 7px; }
.topo-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.topo-dot.st-healthy { background-color: #22c55e; box-shadow: 0 0 7px 0 rgba(34,197,94,0.6); }
.topo-dot.st-warning { background-color: #f59e0b; box-shadow: 0 0 7px 0 rgba(245,158,11,0.6); }
.topo-dot.st-critical { background-color: #ef4444; box-shadow: 0 0 7px 0 rgba(239,68,68,0.6); }
.topo-role { color: #64748b; font-size: 0.64rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; }
.topo-name {
    color: #e2e8f0; font-size: 0.85rem; font-weight: 600;
    font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
}
.topo-meta { color: #64748b; font-size: 0.74rem; }

hr { border-color: #1a2338; }
code, .gh-mono { font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace; font-size: 0.82em; }

/* Sign-in screen */
.login-brand { display: flex; flex-direction: column; align-items: center; gap: 10px; margin-bottom: 6px; }
.login-logo { width: 52px; height: 52px; border-radius: 12px; }
.login-title { color: #e2e8f0; font-size: 1.3rem; font-weight: 700; letter-spacing: -0.01em; }
.login-sub { color: #94a3b8; font-size: 0.84rem; text-align: center; max-width: 360px; line-height: 1.5; }
.login-accounts {
    border: 1px solid #1f2940; border-radius: 8px; background-color: #121729;
    padding: 12px 16px; margin-top: 4px;
}
.login-accounts-label { color: #64748b; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 7px; }
.login-account-row { color: #cbd5e1; font-size: 0.82rem; padding: 3px 0; display: flex; justify-content: space-between; gap: 10px; }
.login-account-role { color: #67e8f9; font-weight: 600; }
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
