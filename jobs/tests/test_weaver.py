"""Tests for Weaver — entity resolution against the relationship graph."""
from unittest.mock import patch


class TestWeaverIdentity:

    def test_identity_contains_mycelium(self):
        from bot.characters.weaver import IDENTITY
        assert "mycelium" in IDENTITY.lower()

    def test_identity_contains_invisibility_rule(self):
        from bot.characters.weaver import IDENTITY
        assert "invisible" in IDENTITY.lower()

    def test_identity_contains_resolution_states(self):
        from bot.characters.weaver import IDENTITY
        for state in ("NEW", "MATCHED", "UNCERTAIN"):
            assert state in IDENTITY

    def test_identity_contains_no_fabricate_rule(self):
        from bot.characters.weaver import IDENTITY
        assert "fabricate" in IDENTITY.lower()


class TestWeaverResolve:

    @patch("bot.characters.weaver.get_existing_graph")
    @patch("bot.characters.weaver.chat_conversation")
    def test_new_entity_resolved_as_new(self, mock_chat, mock_graph):
        from bot.characters.weaver import resolve
        mock_graph.return_value = {"contacts": [], "companies": [], "signals": []}
        mock_chat.return_value = '{"resolved": [{"entity": {"name": "Jim Blom", "type": "person"}, "resolution": "NEW", "matched_id": null, "candidate_ids": [], "reason": "No existing contact with this name"}], "flags": []}'
        result = resolve([{"name": "Jim Blom", "type": "person", "role": "Co-founder"}])
        assert result is not None
        assert result["resolved"][0]["resolution"] == "NEW"

    @patch("bot.characters.weaver.get_existing_graph")
    @patch("bot.characters.weaver.chat_conversation")
    def test_existing_entity_resolved_as_matched(self, mock_chat, mock_graph):
        from bot.characters.weaver import resolve
        mock_graph.return_value = {
            "contacts": [{"id": "abc-123", "full_name": "Flavia Santos", "role": "CTO", "company_id": None}],
            "companies": [],
            "signals": [],
        }
        mock_chat.return_value = '{"resolved": [{"entity": {"name": "Flavia Santos", "type": "person"}, "resolution": "MATCHED", "matched_id": "abc-123", "candidate_ids": [], "reason": "Exact name match in contacts"}], "flags": []}'
        result = resolve([{"name": "Flavia Santos", "type": "person"}])
        assert result is not None
        assert result["resolved"][0]["resolution"] == "MATCHED"
        assert result["resolved"][0]["matched_id"] == "abc-123"

    @patch("bot.characters.weaver.get_existing_graph")
    @patch("bot.characters.weaver.chat_conversation")
    def test_ambiguous_entity_flagged_as_uncertain(self, mock_chat, mock_graph):
        from bot.characters.weaver import resolve
        mock_graph.return_value = {
            "contacts": [
                {"id": "id-1", "full_name": "Jim de Vries", "role": "CEO", "company_id": None},
                {"id": "id-2", "full_name": "Jim Blom", "role": "CTO", "company_id": None},
            ],
            "companies": [],
            "signals": [],
        }
        mock_chat.return_value = '{"resolved": [{"entity": {"name": "Jim", "type": "person"}, "resolution": "UNCERTAIN", "matched_id": null, "candidate_ids": ["id-1", "id-2"], "reason": "Multiple contacts named Jim, cannot determine which"}], "flags": ["Ambiguous contact: Jim — 2 candidates"]}'
        result = resolve([{"name": "Jim", "type": "person"}])
        assert result is not None
        assert result["resolved"][0]["resolution"] == "UNCERTAIN"
        assert len(result["resolved"][0]["candidate_ids"]) == 2

    @patch("bot.characters.weaver.chat_conversation")
    def test_llm_failure_returns_none(self, mock_chat):
        from bot.characters.weaver import resolve
        mock_chat.side_effect = Exception("LLM timeout")
        with patch("bot.characters.weaver.get_existing_graph") as mock_graph:
            mock_graph.return_value = {"contacts": [], "companies": [], "signals": []}
            result = resolve([{"name": "Test", "type": "person"}])
        assert result is None

    def test_empty_entities_returns_empty_resolved(self):
        from bot.characters.weaver import resolve
        result = resolve([])
        assert result == {"resolved": [], "flags": []}


