"""Tests for account plan and client expansion GraphQL functions."""
from unittest.mock import patch


class TestAccountPlanCRUD:
    @patch("mothertree.graphql_client.graphql")
    def test_get_account_plan(self, mock_gql):
        mock_gql.return_value = {"allAccountPlansList": [
            {"id": "plan-1", "companyId": "co-1", "whiteSpace": "AI platform", "strategy": "Expand to ML ops"}
        ]}
        from mothertree.graphql_client import get_account_plan
        plan = get_account_plan("co-1")
        assert plan is not None
        assert plan["whiteSpace"] == "AI platform"

    @patch("mothertree.graphql_client.graphql")
    def test_get_account_plan_not_found(self, mock_gql):
        mock_gql.return_value = {"allAccountPlansList": []}
        from mothertree.graphql_client import get_account_plan
        assert get_account_plan("co-unknown") is None

    @patch("mothertree.graphql_client.graphql")
    def test_create_account_plan(self, mock_gql):
        mock_gql.return_value = {"createAccountPlan": {"accountPlan": {"id": "plan-1", "companyId": "co-1"}}}
        from mothertree.graphql_client import create_account_plan
        plan = create_account_plan("co-1", white_space="AI platform")
        assert plan is not None

    @patch("mothertree.graphql_client.graphql")
    def test_update_account_plan(self, mock_gql):
        mock_gql.return_value = {"updateAccountPlanById": {"accountPlan": {"id": "plan-1"}}}
        from mothertree.graphql_client import update_account_plan
        update_account_plan("plan-1", strategy="Expand to ML ops")
        mock_gql.assert_called_once()

    @patch("mothertree.graphql_client.graphql")
    def test_get_due_qbrs(self, mock_gql):
        mock_gql.return_value = {"allAccountPlansList": [
            {"id": "plan-1", "companyId": "co-1", "nextQbr": "2026-04-01"}
        ]}
        from mothertree.graphql_client import get_due_qbrs
        plans = get_due_qbrs()
        assert len(plans) == 1

    @patch("mothertree.graphql_client.graphql")
    def test_get_accounts_with_plans(self, mock_gql):
        mock_gql.return_value = {"allAccountPlansList": [
            {"id": "plan-1", "companyId": "co-1", "companyByCompanyId": {"name": "Sanoma Learning"}}
        ]}
        from mothertree.graphql_client import get_accounts_with_plans
        accounts = get_accounts_with_plans()
        assert len(accounts) == 1


class TestCompanyClientFields:
    @patch("mothertree.graphql_client.graphql")
    def test_update_company_client_fields(self, mock_gql):
        mock_gql.return_value = {"updateCompanyById": {"company": {"id": "co-1"}}}
        from mothertree.graphql_client import update_company_client_fields
        update_company_client_fields("co-1", client_since="2014-01-01", services=["IDP", "operate"])
        mock_gql.assert_called_once()

    @patch("mothertree.graphql_client.graphql")
    def test_get_client_companies(self, mock_gql):
        mock_gql.return_value = {"allCompaniesList": [
            {"id": "co-1", "name": "Sanoma Learning", "clientSince": "2014-01-01"}
        ]}
        from mothertree.graphql_client import get_client_companies
        clients = get_client_companies()
        assert len(clients) == 1


class TestEngagementServiceMeeting:
    @patch("mothertree.graphql_client.graphql")
    def test_get_due_service_meetings(self, mock_gql):
        mock_gql.return_value = {"allEngagementsList": [
            {"id": "eng-1", "title": "IDP Build", "nextServiceMeeting": "2026-04-14", "ownerUserId": "user-1"}
        ]}
        from mothertree.graphql_client import get_due_service_meetings
        meetings = get_due_service_meetings()
        assert len(meetings) == 1

    @patch("mothertree.graphql_client.graphql")
    def test_update_service_meeting(self, mock_gql):
        mock_gql.return_value = {"updateEngagementById": {"engagement": {"id": "eng-1"}}}
        from mothertree.graphql_client import update_service_meeting
        update_service_meeting("eng-1", notes="All good", next_date="2026-05-14")
        mock_gql.assert_called_once()
