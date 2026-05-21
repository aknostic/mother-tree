"""Tests for Pulse GraphQL queries."""
from unittest.mock import patch


class TestPulseQueries:
    @patch("mothertree.graphql_client.graphql")
    def test_get_due_reminders(self, mock_gql):
        mock_gql.return_value = {
            "allThreadMemoriesList": [
                {
                    "id": 1,
                    "threadTs": "123.456",
                    "channelId": "C123",
                    "messages": [],
                    "remindAfter": "2026-04-09T08:00:00+00:00",
                    "remindContext": "Follow up on proposal",
                    "ownerUserId": "U123",
                    "pulseNudgedAt": None,
                }
            ]
        }
        from mothertree.graphql_client import get_due_reminders
        results = get_due_reminders()
        assert len(results) == 1
        assert results[0]["ownerUserId"] == "U123"

    @patch("mothertree.graphql_client.graphql")
    def test_get_stale_threads(self, mock_gql):
        mock_gql.return_value = {
            "allThreadMemoriesList": [
                {
                    "id": 1,
                    "threadTs": "123.456",
                    "channelId": "C123",
                    "ownerUserId": "U123",
                    "updatedAt": "2026-03-01T00:00:00+00:00",
                    "pulseNudgedAt": None,
                    "remindAfter": None,
                }
            ]
        }
        from mothertree.graphql_client import get_stale_threads
        results = get_stale_threads(days=21)
        assert len(results) == 1

    @patch("mothertree.graphql_client.graphql")
    def test_get_stale_contacts(self, mock_gql):
        mock_gql.return_value = {
            "allContactsList": [
                {
                    "id": "uuid-1",
                    "name": "Sarah",
                    "temperature": "hot",
                    "lastContact": "2026-03-20T00:00:00+00:00",
                    "ownerUserId": "U123",
                    "pulseNudgedAt": None,
                    "companyByCompanyId": {"name": "STACKIT"},
                }
            ]
        }
        from mothertree.graphql_client import get_stale_contacts_for_pulse
        results = get_stale_contacts_for_pulse()
        assert len(results) == 1
        assert results[0]["name"] == "Sarah"

    @patch("mothertree.graphql_client.graphql")
    def test_get_stale_opportunities(self, mock_gql):
        mock_gql.return_value = {
            "allOpportunitiesList": [
                {
                    "id": "uuid-1",
                    "title": "Parai sovereignty",
                    "stage": "signal",
                    "ownerUserId": "U123",
                    "updatedAt": "2026-03-01T00:00:00+00:00",
                    "pulseNudgedAt": None,
                    "companyByCompanyId": {"name": "Parai"},
                }
            ]
        }
        from mothertree.graphql_client import get_stale_opportunities
        results = get_stale_opportunities()
        assert len(results) == 1

    @patch("mothertree.graphql_client.graphql")
    def test_mark_pulse_nudged(self, mock_gql):
        mock_gql.return_value = {"updateThreadMemoryById": {"threadMemory": {"id": 1}}}
        from mothertree.graphql_client import mark_thread_pulse_nudged
        mark_thread_pulse_nudged(1)
        mock_gql.assert_called_once()

    @patch("mothertree.graphql_client.graphql")
    def test_clear_remind_after(self, mock_gql):
        mock_gql.return_value = {"updateThreadMemoryById": {"threadMemory": {"id": 1}}}
        from mothertree.graphql_client import clear_thread_remind_after
        clear_thread_remind_after(1)
        mock_gql.assert_called_once()
