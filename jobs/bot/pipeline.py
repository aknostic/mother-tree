"""Unified message pipeline — dispatch → character → post-process → deliver.

Every message, every context (DM, channel, thread) goes through the same flow.
Every response comes from a character module. No exceptions.
"""
import json
import logging
import threading

from bot.buffer import ChannelBuffer
from bot.characters.base import fix_slack_formatting
from bot.characters.dispatcher import dispatch
from bot.extraction import assess_actions, extract_signal
from bot.markers import extract_action_markers, extract_content_markers, sanitize_user_input
from bot.memory import append_message, get_max_messages, get_memory, window_messages
from mothertree.graphql_client import create_reminder, find_user_by_name, get_active_conversation

log = logging.getLogger(__name__)

_channel_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()
channel_buffer = ChannelBuffer(max_size=20)

THINKING_EMOJI = "thought_balloon"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def handle_message(text: str, user_slack_id: str, user_name: str,
                   channel_id: str, channel_type: str, participant_count: int,
                   respond, client, thread_ts: str = None, ts: str = None,
                   bot_user_id: str = None, file_contents: list[dict] = None) -> None:
    """Process a message through the pipeline."""
    text = sanitize_user_input(text)

    # Append file contents to the message text
    if file_contents:
        file_text = "\n\n".join(
            f"[File: {f['name']}]\n{f['content']}" for f in file_contents
        )
        text = f"{text}\n\n{file_text}" if text else file_text

    if channel_type == "im":
        context_type = "dm"
    elif thread_ts and thread_ts != ts:
        context_type = "thread"
    else:
        context_type = "channel"

    lock = _get_channel_lock(channel_id) if context_type != "dm" else None
    if lock:
        lock.acquire()
    try:
        _process_message(
            text=text, user_slack_id=user_slack_id, user_name=user_name,
            channel_id=channel_id, context_type=context_type,
            participant_count=participant_count, respond=respond, client=client,
            thread_ts=thread_ts, ts=ts, bot_user_id=bot_user_id,
        )
    finally:
        if lock:
            lock.release()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _process_message(text, user_slack_id, user_name, channel_id, context_type,
                     participant_count, respond, client, thread_ts, ts, bot_user_id):
    """The pipeline. Five phases: setup → dispatch → respond → post-process → deliver."""

    # --- SETUP ---
    reply_thread_ts = thread_ts or (ts if context_type == "channel" else None)
    thinking = _post_thinking(client, channel_id, reply_thread_ts, context_type, ts)

    user, active_exercise, enrolled = _resolve_user(user_slack_id, client, participant_count)
    memory_ctx = _get_memory_context(context_type, user["id"] if user else None, channel_id, thread_ts)

    has_bot_participated = (
        context_type == "thread"
        and any(m.get("role") == "assistant" for m in memory_ctx["messages"])
    )

    # --- SIGNAL CORRECTION --- check if this is a reply to a signal receipt
    # Works in threads (channel receipts) and DMs (DM receipts)
    _is_receipt_context = False
    if context_type == "thread" and has_bot_participated:
        bot_messages = [m for m in memory_ctx["messages"] if m.get("role") == "assistant"]
        if bot_messages and "Signal captured" in bot_messages[0].get("content", ""):
            _is_receipt_context = True
    elif context_type == "dm":
        # In DMs, check if the most recent bot message was a receipt
        recent_bot = [m for m in memory_ctx["messages"] if m.get("role") == "assistant"]
        if recent_bot and "Signal captured" in recent_bot[-1].get("content", ""):
            _is_receipt_context = True

    if _is_receipt_context:
        correction = _handle_signal_correction(text, user_name, memory_ctx, client, channel_id, thread_ts, thinking)
        if correction:
            return

    # --- DEBRIEF APPROVAL --- check if this is approve/skip reply to a debrief preview
    if context_type == "dm":
        recent_bot = [m for m in memory_ctx["messages"] if m.get("role") == "assistant"]
        if recent_bot and "Reply *approve* to ingest" in recent_bot[-1].get("content", ""):
            reply = text.strip().lower()
            if reply in ("approve", "skip"):
                handled = _handle_debrief_approval(
                    reply, user, memory_ctx, client, channel_id, thinking)
                if handled:
                    return

    # --- DISPATCH ---
    routing = dispatch(
        text=text, participant_count=participant_count,
        enrolled=enrolled, enrollment=user,
        active_exercise=active_exercise, slack_user_id=user_slack_id,
        bot_user_id=bot_user_id, context_type=context_type,
        has_bot_participated=has_bot_participated,
        recent_messages=memory_ctx["messages"][-5:],
        user=user,
    )

    if routing["character"] == "silent":
        if routing.get("signal_flag"):
            # Signal detected but not responding — keep thinking indicator
            # until extraction and receipt are done, then remove it.
            _background_extract(text, "", user_name,
                                signal_flag=True,
                                actions=[],
                                channel_id=channel_id, thread_ts=ts, client=client,
                                user_id=user["id"] if user else None)
            # Remove thinking after extraction (receipt was posted in thread)
            _delete_thinking(client, channel_id, thinking)
        else:
            # No signal — remove thinking immediately
            _handle_silent(client, channel_id, thinking, context_type, user_name, text)
        return

    # --- RESPOND (with streaming) ---
    history = window_messages(memory_ctx["messages"], get_max_messages(memory_ctx["store_type"]))
    _persist_input(memory_ctx, text, user_name, routing["annotation"])

    # Create streaming callback that updates the thinking message progressively
    stream_cb = _make_stream_callback(client, channel_id, thinking)

    response = _get_response(routing, history, user_name, participant_count,
                              enrollment=user, active_conversation=active_exercise,
                              on_chunk=stream_cb)

    # Store pending debrief/service-meeting extraction for approval flow
    if "Reply *approve* to ingest" in response:
        _store_pending_extraction(memory_ctx, routing.get("annotation"))

    # --- POST-PROCESS ---
    actions, response = _post_process(response, routing["annotation"])

    # --- DELIVER (final update with post-processed response) ---
    _persist_output(memory_ctx, response)
    _send_response(client, channel_id, thinking, response, respond)
    # If this was a top-level channel message answered in a new thread, seed
    # thread memory with both turns. Otherwise subsequent thread replies see
    # empty thread memory, dispatcher thinks the bot never participated, and
    # triage kicks in — producing a "Signal captured" receipt instead of a
    # conversational continuation.
    if context_type == "channel" and reply_thread_ts:
        _seed_thread_memory(reply_thread_ts, channel_id,
                             user["id"] if user else None,
                             text, user_name, response)
    # In DMs, always run extraction — the user is talking directly to Mother Tree
    # and may be sharing signals without the triage flagging them.
    # In channels, respect the triage signal_flag.
    # When Mother Tree already responded conversationally, run extraction silently
    # (no receipt — the conversation IS the acknowledgment).
    dm_always_extract = (context_type == "dm" and not routing.get("training_mode"))
    _background_extract(text, response, user_name,
                        signal_flag=routing["signal_flag"] or dm_always_extract,
                        actions=actions,
                        channel_id=channel_id, thread_ts=ts,
                        client=None, user_id=user["id"] if user else None)


