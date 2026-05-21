"""Training DM handler logic.

Extracted from bot.py for testability. Handles: go, answers, next, practice.
"""
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# Hunter Stage 0 chapter lookup — used for DM formatting and topic resolution
_HUNTER_STAGE0_CHAPTERS = {
    0: {"name": "The Promise"},
    1: {"name": "The Worldview"},
    2: {"name": "The Audience"},
    3: {"name": "The Difference"},
    4: {"name": "The Services"},
}

TOPIC_MAP = {
    "promise": 0, "worldview": 1, "audience": 2,
    "difference": 3, "services": 4,
}


def parse_dm_command(text: str) -> tuple[str, str | None]:
    """Parse a DM message into a command and optional argument."""
    text = text.strip()
    lower = text.lower()

    if lower == "go":
        return "go", None
    if lower == "next":
        return "next", None
    if lower.startswith("practice"):
        parts = lower.split(maxsplit=1)
        topic = parts[1] if len(parts) > 1 else None
        return "practice", topic
    if text.upper() in ("A", "B", "C"):
        return "answer", text.upper()

    return "conversation", None


def resolve_topic(topic: str) -> int | None:
    """Resolve a topic string to a chapter number, or None if unrecognized."""
    return TOPIC_MAP.get(topic.lower())


def calculate_streak(current_streak: int, last_activity: str | None) -> int:
    """Calculate updated streak based on last activity timestamp."""
    if last_activity is None:
        return 1

    tz = ZoneInfo("Europe/Amsterdam")
    now_cet = datetime.now(tz)
    last = datetime.fromisoformat(last_activity)
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    last_cet = last.astimezone(tz)

    days_diff = (now_cet.date() - last_cet.date()).days

    if days_diff == 0:
        return current_streak
    if days_diff == 1:
        return current_streak + 1
    return 1


def format_chapter_complete(chapter: int, chapter_name: str, streak: int) -> str:
    """Format the chapter completion message."""
    display = chapter + 1
    lines = [
        "\u2501" * 20,
        f"Chapter {display} complete \u2014 {chapter_name} \u2713",
        f"Streak: {streak} day{'s' if streak != 1 else ''}",
        "\u2501" * 20,
    ]

    if chapter < 4:
        next_ch = _HUNTER_STAGE0_CHAPTERS[chapter + 1]
        next_display = chapter + 2
        lines.append(f"\nTomorrow: Chapter {next_display} \u2014 {next_ch['name']}")
        lines.append(
            f"\nWant to keep going? Say *next* for chapter {next_display}, "
            f"or *practice {chapter_name.lower().replace('the ', '')}* "
            f"to do more on this one."
        )
    else:
        lines.append(
            "\nStage 0 complete! Stage 1 \u2014 the marketing framework "
            "\u2014 is coming soon.\n\n"
            "In the meantime, say *practice [topic]* to keep sharpening. "
            "Topics: promise, worldview, audience, difference, services."
        )

    return "\n".join(lines)
