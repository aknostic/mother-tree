"""Pulse scanner — three scan types that run sequentially.

1. Due reminders (threads with remind_after <= now)
2. Stale threads and contacts (activity lapsed beyond threshold)
3. Pipeline nudges (opportunities stuck in a stage)

Each scan queries via GraphQL, generates a nudge via Mistral Small,
and delivers a DM via Slack.
"""

import logging
import random
import time
from datetime import UTC, datetime

from slack_sdk import WebClient

from bot.characters.pulse import generate_nudge
from mothertree.config import SLACK_BOT_TOKEN
from mothertree.graphql_client import (
    clear_thread_remind_after,
    get_due_reminders,
    get_slack_user_id,
    get_stale_contacts_for_pulse,
    get_stale_opportunities,
    get_stale_threads,
    graphql,
    mark_company_pulse_nudged,
    mark_contact_pulse_nudged,
    mark_opportunity_pulse_nudged,
    mark_thread_pulse_nudged,
    search_similar,
)

log = logging.getLogger(__name__)

# Stage-aware thresholds (days) — calibrated for 12-24 month sales cycles
STAGE_THRESHOLDS = {
    "soil": 60,
    "signal": 30,
    "reframe": 21,
    "diagnosis": 14,
    "proposal": 21,
    "converted": 30,
}

# Contact temperature thresholds (days)
CONTACT_THRESHOLDS = {
    "hot": 14,
    "warm": 30,
    # cold: not nudged
}

# Minimum days between nudges for the same item
MIN_NUDGE_INTERVAL_DAYS = 7


def _is_snoozed(user_id: str | None) -> bool:
    """Check if a user has snoozed Pulse nudges."""
    if not user_id:
        return False
    from mothertree.graphql_client import is_user_snoozed
    return is_user_snoozed(user_id)


def _recently_nudged(pulse_nudged_at: str | None, min_days: int = MIN_NUDGE_INTERVAL_DAYS) -> bool:
    """Check if an item was nudged too recently."""
    if not pulse_nudged_at:
        return False
    nudged = datetime.fromisoformat(pulse_nudged_at)
    if nudged.tzinfo is None:
        nudged = nudged.replace(tzinfo=UTC)
    return (datetime.now(UTC) - nudged).days < min_days


def _get_thread_stage(thread: dict) -> str | None:
    """Look up the pipeline stage for a thread via its owner's opportunities."""
    owner = thread.get("ownerUserId")
    if not owner:
        return None
    try:
        result = graphql("""
        query($owner: UUID!) {
            allOpportunitiesList(
                filter: {ownerUserId: {equalTo: $owner}},
                orderBy: UPDATED_AT_DESC,
                first: 1
            ) { stage }
        }
        """, {"owner": owner})
        opps = result.get("allOpportunitiesList", [])
        return opps[0]["stage"] if opps else None
    except Exception:
        log.warning("Stage lookup failed for thread %s", thread.get("threadTs"))
        return None


def _get_all_hunters() -> list[dict]:
    """Fallback: get all active hunters for items without an owner."""
    result = graphql("""
    query {
        allUsersList(condition: {role: "hunter", active: true}) {
            id name
        }
    }
    """)
    return result.get("allUsersList", [])


def _send_dm(slack: WebClient, recipient: str, message: str) -> None:
    """Send a DM to a Slack user."""
    try:
        slack.chat_postMessage(channel=recipient, text=message)
    except Exception:
        log.exception("Failed to send Pulse DM to %s", recipient)


def _thread_permalink(slack: WebClient, channel_id: str, thread_ts: str) -> str | None:
    """Return a Slack permalink for a thread, or None if the API call fails.

    We keep the raw thread_ts out of the LLM prompt — the model echoes it
    verbatim into prose, producing unreadable DMs like
    "the thread 1776162509.690509". Instead we ask the LLM to write about
    "the thread" generically and append a clickable permalink ourselves.
    """
    if not channel_id or not thread_ts:
        return None
    try:
        resp = slack.chat_getPermalink(channel=channel_id, message_ts=thread_ts)
        return resp.get("permalink")
    except Exception:
        log.exception("Failed to fetch permalink for %s/%s", channel_id, thread_ts)
        return None


