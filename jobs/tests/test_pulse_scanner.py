"""Tests for Pulse scanner — three scan types + DM delivery."""
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch


class TestDueRemindersScan:
    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner.clear_thread_remind_after")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_due_reminders")
    def test_sends_dm_for_due_reminder(self, mock_get, mock_nudge, mock_clear, mock_slack_id, mock_snoozed):
        mock_get.return_value = [
            {
                "id": 1,
                "threadTs": "123.456",
                "channelId": "C123",
                "messages": [{"role": "user", "content": "Check on proposal", "name": "Jurg"}],
                "remindAfter": "2026-04-09T08:00:00+00:00",
                "remindContext": "Follow up on proposal with Sarah",
                "ownerUserId": "u-jurg",
                "pulseNudgedAt": None,
            }
        ]
        mock_nudge.return_value = "Time to follow up on the proposal with Sarah."
        mock_slack_id.return_value = "U_JURG"

        mock_slack = MagicMock()
        from pulse.scanner import scan_due_reminders
        scan_due_reminders(mock_slack)

        mock_nudge.assert_called_once()
        mock_slack.chat_postMessage.assert_called_once()
        dm_call = mock_slack.chat_postMessage.call_args
        assert dm_call.kwargs["channel"] == "U_JURG"

    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner.clear_thread_remind_after")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_due_reminders")
    def test_clears_remind_after_on_send(self, mock_get, mock_nudge, mock_clear, mock_slack_id, mock_snoozed):
        mock_get.return_value = [
            {
                "id": 42,
                "threadTs": "123.456",
                "channelId": "C123",
                "messages": [],
                "remindAfter": "2026-04-09T08:00:00+00:00",
                "remindContext": "",
                "ownerUserId": "u-jurg",
                "pulseNudgedAt": None,
            }
        ]
        mock_nudge.return_value = "Check in."
        mock_slack_id.return_value = "U_JURG"

        mock_slack = MagicMock()
        from pulse.scanner import scan_due_reminders
        scan_due_reminders(mock_slack)

        mock_clear.assert_called_once_with(42)


class TestStaleThreadsScan:
    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner._get_thread_stage", return_value=None)
    @patch("pulse.scanner.mark_thread_pulse_nudged")
    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_stale_threads")
    def test_nudges_stale_thread(self, mock_get, mock_nudge, mock_ci, mock_mark, mock_stage, mock_slack_id, mock_snoozed):
        old_date = (datetime.now(UTC) - timedelta(days=25)).isoformat()
        mock_get.return_value = [
            {
                "id": 2,
                "threadTs": "456.789",
                "channelId": "C456",
                "ownerUserId": "u-pim",
                "updatedAt": old_date,
                "pulseNudgedAt": None,
            }
        ]
        mock_nudge.return_value = "Thread went quiet. Worth revisiting?"
        mock_slack_id.return_value = "U_PIM"

        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)

        mock_slack.chat_postMessage.assert_called_once()
        mock_mark.assert_called_once_with(2)

    @patch("pulse.scanner.get_stale_threads")
    def test_skips_recently_nudged(self, mock_get):
        recent_nudge = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        mock_get.return_value = [
            {
                "id": 2,
                "threadTs": "456.789",
                "channelId": "C456",
                "ownerUserId": "U_PIM",
                "updatedAt": (datetime.now(UTC) - timedelta(days=25)).isoformat(),
                "pulseNudgedAt": recent_nudge,
            }
        ]
        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)
        mock_slack.chat_postMessage.assert_not_called()


