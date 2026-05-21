# jobs/tests/test_intelligence.py
from unittest.mock import patch

import pytest


@patch("mothertree.intelligence.get_organization_profile")
@patch("mothertree.intelligence.graphql")
class TestGatherContext:
    def test_returns_all_ci_tables(self, mock_gql, mock_get_org):
        mock_gql.return_value = {
            "allChangesList": [{"id": "c1", "statement": "change1"}],
            "allWorldviewsList": [{"id": "w1", "belief": "belief1"}],
            "allPersonasList": [{"id": "p1", "name": "persona1"}],
            "allCompetitorsList": [{"id": "co1", "type": "comp1"}],
            "allContactsList": [{"id": "ct1", "name": "contact1"}],
            "allSignalsList": [{"id": "s1", "content": "signal1"}],
            "allProofPointsList": [{"id": "pp1", "outcome": "proof1"}],
            "allInsightsList": [{"id": "i1", "category": "cat", "reframe": "think again"}],
        }
        mock_get_org.return_value = [
            {"id": "o1", "element_type": "identity", "content": "org1"}
        ]

        from mothertree.intelligence import gather_context
        result = gather_context()

        assert result["changes"] == [{"id": "c1", "statement": "change1"}]
        assert result["worldviews"] == [{"id": "w1", "belief": "belief1"}]
        assert result["personas"] == [{"id": "p1", "name": "persona1"}]
        assert result["competitors"] == [{"id": "co1", "type": "comp1"}]
        assert result["contacts"] == [{"id": "ct1", "name": "contact1"}]
        assert result["signals"] == [{"id": "s1", "content": "signal1"}]
        assert result["proof_points"] == [{"id": "pp1", "outcome": "proof1"}]
        assert result["insights"] == [
            {"id": "i1", "category": "cat", "reframe": "think again"}
        ]
        assert result["organization"] == [
            {"id": "o1", "element_type": "identity", "content": "org1"}
        ]
        assert result["semantic_results"] is None

    def test_with_query_includes_semantic_results(self, mock_gql, mock_get_org):
        mock_gql.return_value = {
            "allChangesList": [], "allWorldviewsList": [],
            "allPersonasList": [], "allCompetitorsList": [],
            "allContactsList": [], "allSignalsList": [],
            "allProofPointsList": [], "allInsightsList": [],
        }
        mock_get_org.return_value = []

        with patch("mothertree.intelligence.search_similar") as mock_search:
            mock_search.return_value = [{"id": "r1", "content": "match"}]
            from mothertree.intelligence import gather_context
            result = gather_context(query="sovereignty")
            assert result["semantic_results"] is not None
            assert result["organization"] == []
            assert mock_search.called


class TestFormatContextForPrompt:
    """format_context_for_prompt turns a gather_context() dict into prompt text."""

    def _base_ctx(self, **overrides):
        base = {
            "changes": [{"statement": "The world is changing"}],
            "worldviews": [{"belief": "Speed matters"}],
            "personas": [{"name": "Alice", "role": "CTO"}],
            "competitors": [{"type": "legacy", "positioning": "old guard"}],
            "contacts": [
                {"name": "Dolf van Delft", "role": "Junior Software Engineer"},
                {"name": "Flavia Paganelli", "role": None},
            ],
            "signals": [
                {"content": "met jim blom from parai today", "source": "slack:Jurg"},
            ],
            "proof_points": [],
            "insights": [
                {"category": "positioning", "reframe": "Think different"},
            ],
            "organization": [],
            "semantic_results": None,
        }
        base.update(overrides)
        return base

    def test_section_headers_present(self):
        from mothertree.intelligence import format_context_for_prompt
        result = format_context_for_prompt(self._base_ctx())
        assert "Change:" in result
        assert "Worldview:" in result
        assert "Personas:" in result
        assert "Competitors:" in result
        assert "Known Contacts:" in result
        assert "Recent Signals:" in result
        assert "Insights:" in result

    def test_contact_and_signal_rendering(self):
        from mothertree.intelligence import format_context_for_prompt
        result = format_context_for_prompt(self._base_ctx())
        assert "- Dolf van Delft (Junior Software Engineer)" in result
        assert "- Flavia Paganelli (unknown role)" in result
        assert "- [slack:Jurg] met jim blom from parai today" in result

    def test_relevant_label_appears_with_semantic_results(self):
        from mothertree.intelligence import format_context_for_prompt
        ctx = self._base_ctx(
            semantic_results=[
                {
                    "table": "change",
                    "label": "Change",
                    "results": [
                        {"statement": "From dependent to independent", "similarity": "0.72"}
                    ],
                },
                {
                    "table": "insights",
                    "label": "Insights",
                    "results": [
                        {"category": "lock-in", "reframe": "Break free", "similarity": "0.85"}
                    ],
                },
            ],
        )
        result = format_context_for_prompt(ctx)
        assert "Change (relevant):" in result
        assert "From dependent to independent" in result
        assert "Insights (relevant):" in result
        assert "Break free" in result
        # When semantic results present, top-N Insights fallback is skipped
        assert "Insights:\n- [positioning]" not in result

    def test_no_relevant_label_when_no_query(self):
        from mothertree.intelligence import format_context_for_prompt
        result = format_context_for_prompt(self._base_ctx())
        assert "(relevant)" not in result

    def test_organization_profile_rendered_at_top(self):
        from mothertree.intelligence import format_context_for_prompt
        ctx = self._base_ctx(
            organization=[
                {"element_type": "identity", "content": "European consultancy"},
                {"element_type": "change", "content": "Freedom to operate"},
            ],
        )
        result = format_context_for_prompt(ctx)
        assert result.startswith("ORGANIZATION PROFILE:")
        assert "- Identity: European consultancy" in result
        assert "- Change: Freedom to operate" in result