def _with_thread_link(message: str, permalink: str | None) -> str:
    """Append a Slack-mrkdwn clickable link to a nudge message."""
    if not permalink:
        return message
    return f"{message}\n\n→ <{permalink}|Open the thread>"


def _fetch_ci_context(query: str) -> str:
    """Fetch relevant CI nuggets via semantic search for nudge context."""
    if not query:
        return ""
    results = []
    for table in ("insights", "worldview"):
        try:
            hits = search_similar(table, query, limit=2)
            results.extend(hits)
        except Exception:
            log.warning("CI context search failed for table %s", table)
    if not results:
        return ""
    parts = []
    for r in results[:3]:
        text = r.get("reframe") or r.get("belief") or r.get("statement") or ""
        if text:
            parts.append(text)
    return " | ".join(parts)


# --- Scan 1: Due Reminders ---

def scan_due_reminders(slack: WebClient) -> None:
    """Process threads where remind_after has passed."""
    threads = get_due_reminders()
    log.info("Pulse: %d due reminders", len(threads))

    for thread in threads:
        if _recently_nudged(thread.get("pulseNudgedAt")):
            continue

        owner_user_id = thread.get("ownerUserId")
        messages = thread.get("messages", [])
        context_parts = []
        if messages:
            recent = messages[-3:] if isinstance(messages, list) else []
            context_parts.append("Recent messages: " + "; ".join(
                m.get("content", "")[:100] for m in recent if isinstance(m, dict)
            ))

        message = generate_nudge(
            nudge_type="reminder",
            target_description="a thread you asked to be reminded about",
            ci_context="\n".join(context_parts),
            remind_context=thread.get("remindContext", ""),
        )
        permalink = _thread_permalink(slack, thread.get("channelId"), thread["threadTs"])
        message = _with_thread_link(message, permalink)

        if owner_user_id:
            if not _is_snoozed(owner_user_id):
                slack_id = get_slack_user_id(owner_user_id)
                if slack_id:
                    _send_dm(slack, slack_id, message)
        else:
            for hunter in _get_all_hunters():
                if not _is_snoozed(hunter["id"]):
                    slack_id = get_slack_user_id(hunter["id"])
                    if slack_id:
                        _send_dm(slack, slack_id, message)

        clear_thread_remind_after(thread["id"])
        log.info("Pulse: reminded thread %s", thread["threadTs"])


# --- Scan 2: Stale Threads + Contacts ---

def scan_stale_threads(slack: WebClient) -> None:
    """Nudge owners of threads that have gone quiet."""
    threads = get_stale_threads(days=14)
    log.info("Pulse: %d candidate stale threads", len(threads))

    for thread in threads:
        if _recently_nudged(thread.get("pulseNudgedAt")):
            continue

        owner_user_id = thread.get("ownerUserId")
        if not owner_user_id:
            continue

        stage = _get_thread_stage(thread)
        threshold = STAGE_THRESHOLDS.get(stage, 14) if stage else 14
        updated_dt = datetime.fromisoformat(thread["updatedAt"])
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=UTC)
        days_idle = (datetime.now(UTC) - updated_dt).days
        if days_idle < threshold:
            continue

        ci_context = _fetch_ci_context(thread.get("threadTs", ""))
        message = generate_nudge(
            nudge_type="stale_thread",
            target_description=f"a thread that's been quiet since {thread['updatedAt'][:10]}",
            ci_context=ci_context,
        )
        permalink = _thread_permalink(slack, thread.get("channelId"), thread["threadTs"])
        message = _with_thread_link(message, permalink)
        if not _is_snoozed(owner_user_id):
            slack_id = get_slack_user_id(owner_user_id)
            if slack_id:
                _send_dm(slack, slack_id, message)
        mark_thread_pulse_nudged(thread["id"])
        log.info("Pulse: nudged stale thread %s", thread["threadTs"])


