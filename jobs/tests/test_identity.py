"""Tests for email-first identity resolution."""
from unittest.mock import MagicMock, patch


class TestChannelLinkLookup:
    @patch("mothertree.graphql_client.graphql")
    def test_finds_existing_link(self, mock_gql):
        mock_gql.return_value = {"allChannelLinksList": [
            {"userId": "user-uuid-1", "channelType": "slack", "channelUserId": "U_JURG"}
        ]}
        from mothertree.graphql_client import get_channel_link
        link = get_channel_link("slack", "U_JURG")
        assert link is not None
        assert link["userId"] == "user-uuid-1"

    @patch("mothertree.graphql_client.graphql")
    def test_returns_none_when_no_link(self, mock_gql):
        mock_gql.return_value = {"allChannelLinksList": []}
        from mothertree.graphql_client import get_channel_link
        link = get_channel_link("slack", "U_UNKNOWN")
        assert link is None


class TestUserLookup:
    @patch("mothertree.graphql_client.graphql")
    def test_get_user_by_email(self, mock_gql):
        mock_gql.return_value = {"allUsersList": [
            {"id": "user-uuid-1", "email": "jurg@aknostic.com", "name": "Jurg", "role": "hunter"}
        ]}
        from mothertree.graphql_client import get_user_by_email
        user = get_user_by_email("jurg@aknostic.com")
        assert user is not None
        assert user["role"] == "hunter"

    @patch("mothertree.graphql_client.graphql")
    def test_get_user_by_email_normalizes(self, mock_gql):
        mock_gql.return_value = {"allUsersList": [
            {"id": "user-uuid-1", "email": "jurg@aknostic.com", "name": "Jurg", "role": "hunter"}
        ]}
        from mothertree.graphql_client import get_user_by_email
        get_user_by_email("Jurg@Aknostic.com")
        assert "jurg@aknostic.com" in str(mock_gql.call_args)

    @patch("mothertree.graphql_client.graphql")
    def test_create_user(self, mock_gql):
        mock_gql.return_value = {"createUser": {"user": {"id": "new-uuid", "email": "pim@aknostic.com"}}}
        from mothertree.graphql_client import create_user
        user = create_user("pim@aknostic.com", "Pim", "citizen")
        assert user is not None


class TestCreateChannelLink:
    @patch("mothertree.graphql_client.graphql")
    def test_creates_link(self, mock_gql):
        mock_gql.return_value = {"createChannelLink": {"channelLink": {"id": "link-1"}}}
        from mothertree.graphql_client import create_channel_link
        create_channel_link("user-uuid-1", "slack", "U_JURG")
        mock_gql.assert_called_once()


class TestReverseLookup:
    @patch("mothertree.graphql_client.graphql")
    def test_get_slack_user_id(self, mock_gql):
        mock_gql.return_value = {"allChannelLinksList": [
            {"channelUserId": "U_JURG", "channelType": "slack"}
        ]}
        from mothertree.graphql_client import get_slack_user_id
        sid = get_slack_user_id("user-uuid-1")
        assert sid == "U_JURG"

    @patch("mothertree.graphql_client.graphql")
    def test_returns_none_when_no_slack(self, mock_gql):
        mock_gql.return_value = {"allChannelLinksList": []}
        from mothertree.graphql_client import get_slack_user_id
        sid = get_slack_user_id("user-uuid-orphan")
        assert sid is None


class TestAdminFunctions:
    @patch("mothertree.graphql_client.graphql")
    def test_is_admin(self, mock_gql):
        mock_gql.return_value = {"allAdminsList": [{"email": "jurg@aknostic.com"}]}
        from mothertree.graphql_client import is_admin
        assert is_admin("jurg@aknostic.com") is True

    @patch("mothertree.graphql_client.graphql")
    def test_is_not_admin(self, mock_gql):
        mock_gql.return_value = {"allAdminsList": []}
        from mothertree.graphql_client import is_admin
        assert is_admin("random@example.com") is False

    @patch("mothertree.graphql_client.graphql")
    def test_add_admin(self, mock_gql):
        mock_gql.return_value = {"createAdmin": {"admin": {"id": "a1"}}}
        from mothertree.graphql_client import add_admin
        add_admin("pim@aknostic.com", granted_by="jurg@aknostic.com")
        mock_gql.assert_called_once()

    @patch("mothertree.graphql_client.graphql")
    def test_ensure_root_admin(self, mock_gql):
        mock_gql.side_effect = [
            {"allAdminsList": []},
            {"createAdmin": {"admin": {"id": "root-1"}}},
        ]
        from mothertree.graphql_client import ensure_root_admin
        ensure_root_admin("jurg@aknostic.com")
        assert mock_gql.call_count == 2