# ---------------------------------------------------------------------------
# Phase: Respond — call the right character module
# ---------------------------------------------------------------------------

def _make_stream_callback(client, channel_id: str, thinking: dict | None):
    """Create a callback that updates the thinking message with streamed text."""
    if not thinking or thinking["type"] != "message":
        return None  # Can't stream into a reaction

    def callback(text_so_far: str):
        try:
            client.chat_update(channel=channel_id, ts=thinking["ts"], text=text_so_far + " ▌")
        except Exception:
            pass  # Non-critical — final update will fix it

    return callback


def _maybe_deliver_contextual_help(user_id: str, trigger: str, entry) -> str | None:
    """Deliver a contextual help tip if not already shown to this user."""
    from mothertree.graphql_client import has_help_been_delivered, record_help_delivered
    if has_help_been_delivered(user_id, entry.key):
        return None
    record_help_delivered(user_id, entry.key)
    return f"\n\n_💡 {entry.summary}_"


def _is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    import re
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))


def _handle_admin_command(annotation: dict) -> str:
    """Handle admin commands: make/remove admin, pending requests, admin enroll."""
    from mothertree.config import ADMIN_EMAIL
    from mothertree.graphql_client import (
        add_admin,
        create_user,
        get_pending_enrollment_requests,
        get_user_by_email,
        remove_admin,
        update_user_role,
    )

    action = annotation.get("action")

    if action == "make_admin":
        email = annotation.get("email")
        if not email:
            return "Usage: `make admin <email>`"
        if not _is_valid_email(email):
            return f"Invalid email: {email}"
        add_admin(email, granted_by="admin")
        return f"Admin granted to {email}."

    if action == "remove_admin":
        email = annotation.get("email")
        if not email:
            return "Usage: `remove admin <email>`"
        if not _is_valid_email(email):
            return f"Invalid email: {email}"
        if email.lower() == ADMIN_EMAIL.lower():
            return "Cannot remove the root admin."
        remove_admin(email)
        return f"Admin revoked for {email}."

    if action == "pending":
        pending = get_pending_enrollment_requests()
        if not pending:
            return "No pending enrollment requests."
        lines = ["*Pending enrollment requests:*"]
        for req in pending:
            lines.append(f"• {req['userId']} → {req['requestedRole']} ({req['createdAt'][:10]})")
        return "\n".join(lines)

    if action == "admin_enroll":
        email = annotation.get("email")
        role = annotation.get("role")
        if not email or not role:
            return "Usage: `enroll <email> as <role>`"
        if not _is_valid_email(email):
            return f"Invalid email: {email}"
        user = get_user_by_email(email)
        if user:
            update_user_role(user["id"], role)
            return f"Updated {email} to {role}."
        create_user(email, email.split("@")[0].title(), role)
        return f"Enrolled {email} as {role}."

    return "Unknown admin command."


def _extract_profile_fields(text: str) -> dict:
    """Extract profile fields from text via LLM."""
    from mothertree.llm import extract
    return extract(text, (
        "Extract personal profile fields from this message. "
        "Return JSON with keys: email, calendar_url, working_days (list of day names), phone. "
        "Set to null if not mentioned."
    ))


def _format_debrief_preview(extraction: dict) -> str:
    """Format debrief extraction as a preview with sensitivity markers."""
    lines = ["*Debrief extraction preview:*\n"]
    item_num = 0

    for category in ("entities", "pain_signals", "value_hooks", "actions"):
        items = extraction.get(category, [])
        if not items:
            continue
        label = category.replace("_", " ").title()
        lines.append(f"*{label}:*")
        for item in items:
            item_num += 1
            text = item.get("name") or item.get("signal") or item.get("hook") or item.get("action") or str(item)
            sensitive = item.get("sensitive", False)
            marker = "⚠️ " if sensitive else ""
            lines.append(f"  {item_num}. {marker}{text}")

    stage = extraction.get("stage", {}).get("current", "")
    if stage:
        lines.append(f"\n_Stage: {stage}_")

    lines.append("\n⚠️ = sensitive (will be dropped on approve)")
    lines.append("Reply *approve* to ingest, *edit* to remove items, or *skip* to discard.")
    return "\n".join(lines)


def _handle_account_review(annotation: dict) -> str:
    """Generate on-demand QBR synthesis for a company."""
    from discipline.qbr_review import synthesize_qbr
    from mothertree.graphql_client import graphql

    company_name = annotation.get("company")
    if not company_name:
        return "Usage: `review <company name>`"

    result = graphql("""
    query($name: String!) {
        allCompaniesList(filter: {name: {includesInsensitive: $name}}, first: 1) {
            id name
        }
    }
    """, {"name": company_name})
    companies = result.get("allCompaniesList", [])
    if not companies:
        return f"No company found matching '{company_name}'."

    company = companies[0]
    briefing = synthesize_qbr(company["id"], company["name"])
    return briefing


def _handle_account_plan(annotation: dict) -> str:
    """Create or update an account plan conversationally."""
    from mothertree.graphql_client import (
        create_account_plan,
        get_account_plan,
        graphql,
    )

    company_name = annotation.get("company")
    if not company_name:
        return "Usage: `account plan <company name>`"

    result = graphql("""
    query($name: String!) {
        allCompaniesList(filter: {name: {includesInsensitive: $name}}, first: 1) {
            id name clientSince services
            contactsByCompanyId: contactsList(first: 10) { name role }
        }
    }
    """, {"name": company_name})
    companies = result.get("allCompaniesList", [])
    if not companies:
        return f"No company found matching '{company_name}'. Create it first by mentioning them in a conversation."

    company = companies[0]
    plan = get_account_plan(company["id"])

    contacts = company.get("contactsByCompanyId", [])
    contact_lines = [f"• {c['name']} ({c.get('role', '?')})" for c in contacts] if contacts else ["• (none tracked)"]
    services = company.get("services") or []
    services_str = ", ".join(services) if services else "(not set)"

    if plan:
        return (
            f"*Account plan for {company['name']}:*\n\n"
            f"*Services:* {services_str}\n"
            f"*Stakeholders:*\n" + "\n".join(contact_lines) + "\n\n"
            f"*White space:* {plan.get('whiteSpace') or '(not set)'}\n"
            f"*Strategy:* {plan.get('strategy') or '(not set)'}\n"
            f"*Triggers:* {', '.join(plan.get('expansionTriggers') or []) or '(not set)'}"
        )

    create_account_plan(company["id"])
    return (
        f"*Account plan created for {company['name']}.*\n\n"
        f"*Services:* {services_str}\n"
        f"*Stakeholders:*\n" + "\n".join(contact_lines) + "\n\n"
        "Fields to fill: *white space*, *strategy*, *expansion triggers*.\n"
        "Use `account plan " + company["name"] + "` again to see the current state."
    )


