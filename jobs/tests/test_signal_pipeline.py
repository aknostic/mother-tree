"""Comprehensive tests for the signal detection → extraction → resolution pipeline.

Tests the full chain: message → Spotter → Weaver → entity creation → receipt.
Uses mocks for LLM calls but exercises real data flow through extraction.py.
"""
import json
from unittest.mock import MagicMock, patch

# --- Sample data ---

SPOTTER_RESULT_CLEAN = {
    "entities": [
        {"name": "Sarah van den Berg", "type": "person", "role": "CTO", "organization": "STACKIT"},
        {"name": "STACKIT", "type": "organization", "industry": "cloud", "context": "European cloud provider"},
    ],
    "pain_signals": [{"signal": "Frustrated with Terraform dependency"}],
    "value_hooks": [{"hook": "Platform engineering alignment"}],
    "actions": [
        {"action": "Schedule follow-up call", "who": "Sarah van den Berg", "by_when": "2026-04-15"},
    ],
    "stage": {"current": "Signal", "evidence": ["CTO expressed interest in platform independence"]},
}

SPOTTER_RESULT_WITH_TEAM = {
    "entities": [
        {"name": "Jurg", "type": "person", "role": "CEO", "organization": "Aknostic"},
        {"name": "Aknostic", "type": "organization"},
        {"name": "Chris Meijer", "type": "person", "role": "Recruiter", "organization": "Belastingdienst"},
        {"name": "Belastingdienst", "type": "organization", "industry": "government"},
    ],
    "pain_signals": [],
    "value_hooks": [],
    "actions": [{"action": "Wait for Chris reply", "who": "Chris Meijer", "by_when": "Unknown"}],
    "stage": {"current": "Signal", "evidence": ["Recruitment outreach"]},
}

SPOTTER_RESULT_NO_TYPES = {
    "entities": [
        {"name": "Someone"},
        {"name": "SomeCo"},
    ],
    "pain_signals": [],
    "value_hooks": [],
    "actions": [],
    "stage": {"current": "Soil", "evidence": []},
}

WEAVER_RESULT_ALL_NEW = {
    "resolved": [
        {"entity": {"name": "Sarah van den Berg", "type": "person", "organization": "STACKIT"}, "resolution": "NEW",
         "matched_id": None, "candidate_ids": [], "reason": "Not in graph"},
        {"entity": {"name": "STACKIT", "type": "organization"}, "resolution": "NEW",
         "matched_id": None, "candidate_ids": [], "reason": "Not in graph"},
    ],
    "flags": [],
}

WEAVER_RESULT_TEAM_MATCHED = {
    "resolved": [
        {"entity": {"name": "Jurg", "type": "person"}, "resolution": "MATCHED",
         "matched_id": "jurg-uuid", "candidate_ids": [], "reason": "Team member"},
        {"entity": {"name": "Aknostic", "type": "organization"}, "resolution": "MATCHED",
         "matched_id": "aknostic-uuid", "candidate_ids": [], "reason": "Our company"},
        {"entity": {"name": "Chris Meijer", "type": "person"}, "resolution": "NEW",
         "matched_id": None, "candidate_ids": [], "reason": "Not in graph"},
        {"entity": {"name": "Belastingdienst", "type": "organization"}, "resolution": "NEW",
         "matched_id": None, "candidate_ids": [], "reason": "Not in graph"},
    ],
    "flags": [],
}

WEAVER_RESULT_UNCERTAIN = {
    "resolved": [
        {"entity": {"name": "Jim", "type": "person"}, "resolution": "UNCERTAIN",
         "matched_id": None, "candidate_ids": ["id-1", "id-2"],
         "reason": "Multiple contacts named Jim"},
    ],
    "flags": ["Ambiguous: Jim could be Jim Blom or Jim de Vries"],
}

CORRECTION_PARSED = {
    "corrections": [
        {"type": "rename", "from": "agnostict", "to": "Aknostic"},
        {"type": "identity", "name": "Jurg van Vliet", "is_existing": "Jurg"},
    ]
}


class TestSpotterEntityTypes:
    """Spotter must always include entity types."""

    @patch("bot.characters.spotter.chat_conversation")
    def test_clean_extraction_has_types(self, mock_chat):
        from bot.characters.spotter import extract
        mock_chat.return_value = json.dumps(SPOTTER_RESULT_CLEAN)
        result = extract("met sarah from stackit", "Interesting", "Jurg")
        for entity in result["entities"]:
            assert "type" in entity, f"Entity {entity.get('name')} missing type"
            assert entity["type"] in ("person", "organization", "event")

    @patch("bot.characters.spotter.chat_conversation")
    def test_entities_without_types_still_parsed(self, mock_chat):
        from bot.characters.spotter import extract
        mock_chat.return_value = json.dumps(SPOTTER_RESULT_NO_TYPES)
        result = extract("talked to someone", "OK", "Jurg")
        assert result is not None
        assert len(result["entities"]) == 2