class TestThreadPermalinkInNudges:
    """The raw thread_ts must never reach the DM; a Slack permalink does."""

    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id", return_value="U_PIM")
    @patch("pulse.scanner._get_thread_stage", return_value=None)
    @patch("pulse.scanner.mark_thread_pulse_nudged")
    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_stale_threads")
    def test_stale_thread_dm_contains_permalink_not_raw_ts(
        self, mock_get, mock_nudge, mock_ci, mock_mark, mock_stage, mock_slack_id, mock_snoozed
    ):
        mock_get.return_value = [
            {
                "id": 2,
                "threadTs": "1776162509.690509",
                "channelId": "C456",
                "ownerUserId": "u-pim",
                "updatedAt": (datetime.now(UTC) - timedelta(days=25)).isoformat(),
                "pulseNudgedAt": None,
            }
        ]
        mock_nudge.return_value = "Worth circling back on the thread when you can."
        mock_slack = MagicMock()
        mock_slack.chat_getPermalink.return_value = {
            "permalink": "https://aknostic.slack.com/archives/C456/p1776162509690509"
        }

        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)

        sent = mock_slack.chat_postMessage.call_args.kwargs["text"]
        assert "1776162509.690509" not in sent  # raw ts must not leak
        assert "https://aknostic.slack.com/archives/C456/p1776162509690509" in sent
        # The LLM must have been told "a thread that's been quiet ..." — no raw ts.
        prompt_target = mock_nudge.call_args.kwargs["target_description"]
        assert "1776162509.690509" not in prompt_target

    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id", return_value="U_PIM")
    @patch("pulse.scanner._get_thread_stage", return_value=None)
    @patch("pulse.scanner.mark_thread_pulse_nudged")
    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_stale_threads")
    def test_stale_thread_dm_degrades_gracefully_when_permalink_fails(
        self, mock_get, mock_nudge, mock_ci, mock_mark, mock_stage, mock_slack_id, mock_snoozed
    ):
        mock_get.return_value = [
            {
                "id": 2,
                "threadTs": "1776162509.690509",
                "channelId": "C456",
                "ownerUserId": "u-pim",
                "updatedAt": (datetime.now(UTC) - timedelta(days=25)).isoformat(),
                "pulseNudgedAt": None,
            }
        ]
        mock_nudge.return_value = "Worth circling back on the thread when you can."
        mock_slack = MagicMock()
        mock_slack.chat_getPermalink.side_effect = Exception("slack down")

        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)

        sent = mock_slack.chat_postMessage.call_args.kwargs["text"]
        # No raw ts, no broken link — just the LLM body.
        assert "1776162509.690509" not in sent
        assert "Open the thread" not in sent
        assert sent == "Worth circling back on the thread when you can."

    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id", return_value="U_JURG")
    @patch("pulse.scanner.clear_thread_remind_after")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_due_reminders")
    def test_due_reminder_dm_contains_permalink_not_raw_ts(
        self, mock_get, mock_nudge, mock_clear, mock_slack_id, mock_snoozed
    ):
        mock_get.return_value = [
            {
                "id": 1,
                "threadTs": "1776162509.690509",
                "channelId": "C123",
                "messages": [],
                "remindAfter": "2026-04-09T08:00:00+00:00",
                "remindContext": "Follow up on the Sanoma proposal",
                "ownerUserId": "u-jurg",
                "pulseNudgedAt": None,
            }
        ]
        mock_nudge.return_value = "Time to circle back."
        mock_slack = MagicMock()
        mock_slack.chat_getPermalink.return_value = {
            "permalink": "https://aknostic.slack.com/archives/C123/p1776162509690509"
        }

        from pulse.scanner import scan_due_reminders
        scan_due_reminders(mock_slack)

        sent = mock_slack.chat_postMessage.call_args.kwargs["text"]
        assert "1776162509.690509" not in sent
        assert "https://aknostic.slack.com/archives/C123/p1776162509690509" in sent
        prompt_target = mock_nudge.call_args.kwargs["target_description"]
        assert "1776162509.690509" not in prompt_target
        assert "C123" not in prompt_target