@patch("mothertree.intelligence.graphql")
class TestGatherPipeline:
    def test_global_returns_all_opportunities(self, mock_gql):
        mock_gql.return_value = {
            "allOpportunitiesList": [{"id": "o1", "stage": "signal", "title": "Deal A"}],
            "allSignalsList": [], "allInteractionsList": [],
            "allContactsList": [], "allUsersList": [],
        }
        from mothertree.intelligence import gather_pipeline
        result = gather_pipeline()
        assert len(result["opportunities"]) == 1
        assert result["scope"] == "global"

    def test_scoped_filters_by_user(self, mock_gql):
        mock_gql.return_value = {
            "allOpportunitiesList": [
                {"id": "o1", "ownerUserId": "u1", "stage": "signal"},
                {"id": "o2", "ownerUserId": "u2", "stage": "reframe"},
            ],
            "allSignalsList": [], "allInteractionsList": [],
            "allContactsList": [], "allUsersList": [],
        }
        from mothertree.intelligence import gather_pipeline
        result = gather_pipeline(user_id="u1")
        assert all(o["ownerUserId"] == "u1" for o in result["opportunities"])

    def test_counts_only_returns_counts(self, mock_gql):
        mock_gql.return_value = {
            "allOpportunities": {"totalCount": 5},
            "recentSignals": {"totalCount": 12},
            "recentInteractions": {"totalCount": 8},
            "warmHotContacts": {"totalCount": 3},
            "allUsersList": [],
        }
        from mothertree.intelligence import gather_pipeline
        result = gather_pipeline(counts_only=True)
        # signals/interactions should be int counts, not lists
        assert isinstance(result["signals"], int) or "count" in str(type(result["signals"]))
        assert result["signals"] == 12
        assert result["interactions"] == 8
        assert result["contacts"] == 3

    def test_scope_defaults_to_global_without_user_id(self, mock_gql):
        mock_gql.return_value = {
            "allOpportunitiesList": [], "allSignalsList": [], "allInteractionsList": [],
            "allContactsList": [], "allUsersList": [],
        }
        from mothertree.intelligence import gather_pipeline
        result = gather_pipeline()
        assert result["scope"] == "global"
        assert result["target_name"] is None

    def test_scope_respected_when_passed_explicitly(self, mock_gql):
        mock_gql.return_value = {
            "allOpportunitiesList": [], "allSignalsList": [], "allInteractionsList": [],
            "allContactsList": [], "allUsersList": [],
        }
        from mothertree.intelligence import gather_pipeline
        result = gather_pipeline(
            user_id="u1", scope="other", target_name="Pim"
        )
        assert result["scope"] == "other"
        assert result["target_name"] == "Pim"


