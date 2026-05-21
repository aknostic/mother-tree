"""Pydantic models for Mother Tree character I/O.

Introduced with Pulse, defined for all characters, enforced incrementally.
"""

from typing import Literal

from pydantic import BaseModel

# -- Pulse --

class PulseNudge(BaseModel):
    """A single nudge message from Pulse to a team member."""
    recipient_slack_id: str
    message: str
    nudge_type: Literal["reminder", "stale_thread", "stale_contact", "pipeline"]
    thread_ts: str | None = None
    context: dict = {}


class SnoozeParsed(BaseModel):
    """Result of parsing a snooze request."""
    new_date: str
    reasoning: str


class DateResolution(BaseModel):
    """Result of smart date resolution (dateparser or LLM)."""
    date: str
    reasoning: str
    tier: Literal["dateparser", "llm"]


# -- Existing characters (defined now, enforced incrementally) --

class DispatchResult(BaseModel):
    """Output of the dispatcher — routes messages to characters."""
    character: str
    intent: str
    annotation: str | None = None
    must_respond: bool
    training_mode: bool
    signal_flag: bool
    clean_text: str
    exercise_pending: dict | None = None


class SpotterExtraction(BaseModel):
    """Output of Spotter — entity and signal extraction."""
    entities: list[dict]
    pain_signals: list[dict]
    value_hooks: list[dict]
    actions: list[dict]
    stage: dict


class WeaverResolution(BaseModel):
    """Output of Weaver — entity resolution against existing graph."""
    resolved: list[dict]
    flags: list[str]
