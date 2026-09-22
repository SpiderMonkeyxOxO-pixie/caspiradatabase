"""AI simulation for Channels and Direct Messages, backed by OpenRouter free models.

When someone sends a message, an AI replies in character after ~10 seconds. The reply is
generated and posted from a background thread so the UI never blocks; the existing
2-second message pollers pick it up.

  Customer conversations (one per client account, opened via the company chips) → a customer of
              that company (shown as e.g. "Autofix Customer Tan Wei Ming") who raises specific
              concerns about their own servers, always in Mandarin Chinese.
  #client-updates → a shared customer queue: a customer of ANY company (never a teammate), so a
              real staff member's name is never impersonated there.
  Other team channels → a teammate from staff.py answers as a coworker, in the language it was
              written in (English → English, Chinese → Chinese) — only one who is not signed in.
  DMs       → the DM partner answers the same way, only if nobody is signed in as them.

Models are tried in order because free models are often rate-limited (429) or overloaded:
the 3 PRIMARY_MODELS, then the curated FALLBACK_MODELS, then every other free chat model
OpenRouter lists (fetched live and cached for 6 hours — see _discover_free_models), and finally
"openrouter/free". The first usable reply wins. If OpenRouter says the account's daily free
allowance is used up, the chain stops at once (that limit is shared by all free models).

The API key is read from st.secrets["OPENROUTER_API_KEY"] (.streamlit/secrets.toml) or the
OPENROUTER_API_KEY environment variable. OPENROUTER_PRIMARY_MODELS / OPENROUTER_FALLBACK_MODELS
(TOML arrays) override the lists; setting the fallbacks also switches the live discovery off.
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

import staff
import store
import telemetry as tm

REPLY_DELAY_S = (8, 12)          # "about 10 seconds"
CUSTOMER_NAME = "Customers"      # sender name shown for the simulated customer in channels

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_PER_MODEL_TIMEOUT_S = 20        # a model that hasn't answered by now is skipped
_TOTAL_BUDGET_S = 75             # across the whole chain of 20+ models
_HISTORY_TURNS = 8
_MAX_TOKENS = 600                # headroom: reasoning models spend part of this on hidden thinking
_MAX_REPLY_CHARS = 450

# The three main models, then curated fallbacks. Every other free chat model is appended live
# (see _discover_free_models) and "openrouter/free" — which auto-routes to whatever free model is
# available — is always tried last.
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
]

# ── AI teammates: the named team in staff.py, when they are not signed in ─────
# The team are real people who sign in. An AI teammate stands in only for someone who is NOT signed
# in right now, so it never talks over a real person.

# #client-updates is a shared customer queue (see GENERIC_CUSTOMER_CHANNEL below), not a
# staff channel, so it is deliberately absent here.
_CHANNEL_POSITIONS = {
    "incidents":         ["I.T Assistant", "Manager", "Supervisor", "Customer Service"],
    "security":          ["I.T Assistant"],
    "reports-analytics": ["Manager", "Supervisor", "Computer Operator"],
}


def _available_teammates(sender: str) -> list:
    """Staff (dicts from staff.py) who could answer: not the sender, and nobody is signed in as them."""
    live = store.live_accounts()
    return [p for p in staff.STAFF if staff.identity(p) != sender and staff.account(p) not in live]


def _pick_channel_persona(channel_id: str, sender: str, text: str):
    """Who answers in a team channel: the @mentioned person, else one whose position fits the channel.
    None if nobody suitable is available (e.g. the @mentioned person is signed in and will answer)."""
    available = {staff.identity(p): p for p in _available_teammates(sender)}
    lowered = text.lower()
    for p in staff.STAFF:                                    # explicit "@庞统 ..." wins
        if f"@{p['name'].lower()}" in lowered:
            return staff.identity(p) if staff.identity(p) in available else None
    positions = _CHANNEL_POSITIONS.get(channel_id)
    pool = [i for i, p in available.items() if not positions or p["position"] in positions] or list(available)
    return random.choice(pool) if pool else None


# ── customer identities ──────────────────────────────────────────────────────
# Each customer is a named person at one of the client companies, shown as e.g.
# "Autofix Customer Tan Wei Ming". Identity is derived from that label, so a follow-up reply
# keeps the same person, company and servers as the question that started the conversation.

# Names fit the company's country. Every customer writes Mandarin, so outside Malaysia these are
# Chinese-speaking staff (Singaporean Chinese, Chinese-Australian, Taiwanese managers in Vietnam,
# Chinese-Indonesian).
_MALAYSIAN_NAMES = [
    "Tan Wei Ming", "Lim Mei Ling", "Lee Jia Hui", "Wong Kah Yee", "Chong Wei Jie", "Ng Siew Lan",
    "Goh Chee Keong", "Teoh Li Ying", "Chan Kok Leong", "Ong Hui Min", "Yap Zhi Hao", "Low Pei Shan",
    "Ahmad Faiz", "Nur Aisyah", "Muhammad Hakim", "Siti Aminah", "Kumar Rajan", "Priya Nair",
]
_NAMES_BY_COUNTRY = {
    "Malaysia":  _MALAYSIAN_NAMES,
    "Singapore": ["Tan Jia Hao", "Lim Shu Fen", "Ng Wei Liang", "Goh Xin Yi", "Chua Boon Kiat", "Teo Hui Ling",
                  "Koh Zhi Wei", "Sim Yu Xuan"],
    "Australia": ["Jason Liu", "Emily Chen", "Kevin Huang", "Michelle Wu", "David Zhang", "Grace Lin",
                  "Andrew Xu", "Sophie Zhou"],
    "Vietnam":   ["Chen Zhi Hao", "Lin Yu Ting", "Huang Jun Wei", "Wu Pei Ling", "Chang Ming Jie",
                  "Tsai Mei Hua", "Liu Kai Xiang", "Hsu Yi Chen"],
    "Indonesia": ["Hendra Wijaya", "Linda Susanto", "Kevin Tanoto", "Stefanie Halim", "Andi Gunawan",
                  "Melissa Kurniawan", "Robert Santoso", "Jessica Salim"],
}
_CUSTOMER_TITLES = [
    "IT Executive", "Operations Manager", "Finance Executive", "Branch Manager",
    "Systems Administrator", "Head of Customer Service", "Warehouse Supervisor", "Project Coordinator",
]


def is_customer(name: str) -> bool:
    """True for simulated customers ("Autofix Customer Tan Wei Ming"); False for team roles."""
    return name == CUSTOMER_NAME or bool(re.match(r"^\S+ Customer \S", name or ""))


def _client_short(client: dict) -> str:
    return client["name"].split()[0]                      # "Autofix Sdn Bhd" → "Autofix"


def _customer_clients() -> list:
    return list(tm.CLIENTS)                                   # every client account can have customers


def _names_for(client: dict) -> list:
    country = client["hq"].split(",")[-1].strip()             # "Kuala Lumpur, Malaysia" → "Malaysia"
    return _NAMES_BY_COUNTRY.get(country, _MALAYSIAN_NAMES)


def _make_identity(client: dict, person: str) -> dict:
    rng = random.Random(f"{client['code']}|{person}")           # stable per person
    fleet = tm.build_fleet(client)
    return {
        "label": f"{_client_short(client)} Customer {person}",
        "person": person,
        "title": rng.choice(_CUSTOMER_TITLES),
        "client": client,
        "servers": rng.sample(fleet, k=min(3, len(fleet))),
    }


def client_by_code(code) -> dict:
    return next((c for c in tm.CLIENTS if c["code"] == code), None)


# #client-updates is a shared customer queue: any of the 11 companies' customers may write there
# (unlike the cust-<code> channels, which each belong to one company). AI replies there are always
# a customer, never a teammate — those bots must never speak in someone else's name.
GENERIC_CUSTOMER_CHANNEL = "client-updates"


def is_customer_facing(channel_id: str) -> bool:
    return store.is_customer_channel(channel_id) or channel_id == GENERIC_CUSTOMER_CHANNEL


def _customer_context(channel_id: str, history: list, client: dict = None) -> tuple:
    """(ident, where) for a customer conversation in `channel_id` — tied to one company for a
    cust-<code> channel, or any company (reused for the rest of that thread) for the shared queue."""
    if store.is_customer_channel(channel_id):
        client = client or client_by_code(channel_id[len(store.CUSTOMER_PREFIX):])
        ident = _customer_identity(history, client)
        where = _customer_where(channel_id)
    else:
        ident = _customer_identity(history, client)
        ch = store.channel_by_id(channel_id)
        where = (f"a shared support inbox that customers from several different companies write "
                 f"into ({ch['name']} — {ch['desc']})")
    return ident, where


def _new_customer(client: dict = None) -> dict:
    client = client or random.choice(_customer_clients())
    return _make_identity(client, random.choice(_names_for(client)))


def _customer_identity(history: list, prefer: dict = None) -> dict:
    """The customer who spoke last in `history` (from client `prefer` if given), else a new one
    (from `prefer` if given, otherwise any client)."""
    for h in reversed(history):
        label = h.get("from", "")
        for client in _customer_clients():
            if prefer and client["code"] != prefer["code"]:
                continue
            prefix = f"{_client_short(client)} Customer "
            if label.startswith(prefix) and len(label) > len(prefix):
                return _make_identity(client, label[len(prefix):])
    return _new_customer(prefer)


# ── configuration (resolved on the main thread, passed into the worker) ──────

def _secret(name: str, default=None):
    """st.secrets raises if no secrets file exists, so guard the lookup."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