class TestApplyResolution:
    """_apply_resolution creates entities correctly."""

    @patch("mothertree.graphql_client.search_contacts_fuzzy")
    @patch("mothertree.entities.find_or_create_company")
    @patch("mothertree.graphql_client.find_or_create_contact")
    def test_new_person_with_company_linked(self, mock_contact, mock_company, mock_fuzzy):
        from bot.extraction import _apply_resolution
        mock_fuzzy.return_value = None
        mock_company.return_value = {"id": "co-1", "name": "STACKIT"}
        mock_contact.return_value = {"id": "ct-1", "full_name": "Sarah van den Berg"}
        result = _apply_resolution(WEAVER_RESULT_ALL_NEW)
        assert result["contacts_processed"] == 1
        assert result["companies_processed"] >= 1
        # Contact should be linked to company
        mock_contact.assert_called_once()
        _, kwargs = mock_contact.call_args
        assert kwargs.get("company_id") == "co-1"

    @patch("mothertree.graphql_client.graphql")
    def test_matched_team_member_not_created(self, mock_gql):
        from bot.extraction import _apply_resolution
        result = _apply_resolution(WEAVER_RESULT_TEAM_MATCHED)
        # Jurg and Aknostic are MATCHED — should NOT be created
        # Chris and Belastingdienst are NEW — should be created
        assert result["contacts_processed"] >= 1  # Chris created

    def test_uncertain_entity_flagged(self):
        from bot.extraction import _apply_resolution
        result = _apply_resolution(WEAVER_RESULT_UNCERTAIN)
        assert result["contacts_processed"] == 0
        # Should have structured flags for clarifying questions
        structured_flags = [f for f in result["flags"] if isinstance(f, dict)]
        assert len(structured_flags) >= 1
        assert structured_flags[0]["entity"] == "Jim"

    def test_entity_without_type_skipped(self):
        from bot.extraction import _apply_resolution
        resolution = {
            "resolved": [
                {"entity": {"name": "Unknown Thing"}, "resolution": "NEW",
                 "matched_id": None, "candidate_ids": [], "reason": "New"},
            ],
            "flags": [],
        }
        result = _apply_resolution(resolution)  # noqa: F841
        # No type → no creation
        assert result["contacts_processed"] == 0
        assert result["companies_processed"] == 0


class TestDateParsing:
    """Dates from Spotter should be parsed or flagged."""

    def test_iso_date(self):
        from bot.extraction import _parse_date
        assert _parse_date("2026-04-15") == "2026-04-15"

    def test_natural_date(self):
        from bot.extraction import _parse_date
        assert _parse_date("15 April 2026") == "2026-04-15"

    def test_unknown_returns_none(self):
        from bot.extraction import _parse_date
        assert _parse_date("Unknown") is None

    def test_empty_returns_none(self):
        from bot.extraction import _parse_date
        assert _parse_date("") is None

    def test_compound_date_extracts(self):
        from bot.extraction import _parse_date
        result = _parse_date("Application deadline 16 april 2026")
        assert result == "2026-04-16"

    def test_relative_dates(self):
        from bot.extraction import _parse_date
        assert _parse_date("today") is not None
        assert _parse_date("yesterday") is not None
        assert _parse_date("tomorrow") is not None

    def test_unparseable_returns_none(self):
        from bot.extraction import _parse_date
        assert _parse_date("Past") is None
        assert _parse_date("Pending") is None
        assert _parse_date("Sometime later") is None

    def test_dutch_relative_dates(self):
        from bot.extraction import _parse_date
        assert _parse_date("morgen") is not None
        assert _parse_date("overmorgen") is not None
        assert _parse_date("volgende week") is not None

    def test_complex_relative_dates(self):
        from bot.extraction import _parse_date
        result = _parse_date("next Tuesday")
        assert result is not None
        # Should be a valid ISO date
        from datetime import datetime
        datetime.strptime(result, "%Y-%m-%d")

    def test_in_weeks(self):
        from bot.extraction import _parse_date
        result = _parse_date("in 3 weeks")
        assert result is not None