class TestWeaverGetExistingGraph:

    @patch("bot.characters.weaver.graphql")
    def test_get_existing_graph_returns_structure(self, mock_graphql):
        from bot.characters.weaver import get_existing_graph
        mock_graphql.return_value = {
            "allContactsList": [{"id": "c1", "fullName": "Test User", "role": "CEO", "companyId": None}],
            "allCompaniesList": [{"id": "co1", "name": "Acme", "industry": "tech"}],
            "allSignalsList": [],
        }
        result = get_existing_graph()
        assert "contacts" in result
        assert "companies" in result
        assert "signals" in result
        assert result["contacts"][0]["fullName"] == "Test User"

    @patch("bot.characters.weaver.graphql")
    def test_get_existing_graph_handles_failure(self, mock_graphql):
        from bot.characters.weaver import get_existing_graph
        mock_graphql.side_effect = Exception("Hasura unavailable")
        result = get_existing_graph()
        assert result == {"contacts": [], "companies": [], "signals": [], "personas": []}


class TestSpotterWeaverChain:
    """Integration tests for Spotter → Weaver chain."""

    @patch("bot.characters.weaver.get_existing_graph")
    @patch("bot.characters.weaver.chat_conversation")
    @patch("bot.characters.spotter.chat_conversation")
    def test_spotter_weaver_chain(self, mock_spotter_chat, mock_weaver_chat, mock_graph):
        from bot.characters.spotter import extract
        from bot.characters.weaver import resolve

        mock_spotter_chat.return_value = '{"entities": [{"name": "Dolf Kreemers", "type": "person", "role": "CTO", "organization": "KPN"}], "pain_signals": [{"signal": "High cloud costs"}], "value_hooks": [], "actions": [], "stage": {"current": "Signal", "evidence": ["CTO expressed cost frustration"]}}'
        mock_graph.return_value = {"contacts": [], "companies": [], "signals": []}
        mock_weaver_chat.return_value = '{"resolved": [{"entity": {"name": "Dolf Kreemers", "type": "person"}, "resolution": "NEW", "matched_id": null, "candidate_ids": [], "reason": "No existing record"}], "flags": []}'

        spotter_result = extract("met Dolf from KPN, high cloud costs", "Interesting signal", "Jurg")
        assert spotter_result is not None
        assert len(spotter_result["entities"]) == 1

        weaver_result = resolve(spotter_result["entities"])
        assert weaver_result is not None
        assert weaver_result["resolved"][0]["resolution"] == "NEW"

    @patch("bot.characters.weaver.get_existing_graph")
    @patch("bot.characters.weaver.chat_conversation")
    @patch("bot.characters.spotter.chat_conversation")
    def test_chain_weaver_failure_yields_none(self, mock_spotter_chat, mock_weaver_chat, mock_graph):
        from bot.characters.spotter import extract
        from bot.characters.weaver import resolve

        mock_spotter_chat.return_value = '{"entities": [{"name": "Test Person", "type": "person"}], "pain_signals": [], "value_hooks": [], "actions": [], "stage": {"current": "Soil", "evidence": []}}'
        mock_graph.return_value = {"contacts": [], "companies": [], "signals": []}
        mock_weaver_chat.side_effect = Exception("Weaver failed")

        spotter_result = extract("test message", "test response", "testuser")
        assert spotter_result is not None

        weaver_result = resolve(spotter_result["entities"])
        assert weaver_result is None


