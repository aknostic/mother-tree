"""Tests for QBR synthesis and service meeting scheduling."""
from unittest.mock import MagicMock, patch


class TestSynthesizeQBR:
    @patch("discipline.qbr_review.generate")
    @patch("discipline.qbr_review.gather_account")
    def test_synthesizes_briefing(self, mock_gather, mock_gen):
        mock_gather.return_value = {
            "company": {"id": "co-1", "name": "Sanoma Learning"},
            "contacts": [{"name": "JJ", "role": "Engineering Lead"}],
            "interactions": [],
            "signals": [{"content": "Budget freeze lifted", "source": "slack"}],
            "opportunities": [],
            "engagements": [{"title": "IDP Build", "status": "active"}],
            "account_plan": None,
        }
        mock_gen.return_value = "QBR briefing for Sanoma Learning"
        from discipline.qbr_review import synthesize_qbr
        result = synthesize_qbr("co-1", "Sanoma Learning")
        assert "Sanoma Learning" in result or "QBR" in result
        mock_gen.assert_called_once()
        mock_gather.assert_called_once_with(company_id="co-1")


class TestDeliverQBRs:
    @patch("discipline.qbr_review.get_slack_user_id")
    @patch("discipline.qbr_review.synthesize_qbr")
    @patch("discipline.qbr_review.get_due_qbrs")
    @patch("discipline.qbr_review.update_account_plan")
    def test_delivers_due_qbrs(self, mock_update, mock_due, mock_synth, mock_slack_id):
        mock_due.return_value = [{
            "id": "plan-1", "companyId": "co-1", "nextQbr": "2026-04-01",
            "companyByCompanyId": {"id": "co-1", "name": "Sanoma", "ownerUserId": "user-1"},
        }]
        mock_synth.return_value = "Briefing text"
        mock_slack_id.return_value = "U_JURG"
        from discipline.qbr_review import deliver_qbrs
        slack = MagicMock()
        deliver_qbrs(slack)
        mock_synth.assert_called_once()
        mock_update.assert_called_once()
        slack.chat_postMessage.assert_called_once()


class TestDeliverServiceMeetingPreps:
    @patch("discipline.qbr_review.gather_account")
    @patch("discipline.qbr_review.get_slack_user_id")
    @patch("discipline.qbr_review.generate")
    @patch("discipline.qbr_review.get_due_service_meetings")
    def test_delivers_prep_for_due_meetings(
        self, mock_due, mock_gen, mock_slack_id, mock_gather
    ):
        mock_due.return_value = [{
            "id": "eng-1", "title": "IDP Build", "ownerUserId": "user-1",
            "nextServiceMeeting": "2026-04-15",
            "companyByCompanyId": {"id": "co-1", "name": "Sanoma"},
        }]
        mock_gather.return_value = {
            "company": {"id": "co-1", "name": "Sanoma"},
            "contacts": [],
            "interactions": [],
            "signals": [],
            "opportunities": [],
            "engagements": [],
            "account_plan": None,
        }
        mock_gen.return_value = "Service meeting prep"
        mock_slack_id.return_value = "U_JURG"
        from discipline.qbr_review import deliver_service_meeting_preps
        slack = MagicMock()
        deliver_service_meeting_preps(slack)
        mock_gen.assert_called_once()
        slack.chat_postMessage.assert_called_once()


class TestExpansionTriggers:
    @patch("pulse.scanner._is_snoozed", return_value=False)
    @patch("pulse.scanner.mark_company_pulse_nudged")
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.graphql")
    def test_detects_stale_account_plan(self, mock_gql, mock_nudge, mock_slack_id, mock_mark, mock_snoozed):
        from datetime import UTC, datetime, timedelta
        stale_date = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        mock_gql.return_value = {"allAccountPlansList": [{
            "id": "plan-1",
            "updatedAt": stale_date,
            "companyByCompanyId": {"id": "co-1", "name": "Sanoma", "ownerUserId": "user-1", "clientSince": "2014-01-01", "pulseNudgedAt": None},
        }]}
        mock_nudge.return_value = "Time to review Sanoma"
        mock_slack_id.return_value = "U_JURG"
        from pulse.scanner import scan_expansion_triggers
        slack = MagicMock()
        scan_expansion_triggers(slack)
        mock_nudge.assert_called_once()
        mock_mark.assert_called_once_with("co-1")

    @patch("pulse.scanner.graphql")
    def test_skips_recently_nudged(self, mock_gql):
        from datetime import UTC, datetime
        mock_gql.return_value = {"allAccountPlansList": [{
            "id": "plan-1",
            "updatedAt": "2026-01-01T00:00:00+00:00",
            "companyByCompanyId": {"id": "co-1", "name": "Sanoma", "ownerUserId": "user-1", "clientSince": "2014-01-01", "pulseNudgedAt": datetime.now(UTC).isoformat()},
        }]}
        from pulse.scanner import scan_expansion_triggers
        slack = MagicMock()
        scan_expansion_triggers(slack)
        slack.chat_postMessage.assert_not_called()
