"""Calendar sync — scan iCal feeds for meeting prep and debrief.

Fetches each enrolled user's iCal feed, finds upcoming and past meetings,
generates prep suggestions before and debrief prompts after.

Thin caller: CI context is gathered via ``mothertree.intelligence.gather_meeting_context``;
only user/interaction lookups (identity + debrief-exists check) remain here.
"""
import logging
from datetime import UTC, datetime, timedelta

import httpx
import icalendar
import recurring_ical_events
from slack_sdk import WebClient

from mothertree.config import SLACK_BOT_TOKEN
from mothertree.graphql_client import graphql
from mothertree.intelligence import gather_context, gather_meeting_context
from mothertree.llm import generate

log = logging.getLogger(__name__)

PREP_WINDOW_DAYS = 2   # prep for meetings within next 2 days
DEBRIEF_WINDOW_DAYS = 3  # prompt debrief for meetings up to 3 days ago


def fetch_ical(url: str) -> icalendar.Calendar | None:
    """Fetch and parse an iCal feed."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return icalendar.Calendar.from_ical(resp.text)
    except Exception as e:
        log.warning("Failed to fetch iCal from %s: %s", url[:50], e)
        return None


def get_events_in_window(cal: icalendar.Calendar, start: datetime, end: datetime) -> list[dict]:
    """Extract events within a time window, expanding recurring events."""
    events = recurring_ical_events.of(cal).between(start, end)
    results = []
    for event in events:
        summary = str(event.get("SUMMARY", ""))
        if not summary:
            continue
        dtstart = event.get("DTSTART")
        if dtstart:
            dt = dtstart.dt
            if not isinstance(dt, datetime):
                dt = datetime.combine(dt, datetime.min.time(), tzinfo=UTC)
            elif dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        else:
            continue

        attendees = []
        for a in event.get("ATTENDEE", []):
            name = a.params.get("CN", str(a).replace("mailto:", ""))
            attendees.append(name)

        location = str(event.get("LOCATION", ""))
        description = str(event.get("DESCRIPTION", ""))

        results.append({
            "summary": summary,
            "start": dt,
            "attendees": attendees,
            "location": location,
            "description": description[:500],
        })
    return sorted(results, key=lambda e: e["start"])


def _generate_safe_passage_questions(query: str) -> list[str]:
    """Generate safe passage questions from worldview belief+pain pairs.

    These open the door to vulnerability in a meeting — they show empathy
    and make it safe for the prospect to share their real situation.

    CI data is fetched via ``gather_context`` (single path to CI data);
    we pull the ``worldview`` semantic section and use top matches.
    """
    try:
        ctx = gather_context(query=query, top_n=3)
        similar_worldviews: list[dict] = []
        for section in (ctx.get("semantic_results") or []):
            if section.get("table") == "worldview":
                similar_worldviews = section.get("results", [])
                break
        if not similar_worldviews:
            return []
        pairs = "\n".join(
            f"- Belief: {w.get('belief', '')} | Pain: {w.get('pain', '')}"
            for w in similar_worldviews
        )
        raw = generate(
            "Generate 2 safe passage questions for a consultative sales meeting. "
            "These questions open the door to vulnerability — they show empathy "
            "and make it safe for the prospect to share their real situation. "
            "Based on what the audience believes and feels, write questions that "
            "say 'we understand your world' without pitching. One sentence each. "
            "Return ONLY the questions, one per line.",
            f"Audience worldview:\n{pairs}",
        )
        return [q.strip().lstrip("- •12.") for q in raw.strip().split("\n") if q.strip()][:2]
    except Exception:
        return []


def _format_ci_data_for_prep(ci_data: dict) -> str:
    """Render a gather_meeting_context() dict as prep-prompt context (deterministic)."""
    lines: list[str] = []

    for c in ci_data.get("attendee_contacts", []) or []:
        company = c.get("companyByCompanyId") or {}
        company_str = f" at {company['name']}" if company.get("name") else ""
        lines.append(
            f"Contact: {c.get('name', '?')} ({c.get('role', '?')}){company_str} "
            f"— {c.get('temperature', '?')}"
        )
        if c.get("notes"):
            lines.append(f"  Notes: {c['notes'][:200]}")

    insights = ci_data.get("insights") or []
    if insights:
        lines.append("\nRelevant insights:")
        for i in insights:
            lines.append(f"  - [{i.get('category', '')}] {i.get('reframe', '')}")

    changes = ci_data.get("changes") or []
    if changes:
        lines.append("\nRelevant positioning:")
        for c in changes:
            lines.append(f"  - {c.get('statement', '')}")

    proof_points = ci_data.get("proof_points") or []
    if proof_points:
        lines.append("\nProof points:")
        for p in proof_points:
            client = p.get("client", "A client")
            lines.append(f"  - {client}: {p.get('outcome', '')}")

    return "\n".join(lines) if lines else "No specific context found for this meeting."


def generate_prep(event: dict, ci_data: dict) -> str:
    """Generate meeting prep from a gather_meeting_context() dict."""
    attendee_str = ", ".join(event["attendees"][:5]) if event["attendees"] else "unknown attendees"

    ci_context = _format_ci_data_for_prep(ci_data)

    # Safe passage questions relevant to this meeting
    safe_questions = _generate_safe_passage_questions(event["summary"])
    safe_section = ""
    if safe_questions:
        safe_section = "\n\nSafe passage questions (open the door to their real situation):\n"
        safe_section += "\n".join(f"- {q}" for q in safe_questions)

    system = (
        "You are Mother Tree preparing a hunter for an upcoming meeting. "
        "Be direct, practical. Focus on: who they're meeting, what we know, "
        "suggested reframes or insights to bring, and one question to ask. "
        "End with: 'What's the one thing you don't know yet about their situation?' "
        "150 words max."
    )
    prompt = (
        f"Meeting: {event['summary']}\n"
        f"When: {event['start'].strftime('%A %B %d at %H:%M')}\n"
        f"Attendees: {attendee_str}\n"
        f"Location: {event['location']}\n\n"
        f"What we know:\n{ci_context}{safe_section}"
    )
    return generate(system, prompt)


def generate_debrief_prompt(event: dict) -> str:
    """Generate a debrief nudge for a past meeting."""
    attendee_str = ", ".join(event["attendees"][:5]) if event["attendees"] else "the attendees"
    return (
        f"*Debrief: {event['summary']}*\n"
        f"({event['start'].strftime('%A %B %d')} with {attendee_str})\n\n"
        f"How did it go? Drop your notes here — I'll capture the signals."
    )


def check_debrief_exists(event: dict, user_slack_id: str) -> bool:
    """Check if a debrief/interaction was already logged for this meeting.

    Queries the ``interactions`` table directly (identity/operational lookup,
    not a CI data query). Left inline intentionally — see code principles note.
    """
    date_str = event["start"].strftime("%Y-%m-%d")
    try:
        data = graphql("""
        query($date: Date!, $summary: String!) {
          allInteractionsList(filter: {
            and: [
              {date: {greaterThanOrEqualTo: $date}},
              {summary: {includesInsensitive: $summary}}
            ]
          }, first: 1) { id }
        }
        """, {"date": date_str, "summary": event['summary'][:30]})
        return len(data.get("allInteractionsList", [])) > 0
    except Exception:
        return False  # Assume no debrief on error


def get_calendar_feeds() -> list[dict]:
    """Get all enrolled users with calendar feeds."""
    data = graphql("""
    query {
      allUsersList(filter: {
        active: {equalTo: true},
        role: {notEqualTo: "citizen"}
      }) {
        id name role calendarUrl
      }
    }
    """)
    return [e for e in data.get("allUsersList", []) if e.get("calendarUrl")]


def deliver_calendar_sync() -> None:
    """CronJob: scan calendars, deliver prep and debrief prompts."""
    feeds = get_calendar_feeds()
    if not feeds:
        log.info("No calendar feeds configured")
        return

    now = datetime.now(UTC)
    slack = WebClient(token=SLACK_BOT_TOKEN)

    for user in feeds:
        try:
            cal = fetch_ical(user["calendarUrl"])
            if not cal:
                continue

            # Upcoming meetings — prep
            from mothertree.graphql_client import get_slack_user_id
            slack_id = get_slack_user_id(user["id"])
            if not slack_id:
                log.warning("No Slack link for user %s, skipping calendar sync", user["name"])
                continue

            upcoming = get_events_in_window(
                cal,
                now,
                now + timedelta(days=PREP_WINDOW_DAYS),
            )
            for event in upcoming:
                ci_data = gather_meeting_context(event)
                prep = generate_prep(event, ci_data)
                slack.chat_postMessage(
                    channel=slack_id,
                    text=f"*Prep: {event['summary']}*\n{event['start'].strftime('%A %B %d at %H:%M')}\n\n{prep}",
                )
                log.info("Prep sent to %s for %s", user["name"], event["summary"])

            # Past meetings — debrief prompt
            past = get_events_in_window(
                cal,
                now - timedelta(days=DEBRIEF_WINDOW_DAYS),
                now - timedelta(hours=1),  # at least 1 hour ago
            )
            for event in past:
                if not check_debrief_exists(event, slack_id):
                    debrief = generate_debrief_prompt(event)
                    slack.chat_postMessage(
                        channel=slack_id,
                        text=debrief,
                    )
                    log.info("Debrief prompt sent to %s for %s", user["name"], event["summary"])

        except Exception:
            log.exception("Calendar sync failed for %s", user["name"])


def main():
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    deliver_calendar_sync()
