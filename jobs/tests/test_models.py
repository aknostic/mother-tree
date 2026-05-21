"""Tests for Pydantic models."""
from mothertree.models import DateResolution, DispatchResult, PulseNudge, SnoozeParsed


class TestPulseNudge:
    def test_minimal_nudge(self):
        nudge = PulseNudge(
            recipient_slack_id="U123",
            message="Thread with Sarah went quiet.",
            nudge_type="stale_thread",
        )
        assert nudge.thread_ts is None
        assert nudge.context == {}

    def test_reminder_nudge_with_context(self):
        nudge = PulseNudge(
            recipient_slack_id="U123",
            message="Meeting prep time.",
            nudge_type="reminder",
            thread_ts="1234567890.123456",
            context={"meeting_date": "2026-04-21"},
        )
        assert nudge.nudge_type == "reminder"
        assert nudge.thread_ts == "1234567890.123456"

    def test_invalid_nudge_type(self):
        import pytest
        with pytest.raises(ValueError):
            PulseNudge(
                recipient_slack_id="U123",
                message="test",
                nudge_type="invalid",
            )


class TestSnoozeParsed:
    def test_snooze(self):
        s = SnoozeParsed(new_date="2026-04-17", reasoning="User said next week")
        assert s.new_date == "2026-04-17"


class TestDateResolution:
    def test_dateparser_tier(self):
        d = DateResolution(date="2026-04-10", reasoning="tomorrow", tier="dateparser")
        assert d.tier == "dateparser"

    def test_llm_tier(self):
        d = DateResolution(date="2026-04-18", reasoning="3 days before April 21 meeting", tier="llm")
        assert d.tier == "llm"


class TestDispatchResult:
    def test_minimal(self):
        r = DispatchResult(
            character="mother_tree",
            intent="question",
            must_respond=True,
            training_mode=False,
            signal_flag=False,
            clean_text="hello",
        )
        assert r.annotation is None
        assert r.exercise_pending is None