class TestStageAwareThresholds:
    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.mark_thread_pulse_nudged")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner._get_thread_stage")
    @patch("pulse.scanner.get_stale_threads")
    def test_skips_soil_thread_under_60_days(self, mock_get, mock_stage, mock_nudge, mock_mark, mock_ci):
        from datetime import UTC, datetime, timedelta
        mock_get.return_value = [{
            "id": 5, "threadTs": "soil.123", "channelId": "C1",
            "ownerUserId": "U1", "updatedAt": (datetime.now(UTC) - timedelta(days=20)).isoformat(),
            "pulseNudgedAt": None,
        }]
        mock_stage.return_value = "soil"

        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)
        mock_nudge.assert_not_called()

    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.mark_thread_pulse_nudged")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner._get_thread_stage")
    @patch("pulse.scanner.get_stale_threads")
    def test_nudges_diagnosis_thread_over_14_days(self, mock_get, mock_stage, mock_nudge, mock_mark, mock_ci, mock_slack_id, mock_snoozed):
        from datetime import UTC, datetime, timedelta
        mock_get.return_value = [{
            "id": 6, "threadTs": "diag.456", "channelId": "C1",
            "ownerUserId": "u-1", "updatedAt": (datetime.now(UTC) - timedelta(days=16)).isoformat(),
            "pulseNudgedAt": None,
        }]
        mock_stage.return_value = "diagnosis"
        mock_nudge.return_value = "Check in on diagnosis."
        mock_slack_id.return_value = "U1"

        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)
        mock_nudge.assert_called_once()

    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.mark_thread_pulse_nudged")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner._get_thread_stage")
    @patch("pulse.scanner.get_stale_threads")
    def test_default_14_days_when_no_opportunity(self, mock_get, mock_stage, mock_nudge, mock_mark, mock_ci, mock_slack_id, mock_snoozed):
        from datetime import UTC, datetime, timedelta
        mock_get.return_value = [{
            "id": 7, "threadTs": "no_opp.789", "channelId": "C1",
            "ownerUserId": "u-1", "updatedAt": (datetime.now(UTC) - timedelta(days=16)).isoformat(),
            "pulseNudgedAt": None,
        }]
        mock_stage.return_value = None
        mock_nudge.return_value = "Thread went quiet."
        mock_slack_id.return_value = "U1"

        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)
        mock_nudge.assert_called_once()


class TestStaleContactsScan:
    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner.mark_contact_pulse_nudged")
    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_stale_contacts_for_pulse")
    def test_nudges_hot_contact(self, mock_get, mock_nudge, mock_ci, mock_mark, mock_slack_id, mock_snoozed):
        old_contact = (datetime.now(UTC) - timedelta(days=16)).isoformat()
        mock_get.return_value = [
            {
                "id": "uuid-1",
                "name": "Sarah",
                "role": "CTO",
                "temperature": "hot",
                "lastContact": old_contact,
                "ownerUserId": "u-jurg",
                "pulseNudgedAt": None,
                "companyByCompanyId": {"name": "STACKIT"},
            }
        ]
        mock_nudge.return_value = "Sarah at STACKIT — worth checking in."
        mock_slack_id.return_value = "U_JURG"

        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_contacts
        scan_stale_contacts(mock_slack)
        mock_slack.chat_postMessage.assert_called_once()

    @patch("pulse.scanner.get_stale_contacts_for_pulse")
    def test_skips_contacts_within_threshold(self, mock_get):
        recent_contact = (datetime.now(UTC) - timedelta(days=5)).isoformat()
        mock_get.return_value = [
            {
                "id": "uuid-1",
                "name": "Sarah",
                "temperature": "hot",
                "lastContact": recent_contact,
                "ownerUserId": "U_JURG",
                "pulseNudgedAt": None,
                "companyByCompanyId": {"name": "STACKIT"},
            }
        ]
        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_contacts
        scan_stale_contacts(mock_slack)
        mock_slack.chat_postMessage.assert_not_called()


