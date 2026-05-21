"""Monthly retrospective — first Monday of the month.

Pipeline health, insight usage patterns, training progress,
signal volume trends. Uses LLM to synthesize the data into
an actionable summary.

Thin caller: gathers counts via ``gather_pipeline(counts_only=True)`` and
synthesizes the retrospective via ``synthesize_monthly``. Only user-identity
queries (for Slack delivery) remain inline.
"""
import logging

from slack_sdk import WebClient

from mothertree.config import SLACK_BOT_TOKEN
from mothertree.graphql_client import get_slack_user_id, graphql
from mothertree.intelligence import gather_pipeline, synthesize_monthly

log = logging.getLogger(__name__)


def deliver_monthly_retro() -> None:
    """CronJob: generate and deliver monthly retrospective."""
    state = gather_pipeline(days=30, counts_only=True)
    retro = synthesize_monthly(state)
    log.info("Monthly retro generated")

    # Identity-only query: active hunters/gatherers for DM delivery.
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
                text=f"*Monthly retrospective*\n\n{retro}",
            )
            log.info("Monthly retro sent to %s", member["name"])
        except Exception:
            log.exception("Failed to send retro to %s", member["name"])


def main():
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    deliver_monthly_retro()
