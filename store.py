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
    "messages": {},
    "tickets": [],
    "emails": [],
}


def _load() -> dict:
    if _STORE_PATH.exists():
        try:
            return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in _DEFAULT.items()}


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
