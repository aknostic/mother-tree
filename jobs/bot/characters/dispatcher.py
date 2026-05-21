"""Dispatcher — the Receptionist.

Looks at every incoming message and routes to the right character.
Two-tier: deterministic pattern matching first, LLM triage only when needed.
"""
import logging
import re

from bot.detect import GLOBAL_COMMANDS
from bot.enrich import extract_urls, fetch_and_follow
from mothertree.graphql_client import is_admin
from mothertree.llm import extract

log = logging.getLogger(__name__)

PERSONA_NAMES = {"saga", "lena", "trainer"}

_DEBRIEF_TRIGGERS = frozenset({"debrief", "meeting notes"})

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_CALENDAR_RE = re.compile(r"https?://calendar\.|\.ics|ical", re.IGNORECASE)
_DAYS_RE = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|maandag|dinsdag|woensdag|donderdag|vrijdag)\b", re.IGNORECASE)


def _is_admin_user(user: dict) -> bool:
    """Check if resolved user is an admin."""
    return is_admin(user.get("email", "")) if user else False


def _detect_profile_sharing(text: str) -> bool:
    """Detect if a DM contains personal profile information."""
    if _EMAIL_RE.search(text):
        return True
    if _CALENDAR_RE.search(text):
        return True
    if _DAYS_RE.search(text) and any(w in text.lower() for w in ("work", "available", "days", "schedule", "werk")):
        return True
    if re.search(r"(?:phone|tel|mob|bel)\s*[:.]?\s*\+?\d[\d\s\-]{8,}|\+\d{1,3}[\s\-]?\d[\d\s\-]{7,}", text, re.IGNORECASE):
        return True
    return False


def _detect_persona(text: str) -> str | None:
    """Detect a persona reference in natural conversation.

    Matches:
    - "ask saga ..." / "ask lena ..." / "ask trainer ..."
    - "what would saga say" / "what would lena think"
    - "saga's take on ..." / "lena's view on ..."
    - "how would saga ..." / "how would lena ..."
    - Any mention of saga/lena in a question context
    """
    lower = text.lower()

    # Explicit "ask <persona>" pattern
    parts = lower.split()
    if len(parts) >= 2 and parts[0] == "ask" and parts[1] in PERSONA_NAMES:
        return parts[1]

    # Conversational patterns
    for name in ("saga", "lena"):
        if name not in lower:
            continue
        # "what would saga say/think", "how would lena approach"
        if f"would {name}" in lower:
            return name
        # "saga's take/view/perspective/opinion"
        if f"{name}'s" in lower or f"{name}s " in lower:
            return name
        # "ask saga" anywhere in the message
        if f"ask {name}" in lower:
            return name
        # Name mentioned in a question
        if name in lower and "?" in text:
            return name

    # "trainer" only via explicit "ask trainer"
    if len(parts) >= 2 and parts[0] == "ask" and parts[1] == "trainer":
        return "trainer"

    return None


TRIAGE_SYSTEM = """You decide whether Mother Tree should respond to a message and whether it contains commercial signal intelligence.

Return JSON only:
{"respond": true/false, "signal": {"capture": true/false, "confidence": 0.0-1.0}, "reason": "one sentence"}

Rules:
- If this is a DM (1 participant), respond is ALWAYS true.
- Respond when: direct question, request for help, Mother Tree has something useful to add.
- Stay silent when: people talking to each other, small talk, reactions, greetings between colleagues.
- Signal capture: intelligence about a prospect, client, market, competitor, or event.
- Be conservative in channels — if unsure, stay silent."""


def _call_triage_llm(prompt: str) -> dict:
    """Make the triage LLM call."""
    return extract(prompt, TRIAGE_SYSTEM)


def _build_triage_prompt(text: str, participant_count: int, recent_messages: list[dict]) -> str:
    """Build the triage prompt with context."""
    context = ""
    if recent_messages:
        context = "\nRecent messages:\n" + "\n".join(
            f"- [{m.get('name', 'someone')}]: {m['content'][:100]}"
            for m in recent_messages[-5:]
        )
    return f"Participants: {participant_count}\n{context}\n\nNew message: {text}"


