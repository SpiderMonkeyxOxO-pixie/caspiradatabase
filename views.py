"""Role-based views and shared UI components for the Caspira console.

Each public view_* function renders the complete tab layout for one role.
Shared components (messaging, email, tickets, reports) are called by the
views that need them. ROLE_VIEW maps role name → view function for dispatch.
"""

import base64
import io
import random
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import store
import telemetry as tm

# ============================================================
# CONSTANTS & SHARED STYLE HELPERS
# ============================================================

_B = "background:"
_BD = ";border:"
_C = ";color:"

STATUS_STYLE = {
    "Healthy":  f"{_B}rgba(34,197,94,0.12){_C}#22c55e{_BD}1px solid rgba(34,197,94,0.28);",
    "Warning":  f"{_B}rgba(245,158,11,0.12){_C}#f59e0b{_BD}1px solid rgba(245,158,11,0.28);",
    "Critical": f"{_B}rgba(239,68,68,0.12){_C}#ef4444{_BD}1px solid rgba(239,68,68,0.28);",
}
SEVERITY_STYLE = {
    "Critical": f"{_B}rgba(239,68,68,0.12){_C}#ef4444{_BD}1px solid rgba(239,68,68,0.28);",
    "Warning":  f"{_B}rgba(245,158,11,0.12){_C}#f59e0b{_BD}1px solid rgba(245,158,11,0.28);",
    "Info":     f"{_B}rgba(34,211,238,0.12){_C}#22d3ee{_BD}1px solid rgba(34,211,238,0.28);",
}
ALERT_STATUS_STYLE = {
    "Open":         f"{_B}rgba(239,68,68,0.12){_C}#ef4444{_BD}1px solid rgba(239,68,68,0.28);",
    "Acknowledged": f"{_B}rgba(245,158,11,0.12){_C}#f59e0b{_BD}1px solid rgba(245,158,11,0.28);",
    "Resolved":     f"{_B}rgba(34,197,94,0.12){_C}#22c55e{_BD}1px solid rgba(34,197,94,0.28);",
}
RESULT_STYLE  = {"Success": "color:#22c55e;font-weight:600;", "Failed": "color:#ef4444;font-weight:700;"}
PRIORITY_STYLE = {
    "Critical": f"{_B}rgba(239,68,68,0.12){_C}#ef4444{_BD}1px solid rgba(239,68,68,0.28);",
    "High":     f"{_B}rgba(245,158,11,0.12){_C}#f59e0b{_BD}1px solid rgba(245,158,11,0.28);",
    "Medium":   f"{_B}rgba(34,211,238,0.12){_C}#22d3ee{_BD}1px solid rgba(34,211,238,0.28);",
    "Low":      f"{_B}rgba(148,163,184,0.09){_C}#475569{_BD}1px solid rgba(148,163,184,0.2);",
}
TICKET_STATUS_STYLE = {
    "Open":        f"{_B}rgba(239,68,68,0.12){_C}#ef4444{_BD}1px solid rgba(239,68,68,0.28);",
    "In Progress": f"{_B}rgba(245,158,11,0.12){_C}#f59e0b{_BD}1px solid rgba(245,158,11,0.28);",
    "Escalated":   f"{_B}rgba(139,92,246,0.12){_C}#8b5cf6{_BD}1px solid rgba(139,92,246,0.28);",
    "Resolved":    f"{_B}rgba(34,197,94,0.12){_C}#22c55e{_BD}1px solid rgba(34,197,94,0.28);",
}
BADGE_CSS = "padding:2px 9px;border-radius:2em;font-size:0.68rem;font-weight:700;letter-spacing:0.04em;"

ALL_ROLES = [
    "General Manager", "Monitoring", "Data Operation Specialist",
    "I.T Assistant", "Back-end Developer", "Dev-Ops",
    "Infrastructure Engineer", "Customer Service", "Data Analyst",
]

TOOLKIT = [
    {"name": "GitHub", "category": "Source control & CI/CD", "url": "https://github.com",
     "description": "Hosts infrastructure-as-code, runbooks and automation scripts; pull requests gate every change to monitoring configuration."},
    {"name": "Visual Studio Code", "category": "Development", "url": "https://code.visualstudio.com",
     "description": "Primary editor for scripting, configuration management and remote SSH sessions into managed hosts."},
    {"name": "Postman", "category": "API testing", "url": "https://www.postman.com",
     "description": "Builds and validates the REST calls used for alert webhooks, status-page updates and integration testing."},
    {"name": "Cloudflare", "category": "Network & edge security", "url": "https://www.cloudflare.com",
     "description": "DNS, CDN and WAF management for client-facing endpoints, plus DDoS mitigation and TLS certificate handling."},
    {"name": "pgAdmin", "category": "Database administration", "url": "https://www.pgadmin.org",
     "description": "Query console and administration UI for the PostgreSQL primaries and replicas in the fleet."},
    {"name": "MongoDB Compass", "category": "Database administration", "url": "https://www.mongodb.com/products/compass",
     "description": "Schema exploration, index analysis and query profiling for MongoDB collections."},
    {"name": "DBeaver", "category": "Database administration", "url": "https://dbeaver.io",
     "description": "Universal SQL client used across PostgreSQL, MySQL and Redis instances for ad-hoc diagnostics."},
    {"name": "Grafana", "category": "Monitoring & observability", "url": "https://grafana.com",
     "description": "Long-range metric dashboards and alert rules layered on top of the telemetry collected here."},
    {"name": "Docker Hub", "category": "DevOps & containers", "url": "https://hub.docker.com",
     "description": "Registry for the container images used in staging environments and database tooling sidecars."},
    {"name": "Terraform Registry", "category": "Infrastructure as code", "url": "https://registry.terraform.io",
     "description": "Provider modules for provisioning and version-controlling the cloud infrastructure backing each client estate."},
    {"name": "AWS Management Console", "category": "Cloud platform", "url": "https://aws.amazon.com/console",
     "description": "Provisioning, IAM and billing oversight for cloud-hosted compute, storage and managed-database services."},
    {"name": "LeetCode", "category": "Skills & training", "url": "https://leetcode.com",
     "description": "SQL and systems-design practice the team uses to keep query-optimization and troubleshooting skills sharp."},
]

SAMPLE_QUERIES = {
    "Top slow queries": "SELECT query, calls, total_time, mean_time\nFROM pg_stat_statements\nORDER BY mean_time DESC\nLIMIT 10;",
    "Table sizes": "SELECT tablename,\n       pg_size_pretty(pg_total_relation_size(tablename::text)) AS total_size\nFROM pg_tables\nWHERE schemaname = 'public'\nORDER BY pg_total_relation_size(tablename::text) DESC;",
    "Active connections": "SELECT pid, usename, application_name,\n       client_addr, state, query\nFROM pg_stat_activity\nWHERE state != 'idle'\nORDER BY query_start;",
    "Replication status": "SELECT client_addr, state,\n       sent_lsn, write_lsn, flush_lsn, replay_lsn\nFROM pg_stat_replication;",
    "Index usage": "SELECT schemaname, tablename, indexname,\n       idx_scan, idx_tup_read, idx_tup_fetch\nFROM pg_stat_user_indexes\nORDER BY idx_scan DESC\nLIMIT 20;",
}

SCHEMA_TABLES = {
    "PostgreSQL": [
        {"Table": "orders", "Rows": "2,847,392", "Size": "1.2 GB", "Indexes": 5, "Last vacuum": "2h ago"},
        {"Table": "customers", "Rows": "453,221", "Size": "312 MB", "Indexes": 3, "Last vacuum": "6h ago"},
        {"Table": "products", "Rows": "12,847", "Size": "45 MB", "Indexes": 2, "Last vacuum": "1d ago"},
        {"Table": "inventory", "Rows": "98,432", "Size": "87 MB", "Indexes": 4, "Last vacuum": "12h ago"},
        {"Table": "audit_log", "Rows": "15,234,891", "Size": "8.9 GB", "Indexes": 2, "Last vacuum": "30m ago"},
    ],
    "MySQL": [
        {"Table": "transactions", "Rows": "8,234,521", "Size": "3.4 GB", "Indexes": 6, "Last vacuum": "4h ago"},
        {"Table": "accounts", "Rows": "234,562", "Size": "178 MB", "Indexes": 4, "Last vacuum": "8h ago"},
        {"Table": "sessions", "Rows": "1,234,891", "Size": "456 MB", "Indexes": 3, "Last vacuum": "1h ago"},
    ],
    "MongoDB": [
        {"Table": "events (collection)", "Rows": "45,892,341", "Size": "27.8 GB", "Indexes": 4, "Last vacuum": "N/A"},
        {"Table": "logs (collection)", "Rows": "12,345,678", "Size": "9.6 GB", "Indexes": 2, "Last vacuum": "N/A"},
        {"Table": "metrics (collection)", "Rows": "3,456,789", "Size": "2.3 GB", "Indexes": 3, "Last vacuum": "N/A"},
    ],
    "Redis": [
        {"Table": "session_cache (keyspace)", "Rows": "45,231", "Size": "12 MB", "Indexes": 0, "Last vacuum": "N/A"},
        {"Table": "rate_limits (keyspace)", "Rows": "12,456", "Size": "4 MB", "Indexes": 0, "Last vacuum": "N/A"},
    ],
}

RUNBOOKS = [
    {"title": "PostgreSQL Primary Failover", "category": "Incident Response",
     "steps": "1. Verify primary is unreachable via pg_stat_replication\n2. Promote replica: SELECT pg_promote();\n3. Update connection strings in load balancer\n4. Notify affected services\n5. Create post-mortem ticket"},
    {"title": "High CPU / Memory Alert", "category": "Performance",
     "steps": "1. Identify top queries via pg_stat_activity\n2. Check for lock contention: SELECT * FROM pg_locks\n3. Kill blocking process if required: SELECT pg_terminate_backend(pid)\n4. Review and optimize queries\n5. Escalate to Back-end Developer if query optimization needed"},
    {"title": "Disk Usage Warning (>85%)", "category": "Capacity",
     "steps": "1. Check largest tables: SELECT pg_size_pretty(pg_relation_size(tablename::text))\n2. Review audit_log and session tables for archival candidates\n3. Run VACUUM FULL on bloated tables\n4. Open CHG ticket for storage expansion if trend continues"},
    {"title": "Replication Lag > 30s", "category": "Replication",
     "steps": "1. Check primary load: SELECT * FROM pg_stat_replication\n2. Verify network throughput between primary and replica\n3. Review WAL sender/receiver status\n4. Consider pausing heavy write batches on primary\n5. Alert Data Operations Specialist"},
    {"title": "Backup Job Failure", "category": "Backup & Recovery",
     "steps": "1. Check backup job logs in Backups & maintenance tab\n2. Verify S3 bucket connectivity and permissions\n3. Re-run backup manually if < 24h since last success\n4. Escalate to Infrastructure Engineer if S3 unreachable\n5. Document in ticket with resolution"},
    {"title": "Password Reset — User Account", "category": "Access Management",
     "steps": "1. Verify identity via employee ID + manager confirmation\n2. Generate temporary password using standard policy\n3. Force password change on next login\n4. Log action in audit ticket\n5. Notify user via official email channel"},
]

EMAIL_TEMPLATES = {
    "Custom": {"subject": "", "body": ""},
    "Outage Notice": {
        "subject": "Service Outage Notice — {client}",
        "body": "Dear Team,\n\nWe are currently experiencing a service disruption affecting {client}.\n\nImpacted systems: {servers}\nDetected at: {time}\n\nOur team is actively investigating and will provide updates every 30 minutes.\n\nRegards,\n{sender}\n{provider} IT Operations",
    },
    "Maintenance Alert": {
        "subject": "Scheduled Maintenance — {client} — {date}",
        "body": "Dear Team,\n\nPlease be advised that scheduled maintenance is planned for {client} systems.\n\nDate: {date}\nEstimated duration: 2 hours\nExpected impact: Possible read-only period during failover\n\nPlease plan accordingly.\n\nRegards,\n{sender}\n{provider} IT Operations",
    },
    "Resolution Confirmation": {
        "subject": "Issue Resolved — {client}",
        "body": "Dear Team,\n\nWe are pleased to confirm that the reported issue for {client} has been fully resolved.\n\nResolved at: {time}\nRoot cause: Under investigation — post-mortem within 48h\nActions taken: Service restored, monitoring heightened\n\nRegards,\n{sender}\n{provider} IT Operations",
    },
    "SLA Report": {
        "subject": "Monthly SLA Report — {client} — {month}",
        "body": "Dear Team,\n\nPlease find below the SLA summary for {client} for {month}.\n\nUptime: {uptime}%\nOpen incidents: {incidents}\nAverage resolution time: 45 min\nBackup success rate: 98.5%\n\nFull report available in the console. Please reach out with any questions.\n\nRegards,\n{sender}\n{provider} IT Operations",
    },
}


def badge_cell(style_map):
    def _style(val):
        return f"{BADGE_CSS} {style_map.get(val, '')}"
    return _style


def text_cell(style_map):
    def _style(val):
        return style_map.get(val, "")
    return _style


def info_card(title: str, note: str):
    st.markdown(
        f"""<div class="info-card">
            <div class="info-card-head"><span class="info-card-dot"></span>
            <span class="info-card-title">{title}</span></div>
            <p class="info-card-desc">{note}</p>
        </div>""",
        unsafe_allow_html=True,
    )


def fmt_dt(value):
    if pd.isna(value):
        return "—"
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M")


def fmt_minutes(opened, resolved):
    if pd.isna(resolved):
        return "—"
    delta = resolved - opened
    return f"{int(delta.total_seconds() // 60)} min"


# ============================================================
# SIMULATED DATA GENERATORS
# ============================================================

def _gen_deployments(seed_str: str, count: int = 14) -> pd.DataFrame:
    rng = random.Random(abs(hash(seed_str)) % 2 ** 32)
    now = datetime.now()
    services = ["api-gateway", "db-migrator", "backup-agent", "monitoring-collector",
                "query-optimizer", "schema-validator", "replication-watcher"]
    rows = []
    for _ in range(count):
        deployed_at = now - timedelta(hours=rng.randint(1, 96))
        status = rng.choices(["Success", "Success", "Success", "Failed", "In Progress"],
                             weights=[5, 5, 5, 1, 2])[0]
        rows.append({
            "Deployed at": deployed_at.strftime("%Y-%m-%d %H:%M"),
            "Service": rng.choice(services),
            "Version": f"v{rng.randint(1, 5)}.{rng.randint(0, 20)}.{rng.randint(0, 50)}",
            "Environment": rng.choice(["production", "staging", "production"]),
            "Status": status,
            "Duration": f"{rng.randint(45, 420)}s",
            "Author": rng.choice(tm.ENGINEERS),
        })
    return pd.DataFrame(sorted(rows, key=lambda r: r["Deployed at"], reverse=True))


def _gen_oncall(seed_str: str) -> pd.DataFrame:
    rng = random.Random(abs(hash(seed_str)) % 2 ** 32)
    now = datetime.now().date()
    rows = []
    engineers = list(tm.ENGINEERS)
    for i in range(14):
        day = now + timedelta(days=i - 3)
        primary = engineers[rng.randint(0, len(engineers) - 1)]
        backup = engineers[rng.randint(0, len(engineers) - 1)]
        rows.append({
            "Date": day.strftime("%Y-%m-%d (%A)"),
            "Primary on-call": primary,
            "Backup": backup,
            "Status": "Active" if day == now else ("Upcoming" if day > now else "Past"),
        })
    return pd.DataFrame(rows)


def _gen_config_drift(seed_str: str, servers: list) -> pd.DataFrame:
    rng = random.Random(abs(hash(seed_str)) % 2 ** 32)
    params = [
        ("max_connections", "200", "500"),
        ("shared_buffers", "128MB", "256MB"),
        ("work_mem", "4MB", "16MB"),
        ("wal_level", "replica", "logical"),
        ("log_min_duration_statement", "-1", "2000"),
    ]
    rows = []
    for s in servers:
        drifted = rng.random() > 0.55
        if drifted:
            param, expected, actual = rng.choice(params)
            rows.append({
                "Server": s["name"],
                "Parameter": param,
                "Expected": expected,
                "Actual": actual,
                "Drift": "Yes",
                "Last checked": (datetime.now() - timedelta(minutes=rng.randint(5, 120))).strftime("%H:%M"),
            })
        else:
            rows.append({
                "Server": s["name"],
                "Parameter": "—",
                "Expected": "—",
                "Actual": "—",
                "Drift": "Clean",
                "Last checked": (datetime.now() - timedelta(minutes=rng.randint(5, 30))).strftime("%H:%M"),
            })
    return pd.DataFrame(rows)


def _gen_dr_status(seed_str: str, snapshots: list) -> pd.DataFrame:
    rng = random.Random(abs(hash(seed_str)) % 2 ** 32)
    rows = []
    for s in snapshots:
        last_drill = datetime.now() - timedelta(days=rng.randint(7, 90))
        ready = rng.random() > 0.15
        rows.append({
            "Server": s["name"],
            "Role": s["role"],
            "Failover ready": "Yes" if ready else "No",
            "RTO (target)": f"{rng.randint(1, 15)} min",
            "RPO (target)": f"{rng.randint(5, 60)} min",
            "Last DR drill": last_drill.strftime("%Y-%m-%d"),
            "Replica lag": f"{s['replication_lag_s']:.1f}s" if s["role"] == "Replica" else "N/A",
        })
    return pd.DataFrame(rows)