# ── model chain: 3 main models, then every other free chat model ─────────────
# OpenRouter adds and retires free models all the time, so the list of extra fallbacks is fetched
# from its public /models endpoint (cached, refreshed every 6 hours) instead of being hardcoded.

_MODELS_URL = "https://openrouter.ai/api/v1/models"
_DISCOVERY_TTL_S = 6 * 3600
_discovered = {"ids": [], "next": 0.0}
_discovery_lock = threading.Lock()

_NOT_CHAT = re.compile(r"content-safety|guard|moderation|embed|lyria|tts|whisper|rerank|image", re.IGNORECASE)
# Still usable, but tried after the general-purpose models: specialists, code, tiny, vision or preview builds.
_LESS_GENERAL = re.compile(r"code|coder|-fin\b|-sante\b|-vl\b|lfm|mini|nano|small|lite|preview", re.IGNORECASE)


def _discover_free_models() -> list:
    """Every free text-chat model OpenRouter lists right now, general-purpose ones first (largest
    context first). Returns the last good list if OpenRouter can't be reached; [] if there never was one."""
    with _discovery_lock:
        now = time.time()
        if now < _discovered["next"]:
            return list(_discovered["ids"])
        try:
            data = httpx.get(_MODELS_URL, timeout=10).json()["data"]
        except Exception:
            _discovered["next"] = now + 300                      # try again in 5 minutes
            return list(_discovered["ids"])
        general, other = [], []
        for m in data:
            mid = str(m.get("id", ""))
            price = m.get("pricing") or {}
            free = mid.endswith(":free") or (str(price.get("prompt")) == "0" and str(price.get("completion")) == "0")
            out = (m.get("architecture") or {}).get("output_modalities") or ["text"]
            if not free or out != ["text"] or _NOT_CHAT.search(mid) or mid == "openrouter/free":
                continue
            (other if _LESS_GENERAL.search(mid) else general).append((m.get("context_length") or 0, mid))
        ids = [i for _, i in sorted(general, reverse=True)] + [i for _, i in sorted(other, reverse=True)]
        _discovered["ids"], _discovered["next"] = ids, now + _DISCOVERY_TTL_S
        return list(ids)


