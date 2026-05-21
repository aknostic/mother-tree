"""Tests for snooze and completion intent detection in dispatcher."""

from unittest.mock import patch


class TestDispatchSnooze:
    """Snooze intent flows through dispatch()."""

    @patch("bot.characters.dispatcher._call_triage_llm")
    def test_dm_snooze_detected(self, mock_triage):
        from bot.characters.dispatcher import dispatch
        result = dispatch("I'll do that tomorrow", participant_count=1)
        assert result["intent"] == "snooze"
        assert result["annotation"]["type"] == "snooze"
        assert result["must_respond"] is True
        mock_triage.assert_not_called()  # Short-circuits before triage

    @patch("bot.characters.dispatcher._call_triage_llm")
    def test_dm_completion_detected(self, mock_triage):
        from bot.characters.dispatcher import dispatch
        result = dispatch("sent the mail to Hans yesterday", participant_count=1)
        assert result["intent"] == "completion"
        assert result["annotation"]["type"] == "completion"
        assert result["signal_flag"] is True
        mock_triage.assert_not_called()

    def test_channel_message_not_snoozed(self):
        """Snooze detection only fires in DMs."""
        from bot.characters.dispatcher import dispatch
        # participant_count > 1 means channel, won't trigger snooze
        # (will fall through to triage — mock it)
        with patch("bot.characters.dispatcher._call_triage_llm") as mock_triage:
            mock_triage.return_value = {"respond": False, "signal": {"capture": False}}
            result = dispatch("I'll do that tomorrow", participant_count=5)
            assert result["intent"] != "snooze"


class TestSnoozeDetection:
    def test_detects_snooze_tomorrow(self):
        from bot.characters.dispatcher import _detect_snooze
        result = _detect_snooze("I'll do that tomorrow")
        assert result is not None
        assert "tomorrow" in result.lower()

    def test_detects_snooze_next_week(self):
        from bot.characters.dispatcher import _detect_snooze
        result = _detect_snooze("park it until next week")
        assert result is not None

    def test_detects_snooze_not_now(self):
        from bot.characters.dispatcher import _detect_snooze
        result = _detect_snooze("not now, check back Friday")
        assert result is not None

    def test_no_snooze_in_normal_message(self):
        from bot.characters.dispatcher import _detect_snooze
        result = _detect_snooze("What's the latest on the STACKIT deal?")
        assert result is None

    def test_no_snooze_in_long_conversational_next_week(self):
        # Regression: user replied to a debrief nudge with prose that happened
        # to mention "next week"; dispatcher hijacked it as snooze and the
        # handler 400'd against PostGraphile.
        from bot.characters.dispatcher import _detect_snooze
        result = _detect_snooze(
            "that is perfect, i expect candidates flowing next week, "
            "first conversations week after"
        )
        assert result is None

    def test_no_snooze_in_long_conversational_tomorrow(self):
        from bot.characters.dispatcher import _detect_snooze
        result = _detect_snooze(
            "I have a kickoff with the Sanoma team tomorrow morning to "
            "talk through the migration"
        )
        assert result is None

    def test_no_snooze_in_long_conversational_later(self):
        from bot.characters.dispatcher import _detect_snooze
        result = _detect_snooze(
            "let's circle back later this week once Pim has had a chance "
            "to read the proposal"
        )
        assert result is None


class TestCompletionDetection:
    def test_detects_sent_email(self):
        from bot.characters.dispatcher import _detect_completion
        result = _detect_completion("sent the mail to Hans yesterday")
        assert result is True

    def test_detects_met_with(self):
        from bot.characters.dispatcher import _detect_completion
        result = _detect_completion("met with them last Thursday")
        assert result is True

    def test_detects_done(self):
        from bot.characters.dispatcher import _detect_completion
        result = _detect_completion("done, called Sarah this morning")
        assert result is True

    def test_no_completion_in_question(self):
        from bot.characters.dispatcher import _detect_completion
        result = _detect_completion("Should I send the email?")
        assert result is False