class TestApplyResolution:
    """Tests for _apply_resolution in extraction.py."""

    @patch("mothertree.graphql_client.search_contacts_fuzzy")
    @patch("mothertree.graphql_client.find_or_create_contact")
    def test_apply_resolution_contacts(self, mock_contact, mock_fuzzy):
        from bot.extraction import _apply_resolution
        mock_fuzzy.return_value = None
        mock_contact.return_value = {"id": "new-id", "full_name": "Jim Blom"}
        resolution = {
            "resolved": [
                {
                    "entity": {"name": "Jim Blom", "type": "person", "role": "CEO"},
                    "resolution": "NEW",
                    "matched_id": None,
                    "candidate_ids": [],
                    "reason": "Not found",
                }
            ],
            "flags": [],
        }
        result = _apply_resolution(resolution)
        mock_contact.assert_called_once_with(full_name="Jim Blom", role="CEO", company_id=None)
        assert result["contacts_processed"] == 1

    @patch("mothertree.entities.find_or_create_company")
    def test_apply_resolution_companies(self, mock_company):
        from bot.extraction import _apply_resolution
        mock_company.return_value = {"id": "co-id", "name": "Acme Corp"}
        resolution = {
            "resolved": [
                {
                    "entity": {"name": "Acme Corp", "type": "organization"},
                    "resolution": "NEW",
                    "matched_id": None,
                    "candidate_ids": [],
                    "reason": "Not found",
                }
            ],
            "flags": [],
        }
        result = _apply_resolution(resolution)
        mock_company.assert_called_once_with("Acme Corp")
        assert result["companies_processed"] == 1

    def test_apply_resolution_skips_matched(self):
        from bot.extraction import _apply_resolution
        resolution = {
            "resolved": [
                {
                    "entity": {"name": "Existing Person", "type": "person"},
                    "resolution": "MATCHED",
                    "matched_id": "existing-id",
                    "candidate_ids": [],
                    "reason": "Found exact match",
                }
            ],
            "flags": [],
        }
        # MATCHED entities don't need creation — should skip without error
        result = _apply_resolution(resolution)
        assert result["contacts_processed"] == 0

    def test_apply_resolution_skips_uncertain(self):
        from bot.extraction import _apply_resolution
        resolution = {
            "resolved": [
                {
                    "entity": {"name": "Ambiguous Jim", "type": "person"},
                    "resolution": "UNCERTAIN",
                    "matched_id": None,
                    "candidate_ids": ["id-1", "id-2"],
                    "reason": "Multiple candidates",
                }
            ],
            "flags": ["Ambiguous contact"],
        }
        # UNCERTAIN entities are flagged but not created
        result = _apply_resolution(resolution)
        assert result["contacts_processed"] == 0
        assert "Ambiguous contact" in result["flags"]
        # Also includes the structured flag for clarifying questions
        assert any(f.get("entity") == "Ambiguous Jim" for f in result["flags"] if isinstance(f, dict))


class TestContactDedup:
    @patch("mothertree.graphql_client.graphql")
    def test_fuzzy_match_substring_same_company(self, mock_gql):
        mock_gql.return_value = {
            "allContactsList": [
                {"id": "existing-1", "name": "Jurg van Vliet", "companyByCompanyId": {"id": "company-1"}},
            ]
        }
        from mothertree.graphql_client import search_contacts_fuzzy
        result = search_contacts_fuzzy("Jurg", company_id="company-1")
        assert result is not None
        assert result["id"] == "existing-1"

    @patch("mothertree.graphql_client.graphql")
    def test_no_match_short_name_different_company(self, mock_gql):
        mock_gql.return_value = {
            "allContactsList": [
                {"id": "existing-1", "name": "Jan de Vries", "companyByCompanyId": {"id": "company-1"}},
            ]
        }
        from mothertree.graphql_client import search_contacts_fuzzy
        result = search_contacts_fuzzy("Jan", company_id="company-2")
        assert result is None

    @patch("mothertree.graphql_client.graphql")
    def test_no_match_short_name_substring(self, mock_gql):
        """Short names (< 4 chars) require exact match to avoid 'Jan' matching 'Janet'."""
        mock_gql.return_value = {
            "allContactsList": [
                {"id": "existing-1", "name": "Janet Smith", "companyByCompanyId": {"id": "company-1"}},
            ]
        }
        from mothertree.graphql_client import search_contacts_fuzzy
        result = search_contacts_fuzzy("Jan", company_id="company-1")
        assert result is None

    @patch("mothertree.graphql_client.graphql")
    def test_exact_match_always_works(self, mock_gql):
        mock_gql.return_value = {
            "allContactsList": [
                {"id": "existing-1", "name": "Jurg van Vliet", "companyByCompanyId": {"id": "company-1"}},
            ]
        }
        from mothertree.graphql_client import search_contacts_fuzzy
        result = search_contacts_fuzzy("Jurg van Vliet", company_id="company-1")
        assert result is not None

    @patch("mothertree.graphql_client.graphql")
    def test_no_contacts_returns_none(self, mock_gql):
        mock_gql.return_value = {"allContactsList": []}
        from mothertree.graphql_client import search_contacts_fuzzy
        result = search_contacts_fuzzy("Nobody", company_id="company-1")
        assert result is None