def _handle_snooze(annotation: dict, user: dict | None) -> str:
    """Handle snooze — suppress Pulse nudges for a duration."""
    import re
    from datetime import UTC, datetime, timedelta

    from mothertree.graphql_client import set_user_snooze

    if not user or not user.get("id"):
        return "I need to know who you are first. Try enrolling with `enroll`."

    match = (annotation.get("match") or "").lower()

    if "tomorrow" in match or "morgen" in match:
        hours = 24
    elif "next week" in match or "volgende week" in match:
        hours = 7 * 24
    elif "weekend" in match:
        hours = 3 * 24
    else:
        m = re.search(r"in\s+(\d+)\s+(days?|weeks?|dagen|weken)", match)
        if m:
            n = int(m.group(1))
            unit = m.group(2)
            if "week" in unit or "weken" in unit:
                hours = n * 7 * 24
            else:
                hours = n * 24
        else:
            hours = 24

    until = (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
    set_user_snooze(user["id"], until)

    if hours <= 24:
        return "Snoozed until tomorrow."
    days = hours // 24
    return f"Snoozed for {days} days."


def _handle_account_list() -> str:
    """List all companies with account plans."""
    from mothertree.graphql_client import get_accounts_with_plans

    accounts = get_accounts_with_plans()
    if not accounts:
        return "No account plans yet. Say `account plan <company>` to start one."

    lines = ["*Account plans:*"]
    for a in accounts:
        company = a.get("companyByCompanyId", {})
        name = company.get("name", "?")
        next_qbr = a.get("nextQbr", "not set")
        lines.append(f"• *{name}* — QBR: {next_qbr}")
    return "\n".join(lines)


def _handle_service_meeting(annotation: dict) -> str:
    """Handle service meeting debrief — route to existing debrief pipeline."""
    content = annotation.get("content", "")
    if not content:
        return "Paste your service meeting notes after the command: `service meeting <notes>`"

    from bot.characters.spotter import extract_debrief
    extraction = extract_debrief(content)
    if extraction:
        return _format_debrief_preview(extraction)
    return "I couldn't extract anything meaningful from those notes. Try including more detail about attendees, topics discussed, and outcomes."


def _store_pending_extraction(memory_ctx: dict, annotation: dict | None) -> None:
    """Store extraction data for later approval. Uses conversation's pending_debrief field."""
    if not annotation:
        return
    store_id = memory_ctx.get("store_id")
    if not store_id or memory_ctx.get("store_type") != "dm":
        return
    from mothertree.graphql_client import set_pending_debrief
    pending = {
        "type": annotation.get("type"),   # "debrief" or "service_meeting"
        "content": annotation.get("content", ""),
    }
    try:
        set_pending_debrief(store_id, pending)
    except Exception:
        log.exception("Failed to store pending debrief")


def _handle_debrief_approval(reply: str, user: dict | None, memory_ctx: dict,
                              client, channel_id: str, thinking: dict | None) -> bool:
    """Handle approve/skip reply to a debrief extraction preview. Returns True if handled."""
    from mothertree.graphql_client import clear_pending_debrief, get_pending_debrief

    store_id = memory_ctx.get("store_id")
    if not store_id:
        return False

    pending = get_pending_debrief(store_id)
    if not pending:
        return False

    try:
        if reply == "skip":
            clear_pending_debrief(store_id)
            _resolve_thinking(client, channel_id, thinking, "Discarded.")
            from bot.memory import append_message
            append_message(memory_ctx, role="user", content="skip")
            append_message(memory_ctx, role="assistant", content="Discarded.")
            return True

        if reply == "approve":
            ann_type = pending.get("type", "debrief")
            content = pending.get("content", "")

            from bot.characters.spotter import extract_debrief
            extraction = extract_debrief(content)

            if not extraction:
                clear_pending_debrief(store_id)
                _resolve_thinking(client, channel_id, thinking,
                                  "Couldn't re-extract the data. Try submitting the notes again.")
                return True

            ingested = _ingest_debrief_extraction(extraction, user)

            if ann_type == "service_meeting":
                _advance_service_meeting(user)

            clear_pending_debrief(store_id)
            msg = f"Ingested {ingested} items."
            if ann_type == "service_meeting":
                msg += " Service meeting recorded."
            _resolve_thinking(client, channel_id, thinking, msg)
            from bot.memory import append_message
            append_message(memory_ctx, role="user", content="approve")
            append_message(memory_ctx, role="assistant", content=msg)
            return True

    except Exception:
        log.exception("Debrief approval failed")
        try:
            clear_pending_debrief(store_id)
        except Exception:
            pass
        _resolve_thinking(client, channel_id, thinking,
                          "Something went wrong ingesting the debrief. Try submitting the notes again.")
        return True

    return False


def _ingest_debrief_extraction(extraction: dict, user: dict | None) -> int:
    """Ingest non-sensitive items from a debrief extraction as interactions."""
    from mothertree.graphql_client import graphql

    count = 0
    user_id = user.get("id") if user else None

    for category in ("entities", "pain_signals", "value_hooks", "actions"):
        items = extraction.get(category, [])
        for item in items:
            if item.get("sensitive"):
                continue

            text = (item.get("name") or item.get("signal") or
                    item.get("hook") or item.get("action") or str(item))
            detail = item.get("detail") or item.get("context") or ""
            summary = f"[{category}] {text}"
            if detail:
                summary += f" — {detail}"

            try:
                graphql("""
                mutation($obj: InteractionInput!) {
                    createInteraction(input: {interaction: $obj}) {
                        interaction { id }
                    }
                }
                """, {"obj": {
                    "type": "meeting",
                    "summary": summary[:500],
                    "sourceRole": (user or {}).get("role", "hunter"),
                    "userId": user_id,
                }})
                count += 1
            except Exception:
                log.warning("Failed to ingest debrief item: %s", summary[:80])

    return count


def _advance_service_meeting(user: dict | None) -> None:
    """Advance the next service meeting date for the user's most recently due engagement."""
    from datetime import UTC, datetime, timedelta

    from mothertree.graphql_client import get_due_service_meetings, update_service_meeting

    if not user:
        return

    try:
        due = get_due_service_meetings()
        user_meetings = [e for e in due if e.get("ownerUserId") == user.get("id")]
        if not user_meetings:
            user_meetings = due[:1] if due else []

        if not user_meetings:
            log.info("No due service meetings found to advance")
            return

        eng = user_meetings[0]
        next_date = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%d")
        update_service_meeting(eng["id"], next_date=next_date)
    except Exception:
        log.exception("Failed to advance service meeting")


def _next_morning() -> str:
    """Return tomorrow at 08:00 UTC as ISO string."""
    from datetime import UTC, datetime, timedelta
    tomorrow = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return tomorrow.isoformat()


def _parse_reminder_time(text: str) -> tuple[str, str]:
    """Parse a time reference from text. Returns (iso_datetime, cleaned_text).

    Handles: "tomorrow", "Thursday", "Friday", "next week", "in N days",
    "later this week", "this afternoon", day names.
    Falls back to tomorrow morning if unparseable.
    """
    import re
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    lower = text.lower()

    # Strip leading time words for the clean context
    clean = re.sub(
        r"^(tomorrow|today|tonight|this\s+(morning|afternoon|evening|week)|"
        r"next\s+week|later(\s+this\s+week)?|on\s+\w+day|"
        r"in\s+\d+\s+(days?|hours?|weeks?)|"
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday))\s*,?\s*",
        "", lower, count=1
    ).strip()

    # "tomorrow"
    if "tomorrow" in lower:
        dt = now.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return dt.isoformat(), clean

    # "today" / "this afternoon"
    if "today" in lower or "this afternoon" in lower:
        dt = now.replace(hour=14, minute=0, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(days=1)
        return dt.isoformat(), clean

    # "next week"
    if "next week" in lower:
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        dt = (now + timedelta(days=days_until_monday)).replace(hour=8, minute=0, second=0, microsecond=0)
        return dt.isoformat(), clean

    # "later this week" / "later"
    if "later this week" in lower or "later" in lower:
        # 2 days from now, morning
        dt = (now + timedelta(days=2)).replace(hour=8, minute=0, second=0, microsecond=0)
        return dt.isoformat(), clean

    # "in N days/hours/weeks"
    m = re.search(r"in\s+(\d+)\s+(days?|hours?|weeks?)", lower)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if "hour" in unit:
            dt = now + timedelta(hours=n)
        elif "week" in unit:
            dt = (now + timedelta(weeks=n)).replace(hour=8, minute=0, second=0, microsecond=0)
        else:
            dt = (now + timedelta(days=n)).replace(hour=8, minute=0, second=0, microsecond=0)
        return dt.isoformat(), clean

    # Day names: Monday-Sunday
    day_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    for day_name, day_num in day_map.items():
        if day_name in lower:
            days_ahead = (day_num - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next occurrence, not today
            dt = (now + timedelta(days=days_ahead)).replace(hour=8, minute=0, second=0, microsecond=0)
            return dt.isoformat(), clean

    # Fallback: tomorrow morning
    dt = now.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return dt.isoformat(), text  # Don't clean text if we couldn't parse time


def _handle_nudge(annotation: dict, user: dict | None) -> str:
    """Schedule a nudge DM to another user."""
    if not user or not user.get("id"):
        return "I need to know who you are first."

    target_name = annotation.get("target", "")
    context = annotation.get("context", "")

    if not target_name:
        return "Usage: `nudge <name> <message>`"

    # Find the target user
    target = find_user_by_name(target_name)
    if not target:
        return f"I don't know anyone named '{target_name}'. They need to be enrolled first."

    if not context:
        return f"What should I tell {target['name']}? Usage: `nudge {target_name} <message>`"

    # Parse timing from context
    remind_at, clean_context = _parse_reminder_time(context)

    reminder = create_reminder(
        creator_user_id=user["id"],
        target_user_id=target["id"],
        remind_at=remind_at,
        context=clean_context or context,
    )

    if not reminder:
        return "Something went wrong creating the reminder."

    target_first = target["name"].split()[0]
    if remind_at == _next_morning():
        return f"I'll nudge {target_first} tomorrow morning."
    return f"Reminder set for {target_first}. I'll deliver it when the time comes."


def _handle_self_remind(annotation: dict, user: dict | None) -> str:
    """Schedule a reminder for the current user."""
    if not user or not user.get("id"):
        return "I need to know who you are first."

    context = annotation.get("context", "")
    if not context:
        return "What should I remind you about?"

    remind_at, clean_context = _parse_reminder_time(context)

    reminder = create_reminder(
        creator_user_id=user["id"],
        target_user_id=user["id"],
        remind_at=remind_at,
        context=clean_context or context,
    )

    if not reminder:
        return "Something went wrong creating the reminder."

    if remind_at == _next_morning():
        return "I'll remind you tomorrow morning."
    return "Reminder set. I'll ping you when it's time."


def _get_response(routing: dict, history: list, user_name: str, participant_count: int,
                  enrollment=None, active_conversation=None, on_chunk=None) -> str:
    """Call the right character module and return the raw response."""
    character = routing["character"]
    clean_text = routing["clean_text"]
    annotation = routing["annotation"]
    signal_flag = routing["signal_flag"]
    exercise_pending = routing["exercise_pending"]

    try:
        if annotation and annotation.get("type") == "admin":
            return _handle_admin_command(annotation)

        if annotation and annotation.get("type") == "account_review":
            return _handle_account_review(annotation)

        if annotation and annotation.get("type") == "account_plan":
            return _handle_account_plan(annotation)

        if annotation and annotation.get("type") == "account_list":
            return _handle_account_list()

        if annotation and annotation.get("type") == "service_meeting":
            return _handle_service_meeting(annotation)

        if annotation and annotation.get("type") == "help":
            from mothertree.handbook import Handbook
            hb = Handbook("handbook")
            topic = annotation.get("topic")
            role = (enrollment or {}).get("role", "citizen")
            if topic:
                entry = hb.entries.get(topic) or next(
                    (e for e in hb.for_role(role) if topic.lower() in e.key or topic.lower() in e.summary.lower()), None)
                if entry:
                    return entry.content
                return f"I don't have help on '{topic}'. Say *help* to see all topics."
            grouped = hb.grouped_by_topic(role)
            lines = ["Here's what I can help with:\n"]
            for topic_name, entries in grouped.items():
                lines.append(f"*{topic_name.replace('_', ' ').title()}*")
                for e in entries:
                    lines.append(f"  • {e.summary}")
            lines.append("\nSay *help [topic]* for details.")
            return "\n".join(lines)

        if annotation and annotation.get("type") == "snooze":
            return _handle_snooze(annotation, enrollment)

        if annotation and annotation.get("type") == "nudge":
            return _handle_nudge(annotation, enrollment)

        if annotation and annotation.get("type") == "self_remind":
            return _handle_self_remind(annotation, enrollment)

        if annotation and annotation.get("type") == "debrief":
            from bot.characters.spotter import extract_debrief
            content = annotation.get("content", clean_text)
            extraction = extract_debrief(content)
            if extraction:
                return _format_debrief_preview(extraction)
            return "I couldn't extract anything meaningful from that debrief. Try including more detail about attendees, topics discussed, and outcomes."

        # Profile fields detected — extract + persist, then inform the LLM what
        # was stored so it acknowledges accurately instead of confabulating.
        if routing.get("profile_detected") and enrollment and enrollment.get("id"):
            try:
                from mothertree.graphql_client import update_user_profile
                fields = _extract_profile_fields(clean_text)
                saved = {k: v for k, v in fields.items() if v is not None}
                if saved:
                    update_user_profile(enrollment["id"], **saved)
                    log.info(f"Profile side-effect: saved {list(saved)} for user {enrollment['id']}")
                    # Replace whatever annotation dispatcher set (often url_content
                    # for a pasted iCal URL) with the factual profile_saved ack.
                    # The user shared a profile detail; the bot's job is to confirm
                    # the store, not to discuss the URL's fetched content.
                    routing["annotation"] = {
                        "type": "profile_saved",
                        "fields": saved,
                    }
                    annotation = routing["annotation"]
            except Exception:
                log.exception("Profile field extraction failed")

        if routing["training_mode"]:
            return _training_response(clean_text, history, user_name,
                                       participant_count, annotation, exercise_pending,
                                       enrollment=enrollment,
                                       active_conversation=active_conversation)

        if character == "seth":
            from bot.characters.seth import respond
            return respond(question=clean_text, history=history,
                           user_name=user_name, participant_count=participant_count,
                           annotation=annotation, on_chunk=on_chunk)

        if character == "lawrence":
            from bot.characters.lawrence import respond
            return respond(question=clean_text, history=history,
                           user_name=user_name, participant_count=participant_count,
                           annotation=annotation, on_chunk=on_chunk)

        # Default: Mother Tree
        from bot.characters.mother_tree import respond
        return respond(question=clean_text, history=history,
                       user_name=user_name, participant_count=participant_count,
                       annotation=annotation, signal_flag=signal_flag,
                       exercise_pending=exercise_pending,
                       user_id=enrollment.get("id") if enrollment else None,
                       on_chunk=on_chunk)

    except Exception:
        log.exception(f"Character {character} respond failed")
        return _fallback(annotation)


def _training_response(text: str, history: list, user_name: str,
                        participant_count: int, annotation: dict,
                        exercise_pending: dict,
                        enrollment=None, active_conversation=None) -> str:
    """Training mode — delegate to operations.py for state transitions."""
    from training import operations

    if not annotation:
        return _trainer_character_response(text, history, user_name,
                                            participant_count, annotation)

    ann_type = annotation.get("type", "")

    if ann_type == "enroll":
        role = annotation.get("role")
        if not role:
            return "Which role? Reply: *enroll hunter*, *enroll gatherer*, *enroll farmer*, or *enroll citizen*."
        email = annotation.get("email", "")
        return operations.enroll(email=email, name=user_name, role=role)

    if ann_type == "training_next":
        if not enrollment:
            return "You're not enrolled yet. Reply *enroll hunter* to get started."
        return operations.deliver_chapter(enrollment)

    if ann_type == "exercise_go":
        return operations.start_exercises(active_conversation)

    if ann_type == "answer":
        if not active_conversation or not enrollment:
            return "No active exercise. Reply *next* to start a chapter."
        return operations.score_answer(active_conversation, enrollment, annotation.get("answer", ""))

    if ann_type == "practice":
        return "Practice mode coming soon."

    # Freeform training conversation — add exercise context if active
    training_context = annotation or {}
    if active_conversation and active_conversation.get("current_question", -1) >= 0:
        exercise = active_conversation.get("exercise", {}).get("content", {})
        questions = exercise.get("questions", [])
        current_q = active_conversation["current_question"]
        if current_q < len(questions):
            training_context = dict(training_context)
            training_context["active_question"] = questions[current_q]["question"]
            training_context["exercise_rules"] = (
                "The user has an active exercise question. "
                "NEVER reveal the correct answer. NEVER say which option is right. "
                "You may clarify the question, give hints about how to think about it, "
                "or encourage them to make their choice. But the answer must come from them."
            )
    return _trainer_character_response(text, history, user_name,
                                        participant_count, training_context)


def _trainer_character_response(text: str, history: list, user_name: str,
                                  participant_count: int, annotation: dict) -> str:
    """Route freeform training messages to the trainer character."""
    trainer = "seth"
    if annotation and annotation.get("trainer"):
        trainer = annotation["trainer"]
    if trainer == "lawrence":
        from bot.characters.lawrence import respond
    elif trainer == "mother_tree":
        from bot.characters.mother_tree import respond
    else:
        from bot.characters.seth import respond
    return respond(question=text, history=history,
                   user_name=user_name, participant_count=participant_count,
                   annotation=annotation)


def _fallback(annotation: dict = None) -> str:
    """Static fallback when a character handler or LLM call fails.

    For annotations with structured data (enrolled, status, ...) we render
    the data directly. For direct-handler intents (snooze, nudge, debrief, ...)
    we surface what the bot was trying to do — a silent "Something went wrong"
    leaves the user unable to tell whether they were misheard, mis-routed, or
    the platform crashed.
    """
    if annotation is None:
        return "Sorry, I'm having trouble thinking right now. Try again in a moment."
    ann_type = annotation.get("type", "")
    templates = {
        # Data-render fallbacks: LLM failed but the annotation has the payload.
        "enrolled": "Welcome to Mother Tree, {name}. Enrolled as {role}.",
        "status": "Stage {stage}, Chapter {chapter}. Streak: {streak} days.",
        "stats": "Stats loaded.",
        "help": "Just talk to me. In DMs: enroll, status, next, go, practice, ask seth/lawrence. In channels: @Mother Tree followed by your question.",
        "progress": "Progress loaded.",
        "answer": "{feedback}",
        "training_next": "{content}",
        "exercise_go": "{question}",
        "practice": "{content}",
        "citizen_inspiration": "{content}",
        "error": "{message}",
        # Direct-handler failures: say what was attempted so the user can react.
        "snooze": "I read that as a snooze request (matched '{match}') but couldn't save it. If you didn't mean to snooze, ignore me — I'll get smarter.",
        "nudge": "Couldn't set the nudge for *{target}*. Try again in a moment, or DM me `nudge {target} <message>`.",
        "self_remind": "Couldn't set the reminder. Try `remind me <when> <what>`.",
        "debrief": "Couldn't process the debrief just now. Try sending the notes again.",
        "service_meeting": "Couldn't log the service meeting. Try again in a moment.",
        "account_plan": "Couldn't update the account plan. Try again in a moment.",
        "account_review": "Couldn't load the account review. Try again in a moment.",
        "account_list": "Couldn't list account plans. Try again in a moment.",
        "pipeline": "Couldn't load the pipeline view. Try again in a moment.",
        "brief": "Couldn't run the brief. Try again in a moment.",
        "admin": "Admin command failed. Try again in a moment.",
        "completion": "Got it — but couldn't update the trail. Try again in a moment.",
    }
    template = templates.get(ann_type, "Something went wrong. Try again in a moment.")
    try:
        return template.format(**annotation)
    except (KeyError, IndexError):
        return template


# ---------------------------------------------------------------------------
# Phase: Post-process — markers, formatting
# ---------------------------------------------------------------------------

def _post_process(response: str, annotation: dict = None) -> tuple[list[str], str]:
    """Extract markers, replace content, fix formatting. Returns (actions, clean_response)."""
    # Guard against Mistral tool-calling syntax
    if response.startswith("[TOOL_CALLS]"):
        log.warning("LLM returned tool-calling syntax: %s", response[:200])
        response = _fallback(annotation)

    actions, response = extract_action_markers(response)

    content_types, response = extract_content_markers(response)
    if "training" in content_types and annotation and annotation.get("content"):
        response = f"{response}\n\n{annotation['content']}" if response else annotation["content"]

    response = fix_slack_formatting(response)
    return actions, response


# ---------------------------------------------------------------------------
# Phase: Deliver — send, persist, extract
# ---------------------------------------------------------------------------

def _persist_input(memory_ctx: dict, text: str, user_name: str, annotation: dict = None):
    """Persist user message and annotation to memory."""
    try:
        append_message(memory_ctx, role="user", content=text, name=user_name)
    except Exception:
        log.exception("Failed to persist user message")
    if annotation:
        try:
            append_message(memory_ctx, role="system", content=json.dumps(annotation))
        except Exception:
            log.exception("Failed to persist annotation")


def _persist_output(memory_ctx: dict, response: str):
    """Persist assistant response to memory."""
    try:
        append_message(memory_ctx, role="assistant", content=response)
    except Exception:
        log.exception("Failed to persist assistant response")


def _send_response(client, channel_id: str, thinking: dict, response: str, respond_callback):
    """Send the response to Slack."""
    if len(response) > 3900:
        log.warning(f"Response too long ({len(response)} chars) — character should keep under 2500")
    updated = _resolve_thinking(client, channel_id, thinking, response)
    if not updated:
        log.warning("Thinking resolve failed, trying respond callback")
        try:
            respond_callback(response)
        except Exception:
            log.exception("Respond callback also failed")


def _generate_clarifying_question(spotter_result: dict, user_message: str) -> str | None:
    """Generate a natural clarifying question based on what the Spotter found incomplete.

    Returns a short question, or None if the signal is already rich enough.
    The question serves dual purpose: enriches the signal AND transparently
    acknowledges that Mother Tree noticed something worth remembering.
    """
    if not spotter_result:
        return None

    entities = spotter_result.get("entities", [])
    pain_signals = spotter_result.get("pain_signals", [])
    actions = spotter_result.get("actions", [])
    stage = spotter_result.get("stage", {})

    gaps = []

    # Entity gaps — names without roles, companies without context
    for e in entities:
        if e.get("type") == "person" and not e.get("role"):
            gaps.append(f"what {e.get('name', 'they')} do")
        if e.get("type") == "organization" and not e.get("context"):
            gaps.append(f"what {e.get('name', 'they')} are working on")

    # Pain detected but no specifics
    if pain_signals and not any(p.get("evidence") for p in pain_signals):
        gaps.append("what's driving the urgency")

    # Actions without timing
    for a in actions:
        if a.get("action") and not a.get("by_when"):
            gaps.append("when that should happen")
            break

    # Stage is early and could use more context
    if stage.get("current") in ("soil", "signal") and not pain_signals:
        gaps.append("what challenge they're facing")

    if not gaps:
        return None

    # Pick the most useful gap (first one) and phrase naturally
    gap = gaps[0]
    from mothertree.llm import generate
    question = generate(
        "You are Mother Tree. You just noticed a commercial signal in a team conversation. "
        "Ask ONE brief, natural follow-up question to learn more. Be warm, curious, not interrogative. "
        "One sentence max. Sound like a colleague, not a system.",
        f"The team member said: \"{user_message[:200]}\"\n"
        f"You want to know: {gap}\n"
        f"Ask naturally:",
    )
    return question.strip().strip('"')


def _handle_signal_correction(text: str, user_name: str, memory_ctx: dict,
                              client, channel_id: str, thread_ts: str,
                              thinking: dict | None) -> bool:
    """Handle corrections to a signal receipt.

    Parses corrections like "i am Jurg", "agnostict -> Aknostic", "the meeting
    is next Thursday", and updates records accordingly. Returns True if handled.
    """
    try:
        from mothertree.llm import _parse_json, generate

        # Get the original receipt for context
        bot_messages = [m for m in memory_ctx["messages"] if m.get("role") == "assistant"]
        receipt = bot_messages[-1].get("content", "") if bot_messages else ""

        # Handle opportunity confirmation ("yes" reply to opportunity prompt)
        if text.strip().lower() in ("yes", "ja", "confirm", "track it", "yes please") and "Opportunity detected" in receipt:
            try:
                import re
                match = re.search(r"📋 \*Opportunity detected:\*\n\s+(.+?) — (\w+) stage", receipt)
                if match:
                    company_name = match.group(1)
                    stage = match.group(2).lower()
                    from mothertree.entities import find_or_create_company, find_or_create_opportunity
                    company = find_or_create_company(company_name)
                    company_id = company.get("id") if isinstance(company, dict) else None
                    if company_id:
                        find_or_create_opportunity(company_id=company_id, stage=stage)
                        _resolve_thinking(client, channel_id, thinking,
                                          f"✅ Tracking *{company_name}* as an opportunity ({stage} stage).")
                        from bot.memory import append_message
                        append_message(memory_ctx, role="user", content=text, name=user_name)
                        append_message(memory_ctx, role="assistant",
                                       content=f"Tracking {company_name} as opportunity ({stage})")
                        return True
            except Exception:
                log.exception("Opportunity creation failed")

        # Parse the correction into structured updates
        raw = generate(
            "You are Mother Tree. A team member replied to a signal receipt with corrections. "
            "Parse their reply into structured updates. Return valid JSON only.\n\n"
            "Format: {\"corrections\": [{\"type\": \"rename\", \"from\": \"old\", \"to\": \"new\"}, "
            "{\"type\": \"identity\", \"name\": \"X\", \"is_existing\": \"Y\"}, "
            "{\"type\": \"date\", \"action\": \"...\", \"date\": \"...\"}, "
            "{\"type\": \"info\", \"about\": \"...\", \"detail\": \"...\"}]}\n"
            "Types: rename (fix a name/typo), identity (confirm who someone is), "
            "date (add timing), info (add context).\n"
            "If you can't parse it, return {\"corrections\": []}.",
            f"Original receipt:\n{receipt}\n\nUser correction:\n{text}",
        )
        corrections = _parse_json(raw).get("corrections", [])

        if not corrections:
            return False  # Didn't parse as corrections — let normal flow handle it

        # Apply corrections
        from mothertree.graphql_client import graphql
        applied = []

        for c in corrections:
            ctype = c.get("type", "")
            try:
                if ctype == "rename":
                    old_name = c.get("from", "")
                    new_name = c.get("to", "")
                    if old_name and new_name:
                        # Try contacts first
                        result = graphql("""
query($name: String!) {
    allContactsList(filter: {name: {includesInsensitive: $name}}, first: 1) { id name }
}
""", {"name": old_name})
                        contacts = result.get("allContactsList", [])
                        if contacts:
                            graphql("""
                            mutation($id: UUID!, $patch: ContactPatch!) {
                              updateContactById(input: {id: $id, contactPatch: $patch}) { contact { id } }
                            }
                            """, {"id": contacts[0]["id"], "patch": {"name": new_name, "fullName": new_name}})
                            applied.append(f"Renamed contact: {old_name} → {new_name}")
                        else:
                            # Try companies
                            result = graphql("""
query($name: String!) {
    allCompaniesList(filter: {name: {includesInsensitive: $name}}, first: 1) { id name }
}
""", {"name": old_name})
                            companies = result.get("allCompaniesList", [])
                            if companies:
                                graphql("""
                                mutation($id: UUID!, $patch: CompanyPatch!) {
                                  updateCompanyById(input: {id: $id, companyPatch: $patch}) { company { id } }
                                }
                                """, {"id": companies[0]["id"], "patch": {"name": new_name}})
                                applied.append(f"Renamed company: {old_name} → {new_name}")

                elif ctype == "identity":
                    name = c.get("name", "")
                    is_existing = c.get("is_existing", "")
                    if name and is_existing:
                        # Merge: find both contacts, keep the existing one
                        applied.append(f"Noted: {name} is {is_existing}")

                elif ctype == "date":
                    action = c.get("action", "")
                    date_str = c.get("date", "")
                    if action and date_str:
                        from bot.extraction import _parse_date
                        parsed = _parse_date(date_str)
                        if parsed:
                            applied.append(f"Date set: {action} → {parsed}")
                        else:
                            applied.append(f"Noted date for: {action} → {date_str}")

                elif ctype == "info":
                    about = c.get("about", "")
                    detail = c.get("detail", "")
                    if about and detail:
                        applied.append(f"Noted: {about} — {detail}")

            except Exception:
                log.exception("Failed to apply correction: %s", c)

        # Confirm what was updated
        if applied:
            _resolve_thinking(client, channel_id, thinking,
                              "✅ Updated:\n" + "\n".join(f"• {a}" for a in applied))
        else:
            _resolve_thinking(client, channel_id, thinking,
                              "Got it — noted for context.")

        # Persist the correction to thread memory
        from bot.memory import append_message
        append_message(memory_ctx, role="user", content=text, name=user_name)
        append_message(memory_ctx, role="assistant",
                       content="✅ " + "; ".join(applied) if applied else "Noted.")

        return True

    except Exception:
        log.exception("Signal correction handling failed")
        return False  # Fall through to normal processing


def _background_extract(text: str, response: str, user_name: str,
                         signal_flag: bool, actions: list[str],
                         channel_id: str = None, thread_ts: str = None,
                         client=None, user_id: str = None):
    """Background signal extraction and action assessment.

    When a signal is captured, posts a clarifying question in the thread.
    This both enriches the signal AND transparently acknowledges that
    Mother Tree noticed something worth remembering.
    """
    if signal_flag or "capture_signal" in actions:
        try:
            # Run Spotter first to check what we captured
            from bot.characters.spotter import extract as spotter_extract
            spotter_result = spotter_extract(text, response, user_name)

            extraction_result = extract_signal(user_message=text, assistant_response=response,
                                               user_name=user_name, user_id=user_id)

            # Ask a clarifying question — uncertain entities, gaps, or incomplete signals
            if client and channel_id and (signal_flag or spotter_result):
                try:
                    import time  # noqa: I001

                    uncertain = extraction_result.get("uncertain", [])
                    gaps = extraction_result.get("gaps", [])

                    # Build context for the conversational receipt
                    receipt_data = {}
                    if spotter_result:
                        entities = spotter_result.get("entities", [])
                        receipt_data["people"] = [e.get("name") for e in entities if e.get("type") == "person"]
                        receipt_data["companies"] = [e.get("name") for e in entities
                                                      if e.get("type") == "organization"
                                                      and e.get("name", "").lower() not in ("aknostic",)]
                        receipt_data["stage"] = (spotter_result.get("stage") or {}).get("current", "")
                        receipt_data["actions"] = [a.get("action", a.get("what", ""))
                                                    for a in spotter_result.get("actions", [])
                                                    if isinstance(a, dict)][:3]

                    clarify_items = []
                    for u in uncertain[:2]:
                        if isinstance(u, dict) and u.get("entity"):
                            clarify_items.append(f"is {u['entity']} someone we already know?")
                        elif isinstance(u, str) and u.strip():
                            clarify_items.append(u)
                    for g in gaps[:3]:
                        clarify_items.append(str(g).replace("(couldn't parse 'Unknown')", "— when?"))
                    receipt_data["questions"] = clarify_items

                    # Check for opportunity
                    opp_company = None
                    if receipt_data.get("stage", "").lower() in ("signal", "reframe", "diagnosis", "proposal"):
                        if receipt_data.get("companies"):
                            opp_company = receipt_data["companies"][0]

                    # Generate conversational receipt via LLM
                    if receipt_data.get("people") or receipt_data.get("companies"):
                        from mothertree.llm import generate
                        receipt = generate(
                            "You are Mother Tree. You just captured a commercial signal from a team "
                            "conversation. Write a brief, conversational acknowledgment (3-5 lines). "
                            "Mention who and what company you noticed. If there are questions, ask "
                            "them naturally. If there's a potential opportunity, ask if you should "
                            "track it. Sound like a colleague who was paying attention — warm, brief, "
                            "not a database report. End with 'correct me if I got something wrong.'",
                            f"Signal data: {receipt_data}"
                            + (f"\nPotential opportunity: {opp_company} at {receipt_data['stage']} stage"
                               if opp_company else ""),
                        )
                        # Ensure "Signal captured" is in receipt for correction handler detection
                        if "Signal captured" not in receipt:
                            receipt = "🌱 Signal captured.\n\n" + receipt

                        time.sleep(8)
                        client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=thread_ts or "",
                            text=receipt,
                        )
                        # Persist receipt to thread memory so correction handler can find it
                        try:
                            from bot.memory import append_message
                            from mothertree.graphql_client import get_or_create_thread_memory
                            if thread_ts:
                                get_or_create_thread_memory(thread_ts, channel_id)
                                append_thread_msg = {
                                    "messages": [],
                                    "store_type": "thread",
                                    "thread_ts": thread_ts,
                                    "channel_id": channel_id,
                                }
                                append_message(append_thread_msg, role="assistant", content=receipt)
                        except Exception:
                            log.warning("Failed to persist receipt to thread memory")
                except Exception:
                    log.exception("Clarifying question generation failed")
        except Exception:
            log.exception("Background signal extraction failed")

    if actions:
        try:
            assessment = assess_actions(text, response)
            if "ci_save" in actions and not assessment.get("ci_save"):
                log.warning("Action marker ci_save present but assessment disagrees")
            if "capture_signal" in actions and not assessment.get("capture_signal"):
                log.warning("Action marker capture_signal present but assessment disagrees")
        except Exception:
            log.exception("Action assessment failed")


def _handle_silent(client, channel_id: str, thinking: dict,
                    context_type: str, user_name: str, text: str):
    """Handle silent routing — delete thinking, buffer message."""
    _delete_thinking(client, channel_id, thinking)
    if context_type == "channel":
        channel_buffer.add(channel_id, {"role": "user", "name": user_name, "content": text})
        if channel_buffer.should_flush(channel_id):
            _flush_buffer(channel_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_user(slack_user_id: str, client, participant_count: int):
    """Resolve Slack user to Mother Tree user.
    In DMs (participant_count == 1): full resolution with auto-create.
    In channels: resolve only if channel_link already exists (no Slack API call, no auto-create).
    """
    from mothertree.graphql_client import get_channel_link, get_user
    from mothertree.identity import resolve_user
    if participant_count == 1:
        user = resolve_user(slack_user_id, client)
    else:
        link = get_channel_link("slack", slack_user_id)
        user = get_user(link["userId"]) if link else None
    if not user:
        return None, None, False
    active_exercise = get_active_conversation(user["id"]) if participant_count == 1 else None
    enrolled = user.get("role") != "citizen" or user.get("currentStage", 0) > 0
    return user, active_exercise, enrolled


def _get_memory_context(context_type: str, user_id: str,
                         channel_id: str, thread_ts: str) -> dict:
    """Get the right memory store for the context."""
    if context_type == "dm":
        return get_memory(context_type="dm", user_id=user_id)
    if context_type == "channel":
        return get_memory(context_type="channel", channel_id=channel_id)
    return get_memory(context_type="thread", thread_ts=thread_ts, channel_id=channel_id,
                      owner_user_id=user_id)


def _seed_thread_memory(thread_ts: str, channel_id: str, user_id: str | None,
                         user_text: str, user_name: str, bot_response: str) -> None:
    """Seed a freshly-opened thread with the triggering user turn + bot reply.

    When Mother Tree replies to a top-level channel message, the response is
    posted as the first message in a new thread. Without this seed the thread
    memory stays empty and subsequent thread replies look like unseen traffic
    to the dispatcher — which then runs triage and posts "Signal captured"
    receipts instead of continuing the conversation.

    Idempotent: only seeds when the thread memory is empty.
    """
    try:
        thread_mem = get_memory(context_type="thread", thread_ts=thread_ts,
                                channel_id=channel_id, owner_user_id=user_id)
        if thread_mem.get("messages"):
            return  # Already seeded or populated
        append_message(thread_mem, role="user", content=user_text, name=user_name)
        append_message(thread_mem, role="assistant", content=bot_response)
    except Exception:
        log.exception("Failed to seed thread memory from channel context")


def _get_channel_lock(channel_id: str) -> threading.Lock:
    with _locks_lock:
        if channel_id not in _channel_locks:
            _channel_locks[channel_id] = threading.Lock()
        return _channel_locks[channel_id]


# ---------------------------------------------------------------------------
# Thinking indicator
# ---------------------------------------------------------------------------

def _post_thinking(client, channel_id: str, thread_ts: str | None,
                   context_type: str = "dm", message_ts: str | None = None) -> dict | None:
    """Show thinking indicator."""
    try:
        log.info(f"Thinking: context_type={context_type}, message_ts={message_ts}, thread_ts={thread_ts}")
        if context_type == "channel" and message_ts:
            client.reactions_add(name=THINKING_EMOJI, channel=channel_id, timestamp=message_ts)
            return {"type": "reaction", "ts": message_ts}
        result = client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text="_thinking..._")
        return {"type": "message", "ts": result["ts"]}
    except Exception as e:
        log.warning(f"Failed to post thinking indicator: {e}")
        return None


def _resolve_thinking(client, channel_id: str, thinking: dict | None, response: str):
    """Replace thinking indicator with the real response."""
    if not thinking:
        return None
    try:
        log.info(f"Resolving thinking: type={thinking['type']}, response_len={len(response)}")
        if thinking["type"] == "reaction":
            try:
                client.reactions_remove(name=THINKING_EMOJI, channel=channel_id, timestamp=thinking["ts"])
            except Exception:
                pass
            result = client.chat_postMessage(channel=channel_id, thread_ts=thinking["ts"], text=response)
            log.info(f"Posted thread response: {result.get('ok')}, ts={result.get('ts')}")
            return result["ts"]
        result = client.chat_update(channel=channel_id, ts=thinking["ts"], text=response)
        log.info(f"Updated message: {result.get('ok')}, ts={result.get('ts')}")
        return thinking["ts"]
    except Exception as e:
        log.exception(f"Failed to resolve thinking indicator: {e}")
        return None


def _delete_thinking(client, channel_id: str, thinking: dict | None):
    """Remove thinking indicator."""
    if not thinking:
        return
    try:
        if thinking["type"] == "reaction":
            client.reactions_remove(name=THINKING_EMOJI, channel=channel_id, timestamp=thinking["ts"])
        else:
            client.chat_delete(channel=channel_id, ts=thinking["ts"])
    except Exception:
        pass


def _flush_buffer(channel_id: str):
    """Flush buffered messages to channel memory."""
    from mothertree.graphql_client import append_channel_message, get_or_create_channel_memory
    messages = channel_buffer.flush(channel_id)
    if not messages:
        return
    try:
        get_or_create_channel_memory(channel_id)
        for msg in messages:
            append_channel_message(channel_id, role=msg["role"], content=msg["content"], name=msg.get("name"))
    except Exception:
        log.exception(f"Failed to flush buffer for channel {channel_id}")