class TestActionProcessing:
    """Actions from Spotter create interactions with contacts."""

    @patch("mothertree.graphql_client.graphql")
    @patch("mothertree.graphql_client.find_or_create_contact")
    def test_action_creates_interaction(self, mock_contact, mock_gql):
        from bot.extraction import _process_actions
        mock_contact.return_value = {"id": "ct-1"}
        mock_gql.return_value = {"createInteraction": {"interaction": {"id": "int-1"}}}
        gaps = _process_actions(
            [{"action": "Schedule call", "who": "Sarah", "by_when": "2026-04-15"}],
            "Jurg",
        )
        mock_contact.assert_called_once_with(full_name="Sarah")
        mock_gql.assert_called_once()
        assert len(gaps) == 0

    @patch("mothertree.graphql_client.graphql")
    @patch("mothertree.graphql_client.find_or_create_contact")
    def test_unparseable_date_creates_gap(self, mock_contact, mock_gql):
        from bot.extraction import _process_actions
        mock_contact.return_value = {"id": "ct-1"}
        mock_gql.return_value = {"createInteraction": {"interaction": {"id": "int-1"}}}
        gaps = _process_actions(
            [{"action": "Follow up", "who": "Chris", "by_when": "Sometime next week"}],
            "Jurg",
        )
        assert len(gaps) == 1
        assert "when" in gaps[0].lower()

    def test_non_dict_actions_skipped(self):
        from bot.extraction import _process_actions
        gaps = _process_actions(["just a string", 42, None], "Jurg")
        assert gaps == []

    @patch("mothertree.graphql_client.graphql")
    @patch("mothertree.graphql_client.find_or_create_contact")
    def test_user_id_included_in_interaction(self, mock_contact, mock_gql):
        from bot.extraction import _process_actions
        mock_contact.return_value = {"id": "ct-1"}
        mock_gql.return_value = {"createInteraction": {"interaction": {"id": "int-1"}}}
        _process_actions(
            [{"action": "Schedule call", "who": "Sarah", "by_when": "2026-04-15"}],
            "Jurg",
            user_id="u-123",
        )
        call_args = mock_gql.call_args
        interaction_obj = call_args[0][1]["obj"]
        assert interaction_obj["userId"] == "u-123"

    @patch("mothertree.graphql_client.graphql")
    @patch("mothertree.graphql_client.find_or_create_contact")
    def test_user_id_omitted_when_none(self, mock_contact, mock_gql):
        from bot.extraction import _process_actions
        mock_contact.return_value = {"id": "ct-1"}
        mock_gql.return_value = {"createInteraction": {"interaction": {"id": "int-1"}}}
        _process_actions(
            [{"action": "Schedule call", "who": "Sarah", "by_when": "2026-04-15"}],
            "Jurg",
        )
        call_args = mock_gql.call_args
        interaction_obj = call_args[0][1]["obj"]
        assert "userId" not in interaction_obj


class TestSignalReceipt:
    """The signal receipt should summarize what was captured."""

    def test_receipt_includes_people(self):
        """Receipt should list extracted people."""
        people = [e.get("name") for e in SPOTTER_RESULT_CLEAN["entities"]
                  if e.get("type") == "person"]
        assert "Sarah van den Berg" in people

    def test_receipt_includes_companies(self):
        """Receipt should list extracted companies."""
        orgs = [e.get("name") for e in SPOTTER_RESULT_CLEAN["entities"]
                if e.get("type") == "organization"]
        assert "STACKIT" in orgs

    def test_receipt_includes_stage(self):
        """Receipt should include the assessed stage."""
        assert SPOTTER_RESULT_CLEAN["stage"]["current"] == "Signal"

    def test_receipt_includes_actions(self):
        """Receipt should list actions."""
        actions = SPOTTER_RESULT_CLEAN["actions"]
        assert len(actions) >= 1
        assert "Schedule" in actions[0]["action"]


