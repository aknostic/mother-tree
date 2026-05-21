"""Tests for enrollment approval flow."""
from unittest.mock import patch


class TestEnrollmentRequest:
    @patch("mothertree.graphql_client.graphql")
    def test_create_enrollment_request(self, mock_gql):
        mock_gql.return_value = {"createEnrollmentRequest": {"enrollmentRequest": {"id": "req-1"}}}
        from mothertree.graphql_client import create_enrollment_request
        result = create_enrollment_request("u-1", "hunter")
        assert result is not None

    @patch("mothertree.graphql_client.graphql")
    def test_get_pending_requests(self, mock_gql):
        mock_gql.return_value = {"allEnrollmentRequestsList": [
            {"id": "req-1", "userId": "u-1", "requestedRole": "hunter"}
        ]}
        from mothertree.graphql_client import get_pending_enrollment_requests
        results = get_pending_enrollment_requests()
        assert len(results) == 1

    @patch("mothertree.graphql_client.graphql")
    def test_resolve_request(self, mock_gql):
        mock_gql.return_value = {"updateEnrollmentRequestById": {"enrollmentRequest": {"id": "req-1"}}}
        from mothertree.graphql_client import resolve_enrollment_request
        resolve_enrollment_request("req-1", "approved", approved_by="u-admin")
        mock_gql.assert_called_once()


class TestAdminCommandDetection:
    def test_detects_pending_command(self):
        from bot.characters.dispatcher import _detect_admin_command
        result = _detect_admin_command("pending")
        assert result == {"action": "pending"}

    def test_detects_make_admin(self):
        from bot.characters.dispatcher import _detect_admin_command
        result = _detect_admin_command("make admin jurg@aknostic.com")
        assert result == {"action": "make_admin", "email": "jurg@aknostic.com"}

    def test_detects_enroll_as(self):
        from bot.characters.dispatcher import _detect_admin_command
        result = _detect_admin_command("enroll pim@example.com as hunter")
        assert result == {"action": "admin_enroll", "email": "pim@example.com", "role": "hunter"}

    def test_detects_enroll_with_slack_mailto(self):
        from bot.characters.dispatcher import _detect_admin_command
        result = _detect_admin_command("enroll <mailto:pim@aknostic.com|pim@aknostic.com> as hunter")
        assert result == {"action": "admin_enroll", "email": "pim@aknostic.com", "role": "hunter"}

    def test_make_admin_with_slack_mailto(self):
        from bot.characters.dispatcher import _detect_admin_command
        result = _detect_admin_command("make admin <mailto:pim@aknostic.com|pim@aknostic.com>")
        assert result == {"action": "make_admin", "email": "pim@aknostic.com"}

    def test_no_match_on_regular_text(self):
        from bot.characters.dispatcher import _detect_admin_command
        result = _detect_admin_command("what's the status?")
        assert result is None


class TestRequestTimeout:
    @patch("mothertree.graphql_client.graphql")
    def test_expire_old_requests(self, mock_gql):
        mock_gql.return_value = {"allEnrollmentRequestsList": [
            {"id": "req-old", "userId": "u-old", "createdAt": "2026-04-08T00:00:00+00:00"}
        ]}
        from mothertree.graphql_client import get_expired_enrollment_requests
        results = get_expired_enrollment_requests(hours=48)
        assert len(results) == 1
