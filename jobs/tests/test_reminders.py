"""Tests for reminders GraphQL functions."""
from unittest.mock import MagicMock, patch


class TestCreateReminder:
    @patch("mothertree.graphql_client.graphql")
    def test_creates_reminder(self, mock_gql):
        mock_gql.return_value = {"createReminder": {"reminder": {
            "id": "rem-1", "remindAt": "2026-04-17T08:00:00+00:00",
            "targetUserId": "user-2", "context": "Send NIS2 deck"
        }}}
        from mothertree.graphql_client import create_reminder
        rem = create_reminder("user-1", "user-2", "2026-04-17T08:00:00+00:00", "Send NIS2 deck")
        assert rem is not None
        assert rem["targetUserId"] == "user-2"


class TestGetDueReminders:
    @patch("mothertree.graphql_client.graphql")
    def test_gets_due_reminders(self, mock_gql):
        mock_gql.return_value = {"allRemindersList": [
            {"id": "rem-1", "creatorUserId": "user-1", "targetUserId": "user-2",
             "context": "Send deck", "remindAt": "2026-04-15T08:00:00+00:00",
             "userByCreatorUserId": {"name": "Jurg"}}
        ]}
        from mothertree.graphql_client import get_due_user_reminders
        reminders = get_due_user_reminders()
        assert len(reminders) == 1


class TestMarkDelivered:
    @patch("mothertree.graphql_client.graphql")
    def test_marks_delivered(self, mock_gql):
        mock_gql.return_value = {"updateReminderById": {"reminder": {"id": "rem-1"}}}
        from mothertree.graphql_client import mark_reminder_delivered
        mark_reminder_delivered("rem-1")
        mock_gql.assert_called_once()


class TestFindUserByName:
    @patch("mothertree.graphql_client.graphql")
    def test_finds_user(self, mock_gql):
        mock_gql.return_value = {"allUsersList": [
            {"id": "user-2", "name": "Pim", "email": "pim@aknostic.com", "role": "hunter", "active": True}
        ]}
        from mothertree.graphql_client import find_user_by_name
        user = find_user_by_name("Pim")
        assert user is not None
        assert user["name"] == "Pim"

    @patch("mothertree.graphql_client.graphql")
    def test_returns_none_when_not_found(self, mock_gql):
        mock_gql.return_value = {"allUsersList": []}
        from mothertree.graphql_client import find_user_by_name
        assert find_user_by_name("Unknown") is None


class TestHandleNudge:
    @patch("bot.pipeline.create_reminder")
    @patch("bot.pipeline.find_user_by_name")
    def test_nudge_creates_reminder(self, mock_find, mock_create):
        mock_find.return_value = {"id": "user-2", "name": "Pim", "role": "hunter"}
        mock_create.return_value = {"id": "rem-1", "targetUserId": "user-2"}
        from bot.pipeline import _handle_nudge
        result = _handle_nudge(
            {"type": "nudge", "target": "Pim", "context": "tomorrow send the NIS2 deck"},
            {"id": "user-1", "role": "hunter"},
        )
        assert "Pim" in result
        mock_create.assert_called_once()

    @patch("bot.pipeline.find_user_by_name")
    def test_nudge_unknown_user(self, mock_find):
        mock_find.return_value = None
        from bot.pipeline import _handle_nudge
        result = _handle_nudge(
            {"type": "nudge", "target": "Unknown", "context": "hello"},
            {"id": "user-1", "role": "hunter"},
        )
        assert "don't know" in result.lower()


class TestHandleSelfRemind:
    @patch("bot.pipeline.create_reminder")
    def test_self_remind_creates_reminder(self, mock_create):
        mock_create.return_value = {"id": "rem-1"}
        from bot.pipeline import _handle_self_remind
        result = _handle_self_remind(
            {"type": "self_remind", "context": "Friday check if Pim sent the deck"},
            {"id": "user-1", "role": "hunter"},
        )
        assert "remind" in result.lower() or "set" in result.lower()
        mock_create.assert_called_once()

    def test_self_remind_no_context(self):
        from bot.pipeline import _handle_self_remind
        result = _handle_self_remind(
            {"type": "self_remind", "context": ""},
            {"id": "user-1"},
        )
        assert "what" in result.lower()


class TestParseReminderTime:
    def test_tomorrow(self):
        from bot.pipeline import _parse_reminder_time
        remind_at, clean = _parse_reminder_time("tomorrow send the deck")
        assert "T08:00:00" in remind_at
        assert "send the deck" in clean

    def test_day_name(self):
        from bot.pipeline import _parse_reminder_time
        remind_at, clean = _parse_reminder_time("Thursday to check on this")
        assert "T08:00:00" in remind_at

    def test_in_n_days(self):
        from bot.pipeline import _parse_reminder_time
        remind_at, clean = _parse_reminder_time("in 3 days follow up")
        assert "T08:00:00" in remind_at

    def test_fallback_is_tomorrow(self):
        from bot.pipeline import _parse_reminder_time
        remind_at, text = _parse_reminder_time("send the NIS2 deck to Charlotte")
        assert "T08:00:00" in remind_at
        # text unchanged when no time parsed
        assert "NIS2" in text


class TestScanUserReminders:
    @patch("mothertree.graphql_client.mark_reminder_delivered")
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("mothertree.graphql_client.get_due_user_reminders")
    def test_delivers_due_reminder(self, mock_due, mock_snoozed, mock_slack_id, mock_mark):
        mock_due.return_value = [{
            "id": "rem-1", "creatorUserId": "user-1", "targetUserId": "user-2",
            "context": "Send the NIS2 deck", "userByCreatorUserId": {"name": "Jurg"},
        }]
        mock_slack_id.return_value = "U_PIM"
        from pulse.scanner import scan_user_reminders
        slack = MagicMock()
        scan_user_reminders(slack)
        slack.chat_postMessage.assert_called_once()
        mock_mark.assert_called_once_with("rem-1")
        # Check it's a nudge (not self-reminder)
        call_text = slack.chat_postMessage.call_args[1]["text"]
        assert "Jurg" in call_text

    @patch("mothertree.graphql_client.mark_reminder_delivered")
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("mothertree.graphql_client.get_due_user_reminders")
    def test_delivers_self_reminder(self, mock_due, mock_snoozed, mock_slack_id, mock_mark):
        mock_due.return_value = [{
            "id": "rem-1", "creatorUserId": "user-1", "targetUserId": "user-1",
            "context": "Check if Pim sent the deck", "userByCreatorUserId": {"name": "Jurg"},
        }]
        mock_slack_id.return_value = "U_JURG"
        from pulse.scanner import scan_user_reminders
        slack = MagicMock()
        scan_user_reminders(slack)
        slack.chat_postMessage.assert_called_once()
        call_text = slack.chat_postMessage.call_args[1]["text"]
        assert "Reminder" in call_text
        assert "Jurg" not in call_text  # Self-reminder doesn't show creator

    @patch("pulse.scanner._is_snoozed")
    @patch("mothertree.graphql_client.get_due_user_reminders")
    def test_skips_snoozed_user(self, mock_due, mock_snoozed):
        mock_due.return_value = [{
            "id": "rem-1", "creatorUserId": "user-1", "targetUserId": "user-2",
            "context": "Hello", "userByCreatorUserId": {"name": "Jurg"},
        }]
        mock_snoozed.return_value = True
        from pulse.scanner import scan_user_reminders
        slack = MagicMock()
        scan_user_reminders(slack)
        slack.chat_postMessage.assert_not_called()
