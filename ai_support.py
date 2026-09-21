"""AI simulation for Channels and Direct Messages, backed by OpenRouter free models.

When someone sends a message, an AI replies in character after ~10 seconds. The reply is
generated and posted from a background thread so the UI never blocks; the existing
2-second message pollers pick it up.

  Channels  → "Customers": a client of the company who asks the team questions, always in
              Mandarin Chinese, so the team can practise serving customers.
  DMs       → the DM partner's role answers as a coworker, in the language it was written in.

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
from datetime import date, datetime

import httpx
import streamlit as st

import store

REPLY_DELAY_S = (8, 12)          # "about 10 seconds"
CUSTOMER_NAME = "Customers"      # sender name shown for the simulated customer in channels

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


# ── prompts ──────────────────────────────────────────────────────────────────

def _customer_prompt(sender: str, where: str) -> str:
    return (
        "You are a customer — a staff member at a client company that pays Caspira for managed database "
        "monitoring (uptime, backups, performance, alerts, maintenance, security, reports, billing). "
        f"You are chatting with Caspira's support team in {where}. "
        + (f'The person answering you is their "{sender}". ' if sender else "Whoever is on duty will answer you. ")
        + "Play the customer realistically so the team can practise serving customers.\n\n"
        "Rules:\n"
        "- LANGUAGE: always write in Mandarin Chinese, whatever language the team member uses — the team "
        "cannot read English. Write Simplified Chinese (简体中文) by default; only if the team member writes in "
        "Traditional characters, switch to Traditional. "
        "Keep common terms such as DB, SLA, backup as-is. Natural, everyday business Chinese.\n"
        "- 1–3 short sentences, like a chat message. No markdown, no lists, no emojis, no sign-off.\n"
        "- You ask a lot of questions. Most of your messages should contain a new, concrete question or "
        "request (e.g. why the system was slow this morning, when the last backup ran, whether data can be "
        "restored, when maintenance happens, how an invoice or SLA works, how to add a new database, who to "
        "call in an emergency). Sometimes report a problem or sound worried or impatient.\n"
        "- React to what the team member just said (thank them, doubt them, or ask a follow-up) before or "
        "while asking the next thing. If they greet you, introduce your concern with a question.\n"
        "- Do not repeat questions already asked in the conversation; move on to new topics. You are not a "
        "technical expert and don't know Caspira's internal details.\n"
        "- Never say you are an AI, a model or a simulation.\n"
        "- Output only the message text — no name prefix."
    )


def _system_prompt(persona: str, sender: str, where: str) -> str:
    if persona == CUSTOMER_NAME:
        return _customer_prompt(sender, where)
    return (
        f'You are the "{persona}" on a small managed-services team at Caspira, which runs and monitors '
        f"database servers for client companies. In your role you {_ROLE_DESC.get(persona, 'support the team')}.\n"
        f"You are chatting on the internal team messenger ({where}) with your colleague, the "
        f'"{sender}". Reply to their latest message as a real coworker would.\n\n'
        "Rules:\n"
        "- LANGUAGE: reply in the same language as their latest message. English message → English reply; "
        "Chinese (Mandarin) message → Mandarin reply, in the same script they used (Simplified or Traditional). "
        "Follow the latest message only, even if earlier messages were in another language. Keep common "
        "technical terms (DB, SLA, CI/CD, backup) as-is. In Chinese, sound like a natural coworker, not a translation.\n"
        "- Stay in character as the "
        f"{persona}. Never say you are an AI, a model or a simulation.\n"
        "- 1–2 short sentences, casual workplace tone, written like a chat message. No greeting ritual, "
        "no sign-off, no lists, no markdown, no emojis.\n"
        "- Answer what was asked with a plausible, specific update from your own line of work "
        '(e.g. "on plan — I\'m on the 3rd phase now", "backups finished clean overnight, verifying restores today"). '
        "Keep it consistent with earlier messages in the conversation.\n"
        "- If asked something outside your role, say which colleague would know. The only roles on the team are: "
        f"{', '.join(ALL_ROLES)}. Never refer to any other role or department.\n"
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
    text = re.sub(rf"^\s*\**(?:{re.escape(persona)}|客户|顧客|顾客)\**\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("`", "").strip().strip('"“”')
    if len(text) > _MAX_REPLY_CHARS:
        cut = text[:_MAX_REPLY_CHARS]
        ends = list(re.finditer(r"[。！？]|[.!?](?=\s)", cut))     # English and Chinese sentence ends
        text = cut[:ends[-1].end()] if ends else cut.rstrip() + "…"
    return html.escape(text)


# Some free models write their reasoning / a paraphrase of the instructions into the reply
# ("We need to respond as the customer... no markdown ..."). Never post that.
_LEAK = re.compile(
    r"\b(we|i) (need|must|should|have) to (respond|reply|answer|write|output)\b[^.\n]{0,60}"
    r"\b(as (the|a)|in (chinese|mandarin|english)|customer|user|persona)\b"
    r"|\bno markdown\b|\bsign-?off\b|\bshort sentences\b|\bno emojis?\b|\bno name prefix\b|\bin character\b"
    r"|\bthe (user|customer|team member|colleague) (says|said|wants|asks|asked|is asking|just said|wrote)\b"
    r"|\bsystem prompt\b|\bpersona\b"
    r"|^\s*(let me think|let's (think|see|craft|draft|respond)|first, (we|i))\b",
    re.IGNORECASE,
)
_CJK = re.compile(r"[㐀-鿿]")


def _is_usable(text: str, persona: str) -> bool:
    """False for leaked reasoning, or for a customer reply that isn't Chinese."""
    if _LEAK.search(text):
        return False
    if persona == CUSTOMER_NAME:
        letters = re.sub(r"[\s\W\d_]+", "", text)
        if len(_CJK.findall(text)) < max(4, int(0.5 * len(letters))):
            return False
    return True