def _model_config() -> tuple:
    """Read the model settings on the Streamlit thread: (three main models, fallbacks, discover extras?).
    Setting OPENROUTER_FALLBACK_MODELS in secrets.toml pins the fallbacks and turns discovery off."""
    pinned = _secret("OPENROUTER_FALLBACK_MODELS")
    return (
        list(_secret("OPENROUTER_PRIMARY_MODELS") or PRIMARY_MODELS),
        list(pinned or FALLBACK_MODELS),
        not pinned,
    )


def _model_chain(cfg: tuple) -> list:
    """The order models are tried in: the 3 main ones, the curated fallbacks, every other free chat
    model, and finally OpenRouter's own auto-router."""
    primary, fallback, discover = cfg
    chain, seen = [], set()
    for m in primary + fallback + (_discover_free_models() if discover else []) + ["openrouter/free"]:
        if m not in seen:
            seen.add(m)
            chain.append(m)
    return chain


# ── prompts ──────────────────────────────────────────────────────────────────

def _answerer(sender: str) -> str:
    """Who is answering the customer. For a named staff member, include their job so the customer
    asks fitting questions (a Manager gets escalations, Customer Service gets login problems...)."""
    if not sender:
        return "Whoever is on duty will answer you. "
    person = staff.by_identity(sender)
    if not person:
        return f'The person answering you is their "{sender}". '
    return (
        f'The person answering you is {person["name"]}, their {person["position"]}. Their job: '
        f'{person["details"]} Address them naturally by name, and raise things that fit their job '
        "(for example ask a Manager to escalate, or ask Customer Service about a login problem). "
    )