def _gen_security_checklist(seed_str: str, snapshots: list) -> list:
    rng = random.Random(abs(hash(seed_str)) % 2 ** 32)
    items = []
    checks = [
        ("TLS certificates valid", True),
        ("OS security patches current", rng.random() > 0.2),
        ("Database minor version up to date", rng.random() > 0.3),
        ("Firewall rules reviewed", rng.random() > 0.1),
        ("Backup encryption enabled", True),
        ("Audit logging active", True),
        ("Unused accounts removed", rng.random() > 0.25),
        ("Strong password policy enforced", True),
        ("Connection rate limiting active", rng.random() > 0.2),
        ("Last penetration test < 6 months", rng.random() > 0.4),
    ]
    for label, passed in checks:
        items.append({"check": label, "passed": passed})
    return items


# ============================================================
# SHARED COMPONENTS
# ============================================================

_ROLE_COLOR = {
    "General Manager":          "#f59e0b",
    "Monitoring":               "#22d3ee",
    "Data Operation Specialist": "#34d399",
    "I.T Assistant":            "#60a5fa",
    "Back-end Developer":       "#a78bfa",
    "Dev-Ops":                  "#fb923c",
    "Infrastructure Engineer":  "#f87171",
    "Customer Service":         "#f472b6",
    "Data Analyst":             "#2dd4bf",
}

_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
_MAX_FILE_MB = 5


def _svg(paths: str, size: int = 14, color: str = "currentColor", style: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="display:inline-block;vertical-align:middle;{style}">{paths}</svg>'
    )


_CH_SVG: dict[str, str] = {
    "general":           '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    "incidents":         '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>',
    "operations":        '<path d="M20 7h-9"/><path d="M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
    "database":          '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    "development":       '<path d="m18 16 4-4-4-4"/><path d="m6 8-4 4 4 4"/><path d="m14.5 4-5 16"/>',
    "deployments":       '<line x1="12" x2="12" y1="19" y2="5"/><polyline points="5 12 12 5 19 12"/>',
    "security":          '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "backups-dr":        '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
    "client-updates":    '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "reports-analytics": '<line x1="18" x2="18" y1="20" y2="10"/><line x1="12" x2="12" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="14"/>',
    "on-call":           '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.34 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9a16 16 0 0 0 6.29 6.29l.61-.61a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
    "infrastructure":    '<rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/>',
}
_SVG_CLIP  = '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>'
_SVG_IMG   = '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>'
_SVG_USERS = '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
_SVG_CHAT  = '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'


def _role_avatar(role: str) -> str:
    parts = role.split()
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else role[:2].upper()


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


def render_channels(current_role: str):
    # ── session init ────────────────────────────────────────────────────
    if "ch_selected" not in st.session_state:
        st.session_state.ch_selected = store.CHANNELS[0]["id"]
    if "ch_last_seen" not in st.session_state:
        st.session_state.ch_last_seen = {}

    col_list, col_msgs = st.columns([1, 3], gap="medium")

    # ── channel list sidebar ────────────────────────────────────────────
    with col_list:
        st.markdown(
            '<div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;'
            'letter-spacing:0.1em;color:#475569;margin-bottom:10px;">Team Channels</div>',
            unsafe_allow_html=True,
        )
        for ch in store.CHANNELS:
            msgs    = store.get_channel_messages(ch["id"])
            unread  = max(0, len(msgs) - st.session_state.ch_last_seen.get(ch["id"], 0))
            active  = st.session_state.ch_selected == ch["id"]
            ic_col  = "#22d3ee" if active else "#475569"

            # preview under button
            preview_line = ""
            if msgs:
                lm = msgs[-1]
                preview_text = lm.get("text") or (lm["attachment"]["name"] if lm.get("attachment") else "")
                sender = lm["from"].split()[0]
                trimmed = preview_text[:26] + ("…" if len(preview_text) > 26 else "")
                preview_line = f"{sender}: {trimmed}"

            badge = (
                f'<span style="background:#ef4444;color:#fff;border-radius:999px;'
                f'padding:1px 6px;font-size:0.62rem;font-weight:700;margin-left:4px;">{unread}</span>'
                if unread and not active else ""
            )

            # icon + button in tight 2-col layout
            ic, btn = st.columns([1, 7], gap="small")
            with ic:
                st.markdown(
                    f'<div style="display:flex;align-items:center;justify-content:center;'
                    f'height:36px;">{_svg(_CH_SVG.get(ch["id"], ""), 15, ic_col)}</div>',
                    unsafe_allow_html=True,
                )
            with btn:
                label = ch["name"] + (f" ({unread})" if unread and not active else "")
                if st.button(
                    label,
                    key=f"ch_btn_{ch['id']}",
                    type="primary" if active else "secondary",
                    use_container_width=True,
                    help=ch["desc"],
                ):
                    st.session_state.ch_selected = ch["id"]
                    st.session_state.ch_last_seen[ch["id"]] = len(msgs)
                    st.rerun()

            if preview_line:
                st.markdown(
                    f'<div style="font-size:0.66rem;color:#475569;margin:-4px 0 4px 2px;'
                    f'overflow:hidden;white-space:nowrap;text-overflow:ellipsis;">{preview_line}</div>',
                    unsafe_allow_html=True,
                )

    # ── message panel ───────────────────────────────────────────────────
    with col_msgs:
        sel_id = st.session_state.ch_selected
        sel_ch = next((c for c in store.CHANNELS if c["id"] == sel_id), store.CHANNELS[0])
        msgs   = store.get_channel_messages(sel_id)
        st.session_state.ch_last_seen[sel_id] = len(msgs)

        ch_icon_svg = _svg(_CH_SVG.get(sel_id, ""), 18, "#22d3ee", "margin-right:7px;")

        # header
        hc1, hc2 = st.columns([5, 1])
        with hc1:
            st.markdown(
                f'<div style="font-size:1.05rem;font-weight:700;color:#e2e8f0;'
                f'display:flex;align-items:center;">'
                f'{ch_icon_svg}{sel_ch["name"]}</div>'
                f'<div style="font-size:0.78rem;color:#64748b;margin-top:2px;">'
                f'{sel_ch["desc"]}</div>',
                unsafe_allow_html=True,
            )
        with hc2:
            u_svg = _svg(_SVG_USERS, 12, "#475569", "margin-right:3px;")
            c_svg = _svg(_SVG_CHAT,  12, "#475569", "margin-right:3px;margin-left:8px;")
            st.markdown(
                f'<div style="text-align:right;font-size:0.72rem;color:#475569;padding-top:8px;">'
                f'{u_svg}{len(ALL_ROLES)}&nbsp;{c_svg}{len(msgs)}</div>',
                unsafe_allow_html=True,
            )
        st.markdown('<hr style="border-color:#1e293b;margin:6px 0 10px;">', unsafe_allow_html=True)

        # ── message bubbles ───────────────────────────────────────────
        bubbles_html = ""
        if not msgs:
            empty_icon = _svg(_CH_SVG.get(sel_id, ""), 40, "#1e293b")
            bubbles_html = (
                f'<div style="display:flex;flex-direction:column;align-items:center;'
                f'justify-content:center;height:100%;padding:52px 0;">'
                f'<div style="margin-bottom:14px;">{empty_icon}</div>'
                f'<div style="color:#334155;font-size:0.9rem;font-weight:600;">No messages yet</div>'
                f'<div style="color:#1e293b;font-size:0.78rem;margin-top:4px;">'
                f'Be the first to post in {sel_ch["name"]}.</div></div>'
            )

        for m in msgs[-100:]:
            is_mine  = m["from"] == current_role
            rc       = _ROLE_COLOR.get(m["from"], "#94a3b8")
            initials = _role_avatar(m["from"])
            flex_dir = "row-reverse" if is_mine else "row"
            align    = "flex-end"    if is_mine else "flex-start"
            br       = "12px 4px 12px 12px" if is_mine else "4px 12px 12px 12px"
            bg       = "rgba(34,211,238,0.07)" if is_mine else "rgba(15,23,42,0.9)"
            bd       = "1px solid rgba(34,211,238,0.18)" if is_mine else "1px solid #1e293b"

            ts = m.get("ts", "")
            now_date     = datetime.now().strftime("%Y-%m-%d")
            time_str     = ts[11:16] if len(ts) >= 16 else ""
            date_str     = ts[:10]   if len(ts) >= 10 else ""
            time_display = time_str  if date_str == now_date else f"{date_str} {time_str}"

            att_html = ""
            att = m.get("attachment")
            if att:
                if att.get("mime", "") in _IMAGE_MIMES:
                    img_label_svg = _svg(_SVG_IMG, 11, "#475569", "margin-right:3px;")
                    att_html = (
                        f'<div style="margin-top:7px;">'
                        f'<img src="data:{att["mime"]};base64,{att["data_b64"]}" '
                        f'style="max-width:260px;max-height:260px;border-radius:8px;'
                        f'display:block;border:1px solid rgba(255,255,255,0.08);" />'
                        f'<div style="font-size:0.67rem;color:#475569;margin-top:3px;">'
                        f'{img_label_svg}{att["name"]} &middot; {_fmt_size(att.get("size", 0))}'
                        f'</div></div>'
                    )
                else:
                    file_svg = _svg(_SVG_CLIP, 20, "#64748b")
                    att_html = (
                        f'<div style="margin-top:7px;background:rgba(255,255,255,0.04);'
                        f'border:1px solid rgba(255,255,255,0.09);border-radius:8px;'
                        f'padding:9px 13px;display:inline-flex;align-items:center;gap:10px;">'
                        f'{file_svg}'
                        f'<div>'
                        f'<div style="font-size:0.82rem;color:#e2e8f0;font-weight:600;">{att["name"]}</div>'
                        f'<div style="font-size:0.69rem;color:#64748b;">{_fmt_size(att.get("size", 0))}</div>'
                        f'</div></div>'
                    )

            text_html = (
                f'<div style="color:#cbd5e1;font-size:0.85rem;line-height:1.55;word-break:break-word;">'
                f'{m["text"]}</div>'
            ) if m.get("text") else ""

            ta = "right" if is_mine else "left"
            bubbles_html += (
                f'<div style="display:flex;flex-direction:{flex_dir};align-items:flex-start;'
                f'gap:8px;margin-bottom:12px;align-self:{align};max-width:84%;">'
                f'<div style="flex-shrink:0;width:34px;height:34px;border-radius:50%;'
                f'background:{rc}1a;border:2px solid {rc};display:flex;align-items:center;'
                f'justify-content:center;font-size:0.6rem;font-weight:800;color:{rc};">{initials}</div>'
                f'<div style="flex:1;min-width:0;">'
                f'<div style="font-size:0.7rem;font-weight:700;color:{rc};'
                f'margin-bottom:3px;text-align:{ta};">'
                f'{m["from"]} <span style="color:#475569;font-weight:400;font-size:0.67rem;">'
                f'{time_display}</span></div>'
                f'<div style="background:{bg};border:{bd};border-radius:{br};padding:9px 13px;">'
                f'{text_html}{att_html}</div>'
                f'</div></div>'
            )

        st.markdown(
            f'<div style="height:430px;overflow-y:auto;display:flex;flex-direction:column;'
            f'padding:16px;background:linear-gradient(180deg,#06090f 0%,#080d1a 100%);'
            f'border:1px solid #1e293b;border-radius:10px;margin-bottom:12px;">'
            f'{bubbles_html}</div>',
            unsafe_allow_html=True,
        )

        # ── compose ───────────────────────────────────────────────────
        with st.container(border=True):
            with st.form(f"ch_compose_{sel_id}", clear_on_submit=True):
                msg_text = st.text_area(
                    "message",
                    placeholder=f"Message {sel_ch['name']}…",
                    label_visibility="collapsed",
                    height=68,
                )
                attach_file = st.file_uploader(
                    "Attach file or image",
                    type=["png", "jpg", "jpeg", "gif", "webp",
                          "pdf", "csv", "xlsx", "txt", "log", "json", "zip"],
                    help=f"Images display inline · Max {_MAX_FILE_MB} MB",
                    label_visibility="visible",
                )
                fc1, fc2 = st.columns([5, 1])
                with fc1:
                    if attach_file:
                        clip_s = _svg(_SVG_CLIP, 12, "#64748b", "margin-right:4px;")
                        st.markdown(
                            f'<div style="font-size:0.78rem;color:#64748b;padding-top:4px;">'
                            f'{clip_s}{attach_file.name} &middot; {_fmt_size(attach_file.size)}</div>',
                            unsafe_allow_html=True,
                        )
                with fc2:
                    submitted = st.form_submit_button(
                        "Send", icon=":material/send:", type="primary", use_container_width=True,
                    )
                if submitted:
                    if not (msg_text and msg_text.strip()) and attach_file is None:
                        st.warning("Write a message or attach a file.")
                    else:
                        attachment = None
                        if attach_file is not None:
                            if attach_file.size > _MAX_FILE_MB * 1024 * 1024:
                                st.error(f"File exceeds {_MAX_FILE_MB} MB limit.")
                            else:
                                raw = attach_file.read()
                                attachment = {
                                    "name": attach_file.name,
                                    "mime": attach_file.type or "application/octet-stream",
                                    "data_b64": base64.b64encode(raw).decode(),
                                    "size": attach_file.size,
                                }
                        store.post_to_channel(
                            current_role, sel_id,
                            (msg_text or "").strip(),
                            attachment=attachment,
                        )
                        st.rerun()


def render_email_composer(current_role: str, client=None, snapshots=None, alerts=None):
    info_card(
        title="Email",
        note="Compose and send emails to clients or team members. Templates pre-fill subject and body — "
             "customise before sending. All sent items are saved below.",
    )
    sent = [e for e in store.get()["emails"] if e["from_role"] == current_role]
    tab_c, tab_s = st.tabs(["Compose", "Sent items"])

    with tab_c:
        with st.container(border=True):
            tpl_name = st.selectbox(
                "Template", list(EMAIL_TEMPLATES.keys()),
                key=f"email_tpl_{current_role}",
            )
            tpl = EMAIL_TEMPLATES[tpl_name]
            now_s = datetime.now().strftime("%Y-%m-%d %H:%M")
            client_name = client["name"] if client else "Client"
            servers_s = ", ".join(s["name"] for s in (snapshots or [])[:3]) if snapshots else "N/A"
            month_s = datetime.now().strftime("%B %Y")
            uptime_s = (
                f"{sum(s['uptime_pct_30d'] for s in snapshots) / len(snapshots):.2f}"
                if snapshots else "99.9"
            )
            open_inc = (
                int(((alerts["status"] != "Resolved") & (alerts["severity"] != "Info")).sum())
                if alerts is not None else 0
            )
            sub_default = tpl["subject"].format(
                client=client_name, date=now_s[:10], month=month_s, time=now_s,
            ) if tpl["subject"] else ""
            body_default = tpl["body"].format(
                client=client_name, servers=servers_s, time=now_s, sender=current_role,
                date=now_s[:10], month=month_s, uptime=uptime_s,
                incidents=str(open_inc), provider=tm.PROVIDER,
            ) if tpl["body"] else ""

            with st.form(f"email_form_{current_role}", clear_on_submit=True):
                default_to = f"operations@{client['domain']}" if client else ""
                to_addr = st.text_input("To", value=default_to)
                subject  = st.text_input("Subject", value=sub_default)
                body     = st.text_area("Message", value=body_default, height=220)
                if st.form_submit_button("Send email", icon=":material/send:", type="primary", width="stretch"):
                    if to_addr.strip() and subject.strip():
                        store.send_email(to_addr.strip(), subject.strip(), body, current_role)
                        st.toast(f"Email sent to {to_addr}", icon=":material/mail:")
                    else:
                        st.warning("Fill in To and Subject before sending.")

    with tab_s:
        if not sent:
            st.info("No sent emails yet.")
        else:
            for e in reversed(sent[-25:]):
                with st.expander(f"**{e['subject']}**  →  {e['to']}  ·  {e['ts'][:16]}"):
                    st.caption(f"Status: {e['status']}")
                    st.text(e["body"])


