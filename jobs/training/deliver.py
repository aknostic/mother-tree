"""Training delivery CronJob — daily check for all enrollments."""
import logging
from datetime import UTC, datetime

from slack_sdk import WebClient

from mothertree.config import SLACK_BOT_TOKEN
from mothertree.graphql_client import get_active_users, get_slack_user_id, update_streak
from training.curriculum import is_citizen_role
from training.operations import citizen_daily_check, daily_check, format_progress

log = logging.getLogger(__name__)

# Citizens get inspiration on Tuesdays and Thursdays (weekday 1 and 3)
CITIZEN_NUDGE_DAYS = {1, 3}


def deliver_training() -> None:
    """Daily CronJob: check all enrollments, deliver chapters or refreshers.

    Citizens get 2x/week proactive inspiration (Tue/Thu).
    Hunters/gatherers/farmers get weekday daily checks.
    """
    slack = WebClient(token=SLACK_BOT_TOKEN)
    enrollments = get_active_users()
    now = datetime.now(UTC)
    weekday = now.weekday()
    log.info("Daily check: %d active enrollments (weekday %d)", len(enrollments), weekday)

    for user in enrollments:
        try:
            role = user.get("role", "")

            # Citizens: 2x/week proactive inspiration
            if is_citizen_role(role):
                if weekday not in CITIZEN_NUDGE_DAYS:
                    log.info("Skipping citizen %s (not a nudge day)", user["name"])
                    continue
                message = citizen_daily_check(user)
                if message:
                    slack_id = get_slack_user_id(user["id"])
                    if slack_id:
                        slack.chat_postMessage(channel=slack_id, text=message)
                    log.info("Citizen inspiration to %s", user["name"])
                continue

            # Non-citizen: streak tracking and daily check
            last = user.get("lastActivity")
            if last:
                last_dt = datetime.fromisoformat(last)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
                days_idle = (now - last_dt).days

                # Reset streak if no activity yesterday
                if days_idle > 1:
                    update_streak(user["id"], 0)

                # Remind if idle 7+ days
                if days_idle >= 7:
                    progress = format_progress(user)
                    slack_id = get_slack_user_id(user["id"])
                    if slack_id:
                        slack.chat_postMessage(
                            channel=slack_id,
                            text=f"Ready to pick it up again? Here's where you left off:\n\n{progress}\n\nReply *next* whenever you're ready.",
                        )
                    log.info("Reminded %s (idle %d days)", user["name"], days_idle)
                    continue

            # Normal daily check
            message = daily_check(user)
            if message:
                slack_id = get_slack_user_id(user["id"])
                if slack_id:
                    slack.chat_postMessage(channel=slack_id, text=message)
                log.info("Delivered to %s", user["name"])
                streak = (user.get("streak") or 0) + 1
                update_streak(user["id"], streak)
            else:
                log.info("Nothing to deliver to %s", user["name"])
        except Exception:
            log.exception("Failed daily check for %s", user["name"])


def main():
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    deliver_training()
