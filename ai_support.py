"""AI teammates for Channels and Direct Messages, backed by OpenRouter free models.

When someone sends a message, an AI plays one of the other team roles and replies in
character after ~10 seconds:

    Data Operation Specialist: How's the work going?
    Back-end Developer:        Stable and on plan — I'm on the 3rd phase now.

The reply is generated and posted from a background thread so the UI never blocks; the
existing 2-second message pollers pick it up. In a DM the partner role replies. In a
channel the reply comes from the role @mentioned in the message, otherwise a role that
fits the channel's topic.

Models are tried in order — PRIMARY_MODELS (the three main ones) then FALLBACK_MODELS —
because free models are often rate-limited (429) or overloaded. The API key is read from
st.secrets["OPENROUTER_API_KEY"] (.streamlit/secrets.toml) or the OPENROUTER_API_KEY
environment variable. OPENROUTER_PRIMARY_MODELS / OPENROUTER_FALLBACK_MODELS (TOML arrays)
override the lists, since OpenRouter retires free model IDs regularly.
"""
import html
import os
import random
import re
import threading
import time

import httpx
import streamlit as st

import store

REPLY_DELAY_S = (8, 12)          # "about 10 seconds"

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_PER_MODEL_TIMEOUT_S = 25
_TOTAL_BUDGET_S = 60
_HISTORY_TURNS = 8
_MAX_TOKENS = 600                # headroom: reasoning models spend part of this on hidden thinking
_MAX_REPLY_CHARS = 450

# Three main models, then progressively broader fallbacks. "openrouter/free" is last:
# it auto-routes to whichever free model is currently available.
PRIMARY_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "poolside/laguna-s-2.1:free",
]
FALLBACK_MODELS = [
    "google/gemma-4-31b-it:free",
    "qwen/qwen3.8-27b:free",
    "z-ai/glm-5.2:free",
    "google/gemma-4-26b-a4b-it:free",
    "openrouter/free",
]

ALL_ROLES = [
    "General Manager", "Monitoring", "Data Operation Specialist",
    "I.T Assistant", "Back-end Developer", "Dev-Ops",
    "Infrastructure Engineer", "Customer Service", "Data Analyst",
]

_ROLE_DESC = {
    "General Manager": "oversees delivery, SLAs, client relationships and budgets; cares about status, risks and deadlines",
    "Monitoring": "watches alerts and incidents around the clock, triages them and runs the on-call rotation",
    "Data Operation Specialist": "looks after database performance, backups, maintenance windows and health checks",
    "I.T Assistant": "runs the help desk: tickets, the server status board, runbooks and routine emails",
    "Back-end Developer": "writes queries and services, works on schemas, APIs and service health",
    "Dev-Ops": "handles deployments, the CI/CD pipeline and configuration drift",
    "Infrastructure Engineer": "owns the server fleet, capacity planning, disaster recovery and security/compliance",
    "Customer Service": "talks to clients: their tickets, service status and SLA updates",
    "Data Analyst": "builds analytics, reports and data exports for the team and clients",
}

# Which roles plausibly chime in on each channel (the sender is always excluded).
_CHANNEL_ROLES = {
    "general":           ALL_ROLES,
    "incidents":         ["Monitoring", "I.T Assistant", "Dev-Ops", "Infrastructure Engineer", "Data Operation Specialist"],
    "operations":        ["Monitoring", "Data Operation Specialist", "I.T Assistant", "Infrastructure Engineer"],
    "database":          ["Data Operation Specialist", "Back-end Developer", "Data Analyst"],
    "development":       ["Back-end Developer", "Dev-Ops"],
    "deployments":       ["Dev-Ops", "Back-end Developer", "Monitoring"],
    "security":          ["Infrastructure Engineer", "I.T Assistant", "Dev-Ops"],
    "backups-dr":        ["Data Operation Specialist", "Infrastructure Engineer", "Monitoring"],
    "client-updates":    ["Customer Service", "General Manager", "Monitoring"],
    "reports-analytics": ["Data Analyst", "General Manager", "Data Operation Specialist"],
    "on-call":           ["Monitoring", "Dev-Ops", "I.T Assistant", "Infrastructure Engineer"],
    "infrastructure":    ["Infrastructure Engineer", "Dev-Ops", "Data Operation Specialist"],
}


# ── configuration (resolved on the main thread, passed into the worker) ──────