class TestGetExistingGraph:
    @patch("bot.characters.weaver.graphql")
    def test_includes_personas(self, mock_gql):
        mock_gql.return_value = {
            "allContactsList": [],
            "allCompaniesList": [],
            "allSignalsList": [],
            "allPersonasList": [
                {"id": "p1", "name": "Maria Santos", "role": "Enterprise Platform Director", "profile": "Runs platform across multi-country orgs."}
            ],
        }
        from bot.characters.weaver import get_existing_graph
        graph = get_existing_graph()
        assert "personas" in graph
        assert len(graph["personas"]) == 1
        assert graph["personas"][0]["name"] == "Maria Santos"

    @patch("bot.characters.weaver.graphql")
    def test_error_fallback_includes_personas_key(self, mock_gql):
        mock_gql.side_effect = Exception("GraphQL down")
        from bot.characters.weaver import get_existing_graph
        graph = get_existing_graph()
        assert "personas" in graph
        assert graph["personas"] == []


class TestFormatGraphSummary:
    def test_personas_section_in_output(self):
        from bot.characters.weaver import _format_graph_summary
        graph = {
            "contacts": [],
            "companies": [],
            "signals": [],
            "personas": [
                {"name": "Maria Santos", "role": "Enterprise Platform Director", "profile": "Runs platform across multi-country orgs."},
                {"name": "Joost van der Berg", "role": "Technical Evaluator", "profile": "Founding Engineer/Tech Lead."},
            ],
        }
        result = _format_graph_summary(graph)
        assert "Known personas" in result
        assert "NOT real contacts" in result
        assert "Maria Santos" in result
        assert "Joost van der Berg" in result

    def test_includes_profile_snippet(self):
        from bot.characters.weaver import _format_graph_summary
        graph = {
            "contacts": [], "companies": [], "signals": [],
            "personas": [
                {"name": "Maria Santos", "role": "Director", "profile": "Runs platform across multi-country orgs."},
            ],
        }
        result = _format_graph_summary(graph)
        assert "Runs platform" in result

    def test_no_personas_section_when_empty(self):
        from bot.characters.weaver import _format_graph_summary
        graph = {"contacts": [], "companies": [], "signals": [], "personas": []}
        result = _format_graph_summary(graph)
        assert "persona" not in result.lower()


class TestTeamContext:
    @patch("bot.characters.weaver.graphql")
    def test_uses_organization_name_config(self, mock_gql):
        mock_gql.side_effect = [
            {"allUsersList": []},
            {"allOrganizationsList": []},
        ]
        with patch("bot.characters.weaver.ORGANIZATION_NAME", "Aknostic"):
            from bot.characters.weaver import _get_team_context
            result = _get_team_context()
            assert "Aknostic" in result

    @patch("bot.characters.weaver.graphql")
    def test_fallback_when_no_org_name(self, mock_gql):
        mock_gql.side_effect = [
            {"allUsersList": []},
            {"allOrganizationsList": []},
        ]
        with patch("bot.characters.weaver.ORGANIZATION_NAME", ""):
            from bot.characters.weaver import _get_team_context
            result = _get_team_context()
            assert "our organization" in result