def render_ticket_system(current_role: str, mode: str = "full"):
    """mode='full' for IT Assistant (all tickets, full CRUD).
    mode='cs' for Customer Service (own tickets, create + track)."""
    info_card(
        title="Help Desk — Ticket System",
        note="Create, track and resolve support tickets. All tickets persist across sessions.",
    )
    tab_q, tab_new = st.tabs(["Ticket queue", "New ticket"])

    with tab_q:
        all_tickets = store.get()["tickets"]
        tickets = all_tickets if mode == "full" else [t for t in all_tickets if t["created_by"] == current_role]

        f1, f2, f3 = st.columns(3)
        status_f = f1.multiselect(
            "Status", ["Open", "In Progress", "Escalated", "Resolved"],
            default=["Open", "In Progress", "Escalated"],
            key=f"tk_st_{current_role}",
        )
        prio_f = f2.multiselect(
            "Priority", ["Critical", "High", "Medium", "Low"],
            default=["Critical", "High", "Medium", "Low"],
            key=f"tk_pr_{current_role}",
        )
        search = f3.text_input("Search", placeholder="ID or keyword", key=f"tk_srch_{current_role}")

        shown = [
            t for t in tickets
            if t["status"] in status_f
            and t["priority"] in prio_f
            and (not search or search.lower() in t["title"].lower() or search.lower() in t["id"].lower())
        ]

        if not shown:
            st.info("No tickets match the current filters.")
        else:
            for t in sorted(shown, key=lambda x: x["updated_at"], reverse=True):
                p_icon = {"Critical": "🔴", "High": "🟠", "Medium": "🔵", "Low": "⚪"}.get(t["priority"], "⚪")
                with st.expander(f'{p_icon} **{t["id"]}** — {t["title"]}  ·  _{t["status"]}_'):
                    tc1, tc2 = st.columns([2, 1])
                    with tc1:
                        st.markdown(f"**Description:** {t['description']}")
                        st.caption(f"Created by: **{t['created_by']}** · Assigned to: **{t['assigned_to']}** · Updated: {t['updated_at'][:16]}")
                        if t.get("notes"):
                            st.markdown("**Notes:**")
                            for note in t["notes"]:
                                st.caption(f"[{note['ts'][:16]}] **{note['author']}**: {note['text']}")
                        with st.form(f"note_{t['id']}", clear_on_submit=True):
                            note_in = st.text_input("Add note", placeholder="Type a note…", key=f"ni_{t['id']}")
                            if st.form_submit_button("Save", type="secondary"):
                                if note_in.strip():
                                    store.add_note(t["id"], current_role, note_in.strip())
                                    st.rerun()
                    with tc2:
                        new_status = st.selectbox(
                            "Status",
                            ["Open", "In Progress", "Escalated", "Resolved"],
                            index=["Open", "In Progress", "Escalated", "Resolved"].index(t["status"]),
                            key=f"st_{t['id']}",
                        )
                        if mode == "full":
                            opts = ["Unassigned"] + list(tm.ENGINEERS)
                            cur_a = t["assigned_to"] if t["assigned_to"] in opts else "Unassigned"
                            new_assigned = st.selectbox("Assign to", opts, index=opts.index(cur_a), key=f"as_{t['id']}")
                        else:
                            new_assigned = t["assigned_to"]
                        if st.button("Update", type="primary", width="stretch", key=f"upd_{t['id']}"):
                            store.update_ticket(t["id"], status=new_status, assigned_to=new_assigned)
                            st.rerun()

    with tab_new:
        with st.form(f"new_ticket_{current_role}", clear_on_submit=True):
            st.markdown("**Create new ticket**")
            title = st.text_input("Title", placeholder="Short description of the issue")
            desc  = st.text_area("Description", placeholder="What happened? Steps, impact, errors…", height=110)
            nc1, nc2 = st.columns(2)
            prio = nc1.selectbox("Priority", ["Critical", "High", "Medium", "Low"], index=2)
            if mode == "full":
                assigned = nc2.selectbox("Assign to", ["Unassigned"] + list(tm.ENGINEERS))
            else:
                assigned = "Unassigned"
                nc2.text_input("Reported by", value=current_role, disabled=True)
            if st.form_submit_button("Create ticket", icon=":material/add_task:", type="primary", width="stretch"):
                if title.strip():
                    ticket = store.create_ticket(title.strip(), desc.strip(), prio, current_role, assigned)
                    st.toast(f"Ticket {ticket['id']} created", icon=":material/check_circle:")
                    st.rerun()
                else:
                    st.warning("Add a title before creating.")


def render_report_generator(current_role: str, snapshots: list, alerts: pd.DataFrame,
                             backups: pd.DataFrame, histories: dict, client: dict):
    info_card(
        title="Report Generator",
        note="Build and download reports from live telemetry data. Choose report type, select servers, pick format.",
    )
    with st.container(border=True):
        rc1, rc2, rc3 = st.columns(3)
        rpt_type = rc1.selectbox(
            "Report type",
            ["Fleet Health Summary", "Performance Metrics", "Incident Report", "Backup Status", "Capacity Planning"],
            key=f"rpt_type_{current_role}",
        )
        srv_opts = [s["name"] for s in snapshots]
        srv_sel  = rc2.multiselect("Servers", srv_opts, default=srv_opts, key=f"rpt_srv_{current_role}")
        fmt      = rc3.selectbox("Format", ["Excel (.xlsx)", "CSV (.csv)"], key=f"rpt_fmt_{current_role}")

        if st.button("Generate report", icon=":material/download:", type="primary", key=f"rpt_gen_{current_role}"):
            filtered = [s for s in snapshots if s["name"] in srv_sel]
            if not filtered:
                st.warning("Select at least one server.")
            else:
                if rpt_type == "Fleet Health Summary":
                    df = pd.DataFrame([{
                        "Server": s["name"], "Hostname": s["hostname"], "Role": s["role"],
                        "Engine": f"{s['engine']} {s['version']}", "Region": s["region"],
                        "Status": s["status"], "CPU %": s["cpu_pct"], "Memory %": s["memory_pct"],
                        "Disk %": s["disk_pct"], "Uptime %": s["uptime_pct_30d"],
                    } for s in filtered])
                    sheets = {"Fleet Health": df}

                elif rpt_type == "Performance Metrics":
                    rows = []
                    for s in filtered:
                        h = histories.get(s["name"])
                        if h is not None:
                            hc = h.copy()
                            hc.insert(0, "Server", s["name"])
                            rows.append(hc)
                    df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
                    sheets = {"Performance Metrics": df}

                elif rpt_type == "Incident Report":
                    names = [s["name"] for s in filtered]
                    df = alerts[alerts["server"].isin(names)].copy()
                    df["opened"]   = df["opened"].astype(str)
                    df["resolved"] = df["resolved"].astype(str)
                    sheets = {"Incidents": df}

                elif rpt_type == "Backup Status":
                    names = [s["name"] for s in filtered]
                    df = backups[backups["server"].isin(names)].copy()
                    df["timestamp"] = df["timestamp"].astype(str)
                    sheets = {"Backup Log": df}

                else:  # Capacity Planning
                    df = pd.DataFrame([{
                        "Server": s["name"], "Disk Used (GB)": s["disk_used_gb"],
                        "Disk Capacity (GB)": s["disk_capacity_gb"],
                        "Disk %": s["disk_pct"],
                        "Days to Full": s.get("days_to_disk_full") or "Stable",
                        "CPU %": s["cpu_pct"], "Memory %": s["memory_pct"],
                    } for s in filtered])
                    sheets = {"Capacity Planning": df}

                fname_base = f"{client['code']}_{rpt_type.lower().replace(' ', '_')}"
                if fmt == "Excel (.xlsx)":
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                        for sheet_name, sdf in sheets.items():
                            sdf.to_excel(writer, sheet_name=sheet_name[:31], index=False)
                    st.download_button(
                        label=f"Download {rpt_type}.xlsx",
                        data=buf.getvalue(),
                        file_name=f"{fname_base}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        icon=":material/download:",
                        key=f"dl_{current_role}_{rpt_type}",
                    )
                else:
                    first_df = list(sheets.values())[0]
                    st.download_button(
                        label=f"Download {rpt_type}.csv",
                        data=first_df.to_csv(index=False),
                        file_name=f"{fname_base}.csv",
                        mime="text/csv",
                        icon=":material/download:",
                        key=f"dl_{current_role}_{rpt_type}",
                    )


# ============================================================
# REUSABLE DATA PANELS
# ============================================================

_ROLE_CLASS      = {"Primary": "role-primary", "Replica": "role-replica", "Cache": "role-cache"}
_STATUS_DOT_CLASS = {"Healthy": "st-healthy", "Warning": "st-warning", "Critical": "st-critical"}


def _topo_node_html(s: dict) -> str:
    return (
        f'<div class="topo-node {_ROLE_CLASS.get(s["role"], "")}">'
        f'<div class="topo-node-head">'
        f'<span class="topo-dot {_STATUS_DOT_CLASS.get(s["status"], "")}"></span>'
        f'<span class="topo-role">{s["role"]}</span></div>'
        f'<div class="topo-name">{s["name"]}</div>'
        f'<div class="topo-meta">{s["region"]} &middot; CPU {s["cpu_pct"]:.0f}% &middot; {s["status"]}</div>'
        f'</div>'
    )


def _fleet_panel(snapshots: list, server_names: list, alerts: pd.DataFrame):
    with st.container(border=True):
        info_card(
            title="Fleet Inventory",
            note="Real-time health, load and capacity of every database host. A host in Warning or Critical "
                 "here needs attention before it becomes a client-facing incident.",
        )
        st.markdown("**Replication topology**")
        st.caption("Engines grouped by role — primaries feed replicas and caches, coloured by health status.")
        engine_clusters: dict = {}
        for s in snapshots:
            engine_clusters.setdefault(f"{s['engine']} {s['version']}", []).append(s)
        blocks = []
        for engine_label, members in engine_clusters.items():
            primary = next((m for m in members if m["role"] == "Primary"), members[0])
            deps = [m for m in members if m is not primary]
            body = f'<div class="topo-row">{_topo_node_html(primary)}</div>'
            if deps:
                body += '<div class="topo-connector"></div>'
                body += f'<div class="topo-row">{"".join(_topo_node_html(m) for m in deps)}</div>'
            blocks.append(f'<div class="topo-cluster"><div class="topo-engine">{engine_label}</div>{body}</div>')
        st.markdown('<div class="topo-grid">' + "".join(blocks) + "</div>", unsafe_allow_html=True)

        st.divider()
        st.markdown("**Host inventory**")
        display = pd.DataFrame([{
            "Server": s["name"], "Role": s["role"],
            "Engine": f"{s['engine']} {s['version']}", "Region": s["region"],
            "Status": s["status"], "CPU %": f"{s['cpu_pct']:.1f}",
            "Mem %": f"{s['memory_pct']:.1f}", "Disk %": f"{s['disk_pct']:.1f}",
            "Uptime %": f"{s['uptime_pct_30d']:.2f}",
        } for s in snapshots])
        styled = display.style.map(badge_cell(STATUS_STYLE), subset=["Status"])
        st.dataframe(styled, hide_index=True, width="stretch", height=280)


def _server_detail_panel(servers: list, snapshots: list, histories: dict,
                          seed: str, live_mode: bool, client: dict):
    with st.container(border=True):
        info_card(
            title="Server Detail",
            note="Deep dive into one host — utilization, latency, replication and capacity trajectory.",
        )
        server_names = [s["name"] for s in snapshots]
        focus = st.session_state.get("focus_server")
        default_ix = server_names.index(focus) if focus in server_names else 0
        selected = st.selectbox("Select a server to inspect", server_names, index=default_ix, key=f"sd_sel_{seed}")
        if focus and focus == selected:
            st.session_state.pop("focus_server", None)
            st.caption(f"↳ Jumped here from Alerts — **{selected}** preselected.")

        sel_snap = next(s for s in snapshots if s["name"] == selected)
        sel_hist = histories[selected].set_index("timestamp")

        ic, mc = st.columns([2, 3], gap="large")
        with ic:
            st.markdown(f"""
| | |
|---|---|
| **Hostname** | {sel_snap['hostname']} |
| **IP address** | {sel_snap['ip_address']} |
| **OS** | {sel_snap['os']} |
| **Engine** | {sel_snap['engine']} {sel_snap['version']} |
| **Role** | {sel_snap['role']} |
| **Region** | {sel_snap['region']} |
""")
        with mc:
            d1, d2, d3 = st.columns(3)
            d1.metric("Status", sel_snap["status"])
            d1.metric("CPU %", f"{sel_snap['cpu_pct']:.1f}%")
            d2.metric("Memory %", f"{sel_snap['memory_pct']:.1f}%")
            d2.metric("Connections", sel_snap["connections"])
            d3.metric("Disk used", f"{sel_snap['disk_used_gb']:.0f}/{sel_snap['disk_capacity_gb']} GB")
            d3.metric("IOPS", f"{sel_snap['iops']:,}")

        t1, t2, t3, t4 = st.tabs(["Resource utilization", "Query latency & connections", "Replication", "Capacity planning"])

        with t1:
            if live_mode:
                server_obj  = next(s for s in servers if s["name"] == selected)
                buffer_key  = f"live_buf_{client['code']}_{selected}"

                @st.fragment(run_every=2)
                def _live_chart(srv=server_obj, bkey=buffer_key, bseed=seed):
                    if bkey not in st.session_state:
                        seed_hist = tm.generate_history(srv, hours=2, jitter_seed=f"{bseed}-live").tail(30)
                        st.session_state[bkey] = [
                            {"timestamp": r.timestamp, "cpu_pct": float(r.cpu_pct),
                             "memory_pct": float(r.memory_pct), "disk_pct": float(r.disk_pct)}
                            for r in seed_hist.itertuples()
                        ]
                    buf  = st.session_state[bkey]
                    last = buf[-1]
                    buf.append({
                        "timestamp":  pd.Timestamp.now(),
                        "cpu_pct":    min(99.0, max(1.0,  last["cpu_pct"]    + random.gauss(0, 4.5))),
                        "memory_pct": min(97.0, max(5.0,  last["memory_pct"] + random.gauss(0, 2.0))),
                        "disk_pct":   min(98.0, max(10.0, last["disk_pct"]   + random.gauss(0, 0.4))),
                    })
                    if len(buf) > 36:
                        buf.pop(0)
                    live_df = pd.DataFrame(buf).set_index("timestamp")
                    st.markdown(
                        '<span class="live-indicator"><span class="live-dot"></span>LIVE</span>'
                        f'&nbsp;<span style="color:#64748b;font-size:0.78rem;">streaming · CPU, memory, disk · '
                        f'updated {pd.Timestamp.now().strftime("%H:%M:%S")}</span>',
                        unsafe_allow_html=True,
                    )
                    st.line_chart(live_df[["cpu_pct", "memory_pct", "disk_pct"]], height=300,
                                  color=["#8b5cf6", "#22d3ee", "#34d399"])
                _live_chart()
            else:
                st.caption("CPU, memory and disk utilization (%) over the selected window")
                st.line_chart(sel_hist[["cpu_pct", "memory_pct", "disk_pct"]], height=300,
                              color=["#8b5cf6", "#22d3ee", "#34d399"])

        with t2:
            lc1, lc2 = st.columns(2)
            with lc1:
                st.caption("Query latency (ms)")
                st.line_chart(sel_hist[["query_latency_ms"]], height=260, color=["#22d3ee"])
            with lc2:
                st.caption("Active connections")
                st.line_chart(sel_hist[["connections"]], height=260, color=["#8b5cf6"])
            st.caption("Disk IOPS")
            st.line_chart(sel_hist[["iops"]], height=220, color=["#34d399"])

        with t3:
            if sel_snap["role"] == "Replica":
                st.caption("Replication lag (s) — lower is better")
                st.line_chart(sel_hist[["replication_lag_s"]], height=280, color=["#8b5cf6"])
                lag = sel_snap["replication_lag_s"]
                if lag > 30:
                    st.error(f"Replication lag {lag:.2f}s exceeds 30s threshold.")
                elif lag > 10:
                    st.warning(f"Replication lag {lag:.2f}s approaching threshold.")
                else:
                    st.success(f"Replication lag {lag:.2f}s — within normal range.")
            else:
                st.info(f"{selected} is a {sel_snap['role']} node. Lag is tracked on downstream replicas.")

        with t4:
            st.caption("Disk utilization trend and projected exhaustion")
            st.area_chart(sel_hist[["disk_pct"]], height=260, color=["#22d3ee"])
            used, cap = sel_snap["disk_used_gb"], sel_snap["disk_capacity_gb"]
            cp1, cp2, cp3 = st.columns(3)
            cp1.metric("Used", f"{used:.0f} GB")
            cp2.metric("Free", f"{cap - used:.0f} GB")
            cp3.metric("Capacity", f"{cap} GB")
            days = sel_snap.get("days_to_disk_full")
            if days is not None:
                if days <= 30:
                    st.warning(f"Projected to reach 95% disk in ~{days} days. Plan storage expansion.")
                else:
                    st.info(f"Projected to reach 95% disk in ~{days} days.")
            else:
                st.success("Disk utilization stable — no near-term capacity action required.")


def _alerts_panel(alerts: pd.DataFrame, server_names: list, show_drilldown: bool = True):
    with st.container(border=True):
        info_card(
            title="Alerts & Incidents",
            note="Live triage queue — every monitoring event ranked by severity and ownership status.",
        )
        af1, af2, af3 = st.columns(3)
        sev_f = af1.multiselect("Severity", ["Critical", "Warning", "Info"],
                                 default=["Critical", "Warning", "Info"], key=f"al_sev_{id(alerts)}")
        st_f  = af2.multiselect("Status", ["Open", "Acknowledged", "Resolved"],
                                 default=["Open", "Acknowledged", "Resolved"], key=f"al_st_{id(alerts)}")
        srv_f = af3.multiselect("Server", server_names, default=server_names, key=f"al_srv_{id(alerts)}")

        shown = alerts[
            alerts["severity"].isin(sev_f) &
            alerts["status"].isin(st_f) &
            alerts["server"].isin(srv_f)
        ].copy()

        if shown.empty:
            st.info("No alerts match the current filters.")
            return

        display = pd.DataFrame({
            "Opened":      shown["opened"].apply(fmt_dt),
            "Severity":    shown["severity"],
            "Server":      shown["server"],
            "Description": shown["message"],
            "Status":      shown["status"],
            "Assigned to": shown["assigned_to"],
            "TTR":         [fmt_minutes(o, r) for o, r in zip(shown["opened"], shown["resolved"])],
        })
        styled = (
            display.style
            .map(badge_cell(SEVERITY_STYLE), subset=["Severity"])
            .map(badge_cell(ALERT_STATUS_STYLE), subset=["Status"])
        )
        st.dataframe(styled, hide_index=True, width="stretch", height=400,
                     column_config={
                         "Opened":      st.column_config.TextColumn(width="small"),
                         "Severity":    st.column_config.TextColumn(width="small"),
                         "Server":      st.column_config.TextColumn(width="small"),
                         "Status":      st.column_config.TextColumn(width="small"),
                         "Assigned to": st.column_config.TextColumn(width="small"),
                         "TTR":         st.column_config.TextColumn("Time to resolution", width="small"),
                     })
        st.caption(f"Showing {len(shown)} of {len(alerts)} alerts.")

        if show_drilldown and "Server detail" in [t for t in ["Server detail"]]:
            jc1, jc2 = st.columns([3, 1], vertical_alignment="bottom")
            jump_target = jc1.selectbox("Drill into a host", sorted(shown["server"].unique()), key=f"jt_{id(alerts)}")
            with jc2:
                if st.button("Open in Server detail", icon=":material/north_east:", width="stretch", key=f"jb_{id(alerts)}"):
                    st.session_state["focus_server"] = jump_target
                    st.toast(f"{jump_target} preselected — open the Server detail tab.", icon=":material/north_east:")