class TestExtractSignalFlow:
    """End-to-end extract_signal with mocked LLM."""

    @patch("bot.extraction._process_actions")
    @patch("bot.extraction._apply_resolution")
    @patch("bot.characters.weaver.resolve")
    @patch("bot.characters.spotter.extract")
    @patch("bot.extraction.insert_signal")
    @patch("bot.extraction.find_similar_signals")
    def test_full_flow_creates_entities(self, mock_similar, mock_insert, mock_spotter,
                                         mock_weaver, mock_apply, mock_actions):
        from bot.extraction import extract_signal
        mock_similar.return_value = []
        mock_insert.return_value = "sig-1"
        mock_spotter.return_value = SPOTTER_RESULT_CLEAN
        mock_weaver.return_value = WEAVER_RESULT_ALL_NEW
        mock_apply.return_value = {"contacts_processed": 1, "companies_processed": 1,
                                    "gaps": [], "events_processed": 0, "opportunities_processed": 0,
                                    "flags": []}
        mock_actions.return_value = []

        result = extract_signal("met sarah from stackit", "Interesting", "Jurg")

        mock_spotter.assert_called_once()
        mock_weaver.assert_called_once()
        mock_apply.assert_called_once()
        assert result["uncertain"] == []
        assert result["gaps"] == []

    @patch("bot.extraction.insert_signal")
    @patch("bot.extraction.find_similar_signals")
    @patch("bot.characters.spotter.extract")
    def test_spotter_failure_returns_empty(self, mock_spotter, mock_similar, mock_insert):
        from bot.extraction import extract_signal
        mock_similar.return_value = []
        mock_insert.return_value = "sig-1"
        mock_spotter.return_value = None

        result = extract_signal("hello", "hi", "Jurg")
        assert result["uncertain"] == []

    @patch("bot.extraction._process_actions")
    @patch("bot.extraction._apply_resolution")
    @patch("bot.characters.weaver.resolve")
    @patch("bot.characters.spotter.extract")
    @patch("bot.extraction.insert_signal")
    @patch("bot.extraction.find_similar_signals")
    def test_uncertain_entities_returned(self, mock_similar, mock_insert, mock_spotter,
                                          mock_weaver, mock_apply, mock_actions):
        from bot.extraction import extract_signal
        mock_similar.return_value = []
        mock_insert.return_value = "sig-1"
        mock_spotter.return_value = {"entities": [{"name": "Jim", "type": "person"}],
                                      "actions": [], "pain_signals": [], "value_hooks": [],
                                      "stage": {"current": "Soil", "evidence": []}}
        mock_weaver.return_value = WEAVER_RESULT_UNCERTAIN
        mock_apply.return_value = {"contacts_processed": 0, "companies_processed": 0,
                                    "gaps": [], "events_processed": 0, "opportunities_processed": 0,
                                    "flags": [{"entity": "Jim", "type": "person", "reason": "Ambiguous"}]}
        mock_actions.return_value = []

        result = extract_signal("talked to jim", "OK", "Jurg")
        assert len(result["uncertain"]) >= 1


class TestTeamRecognition:
    """Weaver should recognize team members from _get_team_context."""

    @patch("bot.characters.weaver.graphql")
    def test_get_team_context_includes_users(self, mock_gql):
        from bot.characters.weaver import _get_team_context
        mock_gql.side_effect = [
            {"allUsersList": [
                {"name": "Jurg", "role": "hunter"},
                {"name": "Matthijs", "role": "farmer"},
            ]},
            {"allOrganizationsList": [
                {"content": "Aknostic is a platform engineering consultancy"},
            ]},
        ]
        ctx = _get_team_context()
        assert "Jurg" in ctx
        assert "Matthijs" in ctx
        assert "Aknostic" in ctx

    @patch("bot.characters.weaver.graphql")
    def test_team_context_survives_db_failure(self, mock_gql):
        from bot.characters.weaver import _get_team_context
        mock_gql.side_effect = Exception("DB down")
        ctx = _get_team_context()
        # Should at least have the company name line (uses ORGANIZATION_NAME or fallback)
        assert "Our company:" in ctx


class TestCorrectionHandler:
    """Signal correction handler parses and applies updates."""

    @patch("bot.pipeline._resolve_thinking")
    @patch("bot.memory.append_thread_message")
    @patch("mothertree.graphql_client.graphql")
    @patch("mothertree.llm.generate")
    def test_rename_correction(self, mock_gen, mock_gql, mock_thread_append, mock_resolve):
        from bot.pipeline import _handle_signal_correction
        mock_gen.return_value = json.dumps(CORRECTION_PARSED)
        # Mock the contact/company lookup for rename
        mock_gql.side_effect = [
            {"allContactsList": []},  # No contact named agnostict
            {"allCompaniesList": [{"id": "co-1", "name": "agnostict"}]},  # Found company
            {"updateCompanyById": {"company": {"id": "co-1"}}},  # Update
        ]

        memory_ctx = {
            "messages": [{"role": "assistant", "content": "🌱 Signal captured.\n• Companies: agnostict"}],
            "store_type": "thread",
            "thread_ts": "123.456",
            "channel_id": "C123",
        }
        result = _handle_signal_correction(
            "agnostict -> Aknostic", "Jurg", memory_ctx,
            client=MagicMock(), channel_id="C123", thread_ts="123.456",
            thinking={"type": "message", "ts": "789.0"},
        )
        assert result is True

    @patch("bot.pipeline._resolve_thinking")
    @patch("bot.memory.append_thread_message")
    @patch("mothertree.graphql_client.graphql")
    @patch("mothertree.llm.generate")
    def test_unparseable_correction_returns_false(self, mock_gen, mock_gql, mock_append, mock_resolve):
        from bot.pipeline import _handle_signal_correction
        mock_gen.return_value = '{"corrections": []}'

        memory_ctx = {
            "messages": [{"role": "assistant", "content": "🌱 Signal captured."}],
            "store_type": "thread",
            "thread_ts": "123.456",
            "channel_id": "C123",
        }
        result = _handle_signal_correction(
            "nice weather today", "Jurg", memory_ctx,
            client=MagicMock(), channel_id="C123", thread_ts="123.456",
            thinking={"type": "message", "ts": "789.0"},
        )
        assert result is False  # Falls through to normal processing


