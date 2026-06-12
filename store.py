"""Supabase-backed persistence — same public API as the JSON store.

get_channel_messages / get_thread / get_inbox always hit Supabase directly
so messages appear for all users in real time. Everything else is
session-state cached (refreshed on first page load per browser tab).
"""
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import streamlit as st
from supabase import create_client, Client

# ── credentials ──────────────────────────────────────────────────────────────
_SUPABASE_URL = "https://hsvmlcibtgthvrfscehl.supabase.co"
_SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imhzdm1sY2lidGd0aHZyZnNjZWhsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA5OTQwODksImV4cCI6MjA5NjU3MDA4OX0"
    ".gpmcWnh96rkiG_zxT5J5d289wT80jSXtlEoeuUfFubw"
)

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

# ── Supabase client ───────────────────────────────────────────────────────────

def _sb() -> Client:
    if "sb_client" not in st.session_state:
        st.session_state.sb_client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    return st.session_state.sb_client


# ── column-name translators (DB → Python dict) ───────────────────────────────

def _norm_msg(row: dict) -> dict:
    r = dict(row)
    r["from"] = r.pop("from_role", r.get("from", ""))
    return r

def _norm_email(row: dict) -> dict:
    r = dict(row)
    r["to"] = r.pop("to_addr", r.get("to", ""))
    return r

def _norm_window(row: dict) -> dict:
    r = dict(row)
    r["start"] = r.pop("start_time", r.get("start", ""))
    r["end"]   = r.pop("end_time",   r.get("end", ""))
    return r

def _norm_backup(row: dict) -> dict:
    r = dict(row)
    r["timestamp"] = r.pop("ts", r.get("timestamp", ""))
    return r


# ── session-state cache ───────────────────────────────────────────────────────

_DEFAULT: dict = {
    "messages":         {},
    "tickets":          [],
    "emails":           [],
    "channels":         {},
    "maint_windows":    [],
    "uiux_submissions": [],
    "bugs":             [],
    "web_projects":     [],
    "documents":        [],
    "backup_records":   [],
}


def _fetch_all() -> dict:
    """Pull all non-realtime tables from Supabase in parallel."""
    base = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in _DEFAULT.items()}

    def _q(table, normalizer=None):
        try:
            c = create_client(_SUPABASE_URL, _SUPABASE_KEY)
            res = c.table(table).select("*").execute()
            data = res.data or []
            return [normalizer(r) for r in data] if normalizer else data
        except Exception:
            return []

    configs = [
        ("tickets",          None),
        ("emails",           _norm_email),
        ("maint_windows",    _norm_window),
        ("uiux_submissions", None),
        ("bugs",             None),
        ("web_projects",     None),
        ("documents",        None),
        ("backup_records",   _norm_backup),
    ]

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_q, tbl, norm): tbl for tbl, norm in configs}
        for fut in as_completed(futures):
            base[futures[fut]] = fut.result()

    return base


def get() -> dict:
    """Return the in-memory store, loading from Supabase on first call per session."""
    if "store" not in st.session_state:
        st.session_state.store = _fetch_all()
    return st.session_state.store


# ── Messages (DMs) ────────────────────────────────────────────────────────────

def _thread_key(role_a: str, role_b: str) -> str:
    return "::".join(sorted([role_a, role_b]))


def send_message(from_role: str, to_role: str, text: str) -> None:
    key = _thread_key(from_role, to_role)
    try:
        _sb().table("messages").insert({
            "id": str(uuid.uuid4())[:8],
            "thread_key": key,
            "from_role": from_role,
            "text": text,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }).execute()
    except Exception as e:
        st.error(f"Send failed: {e}")


def get_thread(role_a: str, role_b: str) -> list:
    key = _thread_key(role_a, role_b)
    try:
        res = _sb().table("messages").select("*").eq("thread_key", key).order("ts").execute()
        return [_norm_msg(r) for r in (res.data or [])]
    except Exception as e:
        st.warning(f"⚠ DM read error: {e}")
        return []


def get_inbox(role: str) -> list:
    try:
        res = (
            _sb().table("messages")
            .select("*")
            .or_(f"thread_key.like.{role}::%,thread_key.like.%::{role}")
            .order("ts")
            .execute()
        )
    except Exception:
        return []

    threads: dict = {}
    for r in res.data or []:
        key = r["thread_key"]
        parts = key.split("::")
        if role not in parts:
            continue
        other = parts[0] if parts[1] == role else parts[1]
        msg = {"from": r["from_role"], "text": r["text"], "ts": r["ts"]}
        if key not in threads:
            threads[key] = {"other": other, "key": key, "last": msg, "count": 0}
        threads[key]["last"] = msg
        threads[key]["count"] += 1
    return sorted(threads.values(), key=lambda t: t["last"]["ts"] if t["last"] else "", reverse=True)