def _backups_panel(backups: pd.DataFrame, maintenance: pd.DataFrame, server_names: list):
    info_card(
        title="Backups & Maintenance",
        note="Safety net: proof every server has a recoverable backup and upcoming change windows are scheduled.",
    )
    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            st.markdown("**Backup job history**")
            bsrv = st.multiselect("Filter by server", server_names, default=server_names, key=f"bk_srv_{id(backups)}")
            shown_bk = backups[backups["server"].isin(bsrv)].copy()
            display_bk = pd.DataFrame({
                "Run time": shown_bk["timestamp"].apply(fmt_dt),
                "Server":   shown_bk["server"],
                "Type":     shown_bk["type"],
                "Result":   shown_bk["result"],
                "Duration": shown_bk["duration_min"].astype(str) + " min",
                "Size":     shown_bk["size_gb"].astype(str) + " GB",
            })
            styled_bk = display_bk.style.map(text_cell(RESULT_STYLE), subset=["Result"])
            st.dataframe(styled_bk, hide_index=True, width="stretch", height=340)
            failed = int((shown_bk["result"] == "Failed").sum())
            if failed:
                st.warning(f"{failed} backup job(s) failed — review logs and re-run.")
            else:
                st.success("All displayed backup jobs completed successfully.")
    with right:
        with st.container(border=True):
            st.markdown("**Scheduled maintenance**")
            display_mt = pd.DataFrame({
                "Scheduled for": maintenance["scheduled_for"].apply(fmt_dt),
                "Server":        maintenance["server"],
                "Description":   maintenance["description"],
                "Duration":      maintenance["duration_hours"].astype(str) + " hr",
                "Owner":         maintenance["owner"],
                "Change ticket": maintenance["change_ticket"],
            })
            st.dataframe(display_mt, hide_index=True, width="stretch", height=340)
            st.caption("Entries are drawn from the change-management calendar.")


def _toolkit_panel():
    with st.container(border=True):
        info_card(
            title="Operations Toolkit",
            note="Quick-launch directory of external platforms the team uses day to day.",
        )
        cats = sorted({t["category"] for t in TOOLKIT})
        sel_cats = st.multiselect("Filter by category", cats, default=cats, key="tk_cats")
        shown = [t for t in TOOLKIT if t["category"] in sel_cats]
        if not shown:
            st.info("No tools match the selected categories.")
        else:
            cards = "".join(
                f'<div class="tool-card">'
                f'<div class="tool-name"><a href="{t["url"]}" target="_blank" rel="noopener noreferrer">{t["name"]}</a></div>'
                f'<span class="tool-cat">{t["category"]}</span>'
                f'<div class="tool-desc">{t["description"]}</div>'
                f'</div>'
                for t in shown
            )
            st.markdown(f'<div class="tool-grid">{cards}</div>', unsafe_allow_html=True)
            st.caption(f"Showing {len(shown)} of {len(TOOLKIT)} tools.")


# ============================================================
# ROLE VIEWS
# ============================================================

def view_general_manager(client, snapshots, alerts, backups, maintenance,
                          histories, servers, seed, live_mode, server_names, window_hours):
    tabs = st.tabs(["Executive Overview", "Reports", "Email", "Channels"])

    with tabs[0]:
        info_card(
            title="Executive Overview",
            note="Bird's-eye view of the managed estate — client health, open incidents and team activity.",
        )
        # KPI row
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Clients managed", len(tm.CLIENTS))
        k2.metric("Servers monitored", len(snapshots))
        open_inc = int(((alerts["status"] != "Resolved") & (alerts["severity"] != "Info")).sum())
        k3.metric("Open incidents", open_inc)
        avg_uptime = sum(s["uptime_pct_30d"] for s in snapshots) / len(snapshots)
        k4.metric("Fleet uptime (sampled)", f"{avg_uptime:.2f}%")

        st.divider()
        cl1, cl2 = st.columns(2, gap="large")
        with cl1:
            st.markdown("**Client health summary**")
            client_rows = []
            for c in tm.CLIENTS:
                fleet = tm.build_fleet(c)
                snaps = [tm.latest_snapshot(tm.generate_history(s, hours=6, jitter_seed=seed), s) for s in fleet]
                h_cnt = sum(1 for s in snaps if s["status"] == "Healthy")
                c_cnt = sum(1 for s in snaps if s["status"] == "Critical")
                status = "Critical" if c_cnt > 0 else ("Warning" if h_cnt < len(snaps) else "Healthy")
                client_rows.append({"Client": c["name"], "Tier": c["tier"], "Servers": len(snaps),
                                     "Status": status, "Critical": c_cnt})
            cdf = pd.DataFrame(client_rows)
            styled_c = cdf.style.map(badge_cell(STATUS_STYLE), subset=["Status"])
            st.dataframe(styled_c, hide_index=True, width="stretch", height=260)

        with cl2:
            st.markdown("**Recent incidents**")
            recent = alerts[alerts["status"] != "Resolved"].sort_values("opened", ascending=False).head(8)
            if recent.empty:
                st.success("No open incidents across the estate.")
            else:
                display_r = pd.DataFrame({
                    "Opened":   recent["opened"].apply(fmt_dt),
                    "Severity": recent["severity"],
                    "Server":   recent["server"],
                    "Status":   recent["status"],
                })
                styled_r = (display_r.style
                            .map(badge_cell(SEVERITY_STYLE), subset=["Severity"])
                            .map(badge_cell(ALERT_STATUS_STYLE), subset=["Status"]))
                st.dataframe(styled_r, hide_index=True, width="stretch", height=260)

    with tabs[1]:
        render_report_generator("General Manager", snapshots, alerts, backups, histories, client)

    with tabs[2]:
        render_email_composer("General Manager", client=client, snapshots=snapshots, alerts=alerts)

    with tabs[3]:
        render_channels("General Manager")


def view_monitoring(client, snapshots, alerts, backups, maintenance,
                    histories, servers, seed, live_mode, server_names, window_hours):
    tabs = st.tabs(["Operations Center", "Incidents", "On-Call", "Reports", "Channels"])

    with tabs[0]:
        info_card(
            title="Operations Center",
            note="Live view of the entire estate — fleet health, active alerts and replication topology.",
        )
        open_inc = int(((alerts["status"] != "Resolved") & (alerts["severity"] != "Info")).sum())
        critical_cnt = int((alerts["severity"] == "Critical").sum())
        o1, o2, o3, o4 = st.columns(4)
        o1.metric("Total servers", len(snapshots))
        o2.metric("Open incidents", open_inc)
        o3.metric("Critical alerts", critical_cnt)
        o4.metric("Avg latency", f"{sum(s['query_latency_ms'] for s in snapshots)/len(snapshots):.1f} ms")
        st.divider()
        _fleet_panel(snapshots, server_names, alerts)

    with tabs[1]:
        _alerts_panel(alerts, server_names, show_drilldown=False)
        st.divider()
        st.markdown("**Create incident**")
        with st.form("create_incident_monitoring", clear_on_submit=True):
            ci1, ci2 = st.columns(2)
            inc_server = ci1.selectbox("Server", server_names)
            inc_sev    = ci2.selectbox("Severity", ["Critical", "Warning", "Info"])
            inc_desc   = st.text_area("Description", placeholder="Describe the incident…", height=90)
            if st.form_submit_button("Create incident ticket", icon=":material/add_alert:", type="primary"):
                if inc_desc.strip():
                    store.create_ticket(
                        title=f"[{inc_sev}] Incident on {inc_server}",
                        description=inc_desc.strip(),
                        priority=inc_sev if inc_sev != "Info" else "Low",
                        created_by="Monitoring",
                        assigned_to="Unassigned",
                    )
                    st.toast(f"Incident ticket created for {inc_server}", icon=":material/add_alert:")
                else:
                    st.warning("Add a description.")

    with tabs[2]:
        info_card(title="On-Call Schedule", note="14-day rotation — current, past and upcoming shifts.")
        oncall_df = _gen_oncall(seed)
        active_row = oncall_df[oncall_df["Status"] == "Active"]
        if not active_row.empty:
            ac = active_row.iloc[0]
            st.success(f"Today's on-call: **{ac['Primary on-call']}** (backup: {ac['Backup']})")
        st.dataframe(oncall_df, hide_index=True, width="stretch", height=380)

    with tabs[3]:
        render_report_generator("Monitoring", snapshots, alerts, backups, histories, client)

    with tabs[4]:
        render_channels("Monitoring")


def view_data_ops(client, snapshots, alerts, backups, maintenance,
                  histories, servers, seed, live_mode, server_names, window_hours):
    tabs = st.tabs(["DB Performance", "Backups", "Maintenance", "Health Check", "Reports", "Channels"])

    with tabs[0]:
        _server_detail_panel(servers, snapshots, histories, seed, live_mode, client)

    with tabs[1]:
        with st.container(border=True):
            _backups_panel(backups, maintenance, server_names)

    with tabs[2]:
        with st.container(border=True):
            info_card(title="Maintenance Schedule", note="Upcoming change windows across the estate.")
            st.dataframe(pd.DataFrame({
                "Scheduled for": maintenance["scheduled_for"].apply(fmt_dt),
                "Server":        maintenance["server"],
                "Description":   maintenance["description"],
                "Duration":      maintenance["duration_hours"].astype(str) + " hr",
                "Owner":         maintenance["owner"],
                "Ticket":        maintenance["change_ticket"],
            }), hide_index=True, width="stretch")
            st.divider()
            st.markdown("**Schedule new maintenance window**")
            with st.form("new_maint_dataops", clear_on_submit=True):
                mc1, mc2 = st.columns(2)
                m_server = mc1.selectbox("Server", server_names)
                m_desc   = mc2.text_input("Description", placeholder="Brief description of work")
                mc3, mc4 = st.columns(2)
                m_date   = mc3.date_input("Scheduled date", value=datetime.now().date() + timedelta(days=7))
                m_dur    = mc4.number_input("Duration (hours)", min_value=1, max_value=12, value=2)
                if st.form_submit_button("Add to calendar", icon=":material/event:", type="primary"):
                    if m_desc.strip():
                        store.create_ticket(
                            title=f"Maintenance: {m_desc.strip()} on {m_server}",
                            description=f"Scheduled for {m_date}, duration {m_dur}h",
                            priority="Low", created_by="Data Operation Specialist",
                        )
                        st.toast(f"Maintenance window added for {m_server}", icon=":material/event:")

    with tabs[3]:
        with st.container(border=True):
            info_card(
                title="Database Health Check",
                note="Run a simulated connectivity, replication and performance test against any server in the fleet.",
            )
            hc_server = st.selectbox("Select server", server_names, key="hc_server")
            if st.button("Run health check", icon=":material/play_circle:", type="primary", key="hc_run"):
                snap = next(s for s in snapshots if s["name"] == hc_server)
                with st.status(f"Running health checks on {hc_server}…", expanded=True) as status_box:
                    import time as _time
                    st.write("Testing connectivity…")
                    _time.sleep(0.4)
                    st.write("Checking replication status…")
                    _time.sleep(0.4)
                    st.write("Measuring query latency…")
                    _time.sleep(0.4)
                    st.write("Verifying disk capacity…")
                    _time.sleep(0.3)
                    status_box.update(label="Health check complete", state="complete", expanded=False)

                results = [
                    ("Connectivity", True, f"Host {snap['hostname']} reachable on port 5432"),
                    ("Replication", snap["replication_lag_s"] <= 30 if snap["role"] == "Replica" else True,
                     f"Lag {snap['replication_lag_s']:.2f}s" if snap["role"] == "Replica" else "Primary — N/A"),
                    ("Query latency", snap["query_latency_ms"] < 100,
                     f"{snap['query_latency_ms']:.1f}ms (threshold 100ms)"),
                    ("Disk capacity", snap["disk_pct"] < 85,
                     f"{snap['disk_pct']:.1f}% used (threshold 85%)"),
                    ("CPU load",     snap["cpu_pct"] < 90, f"{snap['cpu_pct']:.1f}% (threshold 90%)"),
                ]
                for check, passed, detail in results:
                    if passed:
                        st.success(f"**{check}** — {detail}")
                    else:
                        st.error(f"**{check}** FAILED — {detail}")

    with tabs[4]:
        render_report_generator("Data Operation Specialist", snapshots, alerts, backups, histories, client)

    with tabs[5]:
        render_channels("Data Operation Specialist")


def view_it_assistant(client, snapshots, alerts, backups, maintenance,
                      histories, servers, seed, live_mode, server_names, window_hours):
    tabs = st.tabs(["Help Desk", "Server Status", "Runbooks", "Email", "Channels"])

    with tabs[0]:
        render_ticket_system("I.T Assistant", mode="full")

    with tabs[1]:
        with st.container(border=True):
            info_card(title="Server Status Board", note="Read-only health snapshot of the current fleet.")
            display = pd.DataFrame([{
                "Server":  s["name"], "Role": s["role"],
                "Engine":  f"{s['engine']} {s['version']}",
                "Region":  s["region"], "Status": s["status"],
                "CPU %":   f"{s['cpu_pct']:.1f}",
                "Mem %":   f"{s['memory_pct']:.1f}",
                "Disk %":  f"{s['disk_pct']:.1f}",
                "Uptime %": f"{s['uptime_pct_30d']:.2f}",
            } for s in snapshots])
            styled = display.style.map(badge_cell(STATUS_STYLE), subset=["Status"])
            st.dataframe(styled, hide_index=True, width="stretch")
            critical = [s for s in snapshots if s["status"] == "Critical"]
            if critical:
                st.error(f"{len(critical)} server(s) in Critical state — escalate to Monitoring or Infrastructure Engineer.")

    with tabs[2]:
        with st.container(border=True):
            info_card(title="Runbooks", note="Step-by-step procedures for common incidents and maintenance tasks.")
            for rb in RUNBOOKS:
                with st.expander(f"**{rb['title']}**  ·  _{rb['category']}_"):
                    for line in rb["steps"].split("\n"):
                        st.markdown(line)

    with tabs[3]:
        render_email_composer("I.T Assistant", client=client, snapshots=snapshots, alerts=alerts)

    with tabs[4]:
        render_channels("I.T Assistant")


def view_backend_dev(client, snapshots, alerts, backups, maintenance,
                     histories, servers, seed, live_mode, server_names, window_hours):
    tabs = st.tabs(["Query Runner", "Schema Explorer", "Service Health", "Channels"])

    with tabs[0]:
        with st.container(border=True):
            info_card(
                title="Query Runner",
                note="Simulated SQL sandbox — select a sample query or write your own. "
                     "Results reflect current telemetry data, not a live database connection.",
            )
            q1, q2 = st.columns([1, 2])
            with q1:
                sample = st.selectbox("Sample queries", ["Custom"] + list(SAMPLE_QUERIES.keys()), key="qr_sample")
                qr_server = st.selectbox("Target server", server_names, key="qr_server")
            with q2:
                default_sql = SAMPLE_QUERIES.get(sample, "") if sample != "Custom" else ""
                sql = st.text_area("SQL", value=default_sql, height=160,
                                   placeholder="SELECT * FROM pg_stat_activity WHERE state != 'idle';",
                                   key="qr_sql")

            if st.button("Run query", icon=":material/play_circle:", type="primary", key="qr_run"):
                if not sql.strip():
                    st.warning("Enter a query to run.")
                else:
                    snap = next(s for s in snapshots if s["name"] == qr_server)
                    hist = histories[qr_server]
                    if "pg_stat_statements" in sql or "slow quer" in sql.lower():
                        result_df = hist[["timestamp", "query_latency_ms", "connections"]].tail(10).copy()
                        result_df.columns = ["timestamp", "mean_time_ms", "calls"]
                        result_df["query"] = "SELECT ... (anonymised)"
                    elif "table" in sql.lower() and "size" in sql.lower():
                        result_df = pd.DataFrame(SCHEMA_TABLES.get(snap["engine"], []))
                    elif "replication" in sql.lower():
                        result_df = pd.DataFrame([{
                            "client_addr": snap["ip_address"], "state": "streaming",
                            "sent_lsn": "0/15000000", "write_lsn": "0/14FFFF80",
                            "flush_lsn": "0/14FFFF80", "replay_lsn": "0/14FFFF40",
                        }]) if snap["role"] == "Primary" else pd.DataFrame(columns=["client_addr", "state"])
                    else:
                        result_df = hist[["timestamp", "cpu_pct", "memory_pct", "connections",
                                          "query_latency_ms"]].tail(15).copy()
                    st.success(f"Query executed on {qr_server} — {len(result_df)} rows returned (simulated)")
                    st.dataframe(result_df, hide_index=True, width="stretch")

    with tabs[1]:
        with st.container(border=True):
            info_card(title="Schema Explorer", note="Table inventory per engine with row counts, sizes and index stats.")
            se_server = st.selectbox("Server", server_names, key="se_server")
            snap = next(s for s in snapshots if s["name"] == se_server)
            engine_key = snap["engine"]
            tables = SCHEMA_TABLES.get(engine_key, [])
            if tables:
                st.markdown(f"**{engine_key} {snap['version']}** — {snap['hostname']}")
                st.dataframe(pd.DataFrame(tables), hide_index=True, width="stretch")
                st.caption(f"{len(tables)} tables / collections in the public schema.")
            else:
                st.info(f"Schema metadata not available for {engine_key}.")

    with tabs[2]:
        with st.container(border=True):
            info_card(title="Service Health", note="API gateway and internal service response times.")
            sh_rng = random.Random(abs(hash(seed)) % 2 ** 32)
            services_data = [
                {"Service": "REST API Gateway",    "Status": "Healthy", "Latency": f"{sh_rng.randint(12, 45)}ms",  "Error rate": "0.01%", "Last checked": "just now"},
                {"Service": "GraphQL Endpoint",    "Status": "Healthy", "Latency": f"{sh_rng.randint(20, 80)}ms",  "Error rate": "0.02%", "Last checked": "30s ago"},
                {"Service": "WebSocket Service",   "Status": "Warning", "Latency": f"{sh_rng.randint(80, 180)}ms", "Error rate": "0.12%", "Last checked": "1m ago"},
                {"Service": "Background Jobs API", "Status": "Healthy", "Latency": f"{sh_rng.randint(5, 25)}ms",   "Error rate": "0.00%", "Last checked": "15s ago"},
                {"Service": "Auth Service",        "Status": "Healthy", "Latency": f"{sh_rng.randint(8, 30)}ms",   "Error rate": "0.00%", "Last checked": "45s ago"},
            ]
            sh_df = pd.DataFrame(services_data)
            styled_sh = sh_df.style.map(badge_cell(STATUS_STYLE), subset=["Status"])
            st.dataframe(styled_sh, hide_index=True, width="stretch")

    with tabs[3]:
        render_channels("Back-end Developer")