def _strip_slack_email(text: str) -> str:
    """Strip Slack mailto formatting: <mailto:x@y.z|x@y.z> → x@y.z"""
    return re.sub(r'<mailto:([^|>]+)\|[^>]+>', r'\1', text)


def _detect_admin_command(text: str) -> dict | None:
    """Detect admin commands from DM text."""
    lower = _strip_slack_email(text).lower().strip()
    parts = lower.split()
    if len(parts) >= 2 and parts[0] == "make" and parts[1] == "admin":
        email = parts[2] if len(parts) > 2 else None
        return {"action": "make_admin", "email": email}
    if len(parts) >= 2 and parts[0] == "remove" and parts[1] == "admin":
        email = parts[2] if len(parts) > 2 else None
        return {"action": "remove_admin", "email": email}
    if lower == "pending":
        return {"action": "pending"}
    # "enroll email as role" — admin enrollment
    if parts and parts[0] == "enroll" and "as" in parts:
        as_idx = parts.index("as")
        email = parts[1] if len(parts) > 1 else None
        role = parts[as_idx + 1] if len(parts) > as_idx + 1 else None
        if email and role and role in ("hunter", "gatherer", "farmer", "citizen"):
            return {"action": "admin_enroll", "email": email, "role": role}
    return None


# Snooze patterns — phrases that indicate "not now, remind me later".
# "remind me ..." is handled separately as an explicit self-reminder command,
# so it is not in this list.
_SNOOZE_PATTERNS = [
    r"\b(tomorrow|morgen)\b",
    r"\b(next week|volgende week)\b",
    r"\b(park it|parkeer)\b",
    r"\b(not now|niet nu)\b",
    r"\b(check back|later|snooze)\b",
    r"\b(after|na)\s+(the\s+)?(weekend|vakantie|kubecon|conference|event)\b",
    r"\b(in\s+\d+\s+(days?|weeks?|dagen|weken))\b",
]

# Snooze replies to a Pulse nudge are short by nature ("tomorrow", "park it",
# "not now, check back Friday"). Anything longer is conversational prose that
# happens to mention a time word — don't hijack it.
_SNOOZE_MAX_WORDS = 6

# Completion patterns — phrases that indicate an action was taken
_COMPLETION_PATTERNS = [
    r"\b(sent|verzonden)\s+(the\s+)?(mail|email|message)\b",
    r"\b(met with|spoke with|called|gebeld|gesproken)\b",
    r"\b(done|klaar|afgerond)\b",
    r"\b(followed up|contacted|reached out)\b",
    r"\b(had a? ?(call|meeting|conversation))\b",
]


def _detect_snooze(text: str) -> str | None:
    """Detect snooze intent in a short reply to a Pulse nudge.

    Returns the matched phrase or None. Long messages that incidentally
    mention "next week" / "tomorrow" / "later" are treated as conversation,
    not as snooze commands.
    """
    lower = text.lower().strip()
    if len(lower.split()) > _SNOOZE_MAX_WORDS:
        return None
    for pattern in _SNOOZE_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            return match.group(0)
    return None


def _detect_completion(text: str) -> bool:
    """Detect completion intent — user reports they took an action."""
    lower = text.lower()
    # Questions are not completions
    if lower.strip().endswith("?"):
        return False
    for pattern in _COMPLETION_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


# Pipeline phrasings we recognize as natural-language variants of the bare
# `pipeline` command. Each entry is (regex, scope) — "other"/target is handled
# separately below via a capture group.
_PIPELINE_PATTERNS: list[tuple[str, str]] = [
    (r"^the\s+pipeline$", "global"),
    (r"^pipeline$", "global"),
    (r"^my\s+pipeline$", "personal"),
]