def _customer_prompt(sender: str, where: str, ident: dict) -> str:
    c = ident["client"]
    servers = "; ".join(f"{s['name']} ({s['engine']} {s['role'].lower()}, {s['hostname']})" for s in ident["servers"])
    return (
        f"You are {ident['person']}, {ident['title']} at {c['name']} ({c['industry']}, based in {c['hq']}). "
        "Your company pays Caspira for managed database monitoring (uptime, backups, performance, alerts, "
        f"maintenance, security, reports, billing). Caspira runs your databases, including: {servers}. "
        f"You are chatting with Caspira's support team in {where}. "
        + _answerer(sender)
        + "Play this customer realistically so the team can practise serving customers.\n\n"
        "Rules:\n"
        "- Be SPECIFIC, like a real person with a real problem. Tie every concern to your own business "
        f"({c['industry']}) and name your actual system: use one of the server names above, say what you "
        "saw (a time, an error message, a number, a report that looks wrong) and what it stops your staff "
        "from doing. Never ask vague, generic questions like \"is everything ok?\".\n"
        "- LANGUAGE: always write in Mandarin Chinese, whatever language the team member uses — the team "
        "cannot read English. Write Simplified Chinese (简体中文) by default; only if the team member writes in "
        "Traditional characters, switch to Traditional. "
        "Keep common terms such as DB, SLA, backup as-is. Natural, everyday business Chinese.\n"
        "- 1–3 short sentences, like a chat message. No markdown, no lists, no emojis, no sign-off.\n"
        "- You ask a lot of questions. Most of your messages should contain a new, concrete question or "
        "request (e.g. why the system was slow this morning, when the last backup ran, whether data can be "
        "restored, when maintenance happens, how an invoice or SLA works, how to add a new database, who to "
        "call in an emergency). Sometimes report a problem or sound worried or impatient.\n"
        "- Keep the conversation going like a real customer relationship. Read the conversation so far and "
        "make the natural next move:\n"
        "    • no conversation yet, or they greet you: raise your specific concern.\n"
        "    • they answered but it is not fully resolved or you are unsure: press with a follow-up — ask for "
        "evidence, the cause, an ETA, or what exactly they did.\n"
        "    • they say it is fixed: check it (\"is it stable now?\", \"what stops it happening again?\") and ask "
        "them to keep monitoring and update you, or ask for the incident report / a status update.\n"
        "    • sometimes ask them to REVISE something they sent (a report, timeline, quote, wording or SLA "
        "figure) and say what to change.\n"
        "    • once an issue has settled (usually after 2–3 exchanges on it), sometimes raise future "
        "collaboration: adding servers or new services, a disaster-recovery plan, a better SLA, contract "
        "renewal, pricing, a review meeting.\n"
        "  Always react to what the team member just said first (thank them, doubt them, or ask more).\n"
        "- Do not repeat what was already asked or agreed; move the conversation forward. You are not a "
        "technical expert and don't know Caspira's internal details.\n"
        "- Never say you are an AI, a model or a simulation.\n"
        "- Output only the message text — no name prefix."
    )


def _system_prompt(persona: str, sender: str, where: str) -> str:
    person = staff.by_identity(persona) or {"name": persona, "position": "team member", "details": ""}
    return (
        f'You are {person["name"]}, the {person["position"]} on a small managed-services team at Caspira, '
        "which runs and monitors database servers for client companies. Your job: "
        f'{person["details"] or "support the team."}\n'
        f"You are chatting on the internal team messenger ({where}) with your colleague "
        f'"{sender}". Reply to their latest message as a real coworker would.\n\n'
        "Rules:\n"
        "- LANGUAGE: reply in the same language as their latest message. English message → English reply; "
        "Chinese (Mandarin) message → Mandarin reply, in the same script they used (Simplified or Traditional). "
        "Follow the latest message only, even if earlier messages were in another language. Keep common "
        "technical terms (DB, SLA, CI/CD, backup) as-is. In Chinese, sound like a natural coworker, not a translation.\n"
        f"- Stay in character as {person['name']}. Never say you are an AI, a model or a simulation.\n"
        "- 1–2 short sentences, casual workplace tone, written like a chat message. No greeting ritual, "
        "no sign-off, no lists, no markdown, no emojis.\n"
        "- Answer what was asked with a plausible, specific update from your own line of work "
        '(e.g. "on plan — I\'m on the 3rd phase now", "backups finished clean overnight, verifying restores today"). '
        "Keep it consistent with earlier messages in the conversation.\n"
        "- If asked something outside your job, say which colleague would know. The only people on the team are: "
        f"{', '.join(staff.IDENTITIES)}. Never refer to any other person, role or department.\n"
        "- Output only the message text — no name prefix."
    )