@patch("mothertree.intelligence.generate")
class TestSynthesizePipeline:
    def _empty_data(self, scope="global", target_name=None):
        return {
            "opportunities": [],
            "signals": [],
            "interactions": [],
            "contacts": [],
            "training": [],
            "scope": scope,
            "target_name": target_name,
        }

    def test_global_uses_monday_review_style(self, mock_gen):
        mock_gen.return_value = "Pipeline review text"
        from mothertree.intelligence import synthesize_pipeline
        result = synthesize_pipeline(self._empty_data("global"), scope="global")
        assert result == "Pipeline review text"
        system_prompt = mock_gen.call_args[0][0]
        assert "Monday" in system_prompt or "briefing" in system_prompt.lower()

    def test_personal_uses_coaching_tone(self, mock_gen):
        mock_gen.return_value = "Your pipeline"
        from mothertree.intelligence import synthesize_pipeline
        result = synthesize_pipeline(
            self._empty_data("personal", "Jurg"), scope="personal"
        )
        assert result == "Your pipeline"
        system_prompt = mock_gen.call_args[0][0]
        assert "your" in system_prompt.lower() or "coaching" in system_prompt.lower()

    def test_other_uses_third_person(self, mock_gen):
        mock_gen.return_value = "Pim's pipeline"
        from mothertree.intelligence import synthesize_pipeline
        data = self._empty_data("other", "Pim")
        synthesize_pipeline(data, scope="other")
        system_prompt = mock_gen.call_args[0][0]
        # Target name should appear in the third-person prompt
        assert "Pim" in system_prompt

    def test_counts_only_data_shape(self, mock_gen):
        """Handle int counts gracefully in data body rendering."""
        mock_gen.return_value = "Retro"
        from mothertree.intelligence import synthesize_pipeline
        data = {
            "opportunities": [],
            "signals": 12,
            "interactions": 8,
            "contacts": 3,
            "training": [],
            "scope": "global",
            "target_name": None,
        }
        # Should not raise — formatter must accept int counts
        result = synthesize_pipeline(data, scope="global")
        assert result == "Retro"


@patch("mothertree.intelligence.search_similar")
@patch("mothertree.intelligence.graphql")
class TestGatherBrief:
    def test_returns_all_table_results(self, mock_gql, mock_search):
        mock_gql.return_value = {
            "allContactsList": [],
            "allCompaniesList": [],
            "allSignalsList": [],
            "allInteractionsList": [],
        }
        mock_search.return_value = [{"id": "1", "content": "match"}]

        from mothertree.intelligence import gather_brief
        result = gather_brief("KPN")
        assert "contacts" in result
        assert "insights" in result
        assert "proof_points" in result
        assert result["query"] == "KPN"

    def test_text_search_uses_parameterized_query(self, mock_gql, mock_search):
        mock_gql.return_value = {
            "allContactsList": [{"name": "Jane", "role": "CTO"}],
            "allCompaniesList": [{"name": "KPN", "industry": "Telecom"}],
            "allSignalsList": [{"content": "KPN looking at private cloud"}],
            "allInteractionsList": [{"summary": "KPN call", "date": "2026-04-01"}],
        }
        mock_search.return_value = []

        from mothertree.intelligence import gather_brief
        result = gather_brief("KPN")

        # Ensure parameterized variable was used
        args, kwargs = mock_gql.call_args
        assert args[1] == {"q": "KPN"} or kwargs.get("variables") == {"q": "KPN"}
        assert "$q" in args[0]

        assert result["contacts"] == [{"name": "Jane", "role": "CTO"}]
        assert result["companies"] == [{"name": "KPN", "industry": "Telecom"}]
        assert result["signals"] == [{"content": "KPN looking at private cloud"}]
        assert result["interactions"] == [{"summary": "KPN call", "date": "2026-04-01"}]

    def test_semantic_search_covers_all_tables_including_proof_points(
        self, mock_gql, mock_search
    ):
        mock_gql.return_value = {
            "allContactsList": [], "allCompaniesList": [],
            "allSignalsList": [], "allInteractionsList": [],
        }
        # Return a unique result per table so we can check each key separately
        mock_search.side_effect = lambda table, *a, **k: [{"table": table}]

        from mothertree.intelligence import gather_brief
        result = gather_brief("KPN")

        # Each semantic table should have been searched
        searched_tables = {c.args[0] for c in mock_search.call_args_list}
        assert "change" in searched_tables
        assert "worldview" in searched_tables
        assert "competitors" in searched_tables
        assert "insights" in searched_tables
        assert "proof_points" in searched_tables

        assert result["changes"] == [{"table": "change"}]
        assert result["worldviews"] == [{"table": "worldview"}]
        assert result["competitors"] == [{"table": "competitors"}]
        assert result["insights"] == [{"table": "insights"}]
        assert result["proof_points"] == [{"table": "proof_points"}]

    def test_text_search_failure_does_not_crash(self, mock_gql, mock_search):
        mock_gql.side_effect = Exception("GraphQL boom")
        mock_search.return_value = []

        from mothertree.intelligence import gather_brief
        result = gather_brief("KPN")
        # Should still return a dict with empty lists for text tables
        assert result["contacts"] == []
        assert result["companies"] == []
        assert result["signals"] == []
        assert result["interactions"] == []