def _secret(name: str, default=None):
    """st.secrets raises if no secrets file exists, so guard the lookup."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


def _model_chain() -> list:
    primary = list(_secret("OPENROUTER_PRIMARY_MODELS") or PRIMARY_MODELS)
    fallback = list(_secret("OPENROUTER_FALLBACK_MODELS") or FALLBACK_MODELS)
    seen, chain = set(), []
    for m in primary + fallback:
        if m not in seen:
            seen.add(m)
            chain.append(m)
    return chain


# ── who replies ──────────────────────────────────────────────────────────────

def _pick_channel_persona(channel_id: str, sender: str, text: str) -> str:
    lowered = text.lower()
    for role in ALL_ROLES:                                   # explicit "@Dev-Ops ..." wins
        if role != sender and f"@{role.lower()}" in lowered:
            return role
    pool = [r for r in _CHANNEL_ROLES.get(channel_id, ALL_ROLES) if r != sender]
    return random.choice(pool or [r for r in ALL_ROLES if r != sender])


# ── prompt ───────────────────────────────────────────────────────────────────

def _system_prompt(persona: str, sender: str, where: str) -> str:
    return (
        f'You are the "{persona}" on a small managed-services team at Caspira, which runs and monitors '
        f"database servers for client companies. In your role you {_ROLE_DESC.get(persona, 'support the team')}.\n"
        f"You are chatting on the internal team messenger ({where}) with your colleague, the "
        f'"{sender}". Reply to their latest message as a real coworker would.\n\n'
        "Rules:\n"
        "- Stay in character as the "
        f"{persona}. Never say you are an AI, a model or a simulation.\n"
        "- 1–2 short sentences, casual workplace tone, written like a chat message. No greeting ritual, "
        "no sign-off, no lists, no markdown, no emojis.\n"
        "- Answer what was asked with a plausible, specific update from your own line of work "
        '(e.g. "on plan — I\'m on the 3rd phase now", "backups finished clean overnight, verifying restores today"). '
        "Keep it consistent with earlier messages in the conversation.\n"
        "- If asked something outside your role, say who on the team would know.\n"
        "- Output only the message text — no name prefix."
    )


def _build_messages(persona: str, sender: str, where: str, history: list, text: str) -> list:
    msgs = [{"role": "system", "content": _system_prompt(persona, sender, where)}]
    for h in history[-_HISTORY_TURNS:]:
        body = (h.get("text") or "").strip()
        if not body:
            continue
        who = h.get("from", "")
        msgs.append({
            "role": "assistant" if who == persona else "user",
            "content": body if who == persona else f"{who}: {body}",
        })
    msgs.append({"role": "user", "content": f"{sender}: {text}"})
    return msgs


# ── model call ───────────────────────────────────────────────────────────────

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _call(model: str, messages: list, key: str, timeout: float):
    """One attempt. Returns (text | None, fatal). fatal=True means stop trying (bad key)."""
    try:
        r = httpx.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "X-Title": "Caspira Console Team Chat",
            },
            json={"model": model, "messages": messages, "max_tokens": _MAX_TOKENS, "temperature": 0.8},
            timeout=timeout,
        )
    except httpx.HTTPError:
        return None, False                       # timeout / network → next model
    if r.status_code in (401, 403):
        return None, True
    if r.status_code != 200:
        return None, False                       # 429 / 5xx / 402 / 404 → next model
    try:
        text = r.json()["choices"][0]["message"].get("content") or ""
    except (ValueError, KeyError, IndexError, TypeError):
        return None, False
    return (_THINK.sub("", text).strip() or None), False   # empty (all tokens spent thinking) → next model


def _clean(text: str, persona: str) -> str:
    """Strip name prefixes / markdown / quotes, cap length, then HTML-escape — the chat feed
    renders message text as raw HTML."""
    text = re.sub(rf"^\s*\**{re.escape(persona)}\**\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("`", "").strip().strip('"“”')
    if len(text) > _MAX_REPLY_CHARS:
        cut = text[:_MAX_REPLY_CHARS]
        text = (cut.rsplit(". ", 1)[0] + ".") if ". " in cut else cut.rstrip() + "…"
    return html.escape(text)


def _generate(persona: str, messages: list, key: str, models: list):
    deadline = time.monotonic() + _TOTAL_BUDGET_S
    for model in models:
        remaining = deadline - time.monotonic()
        if remaining < 5:
            break
        text, fatal = _call(model, messages, key, min(_PER_MODEL_TIMEOUT_S, remaining))
        if fatal:
            break
        if text:
            reply = _clean(text, persona)
            if reply:
                return reply
    return None


# ── public entry point ───────────────────────────────────────────────────────

def schedule_reply(kind: str, target: str, sender: str, text: str, history: list) -> None:
    """Have an AI teammate answer `text` ~10 seconds from now, without blocking the UI.

    kind    "channel" (target = channel id) or "dm" (target = the partner role, who replies)
    sender  the role that just sent the message
    history messages before this one (dicts with "from" and "text"), oldest first
    Silently does nothing if no API key is configured or every model fails.
    """
    key = (_secret("OPENROUTER_API_KEY") or "").strip()
    if not key or not text.strip():
        return
    models = _model_chain()

    if kind == "dm":
        persona, where = target, f"a direct message with the {sender}"
        if persona == sender:
            return
    else:
        persona = _pick_channel_persona(target, sender, text)
        ch = next((c for c in store.CHANNELS if c["id"] == target), None)
        where = f"the {ch['name']} channel — {ch['desc']}" if ch else "a team channel"

    messages = _build_messages(persona, sender, where, history, text)
    delay = random.uniform(*REPLY_DELAY_S)

    def _worker() -> None:
        try:
            started = time.monotonic()
            reply = _generate(persona, messages, key, models)
            if not reply:
                return
            # The delay includes model latency: wait out whatever is left of it.
            time.sleep(max(0.0, delay - (time.monotonic() - started)))
            if kind == "dm":
                store.bg_send_dm(persona, sender, reply)
            else:
                store.bg_post_channel(persona, target, reply)
        except Exception:
            pass                                  # a failed AI reply must never affect the app

    threading.Thread(target=_worker, name="ai-teammate-reply", daemon=True).start()