def _build_messages(persona: str, sender: str, where: str, history: list, text: str, ident: dict = None) -> list:
    system = _customer_prompt(sender, where, ident) if ident else _system_prompt(persona, sender, where)
    msgs = [{"role": "system", "content": system}]
    for h in history[-_HISTORY_TURNS:]:
        body = (h.get("text") or "").strip()
        if not body:
            continue
        who = h.get("from", "")
        mine = who == persona or (ident is not None and is_customer(who))   # earlier customer lines = "me"
        msgs.append({
            "role": "assistant" if mine else "user",
            "content": body if mine else f"{who}: {body}",
        })
    msgs.append({"role": "user", "content": f"{sender}: {text}"})
    return msgs


# ── model call ───────────────────────────────────────────────────────────────

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_limit_until = 0.0                # while now < this, the daily free allowance is known to be used up


def _call(model: str, messages: list, key: str, timeout: float):
    """One attempt. Returns (text | None, fatal). fatal=True means stop trying (bad key, or the daily
    free allowance is used up)."""
    global _limit_until
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
    if r.status_code == 429 and "free-models-per-day" in r.text:
        # The account's daily free allowance is used up. It is shared by every free model, so
        # trying more models is pointless — stop, and don't call again for a while.
        _limit_until = time.time() + 1800
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
    if is_customer(persona):
        letters = re.sub(r"[\s\W\d_]+", "", text)
        if len(_CJK.findall(text)) < max(4, int(0.5 * len(letters))):
            return False
    return True


def _generate(persona: str, messages: list, key: str, cfg: tuple):
    """First usable reply from the model chain, or None (all busy, or the daily allowance is used up)."""
    if time.time() < _limit_until:
        return None
    models = _model_chain(cfg)                   # may fetch the free-model list (cached 6 h)
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
    """Have an AI answer `text` ~10 seconds from now, without blocking the UI.

    kind    "channel" (target = channel id) or "dm" (target = the partner role, who replies)
    sender  the role that just sent the message
    history messages before this one (dicts with "from" and "text"), oldest first
    A customer channel ("cust-<client code>", or the shared #client-updates queue) always gets a
    customer reply, in Chinese — never a teammate, even if a staff member's name is mentioned there.
    A team channel gets a teammate reply in character, in the language the message was written in.
    Silently does nothing if no API key is configured or every model fails.
    """
    key = (_secret("OPENROUTER_API_KEY") or "").strip()
    if not key or not text.strip():
        return
    cfg = _model_config()

    ident = None
    if kind == "dm":
        persona, where = target, f"a direct message with {sender}"
        person = staff.by_identity(persona)
        if person is None or persona == sender or staff.account(person) in store.live_accounts():
            return                                    # only stand in for someone who is not signed in
    elif is_customer_facing(target):
        ident, where = _customer_context(target, history)
        persona = ident["label"]
    else:                                             # team channel → a teammate answers
        persona = _pick_channel_persona(target, sender, text)
        if not persona:
            return                                    # everyone suitable is signed in — they will answer
        ch = store.channel_by_id(target)
        where = f"the {ch['name']} channel — {ch['desc']}"

    messages = _build_messages(persona, sender, where, history, text, ident)
    delay = random.uniform(*REPLY_DELAY_S)

    def _worker() -> None:
        try:
            started = time.monotonic()
            reply = _generate(persona, messages, key, cfg)
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


def _customer_where(channel_id: str) -> str:
    ch = store.channel_by_id(channel_id)
    return f"a private chat channel that exists only for {ch['name']}"