def scan_stale_contacts(slack: WebClient) -> None:
    """Nudge owners of contacts that have gone quiet past their temperature threshold."""
    contacts = get_stale_contacts_for_pulse()
    now = datetime.now(UTC)
    log.info("Pulse: %d candidate contacts", len(contacts))

    for contact in contacts:
        temp = contact.get("temperature", "cold")
        threshold = CONTACT_THRESHOLDS.get(temp)
        if not threshold:
            continue

        last = contact.get("lastContact")
        if last:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=UTC)
            days_idle = (now - last_dt).days
        else:
            days_idle = 999

        if days_idle < threshold:
            continue

        if _recently_nudged(contact.get("pulseNudgedAt")):
            continue

        company = contact.get("companyByCompanyId", {})
        company_name = company.get("name", "") if company else ""
        desc = f"{contact['name']}"
        if contact.get("role"):
            desc += f" ({contact['role']})"
        if company_name:
            desc += f" at {company_name}"
        desc += f" — {temp}, {days_idle} days since last contact"

        ci_query = f"{contact['name']} {company_name}".strip()
        ci_context = _fetch_ci_context(ci_query)
        message = generate_nudge(
            nudge_type="stale_contact",
            target_description=desc,
            ci_context=ci_context,
        )

        owner_user_id = contact.get("ownerUserId")
        if owner_user_id:
            if not _is_snoozed(owner_user_id):
                slack_id = get_slack_user_id(owner_user_id)
                if slack_id:
                    _send_dm(slack, slack_id, message)
        else:
            for hunter in _get_all_hunters():
                if not _is_snoozed(hunter["id"]):
                    slack_id = get_slack_user_id(hunter["id"])
                    if slack_id:
                        _send_dm(slack, slack_id, message)

        mark_contact_pulse_nudged(contact["id"])
        log.info("Pulse: nudged stale contact %s", contact["name"])


# --- Scan 3: Pipeline Nudges ---

def scan_pipeline(slack: WebClient) -> None:
    """Nudge owners of opportunities stuck in a stage."""
    opportunities = get_stale_opportunities()
    now = datetime.now(UTC)
    log.info("Pulse: %d candidate opportunities", len(opportunities))

    for opp in opportunities:
        stage = opp.get("stage", "signal")
        threshold = STAGE_THRESHOLDS.get(stage, 30)

        updated = opp.get("updatedAt")
        if updated:
            updated_dt = datetime.fromisoformat(updated)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=UTC)
            days_stuck = (now - updated_dt).days
        else:
            days_stuck = 999

        if days_stuck < threshold:
            continue

        if _recently_nudged(opp.get("pulseNudgedAt")):
            continue

        company = opp.get("companyByCompanyId", {})
        contact = opp.get("contactByContactId", {})
        company_name = company.get("name", "") if company else ""
        contact_name = contact.get("name", "") if contact else ""

        desc = f"Opportunity: {opp.get('title', 'Untitled')}"
        if company_name:
            desc += f" ({company_name})"
        desc += f" — in {stage} for {days_stuck} days"
        if contact_name:
            desc += f", contact: {contact_name}"

        ci_query = f"{opp.get('title', '')} {company_name}".strip()
        ci_context = _fetch_ci_context(ci_query)
        notes_context = opp.get("notes", "")
        full_context = f"{notes_context}\n{ci_context}".strip() if ci_context else notes_context
        message = generate_nudge(
            nudge_type="pipeline",
            target_description=desc,
            ci_context=full_context,
        )

        owner_user_id = opp.get("ownerUserId")
        if owner_user_id:
            if not _is_snoozed(owner_user_id):
                slack_id = get_slack_user_id(owner_user_id)
                if slack_id:
                    _send_dm(slack, slack_id, message)
        else:
            for hunter in _get_all_hunters():
                if not _is_snoozed(hunter["id"]):
                    slack_id = get_slack_user_id(hunter["id"])
                    if slack_id:
                        _send_dm(slack, slack_id, message)

        mark_opportunity_pulse_nudged(opp["id"])
        log.info("Pulse: nudged opportunity %s", opp.get("title"))


# --- Scan 4: User Reminders ---

