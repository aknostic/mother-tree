"""Quarterly business review + service meeting rhythm.

QBRs: quarterly per account, strategic synthesis for decision makers.
Service meetings: monthly per engagement, operational prep for delivery team.

Thin caller: gathers account-level data via ``mothertree.intelligence``;
QBR- and service-meeting-specific synthesis stays here (unique formats,
not shared with other cronjobs).
"""
import logging
from datetime import UTC, datetime, timedelta

from slack_sdk import WebClient

from mothertree.config import SLACK_BOT_TOKEN
from mothertree.graphql_client import (
    get_due_qbrs,
    get_due_service_meetings,
    get_slack_user_id,
    update_account_plan,
)
from mothertree.intelligence import gather_account
from mothertree.llm import generate

log = logging.getLogger(__name__)


def _format_qbr_context(account: dict, company_name: str) -> str:
    """Format a gather_account() dict into a QBR prompt body (deterministic)."""
    contacts = account.get("contacts") or []
    interactions = account.get("interactions") or []
    opportunities = account.get("opportunities") or []
    engagements = account.get("engagements") or []
    signals = account.get("signals") or []

    stakeholders = (
        ", ".join(
            f"{c.get('name', '?')} ({c.get('role') or '?'})" for c in contacts
        )
        or "none tracked"
    )
    active_engagements = (
        ", ".join(
            f"{e.get('title', '?')} ({e.get('status', '?')})" for e in engagements
        )
        or "none"
    )
    pipeline = (
        ", ".join(o.get("title") or o.get("stage", "?") for o in opportunities)
        or "no opportunities"
    )
    recent_interactions = (
        "; ".join(
            ((i.get("summary") or i.get("type", "?")))[:80]
            for i in interactions[:5]
        )
        or "none"
    )
    recent_signals = (
        "; ".join((s.get("content") or "")[:80] for s in signals[:5]) or "none"
    )

    context = (
        f"Company: {company_name}\n"
        f"Stakeholders: {stakeholders}\n"
        f"Active engagements: {active_engagements}\n"
        f"Pipeline: {pipeline}\n"
        f"Recent interactions ({len(interactions)}): {recent_interactions}\n"
        f"Recent signals ({len(signals)}): {recent_signals}\n"
    )

    for e in engagements:
        if e.get("serviceMeetingNotes"):
            context += (
                f"\nService meeting notes ({e.get('title', '?')}): "
                f"{e['serviceMeetingNotes'][:200]}"
            )

    return context


def synthesize_qbr(company_id: str, company_name: str) -> str:
    """Generate a QBR briefing for a company from available data.

    External signature preserved — called from ``cli.py`` and ``bot/pipeline.py``.
    """
    account = gather_account(company_id=company_id)
    context = _format_qbr_context(account, company_name)

    system = (
        "You are Mother Tree writing a quarterly business review for a consultative sales team. "
        "Be direct and actionable. Structure as:\n"
        "1. *Account health* — what's working, what needs attention\n"
        "2. *Engagement status* — where each engagement stands\n"
        "3. *Expansion opportunities* — white space, triggers, next moves\n"
        "4. *Recommended actions* — 2-3 specific things to do this quarter\n\n"
        "Keep it under 400 words. Use Slack formatting (*bold*, bullets). "
        "Frame for strategic stakeholders, not the delivery team."
    )

    return generate(system, f"QBR data for {company_name}:\n{context}")


def deliver_qbrs(slack: WebClient) -> None:
    """Check and deliver any due QBRs."""
    due = get_due_qbrs()
    log.info("QBR: %d due reviews", len(due))

    for plan in due:
        company = plan.get("companyByCompanyId", {})
        company_name = company.get("name", "?")
        owner_user_id = company.get("ownerUserId")

        try:
            briefing = synthesize_qbr(plan["companyId"], company_name)

            # Store and advance
            next_qbr = (datetime.now(UTC) + timedelta(days=90)).strftime("%Y-%m-%d")
            update_account_plan(
                plan["id"],
                qbr_notes=briefing,
                qbr_at=datetime.now(UTC).isoformat(),
                next_qbr=next_qbr,
            )

            # DM the account owner
            if owner_user_id:
                slack_id = get_slack_user_id(owner_user_id)
                if slack_id:
                    slack.chat_postMessage(
                        channel=slack_id,
                        text=f"*Quarterly review: {company_name}*\n\n{briefing}",
                    )
                    log.info("QBR delivered for %s", company_name)
        except Exception:
            log.exception("QBR failed for %s", company_name)


def _format_service_meeting_context(eng: dict, company_name: str, account: dict) -> str:
    """Format service meeting prep context (deterministic, no LLM)."""
    context = f"Engagement: {eng.get('title', '?')} at {company_name}"

    interactions = account.get("interactions") or []
    if interactions:
        rendered = "; ".join((i.get("summary") or "")[:60] for i in interactions[:3])
        context += f"\nRecent interactions: {rendered or 'none'}"

    signals = account.get("signals") or []
    if signals:
        rendered = "; ".join((s.get("content") or "")[:60] for s in signals[:3])
        context += f"\nRecent signals: {rendered or 'none'}"

    return context


def deliver_service_meeting_preps(slack: WebClient) -> None:
    """Check and deliver service meeting preps for due meetings."""
    due = get_due_service_meetings()
    log.info("Service meetings: %d due", len(due))

    for eng in due:
        company = eng.get("companyByCompanyId", {})
        company_name = company.get("name", "?")
        owner_user_id = eng.get("ownerUserId")

        try:
            # Pull interactions (and related account context) for the company, if known.
            account: dict = {}
            if company.get("id"):
                try:
                    account = gather_account(company_id=company["id"])
                except Exception:
                    log.debug("Could not fetch additional context for service meeting prep")
                    account = {}

            context = _format_service_meeting_context(eng, company_name, account)

            prep = generate(
                "You are Mother Tree preparing a service meeting briefing. "
                "Summarize what's happened since last meeting, flag open issues, "
                "suggest topics to raise. Under 200 words. Use Slack formatting.",
                context,
            )

            if owner_user_id:
                slack_id = get_slack_user_id(owner_user_id)
                if slack_id:
                    slack.chat_postMessage(
                        channel=slack_id,
                        text=f"*Service meeting prep: {eng.get('title', '?')} ({company_name})*\n\n{prep}",
                    )
                    log.info("Service meeting prep sent for %s", eng.get("title"))
        except Exception:
            log.exception("Service meeting prep failed for %s", eng.get("title"))


def deliver_reviews() -> None:
    """CronJob: check and deliver QBRs + service meeting preps."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    slack = WebClient(token=SLACK_BOT_TOKEN)
    deliver_qbrs(slack)
    deliver_service_meeting_preps(slack)


def main():
    """CLI entry point."""
    deliver_reviews()