@patch("mothertree.intelligence.generate")
class TestSynthesizeBrief:
    def test_synthesizes_briefing_from_data(self, mock_gen):
        mock_gen.return_value = "KPN briefing text"
        from mothertree.intelligence import synthesize_brief
        data = {
            "query": "KPN",
            "contacts": [{"name": "Jane", "role": "CTO"}],
            "companies": [], "signals": [], "interactions": [],
            "changes": [], "worldviews": [], "competitors": [],
            "insights": [], "proof_points": [],
        }
        result = synthesize_brief(data, "KPN")
        assert result == "KPN briefing text"
        system_prompt = mock_gen.call_args[0][0]
        assert "briefing" in system_prompt.lower() or "KPN" in mock_gen.call_args[0][1]

    def test_empty_data_returns_no_information(self, mock_gen):
        """When nothing was found, return an empty-brief message without calling LLM."""
        from mothertree.intelligence import synthesize_brief
        data = {
            "query": "Obscure",
            "contacts": [], "companies": [], "signals": [],
            "interactions": [], "changes": [], "worldviews": [], "competitors": [],
            "insights": [], "proof_points": [],
        }
        result = synthesize_brief(data, "Obscure")
        assert "Obscure" in result or "No" in result or "no" in result
        assert not mock_gen.called

    def test_streaming_uses_chat_conversation(self, mock_gen):
        from mothertree.intelligence import synthesize_brief
        data = {
            "query": "KPN",
            "contacts": [{"name": "Jane", "role": "CTO"}],
            "companies": [], "signals": [], "interactions": [],
            "changes": [], "worldviews": [], "competitors": [],
            "insights": [], "proof_points": [],
        }
        chunks = []

        def _on_chunk(c):
            chunks.append(c)

        with patch("mothertree.llm.chat_conversation") as mock_chat:
            mock_chat.return_value = "Streamed brief"
            result = synthesize_brief(data, "KPN", on_chunk=_on_chunk)
            assert result == "Streamed brief"
            assert mock_chat.called
            # generate should NOT have been called when streaming
            assert not mock_gen.called


@patch("mothertree.intelligence.search_similar")
@patch("mothertree.intelligence.graphql")
class TestGatherMeetingContext:
    def test_returns_matched_attendees_and_semantic_results(self, mock_gql, mock_search):
        # Per-attendee contact lookup query -> returns one contact match per attendee
        mock_gql.return_value = {
            "allContactsList": [{"id": "c1", "name": "Jane", "role": "CTO",
                                 "companyByCompanyId": {"name": "KPN"}}]
        }
        mock_search.return_value = [{"id": "i1", "reframe": "relevant", "similarity": "0.9"}]

        from mothertree.intelligence import gather_meeting_context
        event = {"title": "Q3 review", "attendees": ["Jane"], "date": "2026-05-01"}
        result = gather_meeting_context(event)

        assert "event" in result
        assert "attendee_contacts" in result
        assert "insights" in result
        assert "changes" in result
        assert "proof_points" in result
        assert len(result["attendee_contacts"]) == 1


@patch("mothertree.intelligence.graphql")
class TestGatherTrainingState:
    def test_returns_user_and_progress(self, mock_gql):
        mock_gql.return_value = {
            "userById": {"id": "u1", "name": "Jurg", "role": "hunter",
                         "currentStage": 1, "currentChapter": 2, "streak": 5},
            "allTrainingProgressesList": [{"area": "worldview", "score": 0.8}],
        }
        from mothertree.intelligence import gather_training_state
        result = gather_training_state("u1")
        assert result["user"]["name"] == "Jurg"
        assert result["current_stage"] == 1
        assert result["current_chapter"] == 2
        assert result["streak"] == 5
        assert "curriculum_position" in result