def scan_user_reminders(slack: WebClient) -> None:
    """Deliver due reminders (nudges and self-reminders)."""
    from mothertree.graphql_client import get_due_user_reminders, mark_reminder_delivered

    due = get_due_user_reminders()
    log.info("Reminders: %d due", len(due))

    for rem in due:
        target_user_id = rem.get("targetUserId")
        creator = rem.get("userByCreatorUserId", {})
        creator_name = creator.get("name", "someone")
        context = rem.get("context", "")
        is_self = rem.get("creatorUserId") == target_user_id

        if _is_snoozed(target_user_id):
            continue

        slack_id = get_slack_user_id(target_user_id)
        if not slack_id:
            continue

        try:
            if is_self:
                message = f"*Reminder:* {context}"
            else:
                first_name = creator_name.split()[0]
                message = f"*Nudge from {first_name}:* {context}"

            _send_dm(slack, slack_id, message)
            mark_reminder_delivered(rem["id"])
            log.info("Reminder delivered: %s → %s", creator_name, target_user_id)
        except Exception:
            log.exception("Failed to deliver reminder %s", rem["id"])


# --- Main entry point ---

def _check_expired_enrollments(slack: WebClient) -> None:
    """Expire enrollment requests older than 48 hours."""
    from mothertree.graphql_client import get_expired_enrollment_requests, get_slack_user_id, resolve_enrollment_request
    expired = get_expired_enrollment_requests(hours=48)
    for req in expired:
        resolve_enrollment_request(req["id"], "rejected")
        slack_id = get_slack_user_id(req["userId"])
        if slack_id:
            try:
                _send_dm(slack, slack_id, "Your enrollment request expired.")
            except Exception:
                log.exception("Failed to notify expired enrollment %s", req["id"])
    if expired:
        log.info("Pulse: expired %d enrollment requests", len(expired))


def scan_expansion_triggers(slack: WebClient) -> None:
    """Nudge account owners about expansion opportunities."""

    now = datetime.now(UTC)

    # Check stale account plans (>90 days since update, active client)
    result = graphql("""
    query {
        allAccountPlansList {
            id updatedAt
            companyByCompanyId { id name ownerUserId clientSince pulseNudgedAt }
        }
    }
    """)
    plans = result.get("allAccountPlansList", [])
    log.info("Expansion: %d account plans to check", len(plans))

    for plan in plans:
        company = plan.get("companyByCompanyId", {})
        if not company.get("clientSince"):
            continue  # Not an active client
        if _recently_nudged(company.get("pulseNudgedAt")):
            continue

        updated = datetime.fromisoformat(plan["updatedAt"])
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        days_stale = (now - updated).days

        if days_stale < 90:
            continue

        owner_user_id = company.get("ownerUserId")
        if not owner_user_id:
            continue

        message = generate_nudge(
            nudge_type="expansion",
            target_description=f"Account plan for {company['name']} — last updated {days_stale} days ago",
            ci_context="",
        )

        if not _is_snoozed(owner_user_id):
            slack_id = get_slack_user_id(owner_user_id)
            if slack_id:
                _send_dm(slack, slack_id, message)
                mark_company_pulse_nudged(company["id"])
                log.info("Expansion: nudged stale plan for %s", company["name"])


def run_scan() -> None:
    """Run all three Pulse scans sequentially."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Random jitter: 0-600 seconds to avoid exact 5-minute cadence
    jitter = random.randint(0, 600)  # noqa: S311 — scheduling jitter, not crypto
    log.info("Pulse: sleeping %ds (jitter)", jitter)
    time.sleep(jitter)

    slack = WebClient(token=SLACK_BOT_TOKEN)

    log.info("Pulse: starting scan cycle")
    scans = [
        ("reminders", scan_due_reminders),
        ("stale threads", scan_stale_threads),
        ("stale contacts", scan_stale_contacts),
        ("pipeline", scan_pipeline),
        ("expansion", scan_expansion_triggers),
        ("user reminders", scan_user_reminders),
        ("expired enrollments", _check_expired_enrollments),
    ]
    for name, scan_fn in scans:
        try:
            scan_fn(slack)
        except Exception:
            log.exception("Pulse: %s scan failed", name)
    log.info("Pulse: scan cycle complete")
