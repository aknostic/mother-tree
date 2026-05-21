"""Weekly pipeline review — Monday morning briefing for the team.

LLM-synthesized summary with clear priorities and actions for the week.
Sent to hunters and gatherers via Slack DM every Monday at 08:00 CET.

Thin caller: gathers pipeline data and synthesizes the briefing via
``mothertree.intelligence``; only user-identity queries (for Slack delivery)
remain inline here.
"""
import logging

from slack_sdk import WebClient

from mothertree.config import SLACK_BOT_TOKEN
from mothertree.graphql_client import get_slack_user_id, graphql
from mothertree.intelligence import gather_pipeline, synthesize_weekly

log = logging.getLogger(__name__)


def deliver_weekly_review() -> None:
    """CronJob: generate and deliver weekly pipeline briefing."""
    state = gather_pipeline()
    briefing = synthesize_weekly(state)
    log.info(
        "Weekly briefing: %d opportunities, %d signals, %d interactions",
        len(state.get("opportunities", [])),
        len(state.get("signals", [])),
        len(state.get("interactions", [])),
    )

    # Send to all active hunters and gatherers. Identity lookup only — not CI data.
    team = graphql("""
    query {
      allUsersList(filter: {
        role: {in: ["hunter", "gatherer"]},
        active: {equalTo: true}
      }) {
        id name
      }
    }
    """)

    slack = WebClient(token=SLACK_BOT_TOKEN)
    for member in team.get("allUsersList", []):
        slack_id = get_slack_user_id(member["id"])
        if not slack_id:
            continue
        try:
            slack.chat_postMessage(
                channel=slack_id,
                text=f"*Monday briefing*\n\n{briefing}",
            )
            log.info("Weekly briefing sent to %s", member["name"])
        except Exception:
            log.exception("Failed to send briefing to %s", member["name"])


def main():
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    deliver_weekly_review()