# ── Tickets ───────────────────────────────────────────────────────────────────

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
    try:
        _sb().table("tickets").insert(ticket).execute()
    except Exception as e:
        st.error(f"Ticket save failed: {e}")
    s["tickets"].append(ticket)
    return ticket


def update_ticket(ticket_id: str, **kwargs) -> None:
    s = get()
    kwargs["updated_at"] = datetime.now().isoformat(timespec="seconds")
    try:
        _sb().table("tickets").update(kwargs).eq("id", ticket_id).execute()
    except Exception:
        pass
    for t in s["tickets"]:
        if t["id"] == ticket_id:
            t.update(kwargs)


def add_note(ticket_id: str, author: str, note_text: str) -> None:
    sb = _sb()
    s = get()
    try:
        res = sb.table("tickets").select("notes").eq("id", ticket_id).execute()
        notes = (res.data[0].get("notes") or []) if res.data else []
    except Exception:
        notes = []
    new_note = {"author": author, "text": note_text, "ts": datetime.now().isoformat(timespec="seconds")}
    notes.append(new_note)
    now = datetime.now().isoformat(timespec="seconds")
    try:
        sb.table("tickets").update({"notes": notes, "updated_at": now}).eq("id", ticket_id).execute()
    except Exception:
        pass
    for t in s["tickets"]:
        if t["id"] == ticket_id:
            t.setdefault("notes", []).append(new_note)
            t["updated_at"] = now


# ── Channels (public group messages) ─────────────────────────────────────────

def post_to_channel(role: str, channel_id: str, text: str, attachment: dict = None) -> None:
    try:
        _sb().table("channel_messages").insert({
            "id": str(uuid.uuid4())[:8],
            "channel_id": channel_id,
            "from_role": role,
            "text": text,
            "attachment": attachment,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }).execute()
    except Exception as e:
        st.error(f"Post failed: {e}")


def clear_channel(channel_id: str) -> None:
    try:
        _sb().table("channel_messages").delete().eq("channel_id", channel_id).execute()
    except Exception as e:
        st.error(f"Clear failed: {e}")


def get_channel_messages(channel_id: str) -> list:
    try:
        res = _sb().table("channel_messages").select("*").eq("channel_id", channel_id).order("ts").execute()
        return [_norm_msg(r) for r in (res.data or [])]
    except Exception as e:
        st.warning(f"⚠ Channel read error: {e}")
        return []


def get_channel_summaries() -> dict:
    """One query → {channel_id: [msgs_asc]} for all channels — use in sidebar instead of 12 queries."""
    try:
        res = (
            _sb()
            .table("channel_messages")
            .select("channel_id, from_role, text, ts")
            .order("ts", desc=True)
            .limit(500)
            .execute()
        )
        grouped: dict = {}
        for row in (res.data or []):
            cid = row.get("channel_id", "")
            if cid not in grouped:
                grouped[cid] = []
            grouped[cid].append(row)
        return {cid: list(reversed(msgs)) for cid, msgs in grouped.items()}
    except Exception:
        return {}


# ── Maintenance Windows ───────────────────────────────────────────────────────