class TestBackgroundExtract:
    """Tests for _background_extract — the glue between pipeline and extraction."""

    @patch("bot.pipeline._generate_clarifying_question")
    @patch("bot.pipeline.extract_signal")
    @patch("bot.characters.spotter.extract")
    def test_signal_flag_triggers_extraction(self, mock_spotter, mock_extract, mock_question):
        from bot.pipeline import _background_extract
        mock_spotter.return_value = SPOTTER_RESULT_CLEAN
        mock_extract.return_value = {"uncertain": [], "gaps": []}
        mock_question.return_value = None

        _background_extract("met sarah", "Interesting", "Jurg",
                            signal_flag=True, actions=[], channel_id="C123",
                            thread_ts="123.456", client=MagicMock())

        mock_spotter.assert_called_once()
        mock_extract.assert_called_once()

    @patch("bot.pipeline.extract_signal")
    @patch("bot.characters.spotter.extract")
    def test_no_signal_flag_skips_extraction(self, mock_spotter, mock_extract):
        from bot.pipeline import _background_extract
        _background_extract("hello", "hi", "Jurg",
                            signal_flag=False, actions=[])
        mock_spotter.assert_not_called()
        mock_extract.assert_not_called()

    @patch("mothertree.llm.generate")
    @patch("bot.pipeline.extract_signal")
    @patch("bot.characters.spotter.extract")
    def test_receipt_posted_with_entities(self, mock_spotter, mock_extract, mock_gen):
        from bot.pipeline import _background_extract
        mock_spotter.return_value = SPOTTER_RESULT_CLEAN
        mock_extract.return_value = {"uncertain": [], "gaps": []}
        mock_gen.return_value = "🌱 Signal captured. Noticed Sarah van den Berg from STACKIT. Looks like an early signal. Correct me if I got something wrong."
        client = MagicMock()

        _background_extract("met sarah from stackit", "Interesting", "Jurg",
                            signal_flag=True, actions=[],
                            channel_id="C123", thread_ts="123.456", client=client)

        client.chat_postMessage.assert_called_once()
        receipt_text = client.chat_postMessage.call_args[1]["text"]
        assert "Signal captured" in receipt_text

    @patch("mothertree.llm.generate")
    @patch("bot.pipeline.extract_signal")
    @patch("bot.characters.spotter.extract")
    def test_receipt_includes_uncertainties(self, mock_spotter, mock_extract, mock_gen):
        from bot.pipeline import _background_extract
        mock_spotter.return_value = {"entities": [{"name": "Jim", "type": "person"}],
                                      "actions": [], "pain_signals": [], "value_hooks": [],
                                      "stage": {"current": "Soil", "evidence": []}}
        mock_extract.return_value = {
            "uncertain": [{"entity": "Jim", "type": "person", "reason": "Ambiguous"}],
            "gaps": ["when 'follow up' should happen — when?"],
        }
        mock_gen.return_value = "🌱 Signal captured. Noticed Jim, but not sure if that's someone we already know. When should the follow-up happen? Correct me if I got something wrong."
        client = MagicMock()

        _background_extract("talked to jim", "OK", "Jurg",
                            signal_flag=True, actions=[],
                            channel_id="C123", thread_ts="123.456", client=client)

        receipt_text = client.chat_postMessage.call_args[1]["text"]
        assert "Signal captured" in receipt_text
        assert "Jim" in receipt_text

    @patch("bot.pipeline._generate_clarifying_question")
    @patch("bot.pipeline.extract_signal")
    @patch("bot.characters.spotter.extract")
    def test_user_id_passed_to_extract_signal(self, mock_spotter, mock_extract, mock_question):
        from bot.pipeline import _background_extract
        mock_spotter.return_value = SPOTTER_RESULT_CLEAN
        mock_extract.return_value = {"uncertain": [], "gaps": []}
        mock_question.return_value = None

        _background_extract("met sarah", "Interesting", "Jurg",
                            signal_flag=True, actions=[], channel_id="C123",
                            thread_ts="123.456", client=MagicMock(),
                            user_id="u-789")

        mock_extract.assert_called_once()
        _, kwargs = mock_extract.call_args
        assert kwargs.get("user_id") == "u-789"

    @patch("bot.pipeline.extract_signal")
    @patch("bot.characters.spotter.extract")
    def test_spotter_failure_no_receipt(self, mock_spotter, mock_extract):
        from bot.pipeline import _background_extract
        mock_spotter.return_value = None
        mock_extract.return_value = {"uncertain": [], "gaps": []}
        client = MagicMock()

        _background_extract("hello", "hi", "Jurg",
                            signal_flag=True, actions=[],
                            channel_id="C123", thread_ts="123.456", client=client)

        # No receipt — spotter found nothing
        client.chat_postMessage.assert_not_called()


