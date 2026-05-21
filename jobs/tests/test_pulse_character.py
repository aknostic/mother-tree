"""Tests for Pulse character — nudge message generation."""
from unittest.mock import patch


class TestPulseIdentity:
    def test_system_prompt_contains_rules(self):
        from bot.characters.pulse import PULSE_SYSTEM
        assert "Pulse" in PULSE_SYSTEM
        assert "mycorrhizal network" in PULSE_SYSTEM
        assert "One DM per topic" in PULSE_SYSTEM

    def test_system_prompt_never_reveals_name(self):
        from bot.characters.pulse import PULSE_SYSTEM
        assert 'never sees "Pulse"' in PULSE_SYSTEM or "Speak as Mother Tree" in PULSE_SYSTEM


class TestGenerateNudge:
    @patch("bot.characters.pulse.chat")
    def test_generates_short_dm(self, mock_chat):
        mock_chat.return_value = "The STACKIT thread has been quiet for three weeks. Worth a check-in?"
        from bot.characters.pulse import generate_nudge
        msg = generate_nudge(
            nudge_type="stale_thread",
            target_description="STACKIT thread with Sarah, quiet 21 days",
            ci_context="Sarah's sovereignty concerns align with the reframe we extracted.",
        )
        assert msg
        assert len(msg) < 500
        mock_chat.assert_called_once()

    @patch("bot.characters.pulse.chat")
    def test_reminder_nudge(self, mock_chat):
        mock_chat.return_value = "The DSC meeting is April 21. Want me to pull context?"
        from bot.characters.pulse import generate_nudge
        msg = generate_nudge(
            nudge_type="reminder",
            target_description="DSC meeting with Steven and Marco, April 21",
            ci_context="Prepared reframe on total cost of dependency.",
            remind_context="User asked for prep help 2 days before",
        )
        assert "DSC" in msg or "April" in msg