def create_maint_window(title: str, description: str, start: str, end: str,
                         affected_servers: list, owner: str,
                         change_type: str, created_by: str) -> dict:
    s = get()
    db_row = {
        "id": f"MW-{1000 + len(s['maint_windows']) + 1}",
        "title": title, "description": description,
        "start_time": start, "end_time": end,
        "affected_servers": affected_servers,
        "owner": owner, "change_type": change_type,
        "created_by": created_by, "status": "Scheduled",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        _sb().table("maint_windows").insert(db_row).execute()
    except Exception as e:
        st.error(f"Maint window save failed: {e}")
    py_w = {**db_row, "start": start, "end": end}
    del py_w["start_time"]
    del py_w["end_time"]
    s["maint_windows"].append(py_w)
    return py_w


def update_maint_window(window_id: str, **kwargs) -> None:
    s = get()
    try:
        _sb().table("maint_windows").update(kwargs).eq("id", window_id).execute()
    except Exception:
        pass
    for w in s["maint_windows"]:
        if w["id"] == window_id:
            w.update(kwargs)


# ── UI/UX & Infrastructure Submissions ───────────────────────────────────────

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
    try:
        _sb().table("uiux_submissions").insert(sub).execute()
    except Exception as e:
        st.error(f"Submission save failed: {e}")
    s["uiux_submissions"].append(sub)
    return sub


def update_uiux(submission_id: str, **kwargs) -> None:
    s = get()
    kwargs["updated_at"] = datetime.now().isoformat(timespec="seconds")
    try:
        _sb().table("uiux_submissions").update(kwargs).eq("id", submission_id).execute()
    except Exception:
        pass
    for sub in s["uiux_submissions"]:
        if sub["id"] == submission_id:
            sub.update(kwargs)


# ── Bug Tracker ───────────────────────────────────────────────────────────────

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
    try:
        _sb().table("bugs").insert(b).execute()
    except Exception as e:
        st.error(f"Bug save failed: {e}")
    s["bugs"].append(b)
    return b


def update_bug(bug_id: str, **kwargs) -> None:
    s = get()
    kwargs["updated_at"] = datetime.now().isoformat(timespec="seconds")
    try:
        _sb().table("bugs").update(kwargs).eq("id", bug_id).execute()
    except Exception:
        pass
    for b in s["bugs"]:
        if b["id"] == bug_id:
            b.update(kwargs)


# ── Website Projects ──────────────────────────────────────────────────────────

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
    try:
        _sb().table("web_projects").insert(p).execute()
    except Exception as e:
        st.error(f"Project save failed: {e}")
    s["web_projects"].append(p)
    return p


def update_web_project(project_id: str, **kwargs) -> None:
    s = get()
    try:
        _sb().table("web_projects").update(kwargs).eq("id", project_id).execute()
    except Exception:
        pass
    for p in s["web_projects"]:
        if p["id"] == project_id:
            p.update(kwargs)


def add_project_task(project_id: str, task_name: str) -> None:
    sb = _sb()
    s = get()
    try:
        res = sb.table("web_projects").select("tasks").eq("id", project_id).execute()
        tasks = (res.data[0].get("tasks") or []) if res.data else []
    except Exception:
        tasks = []
    new_task = {"name": task_name, "status": "todo", "created_at": datetime.now().isoformat(timespec="seconds")}
    tasks.append(new_task)
    try:
        sb.table("web_projects").update({"tasks": tasks}).eq("id", project_id).execute()
    except Exception:
        pass
    for p in s["web_projects"]:
        if p["id"] == project_id:
            p.setdefault("tasks", []).append(new_task)


def update_task_status(project_id: str, task_idx: int, new_status: str) -> None:
    sb = _sb()
    s = get()
    try:
        res = sb.table("web_projects").select("tasks").eq("id", project_id).execute()
        tasks = (res.data[0].get("tasks") or []) if res.data else []
    except Exception:
        tasks = []
    if 0 <= task_idx < len(tasks):
        tasks[task_idx]["status"] = new_status
    try:
        sb.table("web_projects").update({"tasks": tasks}).eq("id", project_id).execute()
    except Exception:
        pass
    for p in s["web_projects"]:
        if p["id"] == project_id:
            ptasks = p.get("tasks", [])
            if 0 <= task_idx < len(ptasks):
                ptasks[task_idx]["status"] = new_status


def add_backup_record(server: str, type_: str, result: str,
                       duration_min: int, size_gb: float,
                       destination: str = "s3://backups", verified_by: str = "system") -> dict:
    s = get()
    db_row = {
        "id": f"BK-{1000 + len(s['backup_records']) + 1}",
        "server": server, "type": type_, "result": result,
        "duration_min": duration_min, "size_gb": size_gb,
        "destination": destination, "verified_by": verified_by,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "notes": "",
    }
    try:
        _sb().table("backup_records").insert(db_row).execute()
    except Exception as e:
        st.error(f"Backup record save failed: {e}")
    py_rec = {**db_row, "timestamp": db_row["ts"]}
    del py_rec["ts"]
    s["backup_records"].append(py_rec)
    return py_rec


# ── Workflow Documents ────────────────────────────────────────────────────────

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
    try:
        _sb().table("documents").insert(d).execute()
    except Exception as e:
        st.error(f"Document save failed: {e}")
    s["documents"].append(d)
    return d


# ── Emails ────────────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body: str, sender_role: str) -> None:
    s = get()
    db_row = {
        "id": str(uuid.uuid4())[:8],
        "from_role": sender_role,
        "to_addr": to,
        "subject": subject,
        "body": body,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "status": "Sent (simulated)",
    }
    try:
        _sb().table("emails").insert(db_row).execute()
    except Exception as e:
        st.error(f"Email save failed: {e}")
    py_email = {**db_row, "to": to}
    del py_email["to_addr"]
    s["emails"].append(py_email)
