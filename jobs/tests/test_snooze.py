"""Tests for snooze handler and Pulse snooze check."""
from unittest.mock import patch


class TestSnoozeHandler:
    @patch("mothertree.graphql_client.set_user_snooze")
    def test_snooze_tomorrow(self, mock_set):
        from bot.pipeline import _handle_snooze
        result = _handle_snooze(
            {"type": "snooze", "match": "tomorrow", "text": "tomorrow"},
            {"id": "user-1", "role": "hunter"},
        )
        assert "tomorrow" in result.lower()
        mock_set.assert_called_once()

    @patch("mothertree.graphql_client.set_user_snooze")
    def test_snooze_next_week(self, mock_set):
        from bot.pipeline import _handle_snooze
        result = _handle_snooze(
            {"type": "snooze", "match": "next week", "text": "next week"},
            {"id": "user-1", "role": "hunter"},
        )
        assert "7 days" in result
        mock_set.assert_called_once()

    @patch("mothertree.graphql_client.set_user_snooze")
    def test_snooze_n_days(self, mock_set):
        from bot.pipeline import _handle_snooze
        result = _handle_snooze(
            {"type": "snooze", "match": "in 3 days", "text": "in 3 days"},
            {"id": "user-1", "role": "hunter"},
        )
        assert "3 days" in result

    def test_snooze_no_user(self):
        from bot.pipeline import _handle_snooze
        result = _handle_snooze(
            {"type": "snooze", "match": "tomorrow", "text": "tomorrow"},
            None,
        )
        assert "enroll" in result.lower()


class TestSnoozeFallback:
    """When the snooze handler raises (e.g. PostGraphile 400), the fallback
    should explain that a snooze was attempted, not return a generic error."""

    def test_fallback_for_snooze_mentions_what_was_attempted(self):
        from bot.pipeline import _fallback
        msg = _fallback({"type": "snooze", "match": "next week", "text": "..."})
        assert "snooze" in msg.lower()
        assert "next week" in msg
        # Critical: must NOT be the opaque generic message.
        assert msg != "Something went wrong. Try again in a moment."

    def test_fallback_for_debrief_says_debrief(self):
        from bot.pipeline import _fallback
        msg = _fallback({"type": "debrief", "content": "notes"})
        assert "debrief" in msg.lower()
        assert msg != "Something went wrong. Try again in a moment."

    def test_fallback_unknown_type_still_generic(self):
        from bot.pipeline import _fallback
        msg = _fallback({"type": "something_new"})
        assert msg == "Something went wrong. Try again in a moment."


class TestIsSnoozed:
    @patch("mothertree.graphql_client.is_user_snoozed")
    def test_snoozed_user_blocks_nudge(self, mock_snoozed):
        mock_snoozed.return_value = True
        from pulse.scanner import _is_snoozed
        assert _is_snoozed("user-1") is True

    @patch("mothertree.graphql_client.is_user_snoozed")
    def test_non_snoozed_user_allows_nudge(self, mock_snoozed):
        mock_snoozed.return_value = False
        from pulse.scanner import _is_snoozed
        assert _is_snoozed("user-1") is False

    def test_none_user_not_snoozed(self):
        from pulse.scanner import _is_snoozed
        assert _is_snoozed(None) is False