@patch("mothertree.intelligence.graphql")
class TestGatherAccount:
    def test_by_company_id(self, mock_gql):
        mock_gql.return_value = {
            "companyById": {"id": "co1", "name": "KPN", "industry": "Telecom"},
            "allContactsList": [{"id": "ct1", "name": "Jane"}],
            "allOpportunitiesList": [{"id": "o1", "stage": "signal"}],
            "allInteractionsList": [{"id": "i1", "type": "call"}],
            "allSignalsList": [{"id": "s1", "content": "RFQ leaked"}],
            "allAccountPlansList": [{"id": "ap1", "qbrNotes": "..."}],
        }
        from mothertree.intelligence import gather_account
        result = gather_account(company_id="co1")
        assert result["company"]["name"] == "KPN"
        assert len(result["contacts"]) == 1
        assert len(result["opportunities"]) == 1
        assert isinstance(result["signals"], list)
        assert result["signals"][0]["content"] == "RFQ leaked"
        assert result["account_plan"] is not None

    def test_by_company_name(self, mock_gql):
        # First call: lookup by name. Second call: fetch account data.
        mock_gql.side_effect = [
            {"allCompaniesList": [{"id": "co1", "name": "KPN"}]},
            {"companyById": {"id": "co1", "name": "KPN"},
             "allContactsList": [], "allOpportunitiesList": [],
             "allInteractionsList": [], "allSignalsList": [],
             "allAccountPlansList": []},
        ]
        from mothertree.intelligence import gather_account
        result = gather_account(company_name="KPN")
        assert result["company"]["name"] == "KPN"
        assert result["signals"] == []


@patch("mothertree.intelligence.graphql")
class TestResolveUser:
    def test_resolves_by_exact_email(self, mock_gql):
        mock_gql.return_value = {
            "allUsersList": [{"id": "u1", "email": "jurg@aknostic.com", "name": "Jurg"}]
        }
        from mothertree.intelligence import resolve_user
        assert resolve_user("jurg@aknostic.com")["id"] == "u1"

    def test_resolves_by_partial_name(self, mock_gql):
        mock_gql.return_value = {
            "allUsersList": [{"id": "u1", "name": "Jurg van Vliet", "email": "jurg@aknostic.com"}]
        }
        from mothertree.intelligence import resolve_user
        result = resolve_user("jurg")
        assert result["name"] == "Jurg van Vliet"

    def test_returns_none_on_no_match(self, mock_gql):
        mock_gql.return_value = {"allUsersList": []}
        from mothertree.intelligence import resolve_user
        assert resolve_user("nonexistent") is None

    def test_raises_ambiguous_on_multiple(self, mock_gql):
        mock_gql.return_value = {
            "allUsersList": [
                {"id": "u1", "name": "Jurg van Vliet"},
                {"id": "u2", "name": "Jurg Jansen"},
            ]
        }
        from mothertree.intelligence import AmbiguousUserError, resolve_user
        with pytest.raises(AmbiguousUserError) as exc_info:
            resolve_user("jurg")
        assert len(exc_info.value.matches) == 2


@patch("mothertree.intelligence.generate")
class TestSynthesizeWeekly:
    def test_uses_monday_briefing_style(self, mock_gen):
        mock_gen.return_value = "Monday briefing text"
        from mothertree.intelligence import synthesize_weekly
        data = {"opportunities": [], "signals": [], "interactions": [],
                "contacts": [], "training": [], "scope": "global", "target_name": None}
        result = synthesize_weekly(data)
        assert result == "Monday briefing text"
        system = mock_gen.call_args[0][0]
        assert "Monday" in system or "briefing" in system.lower() or "priorities" in system.lower()

    def test_no_streaming_parameter(self, mock_gen):
        """synthesize_weekly is a cronjob function — no on_chunk."""
        import inspect

        from mothertree.intelligence import synthesize_weekly
        sig = inspect.signature(synthesize_weekly)
        assert "on_chunk" not in sig.parameters


@patch("mothertree.intelligence.generate")
class TestSynthesizeMonthly:
    def test_uses_retrospective_style(self, mock_gen):
        mock_gen.return_value = "Monthly retrospective"
        from mothertree.intelligence import synthesize_monthly
        data = {
            "opportunities": [],
            "signals": 12, "interactions": 8, "contacts": 3,
            "training": [], "scope": "global", "target_name": None,
            "total_opportunities": 5,
        }
        result = synthesize_monthly(data)
        assert result == "Monthly retrospective"
        system = mock_gen.call_args[0][0]
        assert "retrospective" in system.lower() or "monthly" in system.lower()

    def test_handles_counts_only_shape(self, mock_gen):
        """synthesize_monthly must accept counts_only=True output from gather_pipeline."""
        mock_gen.return_value = "done"
        from mothertree.intelligence import synthesize_monthly
        data = {
            "opportunities": [],
            "signals": 42, "interactions": 15, "contacts": 7,
            "training": [], "scope": "global", "target_name": None,
            "total_opportunities": 20,
        }
        synthesize_monthly(data)
        user_prompt = mock_gen.call_args[0][1]
        # The data body should mention the counts somewhere
        assert "42" in user_prompt
        assert "15" in user_prompt