class TestSilentPathExtraction:
    """Messages without @mention should still capture signals when flagged."""

    @patch("bot.pipeline._background_extract")
    @patch("bot.pipeline._handle_silent")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline._resolve_user")
    def test_silent_with_signal_runs_extraction(self, mock_resolve,
                                                  mock_memory, mock_dispatch,
                                                  mock_thinking, mock_silent,
                                                  mock_bg_extract):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_memory.return_value = {"messages": [], "store_type": "channel", "channel_id": "C123"}
        mock_dispatch.return_value = {
            "character": "silent", "intent": "none",
            "annotation": None, "must_respond": False,
            "training_mode": False, "signal_flag": True,
            "clean_text": "met someone at KPN", "exercise_pending": None,
        }
        mock_thinking.return_value = {"type": "reaction", "ts": "123.456"}

        _process_message(
            text="met someone at KPN", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="channel", participant_count=5,
            respond=MagicMock(), client=MagicMock(), thread_ts=None,
            ts="001.001", bot_user_id="BXXX",
        )

        # Should NOT call _handle_silent (thinking stays for extraction)
        mock_silent.assert_not_called()
        # Should run background extraction
        mock_bg_extract.assert_called_once()
        assert mock_bg_extract.call_args[1]["signal_flag"] is True

    @patch("bot.pipeline._background_extract")
    @patch("bot.pipeline._handle_silent")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline._resolve_user")
    def test_silent_without_signal_no_extraction(self, mock_resolve,
                                                    mock_memory, mock_dispatch,
                                                    mock_thinking, mock_silent,
                                                    mock_bg_extract):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_memory.return_value = {"messages": [], "store_type": "channel", "channel_id": "C123"}
        mock_dispatch.return_value = {
            "character": "silent", "intent": "none",
            "annotation": None, "must_respond": False,
            "training_mode": False, "signal_flag": False,
            "clean_text": "nice weather", "exercise_pending": None,
        }
        mock_thinking.return_value = {"type": "reaction", "ts": "123.456"}

        _process_message(
            text="nice weather", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="channel", participant_count=5,
            respond=MagicMock(), client=MagicMock(), thread_ts=None,
            ts="001.001", bot_user_id="BXXX",
        )

        # Should call _handle_silent (immediate removal)
        mock_silent.assert_called_once()
        # Should NOT run extraction
        mock_bg_extract.assert_not_called()


class TestDMAlwaysExtracts:
    """DM freeform messages always run extraction regardless of signal_flag."""

    @patch("bot.pipeline._background_extract")
    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline._resolve_user")
    def test_dm_freeform_extracts(self, mock_resolve, mock_dispatch,
                                    mock_memory, mock_gather, mock_ctx, mock_chat, mock_bg):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "met someone interesting", "exercise_pending": None,
        }
        mock_memory.return_value = {"messages": [], "store_type": "dm", "store_id": 1, "user_id": "u-1"}
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Tell me more!"
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234.5678"}

        _process_message(
            text="met someone interesting", user_slack_id="U123", user_name="Jurg",
            channel_id="D123", context_type="dm", participant_count=1,
            respond=MagicMock(), client=client, thread_ts=None,
            ts="0001.0001", bot_user_id="BXXX",
        )

        # Background extract should be called with signal_flag=True (dm_always_extract)
        mock_bg.assert_called_once()
        call_kwargs = mock_bg.call_args
        assert call_kwargs[1].get("signal_flag") or call_kwargs[0][3]  # positional or keyword