def _generate(persona: str, messages: list, key: str, models: list):
    deadline = time.monotonic() + _TOTAL_BUDGET_S
    for model in models:
        remaining = deadline - time.monotonic()
        if remaining < 5:
            break
        text, fatal = _call(model, messages, key, min(_PER_MODEL_TIMEOUT_S, remaining))
        if fatal:
            break
        if text and _is_usable(text, persona):
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
        persona = CUSTOMER_NAME
        ch = next((c for c in store.CHANNELS if c["id"] == target), None)
        where = f"the {ch['name']} channel ({ch['desc']})" if ch else "a support channel"

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


# ── customers who speak first ────────────────────────────────────────────────
# A background loop (one per server process) posts a new customer question into the customer
# channels when the conversation has gone quiet. Guards keep it cheap and non-spammy:
#   • only while someone has the Channels page open (touch() is called by its 2-second poller)
#   • never while the last message is an unanswered customer question
#   • a random quiet gap between questions, and a daily cap (free OpenRouter keys allow ~50 requests/day)

CUSTOMER_CHANNELS = ["client-updates"]
_QUIET_GAP_S = (180, 360)        # how long a conversation must be quiet before a new question
_DAILY_CAP = 15                  # new customer questions per day (follow-up replies are extra)
_PRESENCE_S = 120                # "someone is watching" window after the last touch()
_LOOP_TICK_S = 15


def _opener_messages(where: str, history: list) -> list:
    msgs = [{"role": "system", "content": _customer_prompt("", where)}]
    for h in history[-_HISTORY_TURNS:]:
        body = (h.get("text") or "").strip()
        if not body:
            continue
        who = h.get("from", "")
        msgs.append({
            "role": "assistant" if who == CUSTOMER_NAME else "user",
            "content": body if who == CUSTOMER_NAME else f"{who}: {body}",
        })
    msgs.append({
        "role": "user",
        "content": "[Start a new question now: write the customer's next message to the support team. "
                   "Choose a topic that has not come up yet in this conversation.]",
    })
    return msgs


def _idle_seconds(msgs: list) -> float:
    if not msgs:
        return float("inf")
    try:
        return (datetime.now() - datetime.fromisoformat(msgs[-1]["ts"])).total_seconds()
    except (ValueError, TypeError, KeyError):
        return 0.0


def _customer_loop(state: dict, key: str, models: list, channels: list, cap: int) -> None:
    while True:
        time.sleep(_LOOP_TICK_S)
        try:
            if time.time() - state["last_seen"] > _PRESENCE_S:
                continue                                    # nobody is on the Channels page
            today = date.today().isoformat()
            if state["day"] != today:
                state["day"], state["count"] = today, 0
            if state["count"] >= cap:
                continue
            for ch_id in channels:
                msgs = store.bg_recent_channel_messages(ch_id, 12)
                if msgs and msgs[-1]["from"] == CUSTOMER_NAME:
                    continue                                # a question is still waiting for an answer
                if _idle_seconds(msgs) < state["gap"]:
                    continue
                ch = next((c for c in store.CHANNELS if c["id"] == ch_id), None)
                where = f"the {ch['name']} channel ({ch['desc']})" if ch else "a support channel"
                reply = _generate(CUSTOMER_NAME, _opener_messages(where, msgs), key, models)
                if reply:
                    store.bg_post_channel(CUSTOMER_NAME, ch_id, reply)
                    state["count"] += 1
                    state["gap"] = random.uniform(*_QUIET_GAP_S)
                    break                                   # one new question per tick
        except Exception:
            pass                                            # never let the loop die


@st.cache_resource
def _customer_state() -> dict:
    """Runs once per server process: resolve config on the Streamlit thread, start the loop."""
    key = (_secret("OPENROUTER_API_KEY") or "").strip()
    state = {"last_seen": 0.0, "day": "", "count": 0, "gap": random.uniform(*_QUIET_GAP_S)}
    if key:
        channels = list(_secret("CUSTOMER_CHANNELS") or CUSTOMER_CHANNELS)
        cap = int(_secret("CUSTOMER_DAILY_CAP") or _DAILY_CAP)
        threading.Thread(
            target=_customer_loop, args=(state, key, _model_chain(), channels, cap),
            name="ai-customer-loop", daemon=True,
        ).start()
    return state


def touch() -> None:
    """Call from the Channels page's poller: marks that someone is watching and, on the first
    call in a server process, starts the loop that lets customers open conversations."""
    _customer_state()["last_seen"] = time.time()