def _detect_pipeline_or_brief(text: str) -> dict | None:
    """Return a pipeline/brief annotation dict, or None if no match."""
    lower = text.lower().strip()
    stripped = text.strip()

    # "brief <query>" — preserve original casing for the query text
    if lower.startswith("brief "):
        query = stripped[6:].strip()
        return {"type": "brief", "query": query}
    if lower == "brief":
        return {"type": "brief", "query": ""}

    # "pim's pipeline" / "pim’s pipeline"
    m = re.match(r"^(\w+)['’]s\s+pipeline$", lower)
    if m:
        return {"type": "pipeline", "scope": "other", "target": m.group(1)}

    # "pipeline <name>"
    m = re.match(r"^pipeline\s+(\w+)$", lower)
    if m:
        return {"type": "pipeline", "scope": "other", "target": m.group(1)}

    # "my pipeline" / "pipeline" / "the pipeline"
    for pattern, scope in _PIPELINE_PATTERNS:
        if re.match(pattern, lower):
            return {"type": "pipeline", "scope": scope}

    return None


def dispatch(
    text: str,
    participant_count: int,
    enrolled: bool = False,
    enrollment: dict = None,
    active_exercise: dict = None,
    slack_user_id: str = None,
    bot_user_id: str = None,
    context_type: str = "dm",
    has_bot_participated: bool = False,
    recent_messages: list[dict] = None,
    user: dict = None,
) -> dict:
    """Route a message to the right character.

    Returns:
        character: "mother_tree" | "saga" | "lena" | "silent"
        intent: str — what the message is about
        annotation: dict | None — structured data for the character
        must_respond: bool
        training_mode: bool — Saga+Lena co-train
        signal_flag: bool — triage detected commercial signal
        clean_text: str — text with mention stripped
        exercise_pending: dict | None
    """
    result = {
        "character": "mother_tree",
        "intent": "freeform",
        "annotation": None,
        "must_respond": participant_count == 1,  # DMs always respond
        "training_mode": False,
        "signal_flag": False,
        "clean_text": text,
        "exercise_pending": None,
    }

    clean = text.strip()

    # 1. Strip @bot mention
    if bot_user_id:
        mention_pat = re.compile(r"<@" + re.escape(bot_user_id) + r">", re.IGNORECASE)
        if mention_pat.search(clean):
            clean = mention_pat.sub("", clean).strip()
            result["must_respond"] = True

    result["clean_text"] = clean
    parts = clean.split()
    first = parts[0].lower() if parts else ""

    # 2a. Admin commands (DM only, admin users only)
    if participant_count == 1 and user and _is_admin_user(user):
        admin_action = _detect_admin_command(clean)
        if admin_action:
            result["must_respond"] = True
            result["intent"] = "admin"
            result["annotation"] = {"type": "admin", **admin_action}
            return result

    # 2b. Pipeline / brief — natural-language variants with scope/target
    pipeline_or_brief = _detect_pipeline_or_brief(clean)
    if pipeline_or_brief:
        result["must_respond"] = True
        result["intent"] = pipeline_or_brief["type"]
        result["annotation"] = pipeline_or_brief
        return result

    # 2. Global commands → Mother Tree
    if first in GLOBAL_COMMANDS:
        result["must_respond"] = True
        result["intent"] = first

        if first == "status":
            enrollment_data = enrollment
            if enrollment_data:
                result["annotation"] = {
                    "type": "status",
                    "stage": enrollment_data.get("currentStage"),
                    "chapter": enrollment_data.get("currentChapter"),
                    "streak": enrollment_data.get("streak"),
                    "role": enrollment_data.get("role"),
                }
            else:
                result["annotation"] = {"type": "status", "enrolled": False}
        elif first == "enroll":
            role = parts[1].lower() if len(parts) > 1 else None
            result["annotation"] = {"type": "enroll", "role": role, "email": user.get("email", "") if user else ""}
            result["training_mode"] = True
        elif first == "stats":
            result["annotation"] = {"type": "stats", "data": {}}
        elif first == "progress":
            result["annotation"] = {"type": "progress"}
        elif first == "help":
            topic = " ".join(parts[1:]) if len(parts) > 1 else None
            result["annotation"] = {"type": "help", "topic": topic}
        elif first == "review":
            company_name = " ".join(parts[1:]) if len(parts) > 1 else None
            result["annotation"] = {"type": "account_review", "company": company_name}
        elif first == "accounts":
            result["annotation"] = {"type": "account_list"}

        return result

    # 3. Persona patterns → route to persona character
    # Match explicit: "ask saga ...", "ask lena ..."
    # Match conversational: "what would saga say", "saga's take on", "how would lena approach"
    detected_persona = _detect_persona(clean)
    if detected_persona:
        persona_name = detected_persona
        # Strip "ask <name>" prefix if present, keep full text for conversational patterns
        if first == "ask" and len(parts) >= 2 and parts[1].lower() in PERSONA_NAMES:
            result["clean_text"] = " ".join(parts[2:])
        else:
            result["clean_text"] = clean
        result["must_respond"] = True
        result["intent"] = "persona"
        result["annotation"] = {"type": "persona", "persona": persona_name, "question": clean}

        if persona_name == "trainer":
            result["training_mode"] = True
        else:
            result["character"] = persona_name

        return result

    # 4. Account plan + service meeting (DM only, no enrollment required)
    if participant_count == 1:
        # Nudge another user or self-remind (DM only)
        if first in ("nudge", "remind", "ping") and len(parts) >= 2:
            # "remind me ..." = self-reminder
            if parts[1].lower() == "me":
                context = " ".join(parts[2:]) if len(parts) > 2 else ""
                result["must_respond"] = True
                result["intent"] = "remind"
                result["annotation"] = {"type": "self_remind", "context": context}
                return result
            # "nudge <name> ..." = nudge another user
            target_name = parts[1]
            context = " ".join(parts[2:]) if len(parts) > 2 else ""
            result["must_respond"] = True
            result["intent"] = "nudge"
            result["annotation"] = {"type": "nudge", "target": target_name, "context": context}
            return result

        # "check back <when>" / "follow up <when>"
        if first in ("check", "follow") and len(parts) >= 2:
            if (first == "check" and parts[1].lower() == "back") or \
               (first == "follow" and parts[1].lower() == "up"):
                context = " ".join(parts[2:]) if len(parts) > 2 else ""
                result["must_respond"] = True
                result["intent"] = "remind"
                result["annotation"] = {"type": "self_remind", "context": context}
                return result

        if first == "account" and len(parts) >= 3 and parts[1].lower() == "plan":
            company_name = " ".join(parts[2:])
            result["must_respond"] = True
            result["intent"] = "account"
            result["annotation"] = {"type": "account_plan", "company": company_name}
            return result

        if first == "service" and len(parts) >= 2 and parts[1].lower() == "meeting":
            content = " ".join(parts[2:]) if len(parts) > 2 else ""
            result["must_respond"] = True
            result["intent"] = "service_meeting"
            result["annotation"] = {"type": "service_meeting", "content": content}
            return result

    # 4b. DM-only training patterns
    if participant_count == 1 and enrolled:
        role = (enrollment or {}).get("role")

        if first == "next" and len(parts) == 1:
            result["must_respond"] = True
            result["training_mode"] = True
            result["intent"] = "training"
            if role == "citizen":
                result["annotation"] = {"type": "citizen_inspiration"}
            else:
                result["annotation"] = {"type": "training_next"}
            return result

        if first == "go" and len(parts) == 1:
            result["must_respond"] = True
            result["annotation"] = {"type": "exercise_go"}
            result["training_mode"] = True
            result["intent"] = "training"
            return result

        if first == "practice":
            result["must_respond"] = True
            topic = parts[1].lower() if len(parts) > 1 else None
            result["annotation"] = {"type": "practice", "topic": topic}
            result["training_mode"] = True
            result["intent"] = "training"
            return result

        if clean.upper() in ("A", "B", "C"):
            if active_exercise:
                result["must_respond"] = True
                result["annotation"] = {"type": "answer", "answer": clean.upper()}
                result["training_mode"] = True
                result["intent"] = "training"
                return result

    # 4b. DM snooze/completion (response to Pulse nudge)
    if participant_count == 1:
        snooze_match = _detect_snooze(clean)
        if snooze_match:
            result["must_respond"] = True
            result["intent"] = "snooze"
            result["annotation"] = {"type": "snooze", "match": snooze_match, "text": clean}
            return result

        if _detect_completion(clean):
            result["must_respond"] = True
            result["intent"] = "completion"
            result["annotation"] = {"type": "completion", "text": clean}
            result["signal_flag"] = True  # completion info feeds back through signal pipeline
            return result

    # 4c. DM debrief ingestion
    if participant_count == 1:
        first_line = clean.split("\n")[0].lower().strip()
        if first_line in _DEBRIEF_TRIGGERS:
            result["must_respond"] = True
            result["intent"] = "debrief"
            result["annotation"] = {
                "type": "debrief",
                "content": "\n".join(clean.split("\n")[1:]).strip(),
            }
            return result

    # 4d. DM profile sharing — flag for side-effect extraction, don't short-circuit
    if participant_count == 1 and _detect_profile_sharing(clean):
        result["profile_detected"] = True

    # 5. URL detection → Mother Tree
    urls = extract_urls(clean)
    if urls:
        import threading
        from concurrent.futures import ThreadPoolExecutor
        urls = urls[:3]
        follow_budget = threading.Semaphore(2)
        with ThreadPoolExecutor(max_workers=3) as pool:
            fetched = list(pool.map(lambda u: fetch_and_follow(u, follow_budget), urls))

        result["must_respond"] = True
        result["intent"] = "url"
        url_results = []
        url_failures = []
        for url, content in zip(urls, fetched, strict=False):
            if content:
                url_results.append({"url": url, "content": content})
            else:
                url_failures.append(url)

        if url_results:
            if len(url_results) == 1:
                result["annotation"] = {
                    "type": "url_content",
                    "url": url_results[0]["url"],
                    "content": url_results[0]["content"],
                }
            else:
                result["annotation"] = {
                    "type": "url_content",
                    "urls": [r["url"] for r in url_results],
                    "content": "\n\n---\n\n".join(
                        f"[{r['url']}]\n{r['content']}" for r in url_results
                    ),
                }
        else:
            result["annotation"] = {
                "type": "url_failed",
                "url": url_failures[0] if url_failures else urls[0],
            }
        return result

    # 6. Exercise pending nudge
    if active_exercise and participant_count == 1:
        questions = (active_exercise.get("exercise") or {}).get("content", {}).get("questions", [])
        current_q = active_exercise.get("current_question", 0)
        if questions and current_q >= 0:
            result["exercise_pending"] = {
                "question_num": current_q + 1,
                "total": len(questions),
            }

    # 7. No pattern matched — triage for channels/threads, respond for DMs
    if participant_count == 1:
        return result

    # @mentioned: always respond, skip triage
    if result.get("must_respond"):
        return result

    # Active thread where bot participated: respond without triage
    if context_type == "thread" and has_bot_participated:
        result["must_respond"] = True
        return result

    # Channel/thread: LLM triage (only for non-mentioned messages)
    prompt = _build_triage_prompt(clean, participant_count, recent_messages or [])
    try:
        triage_result = _call_triage_llm(prompt)
    except Exception as e:
        log.warning(f"Triage LLM failed: {e}")
        result["character"] = "silent"
        return result

    # Always capture the signal flag — even when we decide not to respond,
    # the message might contain commercial intelligence worth extracting.
    result["signal_flag"] = triage_result.get("signal", {}).get("capture", False)

    if not triage_result.get("respond", False):
        result["character"] = "silent"
        return result

    return result
