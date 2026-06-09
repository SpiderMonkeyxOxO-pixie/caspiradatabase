"""Role-based views and shared UI components for the Caspira console.

Each public view_* function renders the complete tab layout for one role.
Shared components (messaging, email, tickets, reports) are called by the
views that need them. ROLE_VIEW maps role name → view function for dispatch.
"""

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

STATUS_STYLE = {
    "Healthy":  "background-color:rgba(34,197,94,0.15);color:#22c55e;border:1px solid rgba(34,197,94,0.4);",
    "Warning":  "background-color:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid rgba(245,158,11,0.4);",
    "Critical": "background-color:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.4);",
}
SEVERITY_STYLE = {
    "Critical": "background-color:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.4);",
    "Warning":  "background-color:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid rgba(245,158,11,0.4);",
    "Info":     "background-color:rgba(34,211,238,0.15);color:#22d3ee;border:1px solid rgba(34,211,238,0.4);",
}
ALERT_STATUS_STYLE = {
    "Open":         "background-color:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.4);",
    "Acknowledged": "background-color:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid rgba(245,158,11,0.4);",
    "Resolved":     "background-color:rgba(34,197,94,0.15);color:#22c55e;border:1px solid rgba(34,197,94,0.4);",
}
RESULT_STYLE  = {"Success": "color:#22c55e;", "Failed": "color:#ef4444;font-weight:600;"}
PRIORITY_STYLE = {
    "Critical": "background-color:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.4);",
    "High":     "background-color:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid rgba(245,158,11,0.4);",
    "Medium":   "background-color:rgba(34,211,238,0.15);color:#22d3ee;border:1px solid rgba(34,211,238,0.4);",
    "Low":      "background-color:rgba(148,163,184,0.15);color:#94a3b8;border:1px solid rgba(148,163,184,0.4);",
}
TICKET_STATUS_STYLE = {
    "Open":        "background-color:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.4);",
    "In Progress": "background-color:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid rgba(245,158,11,0.4);",
    "Escalated":   "background-color:rgba(139,92,246,0.15);color:#8b5cf6;border:1px solid rgba(139,92,246,0.4);",
    "Resolved":    "background-color:rgba(34,197,94,0.15);color:#22c55e;border:1px solid rgba(34,197,94,0.4);",
}
BADGE_CSS = "padding:2px 10px;border-radius:2em;font-size:0.74rem;font-weight:600;letter-spacing:0.02em;"

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


def render_channels(current_role: str):
    info_card(
        title="Team Channels",
        note="Public group messaging — every role can read and post in any channel. "
             "Messages are visible to the whole team and persist across sessions.",
    )

    if "ch_selected" not in st.session_state:
        st.session_state.ch_selected = store.CHANNELS[0]["id"]

    col_list, col_msgs = st.columns([1, 3], gap="medium")

    with col_list:
        st.markdown("**Channels**")
        st.divider()
        for ch in store.CHANNELS:
            msgs = store.get_channel_messages(ch["id"])
            last = msgs[-1] if msgs else None
            is_active = st.session_state.ch_selected == ch["id"]

            label_lines = [ch["name"]]
            if last:
                preview = last["text"]
                label_lines.append(f"{last['from'][:14]}: {preview[:22]}{'…' if len(preview) > 22 else ''}")
            else:
                label_lines.append("No messages yet")

            if st.button(
                "\n".join(label_lines),
                key=f"ch_btn_{ch['id']}",
                type="primary" if is_active else "secondary",
                width="stretch",
            ):
                st.session_state.ch_selected = ch["id"]
                st.rerun()

    with col_msgs:
        sel_id = st.session_state.ch_selected
        sel_ch = next((c for c in store.CHANNELS if c["id"] == sel_id), store.CHANNELS[0])

        st.markdown(f"**{sel_ch['name']}**")
        st.caption(sel_ch["desc"])

        msgs = store.get_channel_messages(sel_id)

        bubbles = ""
        if not msgs:
            bubbles = (
                '<div style="color:#64748b;font-size:0.84rem;text-align:center;padding:48px 0;">'
                f'No messages in {sel_ch["name"]} yet — start the conversation!</div>'
            )
        for m in msgs[-80:]:
            is_mine = m["from"] == current_role
            role_color = _ROLE_COLOR.get(m["from"], "#94a3b8")
            align = "flex-end" if is_mine else "flex-start"
            bg    = "rgba(34,211,238,0.07)" if is_mine else "#111827"
            border = "1px solid rgba(34,211,238,0.22)" if is_mine else "1px solid #1f2940"
            ta    = "right" if is_mine else "left"
            bubbles += (
                f'<div style="align-self:{align};max-width:80%;margin-bottom:6px;">'
                f'<div style="color:{role_color};font-size:0.71rem;font-weight:700;'
                f'margin-bottom:2px;text-align:{ta};">{m["from"]}</div>'
                f'<div style="background:{bg};border:{border};border-radius:10px;'
                f'padding:8px 13px;color:#cbd5e1;font-size:0.85rem;line-height:1.5;">{m["text"]}</div>'
                f'<div style="color:#475569;font-size:0.7rem;margin-top:2px;text-align:{ta};">'
                f'{m["ts"][:10]} {m["ts"][11:16]}</div>'
                f'</div>'
            )

        st.markdown(
            f'<div style="height:380px;overflow-y:auto;display:flex;flex-direction:column;'
            f'gap:4px;padding:14px;background:#0a0e1a;border:1px solid #1f2940;'
            f'border-radius:8px;margin-bottom:10px;">{bubbles}</div>',
            unsafe_allow_html=True,
        )

        with st.form(f"ch_post_{current_role}_{sel_id}", clear_on_submit=True):
            rc1, rc2 = st.columns([5, 1], vertical_alignment="bottom")
            with rc1:
                msg_text = st.text_input(
                    "Post",
                    placeholder=f"Post in {sel_ch['name']}…",
                    label_visibility="collapsed",
                )
            with rc2:
                submitted = st.form_submit_button(
                    "Send", icon=":material/send:", type="primary", width="stretch",
                )
            if submitted:
                if msg_text.strip():
                    store.post_to_channel(current_role, sel_id, msg_text.strip())
                    st.rerun()
                else:
                    st.warning("Write something before posting.")


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