def view_devops(client, snapshots, alerts, backups, maintenance,
                histories, servers, seed, live_mode, server_names, window_hours):
    tabs = st.tabs(["Deployments", "Pipeline", "Config Drift", "Toolkit", "Reports", "Channels"])

    with tabs[0]:
        with st.container(border=True):
            info_card(title="Deployment Log", note="Recent deployments across all services and environments.")
            deploy_df = _gen_deployments(seed)
            deploy_style = {
                "Success":     "color:#22c55e;font-weight:600;",
                "Failed":      "color:#ef4444;font-weight:600;",
                "In Progress": "color:#f59e0b;font-weight:600;",
            }
            styled_d = deploy_df.style.map(text_cell(deploy_style), subset=["Status"])
            st.dataframe(styled_d, hide_index=True, width="stretch", height=420)

    with tabs[1]:
        with st.container(border=True):
            info_card(title="CI/CD Pipeline", note="Current build and deployment pipeline stages.")
            stages = [
                {"Stage": "Source checkout",    "Status": "Success", "Duration": "8s",   "Branch": "main"},
                {"Stage": "Unit tests",         "Status": "Success", "Duration": "1m 24s", "Branch": "main"},
                {"Stage": "Integration tests",  "Status": "Success", "Duration": "3m 12s", "Branch": "main"},
                {"Stage": "Security scan",      "Status": "Success", "Duration": "45s",  "Branch": "main"},
                {"Stage": "Build container",    "Status": "Success", "Duration": "2m 08s", "Branch": "main"},
                {"Stage": "Deploy to staging",  "Status": "Success", "Duration": "1m 55s", "Branch": "main"},
                {"Stage": "Smoke tests",        "Status": "Success", "Duration": "38s",  "Branch": "main"},
                {"Stage": "Deploy to production", "Status": "In Progress", "Duration": "—", "Branch": "main"},
            ]
            pipe_style = {"Success": "color:#22c55e;", "Failed": "color:#ef4444;", "In Progress": "color:#f59e0b;"}
            st.dataframe(
                pd.DataFrame(stages).style.map(text_cell(pipe_style), subset=["Status"]),
                hide_index=True, width="stretch",
            )

    with tabs[2]:
        with st.container(border=True):
            info_card(title="Config Drift", note="Servers whose runtime parameters diverge from the expected baseline.")
            drift_df = _gen_config_drift(seed, snapshots)
            drift_style = {"Yes": "color:#ef4444;font-weight:600;", "Clean": "color:#22c55e;"}
            st.dataframe(
                drift_df.style.map(text_cell(drift_style), subset=["Drift"]),
                hide_index=True, width="stretch",
            )
            drifted = int((drift_df["Drift"] == "Yes").sum())
            if drifted:
                st.warning(f"{drifted} server(s) have configuration drift — review and remediate.")
            else:
                st.success("All servers are within expected configuration baselines.")

    with tabs[3]:
        _toolkit_panel()

    with tabs[4]:
        render_report_generator("Dev-Ops", snapshots, alerts, backups, histories, client)

    with tabs[5]:
        render_channels("Dev-Ops")


def view_infra_engineer(client, snapshots, alerts, backups, maintenance,
                        histories, servers, seed, live_mode, server_names, window_hours):
    tabs = st.tabs(["Fleet", "Capacity Planning", "DR Status", "Security", "Reports", "Channels"])

    with tabs[0]:
        _fleet_panel(snapshots, server_names, alerts)

    with tabs[1]:
        with st.container(border=True):
            info_card(
                title="Capacity Planning",
                note="Disk growth projections and days-to-full estimates based on observed usage trends.",
            )
            cap_rows = []
            for s in snapshots:
                days = s.get("days_to_disk_full")
                flag = "Critical" if days and days <= 14 else ("Warning" if days and days <= 30 else "OK")
                cap_rows.append({
                    "Server":     s["name"],
                    "Disk Used":  f"{s['disk_used_gb']:.0f} GB",
                    "Capacity":   f"{s['disk_capacity_gb']} GB",
                    "Disk %":     f"{s['disk_pct']:.1f}",
                    "Days to full": str(days) if days else "Stable",
                    "Flag":       flag,
                    "CPU %":      f"{s['cpu_pct']:.1f}",
                    "Mem %":      f"{s['memory_pct']:.1f}",
                })
            cap_df = pd.DataFrame(cap_rows)
            flag_style = {"Critical": "color:#ef4444;font-weight:600;",
                          "Warning": "color:#f59e0b;font-weight:600;",
                          "OK": "color:#22c55e;"}
            st.dataframe(cap_df.style.map(text_cell(flag_style), subset=["Flag"]),
                         hide_index=True, width="stretch")
            critical_cap = cap_df[cap_df["Flag"] == "Critical"]
            warning_cap  = cap_df[cap_df["Flag"] == "Warning"]
            if not critical_cap.empty:
                st.error(f"{len(critical_cap)} server(s) will reach 95% disk within 14 days — immediate action required.")
            elif not warning_cap.empty:
                st.warning(f"{len(warning_cap)} server(s) projected to hit 95% disk within 30 days — plan storage expansion.")
            else:
                st.success("All servers have comfortable disk headroom.")
            st.caption("Projection based on observed daily growth rate from the telemetry window.")
            st.line_chart(
                pd.DataFrame({s["name"]: histories[s["name"]]["disk_pct"].values for s in snapshots}),
                height=280, color=["#22d3ee", "#8b5cf6", "#34d399", "#f59e0b", "#ef4444", "#a78bfa"],
            )

    with tabs[2]:
        with st.container(border=True):
            info_card(title="DR Status", note="Failover readiness, RTO/RPO targets and last drill dates per server.")
            dr_df = _gen_dr_status(seed, snapshots)
            dr_style = {"Yes": "color:#22c55e;font-weight:600;", "No": "color:#ef4444;font-weight:600;"}
            st.dataframe(dr_df.style.map(text_cell(dr_style), subset=["Failover ready"]),
                         hide_index=True, width="stretch")
            not_ready = int((dr_df["Failover ready"] == "No").sum())
            if not_ready:
                st.warning(f"{not_ready} server(s) not failover-ready — schedule a DR drill.")
            else:
                st.success("All servers are failover-ready.")

    with tabs[3]:
        with st.container(border=True):
            info_card(title="Security & Compliance", note="Automated checklist — passed items are verified at last refresh.")
            checklist = _gen_security_checklist(seed, snapshots)
            pass_cnt = sum(1 for c in checklist if c["passed"])
            total = len(checklist)
            st.metric("Compliance score", f"{pass_cnt}/{total}",
                      delta=f"{'All clear' if pass_cnt == total else f'{total - pass_cnt} item(s) need attention'}")
            st.divider()
            for item in checklist:
                icon = ":material/check_circle:" if item["passed"] else ":material/cancel:"
                color = "#22c55e" if item["passed"] else "#ef4444"
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;padding:5px 0;border-bottom:1px solid #1a2338;">'
                    f'<span style="color:{color};font-size:1.1rem;">{"✅" if item["passed"] else "❌"}</span>'
                    f'<span style="color:#cbd5e1;font-size:0.87rem;">{item["check"]}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    with tabs[4]:
        render_report_generator("Infrastructure Engineer", snapshots, alerts, backups, histories, client)

    with tabs[5]:
        render_channels("Infrastructure Engineer")


def view_customer_service(client, snapshots, alerts, backups, maintenance,
                           histories, servers, seed, live_mode, server_names, window_hours):
    tabs = st.tabs(["Service Status", "Tickets", "Email", "Channels"])

    with tabs[0]:
        info_card(
            title="Service Status",
            note="Platform health as visible to clients — use this to answer inbound queries about system availability.",
        )
        # Overall status banner
        critical = [s for s in snapshots if s["status"] == "Critical"]
        warning  = [s for s in snapshots if s["status"] == "Warning"]
        if critical:
            st.error(f"**Service degraded** — {len(critical)} server(s) in Critical state. "
                     "Active investigation underway. Escalate urgent client calls to Monitoring.")
        elif warning:
            st.warning(f"**Partial degradation** — {len(warning)} server(s) reporting warnings. "
                       "Service is operational but performance may be affected.")
        else:
            st.success("**All systems operational** — no active incidents affecting client services.")

        st.divider()
        # Per-client service map (all clients, their active alerts)
        st.markdown("**Per-client service map**")
        for c in tm.CLIENTS:
            fleet = tm.build_fleet(c)
            snaps = [tm.latest_snapshot(tm.generate_history(s, hours=6, jitter_seed=seed), s) for s in fleet]
            crit  = sum(1 for s in snaps if s["status"] == "Critical")
            warn  = sum(1 for s in snaps if s["status"] == "Warning")
            icon  = "🔴" if crit else ("🟠" if warn else "🟢")
            desc  = f"Critical: {crit}" if crit else (f"Warning: {warn}" if warn else "All healthy")
            with st.expander(f"{icon} **{c['name']}** ({c['tier']}) — {c['hq']} — {desc}"):
                cs_rows = [{"Server": s["name"], "Status": s["status"],
                             "CPU %": f"{s['cpu_pct']:.1f}", "Mem %": f"{s['memory_pct']:.1f}",
                             "Uptime %": f"{s['uptime_pct_30d']:.2f}"}
                           for s in snaps]
                styled_cs = pd.DataFrame(cs_rows).style.map(badge_cell(STATUS_STYLE), subset=["Status"])
                st.dataframe(styled_cs, hide_index=True, width="stretch")

        st.divider()
        st.markdown("**Open incidents affecting clients**")
        open_alerts = alerts[(alerts["status"].isin(["Open", "Acknowledged"])) &
                             (alerts["severity"].isin(["Critical", "Warning"]))].head(10)
        if open_alerts.empty:
            st.info("No open incidents to report.")
        else:
            display = pd.DataFrame({
                "Opened":   open_alerts["opened"].apply(fmt_dt),
                "Severity": open_alerts["severity"],
                "Server":   open_alerts["server"],
                "Status":   open_alerts["status"],
            })
            st.dataframe(
                display.style.map(badge_cell(SEVERITY_STYLE), subset=["Severity"])
                             .map(badge_cell(ALERT_STATUS_STYLE), subset=["Status"]),
                hide_index=True, width="stretch",
            )

    with tabs[1]:
        render_ticket_system("Customer Service", mode="cs")

    with tabs[2]:
        render_email_composer("Customer Service", client=client, snapshots=snapshots, alerts=alerts)

    with tabs[3]:
        render_channels("Customer Service")


def view_data_analyst(client, snapshots, alerts, backups, maintenance,
                      histories, servers, seed, live_mode, server_names, window_hours):
    tabs = st.tabs(["Analytics", "Report Builder", "Export", "Channels"])

    with tabs[0]:
        info_card(
            title="Analytics",
            note="Performance trend analysis, uptime metrics and multi-server comparisons.",
        )
        da1, da2 = st.columns([2, 1])
        with da1:
            metric_sel = st.selectbox(
                "Metric to compare",
                ["cpu_pct", "memory_pct", "disk_pct", "query_latency_ms", "connections", "iops"],
                key="da_metric",
            )
            srv_sel = st.multiselect("Servers", server_names, default=server_names, key="da_servers")
        with da2:
            st.metric("Avg uptime", f"{sum(s['uptime_pct_30d'] for s in snapshots)/len(snapshots):.2f}%")
            open_inc = int(((alerts["status"] != "Resolved") & (alerts["severity"] != "Info")).sum())
            st.metric("Open incidents", open_inc)

        if srv_sel:
            chart_data = pd.DataFrame({
                s: histories[s][metric_sel].values
                for s in srv_sel
                if s in histories
            })
            st.caption(f"**{metric_sel}** over the selected window — all selected servers overlaid")
            st.line_chart(chart_data, height=320,
                          color=["#22d3ee", "#8b5cf6", "#34d399", "#f59e0b", "#ef4444", "#a78bfa"][:len(srv_sel)])
        else:
            st.info("Select at least one server above.")

        st.divider()
        st.markdown("**Incident frequency by severity**")
        sev_counts = alerts.groupby("severity").size().reset_index(name="count")
        for _, row in sev_counts.iterrows():
            badge_s = SEVERITY_STYLE.get(row["severity"], "")
            st.markdown(
                f'<span style="{BADGE_CSS}{badge_s}">{row["severity"]}</span>'
                f'<span style="color:#cbd5e1;font-size:0.88rem;margin-left:12px;">{row["count"]} events</span>',
                unsafe_allow_html=True,
            )

        st.divider()
        st.markdown("**MTTR (mean time to resolution) by server**")
        resolved = alerts[alerts["status"] == "Resolved"].copy()
        if not resolved.empty:
            resolved["ttr_min"] = (resolved["resolved"] - resolved["opened"]).dt.total_seconds() / 60
            mttr = resolved.groupby("server")["ttr_min"].mean().reset_index()
            mttr.columns = ["Server", "MTTR (min)"]
            mttr["MTTR (min)"] = mttr["MTTR (min)"].round(1)
            st.dataframe(mttr.sort_values("MTTR (min)"), hide_index=True, width="stretch", height=220)
        else:
            st.info("No resolved incidents to compute MTTR.")

    with tabs[1]:
        render_report_generator("Data Analyst", snapshots, alerts, backups, histories, client)

    with tabs[2]:
        with st.container(border=True):
            info_card(title="Data Export", note="Download any dataset as CSV or Excel for offline analysis.")
            dataset = st.selectbox("Dataset", [
                "Fleet snapshot",
                "Performance history (selected server)",
                "Alert history",
                "Backup log",
            ], key="da_export_ds")
            exp_srv = None
            if dataset == "Performance history (selected server)":
                exp_srv = st.selectbox("Server", server_names, key="da_exp_srv")
            exp_fmt = st.radio("Format", ["CSV", "Excel (.xlsx)"], horizontal=True, key="da_exp_fmt")

            if st.button("Prepare download", icon=":material/download:", type="primary", key="da_exp_btn"):
                if dataset == "Fleet snapshot":
                    df = pd.DataFrame([{
                        "Server": s["name"], "Status": s["status"], "CPU %": s["cpu_pct"],
                        "Memory %": s["memory_pct"], "Disk %": s["disk_pct"],
                        "Uptime %": s["uptime_pct_30d"], "Latency ms": s["query_latency_ms"],
                    } for s in snapshots])
                elif dataset == "Performance history (selected server)":
                    df = histories[exp_srv].copy()
                elif dataset == "Alert history":
                    df = alerts.copy()
                    df["opened"]   = df["opened"].astype(str)
                    df["resolved"] = df["resolved"].astype(str)
                else:
                    df = backups.copy()
                    df["timestamp"] = df["timestamp"].astype(str)

                fname = f"{client['code']}_{dataset.lower().replace(' ', '_').replace('(', '').replace(')', '')}"
                if exp_fmt == "CSV":
                    st.download_button(
                        f"Download {dataset}.csv", data=df.to_csv(index=False),
                        file_name=f"{fname}.csv", mime="text/csv",
                        icon=":material/download:", key="da_dl",
                    )
                else:
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                        df.to_excel(writer, sheet_name="Data", index=False)
                    st.download_button(
                        f"Download {dataset}.xlsx", data=buf.getvalue(),
                        file_name=f"{fname}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        icon=":material/download:", key="da_dl",
                    )

    with tabs[3]:
        render_channels("Data Analyst")


# ============================================================
# NEW ROLE VIEWS
# ============================================================