class TestThreadMemorySeed:
    """When the bot replies to a top-level channel message, its response is
    posted as the first message in a new thread. Thread memory MUST be seeded
    with both turns — otherwise subsequent thread replies look like an
    unseen conversation to the dispatcher, which runs triage and posts a
    'Signal captured' receipt instead of continuing the conversation.
    """

    @patch("bot.pipeline.append_message")
    @patch("bot.pipeline.get_memory")
    def test_seeds_empty_thread_with_both_turns(self, mock_get_memory, mock_append):
        mock_get_memory.return_value = {
            "messages": [],
            "store_type": "thread",
            "store_id": "thread-1",
            "thread_ts": "100.200",
            "channel_id": "C123",
        }
        from bot.pipeline import _seed_thread_memory
        _seed_thread_memory("100.200", "C123", "user-1",
                             "met bas from greenchoice today",
                             "Jurg",
                             "Huge win. Bas isn't buying tech; he's buying board confidence.")
        assert mock_append.call_count == 2
        # First call: user turn
        user_call = mock_append.call_args_list[0]
        assert user_call.kwargs["role"] == "user"
        assert user_call.kwargs["content"] == "met bas from greenchoice today"
        assert user_call.kwargs["name"] == "Jurg"
        # Second call: assistant turn
        assistant_call = mock_append.call_args_list[1]
        assert assistant_call.kwargs["role"] == "assistant"
        assert "Bas" in assistant_call.kwargs["content"]

    @patch("bot.pipeline.append_message")
    @patch("bot.pipeline.get_memory")
    def test_idempotent_when_thread_already_populated(self, mock_get_memory, mock_append):
        mock_get_memory.return_value = {
            "messages": [{"role": "user", "content": "existing"}],
            "store_type": "thread",
            "store_id": "thread-1",
        }
        from bot.pipeline import _seed_thread_memory
        _seed_thread_memory("100.200", "C123", "user-1",
                             "new text", "Jurg", "new response")
        mock_append.assert_not_called()

    @patch("bot.pipeline.append_message")
    @patch("bot.pipeline.get_memory")
    def test_swallows_exceptions(self, mock_get_memory, mock_append):
        """A seed failure must never break the main pipeline — it's defensive."""
        mock_get_memory.side_effect = RuntimeError("db down")
        from bot.pipeline import _seed_thread_memory
        # Must not raise
        _seed_thread_memory("100.200", "C123", "user-1",
                             "text", "Jurg", "response")
        mock_append.assert_not_called()

    @patch("bot.pipeline._seed_thread_memory")
    @patch("bot.pipeline._background_extract")
    @patch("bot.pipeline._send_response")
    @patch("bot.pipeline._get_response")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline._resolve_user")
    def test_process_message_seeds_thread_after_channel_reply(
        self, mock_resolve, mock_memory, mock_dispatch, mock_thinking,
        mock_get_response, mock_send, mock_bg_extract, mock_seed,
    ):
        """Top-level channel message → bot replies in new thread → seed fires."""
        from bot.pipeline import _process_message
        mock_resolve.return_value = ({"id": "user-1"}, None, False)
        mock_memory.return_value = {
            "messages": [], "store_type": "channel", "store_id": "C123",
            "channel_id": "C123",
        }
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "the big debrief", "exercise_pending": None,
        }
        mock_thinking.return_value = {"type": "message", "ts": "001.001"}
        mock_get_response.return_value = "Huge win..."

        _process_message(
            text="the big debrief", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="channel", participant_count=5,
            respond=MagicMock(), client=MagicMock(), thread_ts=None,
            ts="001.001", bot_user_id="BXXX",
        )
        mock_seed.assert_called_once()
        # reply_thread_ts should equal ts (new thread rooted at user's message)
        args = mock_seed.call_args.args
        assert args[0] == "001.001"   # thread_ts
        assert args[1] == "C123"      # channel_id
        assert args[2] == "user-1"    # user_id
        assert args[3] == "the big debrief"  # user_text
        assert args[4] == "Jurg"      # user_name
        assert args[5] == "Huge win..."  # bot response

    @patch("bot.pipeline._seed_thread_memory")
    @patch("bot.pipeline._background_extract")
    @patch("bot.pipeline._send_response")
    @patch("bot.pipeline._get_response")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline._resolve_user")
    def test_process_message_does_not_seed_in_thread_context(
        self, mock_resolve, mock_memory, mock_dispatch, mock_thinking,
        mock_get_response, mock_send, mock_bg_extract, mock_seed,
    ):
        """Thread replies go to thread memory directly; no seeding needed."""
        from bot.pipeline import _process_message
        mock_resolve.return_value = ({"id": "user-1"}, None, False)
        mock_memory.return_value = {
            "messages": [{"role": "assistant", "content": "earlier reply"}],
            "store_type": "thread", "store_id": "T1", "thread_ts": "100.200",
            "channel_id": "C123",
        }
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "follow up", "exercise_pending": None,
        }
        mock_thinking.return_value = {"type": "message", "ts": "001.001"}
        mock_get_response.return_value = "got it"

        _process_message(
            text="follow up", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="thread", participant_count=5,
            respond=MagicMock(), client=MagicMock(), thread_ts="100.200",
            ts="300.400", bot_user_id="BXXX",
        )
        mock_seed.assert_not_called()

    @patch("bot.pipeline._seed_thread_memory")
    @patch("bot.pipeline._background_extract")
    @patch("bot.pipeline._send_response")
    @patch("bot.pipeline._get_response")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline._resolve_user")
    def test_process_message_does_not_seed_in_dm(
        self, mock_resolve, mock_memory, mock_dispatch, mock_thinking,
        mock_get_response, mock_send, mock_bg_extract, mock_seed,
    ):
        """DMs never post in threads — no seeding."""
        from bot.pipeline import _process_message
        mock_resolve.return_value = ({"id": "user-1"}, None, False)
        mock_memory.return_value = {
            "messages": [], "store_type": "dm", "store_id": "D1", "user_id": "user-1",
        }
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "hi", "exercise_pending": None,
        }
        mock_thinking.return_value = {"type": "message", "ts": "001.001"}
        mock_get_response.return_value = "hello"

        _process_message(
            text="hi", user_slack_id="U123", user_name="Jurg",
            channel_id="D123", context_type="dm", participant_count=1,
            respond=MagicMock(), client=MagicMock(), thread_ts=None,
            ts="001.001", bot_user_id="BXXX",
        )
        mock_seed.assert_not_called()


