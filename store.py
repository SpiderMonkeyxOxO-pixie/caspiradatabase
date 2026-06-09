"""Lightweight JSON-backed persistence for messages, tickets and emails.

Loads once into st.session_state["store"] at first access, writes back to
data/store.json on every mutation so data survives page refreshes.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

_STORE_PATH = Path(__file__).parent / "data" / "store.json"

_DEFAULT: dict = {
    "messages":        {},
    "tickets":         [],
    "emails":          [],
    "channels":        {},
    "maint_windows":   [],
    "uiux_submissions":[],
    "bugs":            [],
    "web_projects":    [],
    "documents":       [],
}

CHANNELS = [
    {"id": "general",           "name": "#general",            "desc": "Company-wide announcements and general discussion"},
    {"id": "incidents",         "name": "#incidents",           "desc": "Active incident response and real-time coordination"},
    {"id": "operations",        "name": "#operations",          "desc": "Day-to-day ops — uptime, runbooks and shift handoffs"},
    {"id": "database",          "name": "#database",            "desc": "Database administration, queries and schema changes"},
    {"id": "development",       "name": "#development",         "desc": "Back-end and application development topics"},
    {"id": "deployments",       "name": "#deployments",         "desc": "Release announcements and CI/CD pipeline status"},
    {"id": "security",          "name": "#security",            "desc": "Security events, compliance checks and access changes"},
    {"id": "backups-dr",        "name": "#backups-dr",          "desc": "Backup status, restore tests and DR coordination"},
    {"id": "client-updates",    "name": "#client-updates",      "desc": "Client communications, SLA updates and account news"},
    {"id": "reports-analytics", "name": "#reports-analytics",   "desc": "Shared reports, dashboards and data insights"},
    {"id": "on-call",           "name": "#on-call",             "desc": "On-call handoffs, escalations and schedule changes"},
    {"id": "infrastructure",    "name": "#infrastructure",      "desc": "Cloud infrastructure, capacity planning and provisioning"},
]


def _load() -> dict:
    base = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in _DEFAULT.items()}
    if _STORE_PATH.exists():
        try:
            data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
            # Merge: add any new top-level keys introduced after the file was written
            for k, v in base.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return base


def _save(data: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def get() -> dict:
    """Return the in-memory store, loading from disk on first call."""
    if "store" not in st.session_state:
        st.session_state.store = _load()
    return st.session_state.store


def _flush() -> None:
    _save(get())


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def _thread_key(role_a: str, role_b: str) -> str:
    return "::".join(sorted([role_a, role_b]))


def send_message(from_role: str, to_role: str, text: str) -> None:
    s = get()
    key = _thread_key(from_role, to_role)
    s["messages"].setdefault(key, []).append({
        "id": str(uuid.uuid4())[:8],
        "from": from_role,
        "text": text,
        "ts": datetime.now().isoformat(timespec="seconds"),
    })
    _flush()


def get_thread(role_a: str, role_b: str) -> list:
    return get()["messages"].get(_thread_key(role_a, role_b), [])


def get_inbox(role: str) -> list:
    threads = []
    for key, msgs in get()["messages"].items():
        parts = key.split("::")
        if role in parts:
            other = parts[0] if parts[1] == role else parts[1]
            last = msgs[-1] if msgs else None
            threads.append({
                "other": other,
                "key": key,
                "last": last,
                "count": len(msgs),
            })
    return sorted(threads, key=lambda t: t["last"]["ts"] if t["last"] else "", reverse=True)


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

def create_ticket(title: str, description: str, priority: str,
                  created_by: str, assigned_to: str = "Unassigned") -> dict:
    s = get()
    ticket = {
        "id": f"TKT-{1000 + len(s['tickets']) + 1}",
        "title": title,
        "description": description,
        "priority": priority,
        "status": "Open",
        "created_by": created_by,
        "assigned_to": assigned_to,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "notes": [],
    }
    s["tickets"].append(ticket)
    _flush()
    return ticket


def update_ticket(ticket_id: str, **kwargs) -> None:
    s = get()
    for t in s["tickets"]:
        if t["id"] == ticket_id:
            t.update(kwargs)
            t["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _flush()


def add_note(ticket_id: str, author: str, note_text: str) -> None:
    s = get()
    for t in s["tickets"]:
        if t["id"] == ticket_id:
            t.setdefault("notes", []).append({
                "author": author,
                "text": note_text,
                "ts": datetime.now().isoformat(timespec="seconds"),
            })
            t["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _flush()


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Channels (public group messages)
# ---------------------------------------------------------------------------

def post_to_channel(role: str, channel_id: str, text: str, attachment: dict = None) -> None:
    s = get()
    msg = {
        "id": str(uuid.uuid4())[:8],
        "from": role,
        "text": text,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    if attachment:
        msg["attachment"] = attachment
    s["channels"].setdefault(channel_id, []).append(msg)
    _flush()


def get_channel_messages(channel_id: str) -> list:
    return get()["channels"].get(channel_id, [])


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Maintenance Windows
# ---------------------------------------------------------------------------

def create_maint_window(title: str, description: str, start: str, end: str,
                         affected_servers: list, owner: str,
                         change_type: str, created_by: str) -> dict:
    s = get()
    w = {
        "id": f"MW-{1000 + len(s['maint_windows']) + 1}",
        "title": title, "description": description,
        "start": start, "end": end,
        "affected_servers": affected_servers,
        "owner": owner, "change_type": change_type,
        "created_by": created_by, "status": "Scheduled",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    s["maint_windows"].append(w)
    _flush()
    return w


def update_maint_window(window_id: str, **kwargs) -> None:
    s = get()
    for w in s["maint_windows"]:
        if w["id"] == window_id:
            w.update(kwargs)
    _flush()


# ---------------------------------------------------------------------------
# UI/UX & Infrastructure Submissions
# ---------------------------------------------------------------------------

def submit_uiux(title: str, type_: str, description: str, priority: str,
                url: str, submitted_by: str, attachment: dict = None) -> dict:
    s = get()
    sub = {
        "id": f"SUB-{100 + len(s['uiux_submissions']) + 1}",
        "title": title, "type": type_, "description": description,
        "priority": priority, "url": url,
        "attachment": attachment,
        "submitted_by": submitted_by,
        "status": "Pending Review",
        "review_notes": "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    s["uiux_submissions"].append(sub)
    _flush()
    return sub


def update_uiux(submission_id: str, **kwargs) -> None:
    s = get()
    for sub in s["uiux_submissions"]:
        if sub["id"] == submission_id:
            sub.update(kwargs)
            sub["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _flush()


# ---------------------------------------------------------------------------
# Bug Tracker
# ---------------------------------------------------------------------------

def create_bug(title: str, description: str, url: str, priority: str,
               category: str, reporter: str) -> dict:
    s = get()
    b = {
        "id": f"BUG-{100 + len(s['bugs']) + 1}",
        "title": title, "description": description, "url": url,
        "priority": priority, "category": category,
        "reporter": reporter, "assignee": "Unassigned",
        "status": "Open", "notes": [],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    s["bugs"].append(b)
    _flush()
    return b


def update_bug(bug_id: str, **kwargs) -> None:
    s = get()
    for b in s["bugs"]:
        if b["id"] == bug_id:
            b.update(kwargs)
            b["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _flush()


# ---------------------------------------------------------------------------
# Website Projects
# ---------------------------------------------------------------------------

def create_web_project(name: str, client_name: str, description: str,
                        tech_stack: list, priority: str,
                        due_date: str, created_by: str) -> dict:
    s = get()
    p = {
        "id": f"WP-{100 + len(s['web_projects']) + 1}",
        "name": name, "client": client_name,
        "description": description, "tech_stack": tech_stack,
        "priority": priority, "due_date": due_date,
        "created_by": created_by, "status": "In Progress",
        "progress": 0, "tasks": [],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    s["web_projects"].append(p)
    _flush()
    return p


def update_web_project(project_id: str, **kwargs) -> None:
    s = get()
    for p in s["web_projects"]:
        if p["id"] == project_id:
            p.update(kwargs)
    _flush()


# ---------------------------------------------------------------------------
# Workflow Documents
# ---------------------------------------------------------------------------

def add_document(title: str, category: str, content: str,
                  tags: str, author: str) -> dict:
    s = get()
    d = {
        "id": f"DOC-{100 + len(s['documents']) + 1}",
        "title": title, "category": category,
        "content": content, "tags": tags,
        "author": author, "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    s["documents"].append(d)
    _flush()
    return d


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------

def send_email(to: str, subject: str, body: str, sender_role: str) -> None:
    # TODO: Replace simulation with real SMTP / SendGrid:
    #   import os, sendgrid
    #   from sendgrid.helpers.mail import Mail
    #   sg = sendgrid.SendGridAPIClient(api_key=os.environ["SENDGRID_API_KEY"])
    #   msg = Mail(from_email="ops@caspira.com", to_emails=to, subject=subject, html_content=body)
    #   sg.send(msg)
    s = get()
    s["emails"].append({
        "id": str(uuid.uuid4())[:8],
        "from_role": sender_role,
        "to": to,
        "subject": subject,
        "body": body,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "status": "Sent (simulated)",
    })
    _flush()