# ── customers who speak first ────────────────────────────────────────────────
# A background loop (one per server process) posts a new customer question into each company's
# conversation when it is quiet, so every account has its own live conversation and the unread
# badges show where something new arrived. Guards keep it cheap and non-spammy:
#   • only while someone has the Channels page open (touch() is called by its 2-second poller)
#   • one new question per 15-second tick, so the 11 companies start up one after another
#   • never while the last message is an unanswered customer question
#   • a random quiet gap between questions, and a daily cap (free OpenRouter keys allow ~50 requests/day)

_QUIET_GAP_S = (180, 360)        # how long a conversation must be quiet before a new question
_DAILY_CAP = 30                  # new customer questions per day (follow-up replies are extra)
_PRESENCE_S = 120                # "someone is watching" window after the last touch()
_LOOP_TICK_S = 15


# A different topic per new conversation, so the 11 companies don't all report the same incident.
_OPENER_TOPICS = [
    "a report or dashboard that has become much slower than usual",
    "worry about whether last night's backup really completed and could be restored",
    "a request to add a new database or server for a new project",
    "a security question: who has access, or a suspicious login alert you received",
    "an invoice or billing amount you do not understand",
    "planned maintenance: when it happens and whether it hits your busy hours",
    "the uptime / SLA figure in last month's report looks wrong to you",
    "storage running low and what it would cost to expand",
    "too many false-alarm alerts waking your staff up at night",
    "disaster recovery: what happens if the main database server fails, and has it been tested",
    "a data export or custom report you need by a deadline",
    "a database upgrade or migration you are planning and want advice on",
    "an error your application showed to your own customers yesterday",
    "giving a new employee access, or removing a leaver's access",
    "a sudden spike in database connections or CPU you noticed",
    "a price or contract question for next year",
]


def _opener_messages(where: str, history: list, ident: dict) -> list:
    msgs = [{"role": "system", "content": _customer_prompt("", where, ident)}]
    for h in history[-_HISTORY_TURNS:]:
        body = (h.get("text") or "").strip()
        if not body:
            continue
        who = h.get("from", "")
        msgs.append({
            "role": "assistant" if is_customer(who) else "user",
            "content": body if is_customer(who) else f"{who}: {body}",
        })
    msgs.append({
        "role": "user",
        "content": "[Start now: write your next message to the support team. Topic for this message: "
                   f"{random.choice(_OPENER_TOPICS)}. Make the details your own — pick your own time, "
                   "numbers and wording; do not reuse example times or error messages. Do not repeat "
                   "anything already discussed in this conversation.]",
    })
    return msgs


def _idle_seconds(msgs: list) -> float:
    if not msgs:
        return float("inf")
    try:
        return (datetime.now() - datetime.fromisoformat(msgs[-1]["ts"])).total_seconds()
    except (ValueError, TypeError, KeyError):
        return 0.0


def _customer_loop(state: dict, key: str, cfg: tuple, cap: int) -> None:
    while True:
        time.sleep(_LOOP_TICK_S)
        try:
            if time.time() - state["last_seen"] > _PRESENCE_S:
                continue                                    # nobody has the Channels page open
            today = date.today().isoformat()
            if state["day"] != today:
                state["day"], state["count"] = today, 0
            if state["count"] >= cap:
                continue
            order = [c["id"] for c in store.CUSTOMER_CHANNELS] + [GENERIC_CUSTOMER_CHANNEL]
            random.shuffle(order)
            for ch_id in order:
                msgs = store.bg_recent_channel_messages(ch_id, 12)
                if msgs and is_customer(msgs[-1]["from"]):
                    continue                                # a question is still waiting for an answer
                if _idle_seconds(msgs) < state["gap"]:
                    continue
                ident, where = _customer_context(ch_id, msgs)
                reply = _generate(ident["label"], _opener_messages(where, msgs, ident), key, cfg)
                if reply:
                    store.bg_post_channel(ident["label"], ch_id, reply)
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
        cap = int(_secret("CUSTOMER_DAILY_CAP") or _DAILY_CAP)
        threading.Thread(
            target=_customer_loop, args=(state, key, _model_config(), cap),
            name="ai-customer-loop", daemon=True,
        ).start()
    return state


def touch() -> None:
    """Call from the Channels page's poller: records that someone is watching and, on the first call
    in a server process, starts the loop that lets customers open conversations."""
    _customer_state()["last_seen"] = time.time()