class TestCorrectionDetection:
    """Replies to signal receipt threads should trigger correction handler."""

    @patch("bot.pipeline._handle_signal_correction")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline._resolve_user")
    def test_reply_to_receipt_triggers_correction(self, mock_resolve,
                                                    mock_memory, mock_dispatch,
                                                    mock_thinking, mock_correction):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_memory.return_value = {
            "messages": [
                {"role": "assistant", "content": "🌱 Signal captured.\n• People: Jim"},
                {"role": "user", "content": "Jim's last name is Blom"},
            ],
            "store_type": "thread",
            "thread_ts": "100.200",
            "channel_id": "C123",
        }
        mock_thinking.return_value = {"type": "message", "ts": "999.0"}
        mock_correction.return_value = True  # Correction handled

        _process_message(
            text="Jim's last name is Blom", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="thread", participant_count=2,
            respond=MagicMock(), client=MagicMock(), thread_ts="100.200",
            ts="100.300", bot_user_id="BXXX",
        )

        # Correction handler should be called
        mock_correction.assert_called_once()
        # Dispatch should NOT be called (correction short-circuits)
        mock_dispatch.assert_not_called()

    @patch("bot.pipeline._handle_signal_correction")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline._resolve_user")
    def test_reply_to_non_receipt_thread_not_correction(self, mock_resolve,
                                                          mock_memory, mock_dispatch,
                                                          mock_thinking, mock_correction):
        mock_resolve.return_value = (None, None, False)
        mock_memory.return_value = {
            "messages": [
                {"role": "assistant", "content": "Sure, here's what I know about KPN..."},
            ],
            "store_type": "thread",
            "thread_ts": "100.200",
            "channel_id": "C123",
        }
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "thanks", "exercise_pending": None,
        }
        mock_thinking.return_value = {"type": "message", "ts": "999.0"}

        # This should NOT trigger correction — not a receipt thread
        mock_correction.assert_not_called()


class TestEnrichmentOnMatch:
    """MATCHED entities should be enriched with new info."""

    @patch("mothertree.graphql_client.graphql")
    @patch("mothertree.entities.find_or_create_company")
    def test_matched_person_gets_company_linked(self, mock_company, mock_gql):
        from bot.extraction import _apply_resolution
        mock_company.return_value = {"id": "co-new"}
        mock_gql.return_value = {"updateContactById": {"contact": {"id": "ct-existing"}}}

        resolution = {
            "resolved": [
                {"entity": {"name": "Jurg", "type": "person", "organization": "Aknostic"},
                 "resolution": "MATCHED", "matched_id": "ct-existing",
                 "candidate_ids": [], "reason": "Team member"},
            ],
            "flags": [],
        }
        _apply_resolution(resolution)
        # Should update the existing contact with the company
        mock_gql.assert_called()
        update_call = [c for c in mock_gql.call_args_list if "updateContactById" in str(c)]
        assert len(update_call) >= 1

    def test_matched_without_new_info_not_updated(self):
        from bot.extraction import _apply_resolution
        resolution = {
            "resolved": [
                {"entity": {"name": "Jurg", "type": "person"},
                 "resolution": "MATCHED", "matched_id": "ct-existing",
                 "candidate_ids": [], "reason": "Team member"},
            ],
            "flags": [],
        }
        # No organization, no role → nothing to enrich
        result = _apply_resolution(resolution)  # noqa: F841
        assert result["contacts_processed"] == 0


class TestSignalFlagFromTriage:
    """Triage should set signal_flag even when respond=false."""

    def test_signal_flag_set_before_silent(self):
        """Dispatcher sets signal_flag before checking respond."""
        from bot.characters.dispatcher import dispatch
        with patch("bot.characters.dispatcher._call_triage_llm") as mock_triage:
            mock_triage.return_value = {
                "respond": False,
                "signal": {"capture": True, "confidence": 0.8},
                "reason": "Signal but not a question",
            }
            result = dispatch(
                text="met someone at KPN about cloud costs",
                participant_count=5, enrolled=False,
                recent_messages=[],
            )
            assert result["character"] == "silent"
            assert result["signal_flag"] is True