class TestPipelineNudges:
    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner.mark_opportunity_pulse_nudged")
    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_stale_opportunities")
    def test_nudges_stuck_opportunity(self, mock_get, mock_nudge, mock_ci, mock_mark, mock_slack_id, mock_snoozed):
        old_date = (datetime.now(UTC) - timedelta(days=35)).isoformat()
        mock_get.return_value = [
            {
                "id": "uuid-opp-1",
                "title": "Parai sovereignty",
                "stage": "signal",
                "ownerUserId": "u-jurg",
                "updatedAt": old_date,
                "pulseNudgedAt": None,
                "notes": "Interested in sovereignty positioning",
                "companyByCompanyId": {"name": "Parai"},
                "contactByContactId": {"name": "Hans", "role": "VP Infra"},
            }
        ]
        mock_nudge.return_value = "The Parai opportunity has been in Signal for 5 weeks."
        mock_slack_id.return_value = "U_JURG"

        mock_slack = MagicMock()
        from pulse.scanner import scan_pipeline
        scan_pipeline(mock_slack)
        mock_slack.chat_postMessage.assert_called_once()


class TestFullScan:
    @patch("pulse.scanner.scan_user_reminders")
    @patch("pulse.scanner.scan_expansion_triggers")
    @patch("pulse.scanner._check_expired_enrollments")
    @patch("pulse.scanner.scan_pipeline")
    @patch("pulse.scanner.scan_stale_contacts")
    @patch("pulse.scanner.scan_stale_threads")
    @patch("pulse.scanner.scan_due_reminders")
    @patch("pulse.scanner.time")
    @patch("pulse.scanner.WebClient")
    def test_runs_all_scans_sequentially(self, mock_wc, mock_time, mock_reminders, mock_threads, mock_contacts, mock_pipeline, mock_expired, mock_expansion, mock_user_reminders):
        from pulse.scanner import run_scan
        run_scan()
        mock_reminders.assert_called_once()
        mock_threads.assert_called_once()
        mock_contacts.assert_called_once()
        mock_pipeline.assert_called_once()
        mock_expired.assert_called_once()
        mock_expansion.assert_called_once()
        mock_user_reminders.assert_called_once()


class TestCIContextFetching:
    @patch("pulse.scanner.search_similar")
    def test_fetch_ci_context_returns_formatted_results(self, mock_search):
        mock_search.return_value = [
            {"reframe": "Cloud sovereignty is about freedom to operate, not isolation."},
            {"belief": "CTOs fear vendor lock-in more than migration cost."},
        ]
        from pulse.scanner import _fetch_ci_context
        result = _fetch_ci_context("STACKIT sovereignty")
        assert "sovereignty" in result.lower() or "freedom" in result.lower()
        mock_search.assert_called()

    @patch("pulse.scanner.search_similar")
    def test_fetch_ci_context_empty_when_no_results(self, mock_search):
        mock_search.return_value = []
        from pulse.scanner import _fetch_ci_context
        result = _fetch_ci_context("unknown topic")
        assert result == ""

    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner._fetch_ci_context")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_stale_contacts_for_pulse")
    @patch("pulse.scanner.mark_contact_pulse_nudged")
    def test_stale_contact_nudge_includes_ci_context(self, mock_mark, mock_get, mock_nudge, mock_ci, mock_slack_id, mock_snoozed):
        from datetime import UTC, datetime, timedelta
        old_contact = (datetime.now(UTC) - timedelta(days=16)).isoformat()
        mock_get.return_value = [{
            "id": "uuid-1", "name": "Sarah", "role": "CTO",
            "temperature": "hot", "lastContact": old_contact,
            "ownerUserId": "u-jurg", "pulseNudgedAt": None,
            "companyByCompanyId": {"name": "STACKIT"},
        }]
        mock_ci.return_value = "Sovereignty concerns align with reframe."
        mock_nudge.return_value = "Sarah at STACKIT — worth checking in."
        mock_slack_id.return_value = "U_JURG"

        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_contacts
        scan_stale_contacts(mock_slack)

        mock_nudge.assert_called_once()
        call_kwargs = mock_nudge.call_args
        # ci_context should be non-empty (passed from _fetch_ci_context)
        assert "ci_context" in str(call_kwargs)