def view_server_maint(*, client, snapshots, servers, seed, role, **_):
    info_card(
        "Server Maintenance & Patch Management",
        "Schedule maintenance windows, track patch levels, log changes and manage planned downtime.",
    )
    rng = random.Random(abs(hash(seed)) % 2 ** 32)
    tabs = st.tabs(["Scheduled Windows", "Patch Tracker", "Create Window", "Change Log"])

    with tabs[0]:
        windows = store.get().get("maint_windows", [])
        active_wins = [w for w in windows if w.get("status") not in ("Completed", "Cancelled")]
        if not active_wins:
            st.markdown(
                '<div style="padding:32px;text-align:center;color:#475569;'
                'background:rgba(15,23,42,0.6);border-radius:10px;border:1px solid #1e293b;">'
                'No scheduled maintenance windows. Use the <b>Create Window</b> tab to schedule one.</div>',
                unsafe_allow_html=True,
            )
        for w in active_wins:
            status_color = {"Scheduled": "#22d3ee", "In Progress": "#f59e0b", "Completed": "#22c55e", "Cancelled": "#475569"}.get(w.get("status", ""), "#475569")
            with st.expander(f"🔧 {w.get('title', 'Untitled')} — {w.get('change_type', '')}  [{w.get('status', '')}]", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**ID:** `{w.get('id', '—')}`")
                    st.markdown(f"**Type:** {w.get('change_type', '—')}")
                    st.markdown(f"**Owner:** {w.get('owner', '—')}")
                    st.markdown(f"**Start:** {w.get('start', '—')}")
                    st.markdown(f"**End:** {w.get('end', '—')}")
                with c2:
                    st.markdown(f"**Affected Servers:** {', '.join(w.get('affected_servers', [])) or '—'}")
                    st.markdown(f"**Created by:** {w.get('created_by', '—')}")
                    st.markdown(f"**Description:** {w.get('description', '—')}")
                new_status = st.selectbox("Update status", ["Scheduled", "In Progress", "Completed", "Cancelled"], key=f"mw_status_{w.get('id')}", index=["Scheduled", "In Progress", "Completed", "Cancelled"].index(w.get("status", "Scheduled")) if w.get("status") in ["Scheduled", "In Progress", "Completed", "Cancelled"] else 0)
                if st.button("Apply Status", key=f"mw_apply_{w.get('id')}", type="primary"):
                    store.update_maint_window(w["id"], status=new_status)
                    st.success(f"Status updated to **{new_status}**.")
                    st.rerun()

    with tabs[1]:
        DB_VERSIONS = {"PostgreSQL": ("15.4", "16.2"), "MySQL": ("8.0.33", "8.0.37"), "MongoDB": ("6.0.8", "7.0.4"), "Redis": ("7.0.12", "7.2.3"), "MariaDB": ("10.11.4", "11.2.2")}
        patch_rows = []
        for s in snapshots:
            db = s.get("db_type", "PostgreSQL")
            cur_ver, latest_ver = DB_VERSIONS.get(db, ("—", "—"))
            up_to_date = rng.random() > 0.35
            patch_rows.append({
                "Server": s["name"], "DB Type": db, "Region": s.get("region", "—"),
                "Current Version": cur_ver if up_to_date else cur_ver.rsplit(".", 1)[0] + f".{rng.randint(0, int(cur_ver.rsplit('.', 1)[-1]) - 1)}",
                "Latest Version": latest_ver,
                "Patch Status": "Up to date" if up_to_date else "Patch available",
                "Last Checked": (datetime.now() - timedelta(hours=rng.randint(1, 48))).strftime("%Y-%m-%d %H:%M"),
            })
        patch_df = pd.DataFrame(patch_rows)
        st.dataframe(
            patch_df.style.map(lambda v: "color:#22c55e;font-weight:600;" if v == "Up to date" else ("color:#f59e0b;font-weight:600;" if v == "Patch available" else ""), subset=["Patch Status"]),
            use_container_width=True, hide_index=True,
        )
        needs_patch = sum(1 for r in patch_rows if r["Patch Status"] == "Patch available")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Servers", len(patch_rows))
        c2.metric("Up to Date", len(patch_rows) - needs_patch)
        c3.metric("Patch Available", needs_patch, delta=f"{needs_patch} pending" if needs_patch else None, delta_color="inverse")

    with tabs[2]:
        server_names = [s["name"] for s in servers] if servers else [s["name"] for s in snapshots]
        with st.form("create_maint_window_form", clear_on_submit=True):
            st.markdown("#### Schedule New Maintenance Window")
            title = st.text_input("Title *", placeholder="e.g. PostgreSQL minor version patch")
            change_type = st.selectbox("Change Type", ["Standard", "Emergency", "Normal", "Expedited"])
            affected = st.multiselect("Affected Servers", server_names)
            col_s, col_e = st.columns(2)
            with col_s:
                start_str = st.text_input("Start (YYYY-MM-DD HH:MM)", placeholder="2026-06-15 02:00")
            with col_e:
                end_str = st.text_input("End (YYYY-MM-DD HH:MM)", placeholder="2026-06-15 04:00")
            description = st.text_area("Description / Scope of Work", height=100)
            submitted = st.form_submit_button("Create Window", type="primary")
            if submitted:
                if not title or not start_str or not end_str:
                    st.error("Title, Start and End are required.")
                else:
                    store.create_maint_window(title, description, start_str, end_str, affected, role, change_type, role)
                    st.success(f"Maintenance window **{title}** scheduled successfully.")

    with tabs[3]:
        all_wins = store.get().get("maint_windows", [])
        closed = [w for w in all_wins if w.get("status") in ("Completed", "Cancelled")]
        if not closed:
            st.info("No completed or cancelled windows in the change log yet.")
        else:
            log_df = pd.DataFrame([{
                "ID": w.get("id", "—"), "Title": w.get("title", "—"),
                "Type": w.get("change_type", "—"), "Owner": w.get("owner", "—"),
                "Start": w.get("start", "—"), "End": w.get("end", "—"),
                "Status": w.get("status", "—"), "Servers": ", ".join(w.get("affected_servers", [])),
            } for w in closed])
            st.dataframe(log_df, use_container_width=True, hide_index=True)


def view_asset_mgmt(*, client, snapshots, servers, seed, role, **_):
    info_card(
        "Asset & Infrastructure Registry",
        "Full visibility into fleet inventory, hardware specs, software licences and server lifecycle status.",
    )
    rng = random.Random(abs(hash(seed)) % 2 ** 32)
    tabs = st.tabs(["Fleet Inventory", "Hardware Specs", "License Registry", "Lifecycle"])

    with tabs[0]:
        fleet_rows = []
        for s in snapshots:
            status_emoji = {"Healthy": "🟢", "Warning": "🟡", "Critical": "🔴"}.get(s.get("status", ""), "⚪")
            fleet_rows.append({
                "Server": s["name"], "DB Type": s.get("db_type", "—"), "Role": s.get("role", "—"),
                "Region": s.get("region", "—"),
                "Status": s.get("status", "—"),
                "CPU %": f"{s.get('cpu_pct', 0):.1f}",
                "Mem %": f"{s.get('mem_pct', 0):.1f}",
                "Disk %": f"{s.get('disk_pct', 0):.1f}",
                "Connections": s.get("active_connections", 0),
                "Uptime 30d %": f"{s.get('uptime_pct_30d', 0):.2f}",
            })
        fleet_df = pd.DataFrame(fleet_rows)
        st.dataframe(
            fleet_df.style.map(badge_cell(STATUS_STYLE), subset=["Status"]),
            use_container_width=True, hide_index=True,
        )
        ca, cb, cc, cd = st.columns(4)
        ca.metric("Total Assets", len(fleet_rows))
        cb.metric("Healthy", sum(1 for r in fleet_rows if r["Status"] == "Healthy"))
        cc.metric("Warning", sum(1 for r in fleet_rows if r["Status"] == "Warning"))
        cd.metric("Critical", sum(1 for r in fleet_rows if r["Status"] == "Critical"))

    with tabs[1]:
        hw_rows = []
        datacenters = ["us-east-1a", "us-west-2b", "eu-west-1a", "ap-southeast-1b", "ca-central-1a"]
        for s in snapshots:
            hw_rows.append({
                "Server": s["name"], "DB Type": s.get("db_type", "—"),
                "CPU Cores": rng.choice([8, 16, 32, 64]),
                "RAM (GB)": rng.choice([32, 64, 128, 256]),
                "Disk (TB)": round(rng.uniform(1.0, 20.0), 1),
                "Network": rng.choice(["1 Gbps", "10 Gbps", "25 Gbps"]),
                "Datacenter": rng.choice(datacenters),
                "Hypervisor": rng.choice(["VMware ESXi 8", "KVM", "AWS Nitro", "Bare Metal"]),
            })
        st.dataframe(pd.DataFrame(hw_rows), use_container_width=True, hide_index=True)

    with tabs[2]:
        vendors = ["HashiCorp", "Oracle", "Red Hat", "Elastic", "DataStax", "Percona", "VMware", "Veeam", "PagerDuty", "Datadog"]
        products = ["Vault Enterprise", "Oracle DB SE2", "RHEL Server", "Elasticsearch Enterprise", "DataStax Astra", "Percona XtraDB", "vSphere", "Backup & Replication", "PagerDuty Teams", "Datadog APM"]
        lic_rows = []
        for i in range(10):
            expiry_days = rng.randint(-30, 400)
            expiry_date = (datetime.now() + timedelta(days=expiry_days)).strftime("%Y-%m-%d")
            lic_rows.append({
                "Product": products[i], "Vendor": vendors[i],
                "Type": rng.choice(["Perpetual", "Annual Subscription", "Monthly SaaS", "Per-core"]),
                "Seats / Units": rng.randint(5, 200),
                "Expiry": expiry_date,
                "Cost/yr ($)": f"{rng.randint(2000, 85000):,}",
                "Status": "Expired" if expiry_days < 0 else ("Expiring Soon" if expiry_days < 60 else "Active"),
            })
        lic_df = pd.DataFrame(lic_rows)
        st.dataframe(
            lic_df.style.map(lambda v: "color:#ef4444;font-weight:600;" if v == "Expired" else ("color:#f59e0b;font-weight:600;" if v == "Expiring Soon" else "color:#22c55e;font-weight:600;" if v == "Active" else ""), subset=["Status"]),
            use_container_width=True, hide_index=True,
        )

    with tabs[3]:
        lc_rows = []
        for s in snapshots:
            purchase_date = datetime.now() - timedelta(days=rng.randint(365, 1825))
            warranty_exp = purchase_date + timedelta(days=rng.randint(730, 1460))
            eol_date = purchase_date + timedelta(days=rng.randint(1825, 3650))
            replacement = eol_date - timedelta(days=rng.randint(180, 365))
            days_to_eol = (eol_date - datetime.now()).days
            lc_rows.append({
                "Server": s["name"], "DB Type": s.get("db_type", "—"),
                "Purchase Date": purchase_date.strftime("%Y-%m-%d"),
                "Warranty Expiry": warranty_exp.strftime("%Y-%m-%d"),
                "EOL Date": eol_date.strftime("%Y-%m-%d"),
                "Planned Replacement": replacement.strftime("%Y-%m-%d"),
                "Days to EOL": days_to_eol,
                "Health": "Critical" if days_to_eol < 180 else ("Warning" if days_to_eol < 365 else "Good"),
            })
        lc_df = pd.DataFrame(lc_rows)
        st.dataframe(
            lc_df.style.map(lambda v: "color:#ef4444;font-weight:600;" if v == "Critical" else ("color:#f59e0b;font-weight:600;" if v == "Warning" else "color:#22c55e;" if v == "Good" else ""), subset=["Health"]),
            use_container_width=True, hide_index=True,
        )
        st.caption("Servers with Days to EOL < 180 are highlighted Critical; < 365 are Warning.")


def view_website_dev(*, client, role, seed, **_):
    info_card(
        "Website Development Hub",
        "Track web projects, manage tasks, review the technology stack and kick off new projects.",
    )
    rng = random.Random(abs(hash(seed)) % 2 ** 32)
    tabs = st.tabs(["Projects", "Tasks", "Tech Stack", "New Project"])

    projects = store.get().get("web_projects", [])

    with tabs[0]:
        total = len(projects)
        active = sum(1 for p in projects if p.get("status") == "In Progress")
        on_hold = sum(1 for p in projects if p.get("status") == "On Hold")
        completed = sum(1 for p in projects if p.get("status") == "Completed")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Projects", total)
        m2.metric("In Progress", active)
        m3.metric("On Hold", on_hold)
        m4.metric("Completed", completed)
        st.markdown("---")
        if not projects:
            st.markdown(
                '<div style="padding:40px;text-align:center;color:#475569;background:rgba(15,23,42,0.6);border-radius:10px;border:1px solid #1e293b;">'
                'No projects yet. Use the <b>New Project</b> tab to create one.</div>',
                unsafe_allow_html=True,
            )
        for p in projects:
            with st.expander(f"📁 {p.get('name', 'Untitled')} — {p.get('status', '—')}", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Client:** {p.get('client', '—')}")
                    st.markdown(f"**Priority:** {p.get('priority', '—')}")
                    st.markdown(f"**Due Date:** {p.get('due_date', '—')}")
                    st.markdown(f"**Tech Stack:** {', '.join(p.get('tech_stack', [])) or '—'}")
                with c2:
                    st.markdown(f"**Created by:** {p.get('created_by', '—')}")
                    st.markdown(f"**Description:** {p.get('description', '—')}")
                new_status = st.selectbox("Status", ["In Progress", "On Hold", "Completed", "Cancelled"], key=f"wp_status_{p.get('id')}")
                if st.button("Update Status", key=f"wp_upd_{p.get('id')}", type="primary"):
                    store.update_web_project(p["id"], status=new_status)
                    st.success("Status updated.")
                    st.rerun()

    with tabs[1]:
        if not projects:
            st.markdown('<div style="padding:28px;text-align:center;color:#475569;">Create a project first to see tasks.</div>', unsafe_allow_html=True)
        else:
            task_names = ["Design wireframes", "Set up repo", "Build API endpoints", "Frontend components", "Write unit tests", "Configure CI/CD", "Deploy to staging", "QA review", "Client feedback round", "Production deploy"]
            todo_col, prog_col, done_col = st.columns(3)
            with todo_col:
                st.markdown('<div style="font-size:0.78rem;font-weight:700;color:#f59e0b;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">TODO</div>', unsafe_allow_html=True)
                for t in rng.sample(task_names, k=min(4, len(task_names))):
                    st.markdown(f'<div style="background:rgba(15,23,42,0.8);border:1px solid #1e293b;border-radius:8px;padding:10px 12px;margin-bottom:6px;color:#cbd5e1;font-size:0.82rem;">⬜ {t}</div>', unsafe_allow_html=True)
            with prog_col:
                st.markdown('<div style="font-size:0.78rem;font-weight:700;color:#22d3ee;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">IN PROGRESS</div>', unsafe_allow_html=True)
                for t in rng.sample(task_names, k=min(3, len(task_names))):
                    st.markdown(f'<div style="background:rgba(34,211,238,0.05);border:1px solid rgba(34,211,238,0.18);border-radius:8px;padding:10px 12px;margin-bottom:6px;color:#e2e8f0;font-size:0.82rem;">🔄 {t}</div>', unsafe_allow_html=True)
            with done_col:
                st.markdown('<div style="font-size:0.78rem;font-weight:700;color:#22c55e;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">DONE</div>', unsafe_allow_html=True)
                for t in rng.sample(task_names, k=min(3, len(task_names))):
                    st.markdown(f'<div style="background:rgba(34,197,94,0.05);border:1px solid rgba(34,197,94,0.18);border-radius:8px;padding:10px 12px;margin-bottom:6px;color:#e2e8f0;font-size:0.82rem;">✅ {t}</div>', unsafe_allow_html=True)

    with tabs[2]:
        TECH_STACK = [
            {"Category": "Frontend", "Technology": "React", "Version": "18.3", "Notes": "Primary SPA framework"},
            {"Category": "Frontend", "Technology": "Next.js", "Version": "14.2", "Notes": "SSR & routing layer"},
            {"Category": "Frontend", "Technology": "Tailwind CSS", "Version": "3.4", "Notes": "Utility-first styling"},
            {"Category": "Backend", "Technology": "Node.js", "Version": "20 LTS", "Notes": "API runtime"},
            {"Category": "Backend", "Technology": "FastAPI", "Version": "0.111", "Notes": "Python microservices"},
            {"Category": "Backend", "Technology": "GraphQL (Apollo)", "Version": "4.9", "Notes": "Data layer"},
            {"Category": "Database", "Technology": "PostgreSQL", "Version": "16.2", "Notes": "Primary RDBMS"},
            {"Category": "Database", "Technology": "Redis", "Version": "7.2", "Notes": "Cache & sessions"},
            {"Category": "Database", "Technology": "MongoDB", "Version": "7.0", "Notes": "Document store"},
            {"Category": "DevOps", "Technology": "Docker", "Version": "25.0", "Notes": "Containerisation"},
            {"Category": "DevOps", "Technology": "GitHub Actions", "Version": "—", "Notes": "CI/CD pipelines"},
            {"Category": "Cloud", "Technology": "AWS (ECS + RDS)", "Version": "—", "Notes": "Primary cloud"},
            {"Category": "Cloud", "Technology": "Cloudflare CDN", "Version": "—", "Notes": "Edge & DNS"},
            {"Category": "Cloud", "Technology": "Vercel", "Version": "—", "Notes": "Frontend hosting"},
        ]
        st.dataframe(pd.DataFrame(TECH_STACK), use_container_width=True, hide_index=True)

    with tabs[3]:
        common_tech = ["React", "Next.js", "Vue.js", "Angular", "Tailwind CSS", "Node.js", "FastAPI", "Django", "Laravel", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Docker", "AWS", "Vercel", "Cloudflare", "GitHub Actions"]
        client_name = client.get("name", "") if client else ""
        with st.form("new_web_project_form", clear_on_submit=True):
            st.markdown("#### Create New Web Project")
            proj_name = st.text_input("Project Name *", placeholder="e.g. Client Portal Redesign")
            proj_client = st.text_input("Client Name", value=client_name)
            proj_desc = st.text_area("Description", height=90)
            tech_sel = st.multiselect("Tech Stack", common_tech, default=["React", "Node.js", "PostgreSQL"])
            col_p, col_d = st.columns(2)
            with col_p:
                priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
            with col_d:
                due_date = st.text_input("Due Date (YYYY-MM-DD)", placeholder="2026-09-01")
            submitted = st.form_submit_button("Create Project", type="primary")
            if submitted:
                if not proj_name:
                    st.error("Project Name is required.")
                else:
                    store.create_web_project(proj_name, proj_client, proj_desc, tech_sel, priority, due_date, role)
                    st.success(f"Project **{proj_name}** created successfully.")


def view_bug_perf(*, client, role, seed, snapshots, **_):
    info_card(
        "Bug Tracker & Web Performance",
        "Log and manage bugs, monitor Core Web Vitals, track PageSpeed targets and analyse performance trends.",
    )
    rng = random.Random(abs(hash(seed)) % 2 ** 32)
    tabs = st.tabs(["Bug Tracker", "Web Vitals", "Speed Target", "Log Issue"])

    bugs = store.get().get("bugs", [])

    with tabs[0]:
        total_b = len(bugs)
        open_b = sum(1 for b in bugs if b.get("status") == "Open")
        inprog_b = sum(1 for b in bugs if b.get("status") == "In Progress")
        resolved_b = sum(1 for b in bugs if b.get("status") == "Resolved")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total", total_b)
        m2.metric("Open", open_b)
        m3.metric("In Progress", inprog_b)
        m4.metric("Resolved", resolved_b)
        st.markdown("---")
        if not bugs:
            st.markdown('<div style="padding:32px;text-align:center;color:#475569;background:rgba(15,23,42,0.6);border-radius:10px;border:1px solid #1e293b;">No bugs logged yet. Use the <b>Log Issue</b> tab.</div>', unsafe_allow_html=True)
        else:
            bug_df = pd.DataFrame([{
                "ID": b.get("id", "—"), "Title": b.get("title", "—"),
                "Category": b.get("category", "—"), "Priority": b.get("priority", "—"),
                "Status": b.get("status", "—"), "URL": b.get("url", "—"),
                "Reporter": b.get("reporter", "—"),
                "Created": b.get("created_at", "—")[:16] if b.get("created_at") else "—",
            } for b in bugs])
            st.dataframe(
                bug_df.style.map(badge_cell(PRIORITY_STYLE), subset=["Priority"]).map(badge_cell(TICKET_STATUS_STYLE), subset=["Status"]),
                use_container_width=True, hide_index=True,
            )
            st.markdown("#### Update Bug Status")
            for b in [x for x in bugs if x.get("status") != "Resolved"][:5]:
                with st.expander(f"#{b.get('id', '—')} — {b.get('title', 'Untitled')}", expanded=False):
                    st.markdown(f"**Priority:** {b.get('priority', '—')} | **Category:** {b.get('category', '—')}")
                    st.markdown(f"**Description:** {b.get('description', '—')}")
                    ns = st.selectbox("New Status", ["Open", "In Progress", "Resolved", "Wont Fix"], key=f"bug_ns_{b.get('id')}")
                    if st.button("Update", key=f"bug_upd_{b.get('id')}", type="primary"):
                        store.update_bug(b["id"], status=ns)
                        st.success("Bug status updated.")
                        st.rerun()

    with tabs[1]:
        lcp = round(rng.uniform(1.8, 4.5), 2)
        inp = round(rng.uniform(80, 350), 0)
        cls_val = round(rng.uniform(0.02, 0.35), 3)
        ttfb = round(rng.uniform(120, 800), 0)
        v1, v2, v3, v4 = st.columns(4)
        def _vmetric(col, name, val, good_thresh, warn_thresh, unit=""):
            status = "Good" if val <= good_thresh else ("Needs Improvement" if val <= warn_thresh else "Poor")
            color = "#22c55e" if status == "Good" else ("#f59e0b" if status == "Needs Improvement" else "#ef4444")
            col.metric(name, f"{val}{unit}")
            col.markdown(f'<span style="color:{color};font-size:0.75rem;font-weight:700;">{status}</span>', unsafe_allow_html=True)
        _vmetric(v1, "LCP (s)", lcp, 2.5, 4.0)
        _vmetric(v2, "INP (ms)", inp, 200, 500, "ms")
        _vmetric(v3, "CLS", cls_val, 0.1, 0.25)
        _vmetric(v4, "TTFB (ms)", ttfb, 200, 600, "ms")
        st.markdown("---")
        st.markdown("""
**LCP (Largest Contentful Paint):** Measures loading performance. Target ≤ 2.5s for good user experience.

**INP (Interaction to Next Paint):** Measures responsiveness to user interactions. Target ≤ 200ms.

**CLS (Cumulative Layout Shift):** Measures visual stability. Target ≤ 0.1 — higher values indicate layout shifts.

**TTFB (Time to First Byte):** Measures server response time. Target ≤ 200ms; values above 600ms indicate server issues.
        """)

    with tabs[2]:
        current_score = rng.randint(65, 82)
        target_score = 90
        gap = target_score - current_score
        st.markdown(f"""
<div style="background:rgba(15,23,42,0.8);border:1px solid #1e293b;border-radius:12px;padding:28px;text-align:center;margin-bottom:20px;">
  <div style="font-size:0.78rem;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">Current PageSpeed Score</div>
  <div style="font-size:4rem;font-weight:800;color:{'#22c55e' if current_score >= 90 else ('#f59e0b' if current_score >= 70 else '#ef4444')};">{current_score}</div>
  <div style="font-size:0.85rem;color:#64748b;margin-top:4px;">Target: <b style="color:#22d3ee;">{target_score}</b> &nbsp;|&nbsp; Gap: <b style="color:#f59e0b;">{gap} points</b></div>
</div>
""", unsafe_allow_html=True)
        progress_val = current_score / 100
        st.progress(progress_val, text=f"PageSpeed: {current_score}/100")
        st.markdown("#### Top Improvement Recommendations")
        recommendations = [
            ("Compress and serve images in next-gen formats (WebP/AVIF)", "#f59e0b"),
            ("Enable text compression (Brotli/Gzip) on the server", "#22d3ee"),
            ("Reduce unused JavaScript — code-split with dynamic imports", "#f59e0b"),
            ("Implement server-side caching with Redis for API responses", "#22c55e"),
            ("Preload LCP image and critical fonts using <link rel=preload>", "#22d3ee"),
            ("Eliminate render-blocking resources (defer non-critical CSS/JS)", "#f59e0b"),
        ]
        for rec, color in recommendations:
            st.markdown(f'<div style="padding:10px 14px;margin-bottom:6px;border-left:3px solid {color};background:rgba(15,23,42,0.7);border-radius:0 8px 8px 0;color:#cbd5e1;font-size:0.84rem;">▸ {rec}</div>', unsafe_allow_html=True)

    with tabs[3]:
        with st.form("log_bug_form", clear_on_submit=True):
            st.markdown("#### Log New Bug / Issue")
            bug_title = st.text_input("Title *", placeholder="e.g. Login button unresponsive on mobile")
            bug_url = st.text_input("Affected URL", placeholder="https://example.com/login")
            col_p, col_c = st.columns(2)
            with col_p:
                bug_priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
            with col_c:
                bug_category = st.selectbox("Category", ["Performance", "UI Bug", "Functionality", "Content", "Security"])
            bug_desc = st.text_area("Description *", height=100, placeholder="Describe the issue, steps to reproduce and expected behavior.")
            submitted = st.form_submit_button("Log Issue", type="primary")
            if submitted:
                if not bug_title or not bug_desc:
                    st.error("Title and Description are required.")
                else:
                    store.create_bug(bug_title, bug_desc, bug_url, bug_priority, bug_category, role)
                    st.success(f"Bug **{bug_title}** logged successfully.")


def view_uiux_infra(*, client, role, **_):
    info_card(
        "UI/UX & Infrastructure Requests",
        "Submit UI/UX design or infrastructure change requests, track review progress and view approved items.",
    )
    tabs = st.tabs(["Submit Request", "In Review", "Approved / Closed"])
    submissions = store.get().get("uiux_submissions", [])

    with tabs[0]:
        with st.form("uiux_submit_form", clear_on_submit=True):
            st.markdown("#### New Submission")
            req_title = st.text_input("Title *", placeholder="e.g. Redesign dashboard header navigation")
            req_type = st.selectbox("Type", [
                "UI Design Change", "Infrastructure Change", "New Feature Request",
                "Performance Improvement", "Security Hardening",
            ])
            col_p, col_u = st.columns(2)
            with col_p:
                req_priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
            with col_u:
                req_url = st.text_input("Reference URL (optional)", placeholder="https://...")
            req_desc = st.text_area("Description *", height=110, placeholder="Explain the change, the problem it solves and any acceptance criteria.")
            attachment = st.file_uploader("Attach file (image or PDF, max 5 MB)", type=["png", "jpg", "jpeg", "pdf", "svg", "webp"])
            submitted = st.form_submit_button("Submit Request", type="primary")
            if submitted:
                if not req_title or not req_desc:
                    st.error("Title and Description are required.")
                else:
                    att_data = None
                    if attachment:
                        raw = attachment.read()
                        if len(raw) > _MAX_FILE_MB * 1024 * 1024:
                            st.error(f"File exceeds {_MAX_FILE_MB} MB limit.")
                        else:
                            att_data = {"name": attachment.name, "mime": attachment.type, "data_b64": base64.b64encode(raw).decode(), "size": len(raw)}
                    store.submit_uiux(req_title, req_type, req_desc, req_priority, req_url, role, attachment=att_data)
                    st.success(f"Request **{req_title}** submitted successfully.")

    with tabs[1]:
        in_review = [s for s in submissions if s.get("status") in ("Pending Review", "In Review")]
        if not in_review:
            st.markdown('<div style="padding:32px;text-align:center;color:#475569;background:rgba(15,23,42,0.6);border-radius:10px;border:1px solid #1e293b;">No requests currently in review.</div>', unsafe_allow_html=True)
        for s in in_review:
            with st.expander(f"📋 {s.get('title', 'Untitled')} — {s.get('type', '—')} [{s.get('status', '—')}]", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Type:** {s.get('type', '—')}")
                    st.markdown(f"**Priority:** {s.get('priority', '—')}")
                    st.markdown(f"**Submitted by:** {s.get('submitted_by', '—')}")
                with c2:
                    st.markdown(f"**URL:** {s.get('url', '—') or '—'}")
                    st.markdown(f"**Created:** {s.get('created_at', '—')[:16] if s.get('created_at') else '—'}")
                st.markdown(f"**Description:** {s.get('description', '—')}")
                new_status = st.selectbox("Update Status", ["Pending Review", "In Review", "Approved", "Rejected"], key=f"uiux_ns_{s.get('id')}")
                if st.button("Update Status", key=f"uiux_upd_{s.get('id')}", type="primary"):
                    store.update_uiux(s["id"], status=new_status)
                    st.success("Status updated.")
                    st.rerun()

    with tabs[2]:
        closed = [s for s in submissions if s.get("status") in ("Approved", "Rejected")]
        if not closed:
            st.info("No approved or closed submissions yet.")
        else:
            closed_df = pd.DataFrame([{
                "ID": s.get("id", "—"), "Title": s.get("title", "—"),
                "Type": s.get("type", "—"), "Priority": s.get("priority", "—"),
                "Status": s.get("status", "—"), "Submitted By": s.get("submitted_by", "—"),
                "Created": s.get("created_at", "—")[:10] if s.get("created_at") else "—",
            } for s in closed])
            st.dataframe(closed_df, use_container_width=True, hide_index=True)


def view_client_support_module(*, client, snapshots, alerts, role, **_):
    info_card(
        "Client Support Module",
        "Manage open support cases, track SLA compliance, access the contact directory and escalate issues.",
    )
    rng = random.Random(abs(hash(str(client))) % 2 ** 32)
    tabs = st.tabs(["Active Cases", "SLA Tracker", "Contact Directory", "Escalate"])

    tickets = store.get().get("tickets", [])
    open_tickets = [t for t in tickets if t.get("status") in ("Open", "In Progress", "Escalated")]

    with tabs[0]:
        if not open_tickets:
            st.markdown('<div style="padding:32px;text-align:center;color:#475569;background:rgba(15,23,42,0.6);border-radius:10px;border:1px solid #1e293b;">No active support cases.</div>', unsafe_allow_html=True)
        for t in open_tickets[:20]:
            with st.expander(f"🎫 #{t.get('id', '—')} — {t.get('title', 'Untitled')} [{t.get('status', '—')}]", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Status:** {t.get('status', '—')}")
                    st.markdown(f"**Priority:** {t.get('priority', '—')}")
                    st.markdown(f"**Assigned to:** {t.get('assigned_to', '—')}")
                with c2:
                    st.markdown(f"**Client:** {t.get('client', '—')}")
                    st.markdown(f"**Created:** {str(t.get('created_at', '—'))[:16]}")
                    st.markdown(f"**Updated:** {str(t.get('updated_at', '—'))[:16]}")
                st.markdown(f"**Description:** {t.get('description', '—')}")
                if t.get("notes"):
                    st.markdown("**Notes:**")
                    for n in t["notes"][-3:]:
                        if isinstance(n, dict):
                            note_text_disp = f"[{n.get('ts','')[:16]}] {n.get('author','')}: {n.get('text','')}"
                        else:
                            note_text_disp = str(n)
                        st.markdown(f'<div style="background:rgba(15,23,42,0.7);border-left:3px solid #22d3ee;padding:8px 12px;border-radius:0 6px 6px 0;margin-bottom:4px;font-size:0.8rem;color:#94a3b8;">{note_text_disp}</div>', unsafe_allow_html=True)
                with st.form(f"note_form_{t.get('id')}", clear_on_submit=True):
                    note_input = st.text_input("Add note", placeholder="Enter update or resolution note...")
                    if st.form_submit_button("Add Note", type="primary"):
                        if note_input.strip():
                            store.add_note(t["id"], role, note_input)
                        st.success("Note added.")
                        st.rerun()

    with tabs[1]:
        all_t = tickets
        total_t = len(all_t)
        resolved_t = [t for t in all_t if t.get("status") == "Resolved"]
        open_over_24h = sum(1 for t in open_tickets if (datetime.now() - pd.Timestamp(t.get("created_at", datetime.now())).to_pydatetime().replace(tzinfo=None)).total_seconds() > 86400)
        escalated_t = sum(1 for t in all_t if t.get("status") == "Escalated")
        sla_pct = round((len(resolved_t) / max(total_t, 1)) * 100, 1)
        avg_res_hours = round(rng.uniform(2.5, 18.0), 1)
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("SLA Compliance", f"{sla_pct}%", delta="+2.1%" if sla_pct > 80 else "-3.5%")
        s2.metric("Avg Resolution Time", f"{avg_res_hours}h")
        s3.metric("Open > 24h", open_over_24h)
        s4.metric("Escalated", escalated_t)
        st.markdown("---")
        sla_tiers = [("P1 — Critical", "1h response / 4h resolution", rng.randint(88, 100), "#ef4444"),
                     ("P2 — High",     "4h response / 8h resolution",  rng.randint(85, 99),  "#f59e0b"),
                     ("P3 — Medium",   "8h response / 24h resolution", rng.randint(90, 100), "#22d3ee"),
                     ("P4 — Low",      "24h response / 72h resolution",rng.randint(92, 100), "#22c55e")]
        for tier, target, compliance, color in sla_tiers:
            st.markdown(f'<div style="display:flex;align-items:center;justify-content:space-between;background:rgba(15,23,42,0.7);border:1px solid #1e293b;border-radius:8px;padding:12px 18px;margin-bottom:8px;"><span style="color:#e2e8f0;font-weight:600;">{tier}</span><span style="color:#64748b;font-size:0.8rem;">{target}</span><span style="color:{color};font-weight:700;font-size:1.05rem;">{compliance}%</span></div>', unsafe_allow_html=True)

    with tabs[2]:
        CONTACTS = [
            ("Alice Chen", "Head of IT Operations", "alice.chen@caspira.io", "+1 415-555-0101", "Tier 1"),
            ("Bob Martinez", "Senior DBA", "bob.martinez@caspira.io", "+1 415-555-0102", "Tier 2"),
            ("Carol Okafor", "Infrastructure Lead", "carol.okafor@caspira.io", "+1 415-555-0103", "Tier 2"),
            ("David Kim", "On-Call Engineer", "david.kim@caspira.io", "+1 415-555-0104", "Tier 1"),
            ("Elena Torres", "Customer Success Manager", "elena.torres@caspira.io", "+1 415-555-0105", "Tier 1"),
            ("Faisal Al-Amin", "Security Engineer", "faisal.alamin@caspira.io", "+1 415-555-0106", "Tier 3"),
            ("Grace Liu", "Backend Developer", "grace.liu@caspira.io", "+1 415-555-0107", "Tier 2"),
            ("Henry Osei", "DevOps Specialist", "henry.osei@caspira.io", "+1 415-555-0108", "Tier 2"),
        ]
        cols = st.columns(2)
        for i, (name, role_c, email, phone, tier) in enumerate(CONTACTS):
            tier_color = {"Tier 1": "#22c55e", "Tier 2": "#22d3ee", "Tier 3": "#f59e0b"}.get(tier, "#475569")
            with cols[i % 2]:
                st.markdown(f"""
<div style="background:rgba(15,23,42,0.8);border:1px solid #1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div>
      <div style="font-size:0.95rem;font-weight:700;color:#e2e8f0;">{name}</div>
      <div style="font-size:0.78rem;color:#64748b;margin-top:2px;">{role_c}</div>
    </div>
    <span style="{BADGE_CSS}background:rgba(0,0,0,0.3);color:{tier_color};border:1px solid {tier_color}44;">{tier}</span>
  </div>
  <div style="margin-top:10px;font-size:0.8rem;color:#94a3b8;">📧 {email}</div>
  <div style="font-size:0.8rem;color:#94a3b8;">📞 {phone}</div>
</div>""", unsafe_allow_html=True)

    with tabs[3]:
        open_ticket_ids = [f"#{t.get('id', '—')} — {t.get('title', 'Untitled')}" for t in open_tickets]
        if not open_ticket_ids:
            st.markdown('<div style="padding:28px;text-align:center;color:#475569;">No open tickets available to escalate.</div>', unsafe_allow_html=True)
        else:
            with st.form("escalate_form", clear_on_submit=True):
                st.markdown("#### Escalate Ticket")
                sel_ticket = st.selectbox("Select Ticket", open_ticket_ids)
                esc_reason = st.text_area("Escalation Reason *", height=90, placeholder="Describe why this ticket needs escalation.")
                col_ep, col_ea = st.columns(2)
                with col_ep:
                    esc_priority = st.selectbox("Escalated Priority", ["High", "Critical"])
                with col_ea:
                    assign_to = st.selectbox("Assign To", ALL_ROLES)
                submitted = st.form_submit_button("Escalate Ticket", type="primary")
                if submitted:
                    if not esc_reason:
                        st.error("Escalation reason is required.")
                    else:
                        ticket_id = sel_ticket.split(" — ")[0].lstrip("#")
                        store.update_ticket(ticket_id, status="Escalated", priority=esc_priority, assigned_to=assign_to)
                        st.success(f"Ticket **{sel_ticket}** escalated to **{assign_to}**.")
                        st.rerun()


def view_workflow_docs(*, role, seed, **_):
    info_card(
        "Workflow & Documentation Library",
        "Centralised SOPs, runbooks, policies and guides. Add documents and search the full library.",
    )
    rng = random.Random(abs(hash(seed)) % 2 ** 32)

    BUILTIN_DOCS = [
        {"id": "builtin-1", "title": "Incident Response Playbook", "category": "Incident Response",
         "content": "1. Acknowledge alert within SLA window.\n2. Assess severity (P1-P4) using impact/urgency matrix.\n3. Open ticket and assign to on-call engineer.\n4. Notify stakeholders via #incidents channel.\n5. Resolve or escalate within SLA.\n6. Write post-mortem within 48h for P1/P2.",
         "tags": "incident, response, playbook, alert, on-call", "author": "IT Operations"},
        {"id": "builtin-2", "title": "Backup & Recovery Procedures", "category": "Backup & Recovery",
         "content": "Daily backups run at 02:00 UTC via automated jobs.\nRetention: 7 daily, 4 weekly, 12 monthly snapshots.\nRecovery: restore from latest snapshot, verify checksums, test on staging before promoting.\nRTO target: 4h. RPO target: 1h.\nEscalate to Infrastructure Engineer if backup job fails twice in a row.",
         "tags": "backup, recovery, RTO, RPO, restore, snapshot", "author": "Infrastructure Team"},
        {"id": "builtin-3", "title": "PostgreSQL Admin Guide", "category": "Database Admin",
         "content": "Routine tasks: VACUUM ANALYZE weekly, REINDEX monthly.\nMonitor: pg_stat_activity, pg_stat_bgwriter, pg_stat_replication.\nCritical parameters: max_connections, shared_buffers, work_mem, wal_level.\nFailover: use pg_promote() on standby, update load balancer, update pg_hba.conf.\nBackup: pg_dump for logical, pg_basebackup for physical.",
         "tags": "postgresql, postgres, admin, DBA, vacuum, replication", "author": "Database Team"},
        {"id": "builtin-4", "title": "Access Management Policy", "category": "Access Management",
         "content": "All access requests must be approved by the relevant team lead.\nPrinciple of least privilege applies to all roles.\nPasswords must meet complexity requirements (12+ chars, mixed case, symbols).\nMFA required for all production database access.\nAccess reviewed quarterly; unused accounts disabled after 90 days of inactivity.\nPassword resets logged in audit ticket.",
         "tags": "access, password, MFA, IAM, permissions, policy", "author": "Security Team"},
        {"id": "builtin-5", "title": "Development Standards & Git Workflow", "category": "Development",
         "content": "Branch strategy: main (prod), develop, feature/*, hotfix/*.\nAll PRs require 1 peer review + CI pass before merge.\nCommit messages: Conventional Commits format (feat:, fix:, chore:, docs:).\nCode style: enforced via ESLint/Prettier (JS) and Black/Flake8 (Python).\nNo secrets in source code — use environment variables or Vault.",
         "tags": "git, development, PR, branch, standards, code review", "author": "Dev Team"},
        {"id": "builtin-6", "title": "Deployment & Release Runbook", "category": "Deployment",
         "content": "1. Merge to develop, verify CI passes on staging.\n2. Create release branch, update CHANGELOG.\n3. Run smoke tests on staging environment.\n4. Open deployment ticket, notify #operations channel.\n5. Deploy to production during low-traffic window (02:00-04:00 UTC).\n6. Monitor error rates and latency for 30 min post-deploy.\n7. Rollback plan: redeploy previous Docker image tag.",
         "tags": "deployment, release, CI/CD, rollback, production, runbook", "author": "DevOps Team"},
    ]

    stored_docs = store.get().get("documents", [])
    all_docs = BUILTIN_DOCS + stored_docs

    CATEGORY_COLORS = {
        "Incident Response": "#ef4444", "Backup & Recovery": "#f59e0b",
        "Database Admin": "#22d3ee", "Access Management": "#8b5cf6",
        "Development": "#22c55e", "Deployment": "#fb923c",
    }

    tabs = st.tabs(["Document Library", "Add Document", "Search"])

    with tabs[0]:
        st.markdown(f"**{len(all_docs)} documents** in library ({len(BUILTIN_DOCS)} built-in, {len(stored_docs)} custom)")
        for doc in all_docs:
            cat = doc.get("category", "General")
            cat_color = CATEGORY_COLORS.get(cat, "#475569")
            badge_html = f'<span style="{BADGE_CSS}background:rgba(0,0,0,0.3);color:{cat_color};border:1px solid {cat_color}44;">{cat}</span>'
            with st.expander(f"{doc.get('title', 'Untitled')}", expanded=False):
                st.markdown(badge_html, unsafe_allow_html=True)
                st.markdown(f"**Author:** {doc.get('author', '—')} &nbsp;|&nbsp; **Tags:** `{doc.get('tags', '—')}`")
                st.markdown("---")
                st.markdown(doc.get("content", "No content available."))

    with tabs[1]:
        with st.form("add_doc_form", clear_on_submit=True):
            st.markdown("#### Add New Document")
            doc_title = st.text_input("Title *", placeholder="e.g. Redis Cache Eviction Policy")
            doc_category = st.selectbox("Category", ["Incident Response", "Backup & Recovery", "Database Admin", "Access Management", "Development", "Deployment", "General"])
            doc_content = st.text_area("Content *", height=200, placeholder="Write the document content here. Markdown is supported.")
            doc_tags = st.text_input("Tags (comma-separated)", placeholder="redis, cache, eviction, policy")
            submitted = st.form_submit_button("Add Document", type="primary")
            if submitted:
                if not doc_title or not doc_content:
                    st.error("Title and Content are required.")
                else:
                    store.add_document(doc_title, doc_category, doc_content, doc_tags, role)
                    st.success(f"Document **{doc_title}** added to the library.")

    with tabs[2]:
        query = st.text_input("Search documents", placeholder="Search by title, content or tags...")
        if query:
            q_lower = query.lower()
            results = [d for d in all_docs if q_lower in d.get("title", "").lower() or q_lower in d.get("content", "").lower() or q_lower in d.get("tags", "").lower()]
            st.markdown(f"**{len(results)} result(s)** for `{query}`")
            if not results:
                st.markdown('<div style="padding:24px;text-align:center;color:#475569;">No documents matched your search.</div>', unsafe_allow_html=True)
            for doc in results:
                cat = doc.get("category", "General")
                cat_color = CATEGORY_COLORS.get(cat, "#475569")
                with st.expander(f"{doc.get('title', 'Untitled')} — {cat}", expanded=True):
                    st.markdown(f'<span style="{BADGE_CSS}background:rgba(0,0,0,0.3);color:{cat_color};border:1px solid {cat_color}44;">{cat}</span>', unsafe_allow_html=True)
                    st.markdown(doc.get("content", ""))
        else:
            st.markdown('<div style="padding:24px;text-align:center;color:#475569;">Enter a search term above to find documents.</div>', unsafe_allow_html=True)


def view_ops_reporting(*, client, snapshots, alerts, backups, seed, role, **_):
    info_card(
        "Operations Reporting & Analytics",
        "KPI dashboards, pre-built fleet reports, trend analysis and export centre for all operational data.",
    )
    rng = random.Random(abs(hash(seed)) % 2 ** 32)
    tabs = st.tabs(["KPI Dashboard", "Fleet Reports", "Trend Analysis", "Export Center"])

    now = datetime.now()
    _snaps = [s for s in snapshots if isinstance(s, dict)]
    avg_uptime = round(sum(s.get("uptime_pct_30d", 99.0) for s in _snaps) / max(len(_snaps), 1), 2)
    mttr_h = round(rng.uniform(0.5, 4.2), 1)
    backup_success_rate = round(rng.uniform(94.0, 99.9), 1)
    # alerts is a DataFrame — use vectorised operations
    active_incidents = int((alerts["status"] == "Open").sum()) if hasattr(alerts, "columns") else 0

    with tabs[0]:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Fleet Availability", f"{avg_uptime}%", delta=f"+{round(rng.uniform(0.01, 0.3), 2)}%")
        k2.metric("Avg MTTR", f"{mttr_h}h", delta=f"-{round(rng.uniform(0.1, 0.5), 1)}h", delta_color="inverse")
        k3.metric("Backup Success Rate", f"{backup_success_rate}%")
        k4.metric("Active Incidents", active_incidents, delta_color="inverse")
        st.markdown("---")
        mini1, mini2, mini3 = st.columns(3)
        with mini1:
            st.markdown("**Top 3 by Latency**")
            top_lat = sorted(_snaps, key=lambda s: s.get("query_latency_ms", 0), reverse=True)[:3]
            st.dataframe(pd.DataFrame([{"Server": s["name"], "Latency (ms)": f"{s.get('query_latency_ms', 0):.1f}"} for s in top_lat]), use_container_width=True, hide_index=True)
        with mini2:
            st.markdown("**Top 3 by Disk Usage**")
            top_disk = sorted(_snaps, key=lambda s: s.get("disk_pct", 0), reverse=True)[:3]
            st.dataframe(pd.DataFrame([{"Server": s["name"], "Disk %": f"{s.get('disk_pct', 0):.1f}"} for s in top_disk]), use_container_width=True, hide_index=True)
        with mini3:
            st.markdown("**Recent 3 Alerts**")
            if hasattr(alerts, "columns") and not alerts.empty:
                recent_alerts = alerts.sort_values("opened", ascending=False).head(3)[["server", "severity", "status"]].rename(columns={"server": "Server", "severity": "Severity", "status": "Status"})
                st.dataframe(recent_alerts, use_container_width=True, hide_index=True)
            else:
                st.caption("No alerts.")

    with tabs[1]:
        REPORT_CARDS = [
            ("Fleet Health Summary", "Comprehensive overview of all servers: status, resource usage, uptime and replication health."),
            ("Backup Coverage Report", "Backup job outcomes, success rates, last backup times and coverage gaps per server."),
            ("Alert Activity Report", "All alerts by severity, status and server over the reporting period."),
            ("Capacity Planning Report", "CPU, memory and disk trends to forecast resource needs for the next quarter."),
        ]
        for title, desc in REPORT_CARDS:
            with st.container():
                rc1, rc2 = st.columns([4, 1])
                with rc1:
                    st.markdown(f"**{title}**")
                    st.caption(desc)
                    last_gen = (now - timedelta(hours=rng.randint(1, 72))).strftime("%Y-%m-%d %H:%M")
                    st.caption(f"Last generated: {last_gen}")
                with rc2:
                    if title == "Fleet Health Summary":
                        csv_data = pd.DataFrame([{k: s.get(k, "—") for k in ["name", "db_type", "role", "region", "status", "cpu_pct", "mem_pct", "disk_pct", "uptime_pct_30d"]} for s in _snaps]).to_csv(index=False)
                    elif title == "Backup Coverage Report":
                        csv_data = (backups.to_csv(index=False) if (hasattr(backups, "to_csv") and not backups.empty) else "server,status,timestamp\n")
                    elif title == "Alert Activity Report":
                        csv_data = (alerts.to_csv(index=False) if (hasattr(alerts, "to_csv") and not alerts.empty) else "server,severity,status\n")
                    else:
                        csv_data = pd.DataFrame([{"Server": s["name"], "CPU %": s.get("cpu_pct"), "Mem %": s.get("mem_pct"), "Disk %": s.get("disk_pct")} for s in _snaps]).to_csv(index=False)
                    st.download_button("Download CSV", data=csv_data, file_name=f"{title.lower().replace(' ', '_')}.csv", mime="text/csv", key=f"rpt_{title[:8]}")
                st.markdown('<hr style="border-color:#1e293b;margin:8px 0;">', unsafe_allow_html=True)

    with tabs[2]:
        st.markdown("#### Key Metric Trends vs Previous Period")
        st.caption("Simulated trend data — connect a time-series store for real historical comparison.")
        alert_count = len(alerts) if hasattr(alerts, "__len__") else 0
        TRENDS = [
            ("Fleet Availability",    f"{avg_uptime}%",   rng.choice(["↑", "↑", "→"]), "#22c55e"),
            ("Alert Volume",          str(alert_count),   rng.choice(["↓", "↓", "→"]), "#22c55e"),
            ("Avg Query Latency",     f"{round(sum(s.get('query_latency_ms', 0) for s in _snaps)/max(len(_snaps),1), 1)} ms", rng.choice(["↑", "→", "↓"]), "#f59e0b"),
            ("Backup Success Rate",   f"{backup_success_rate}%", rng.choice(["↑", "→"]), "#22c55e"),
            ("Avg Disk Utilisation",  f"{round(sum(s.get('disk_pct', 0) for s in _snaps)/max(len(_snaps),1), 1)}%", rng.choice(["↑", "→"]), "#f59e0b"),
            ("Open Incidents",        str(active_incidents), rng.choice(["↓", "→", "↑"]), "#ef4444" if active_incidents > 3 else "#22c55e"),
        ]
        for metric, value, arrow, color in TRENDS:
            arrow_color = "#22c55e" if arrow == "↑" else ("#ef4444" if arrow == "↓" else "#475569")
            st.markdown(f'<div style="display:flex;align-items:center;justify-content:space-between;background:rgba(15,23,42,0.7);border:1px solid #1e293b;border-radius:8px;padding:12px 18px;margin-bottom:6px;"><span style="color:#cbd5e1;font-weight:600;">{metric}</span><span style="color:{color};font-weight:700;">{value}</span><span style="color:{arrow_color};font-size:1.2rem;font-weight:800;">{arrow}</span></div>', unsafe_allow_html=True)

    with tabs[3]:
        st.markdown("#### Export Operational Data")
        st.caption("Download raw CSV exports for use in external reporting tools.")
        e1, e2, e3 = st.columns(3)
        with e1:
            fleet_csv = pd.DataFrame([{k: s.get(k, "—") for k in ["name", "db_type", "role", "region", "status", "cpu_pct", "memory_pct", "disk_pct", "query_latency_ms", "connections", "replication_lag_s", "uptime_pct_30d"]} for s in _snaps]).to_csv(index=False)
            st.download_button("Full Fleet Export CSV", data=fleet_csv, file_name="fleet_export.csv", mime="text/csv", use_container_width=True)
            st.caption(f"{len(snapshots)} servers")
        with e2:
            alerts_csv = (alerts.to_csv(index=False) if (hasattr(alerts, "to_csv") and not alerts.empty) else "no data\n")
            st.download_button("Alerts Export CSV", data=alerts_csv, file_name="alerts_export.csv", mime="text/csv", use_container_width=True)
            st.caption(f"{len(alerts)} alerts")
        with e3:
            backups_csv = (backups.to_csv(index=False) if (hasattr(backups, "to_csv") and not backups.empty) else "no data\n")
            st.download_button("Backup Log CSV", data=backups_csv, file_name="backup_log.csv", mime="text/csv", use_container_width=True)
            st.caption(f"{len(backups)} backup records")


def view_channels_page(*, role, **_):
    info_card(
        "Team Channels",
        "Real-time team communication across all operational channels. Select a channel to read and post messages.",
    )
    render_channels(role)


# ============================================================
# DISPATCH MAP
# ============================================================

ROLE_VIEW = {
    "General Manager":          view_general_manager,
    "Monitoring":               view_monitoring,
    "Data Operation Specialist": view_data_ops,
    "I.T Assistant":            view_it_assistant,
    "Back-end Developer":       view_backend_dev,
    "Dev-Ops":                  view_devops,
    "Infrastructure Engineer":  view_infra_engineer,
    "Customer Service":         view_customer_service,
    "Data Analyst":             view_data_analyst,
}