class TestResolveUser:
    @patch("mothertree.graphql_client.create_channel_link")
    @patch("mothertree.graphql_client.create_user")
    @patch("mothertree.graphql_client.get_user_by_email")
    @patch("mothertree.graphql_client.get_channel_link")
    def test_cached_path(self, mock_link, mock_email, mock_create, mock_create_link):
        """Known Slack user with existing channel_link."""
        mock_link.return_value = {"userId": "user-1"}
        with patch("mothertree.graphql_client.get_user") as mock_get:
            mock_get.return_value = {"id": "user-1", "email": "jurg@aknostic.com", "role": "hunter"}
            from mothertree.identity import resolve_user
            client = MagicMock()
            user = resolve_user("U_JURG", client)
            assert user["id"] == "user-1"
            client.users_info.assert_not_called()

    @patch("mothertree.graphql_client.create_channel_link")
    @patch("mothertree.graphql_client.get_user_by_email")
    @patch("mothertree.graphql_client.get_channel_link")
    def test_first_contact_existing_user(self, mock_link, mock_email, mock_create_link):
        """New Slack user, but email already in users table."""
        mock_link.return_value = None
        mock_email.return_value = {"id": "user-1", "email": "jurg@aknostic.com", "name": "Jurg", "role": "hunter"}
        from mothertree.identity import resolve_user
        client = MagicMock()
        client.users_info.return_value = {"user": {"profile": {"email": "jurg@aknostic.com"}, "real_name": "Jurg van Vliet"}}
        user = resolve_user("U_JURG", client)
        assert user["id"] == "user-1"
        mock_create_link.assert_called_once()

    @patch("mothertree.graphql_client.create_channel_link")
    @patch("mothertree.graphql_client.get_user_by_email")
    @patch("mothertree.graphql_client.get_channel_link")
    def test_refuses_link_when_names_disagree(self, mock_link, mock_email, mock_create_link):
        """Email lookup hits an existing user but Slack real_name is a different person.

        Guards the historical case where ADMIN_SLACK_ID was set to the wrong
        Slack ID and a migration silently linked Matthijs's Slack profile to
        Jurg's user record.
        """
        mock_link.return_value = None
        mock_email.return_value = {"id": "user-1", "email": "jurg@aknostic.com", "name": "Jurg", "role": "hunter"}
        from mothertree.identity import resolve_user
        client = MagicMock()
        # Slack returns Matthijs's profile but the email field somehow matches Jurg's record.
        client.users_info.return_value = {"user": {"profile": {"email": "jurg@aknostic.com"}, "real_name": "Matthijs Bosman"}}
        user = resolve_user("U_MATTHIJS", client)
        assert user is None
        mock_create_link.assert_not_called()

    @patch("mothertree.graphql_client.create_channel_link")
    @patch("mothertree.graphql_client.create_user")
    @patch("mothertree.graphql_client.get_user_by_email")
    @patch("mothertree.graphql_client.get_channel_link")
    def test_first_contact_new_user(self, mock_link, mock_email, mock_create, mock_create_link):
        """Completely new user — auto-create as citizen."""
        mock_link.return_value = None
        mock_email.return_value = None
        mock_create.return_value = {"id": "new-user", "email": "newcomer@example.com", "role": "citizen"}
        from mothertree.identity import resolve_user
        client = MagicMock()
        client.users_info.return_value = {"user": {"profile": {"email": "newcomer@example.com"}, "real_name": "New Person"}}
        user = resolve_user("U_NEW", client)
        assert user["role"] == "citizen"
        mock_create.assert_called_once_with(email="newcomer@example.com", name="New Person", role="citizen")

    @patch("mothertree.graphql_client.get_channel_link")
    def test_bot_user_no_email(self, mock_link):
        """Slack bot user with no email → returns None."""
        mock_link.return_value = None
        from mothertree.identity import resolve_user
        client = MagicMock()
        client.users_info.return_value = {"user": {"profile": {}, "real_name": "SomeBot"}}
        user = resolve_user("U_BOT", client)
        assert user is None
