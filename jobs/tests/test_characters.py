"""Tests for character ensemble modules."""
from unittest.mock import MagicMock, patch


class TestBase:
    """Shared character utilities."""

    def test_no_hallucination_rules_present(self):
        from bot.characters.base import NO_HALLUCINATION_RULES
        assert "NEVER FABRICATE" in NO_HALLUCINATION_RULES

    def test_slack_formatting_rules_present(self):
        from bot.characters.base import SLACK_FORMATTING_RULES
        assert "single asterisk" in SLACK_FORMATTING_RULES

    def test_verbosity_rule_present(self):
        from bot.characters.base import SLACK_FORMATTING_RULES
        assert "150 words" in SLACK_FORMATTING_RULES
        assert "2500 characters" not in SLACK_FORMATTING_RULES

    def test_training_exempt(self):
        from bot.characters.base import SLACK_FORMATTING_RULES
        assert "training" in SLACK_FORMATTING_RULES.lower()

    def test_fix_slack_formatting_bold(self):
        from bot.characters.base import fix_slack_formatting
        assert fix_slack_formatting("**bold**") == "*bold*"

    def test_fix_slack_formatting_heading(self):
        from bot.characters.base import fix_slack_formatting
        result = fix_slack_formatting("### heading")
        assert "###" not in result
        assert "*heading*" in result

    def test_fix_slack_formatting_bullets(self):
        from bot.characters.base import fix_slack_formatting
        assert fix_slack_formatting("- item") == "• item"

    def test_fix_slack_formatting_links(self):
        from bot.characters.base import fix_slack_formatting
        assert fix_slack_formatting("[text](http://example.com)") == "text"

    def test_default_model_and_temperature(self):
        from bot.characters.base import DEFAULT_MODEL, DEFAULT_TEMPERATURE
        from mothertree.config import GENERATION_MODEL
        assert DEFAULT_MODEL == GENERATION_MODEL
        assert DEFAULT_TEMPERATURE == 0.7

    def test_factual_annotation_types(self):
        from bot.characters.base import FACTUAL_ANNOTATION_TYPES
        assert "status" in FACTUAL_ANNOTATION_TYPES
        assert "url_content" not in FACTUAL_ANNOTATION_TYPES

    def test_build_annotation_context_none(self):
        from bot.characters.base import build_annotation_context
        assert build_annotation_context(None) == ""

    def test_build_annotation_context_factual(self):
        from bot.characters.base import build_annotation_context
        result = build_annotation_context({"type": "status", "stage": 0, "chapter": 2})
        assert "FACTS" in result
        assert "status" in result

    def test_build_annotation_context_contextual(self):
        from bot.characters.base import build_annotation_context
        result = build_annotation_context({"type": "url_content", "url": "https://example.com"})
        assert "CONTEXT" in result
        assert "url_content" in result


class TestMotherTree:
    """Mother Tree character — the Librarian."""

    def test_identity_present(self):
        from bot.characters.mother_tree import IDENTITY
        assert "Mother Tree" in IDENTITY
        assert "commercial intelligence" in IDENTITY

    def test_goals_present(self):
        from bot.characters.mother_tree import GOALS
        assert len(GOALS) > 0

    def test_rules_present(self):
        from bot.characters.mother_tree import RULES
        assert "never fabricate" in RULES.lower()

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    def test_respond_includes_identity(self, mock_gather, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "Change:\n- We help organizations..."
        mock_chat.return_value = "response"
        respond(question="test", history=[], user_name="Jurg", participant_count=1)
        system = mock_chat.call_args[0][0][0]["content"]
        assert "Mother Tree" in system
        assert "Jurg" in system

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    def test_respond_includes_ci_context(self, mock_gather, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "Change:\n- test change statement"
        mock_chat.return_value = "response"
        respond(question="test", history=[], user_name="Jurg", participant_count=1)
        system = mock_chat.call_args[0][0][0]["content"]
        assert "test change statement" in system

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    def test_respond_channel_includes_participant_note(self, mock_gather, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "CI data"
        mock_chat.return_value = "response"
        respond(question="test", history=[], user_name="Jurg", participant_count=5)
        system = mock_chat.call_args[0][0][0]["content"]
        assert "group channel" in system.lower()

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    def test_respond_dm_no_participant_note(self, mock_gather, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "CI data"
        mock_chat.return_value = "response"
        respond(question="test", history=[], user_name="Jurg", participant_count=1)
        system = mock_chat.call_args[0][0][0]["content"]
        assert "group channel" not in system.lower()

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    def test_respond_with_annotation(self, mock_gather, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "CI data"
        mock_chat.return_value = "response"
        respond(question="test", history=[], user_name="Jurg", participant_count=1,
                annotation={"type": "status", "stage": 0, "chapter": 2})
        system = mock_chat.call_args[0][0][0]["content"]
        assert "FACTS" in system

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    def test_respond_with_exercise_pending(self, mock_gather, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "CI data"
        mock_chat.return_value = "response"
        respond(question="test", history=[], user_name="Jurg", participant_count=1,
                exercise_pending={"question_num": 2, "total": 3})
        system = mock_chat.call_args[0][0][0]["content"]
        assert "question 2" in system

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    def test_respond_includes_rules(self, mock_gather, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "CI data"
        mock_chat.return_value = "response"
        respond(question="test", history=[], user_name="Jurg", participant_count=1)
        system = mock_chat.call_args[0][0][0]["content"]
        assert "NEVER FABRICATE" in system
        assert "single asterisk" in system

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    def test_respond_calls_llm(self, mock_gather, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Here's what I know."
        result = respond(question="what do we know?", history=[], user_name="Jurg", participant_count=1)
        assert result == "Here's what I know."
        mock_chat.assert_called_once()

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    def test_respond_passes_history(self, mock_gather, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "response"
        history = [{"role": "user", "content": "earlier question"}]
        respond(question="follow up", history=history, user_name="Jurg", participant_count=1)
        messages = mock_chat.call_args[0][0]
        roles = [m["role"] for m in messages]
        assert roles[0] == "system"
        assert "user" in roles[1:]


class TestDispatcher:
    """Dispatcher — the Receptionist. Routes messages to characters."""

    def test_status_command_routes_to_mother_tree(self):
        from bot.characters.dispatcher import dispatch
        enrollment = {"role": "hunter", "currentStage": 0, "currentChapter": 2, "streak": 3}
        result = dispatch(
            text="status", participant_count=1, enrolled=True,
            enrollment=enrollment,
        )
        assert result["character"] == "mother_tree"
        assert result["annotation"]["type"] == "status"
        assert result["must_respond"] is True

    def test_help_command_routes_to_mother_tree(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="help", participant_count=1, enrolled=False)
        assert result["character"] == "mother_tree"
        assert result["annotation"]["type"] == "help"

    def test_persona_saga_routes_to_saga(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="ask saga what is the change?", participant_count=1, enrolled=False)
        assert result["character"] == "saga"
        assert result["clean_text"] == "what is the change?"

    def test_persona_lena_routes_to_lena(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="ask lena how do I close?", participant_count=1, enrolled=False)
        assert result["character"] == "lena"

    def test_persona_trainer_sets_training_mode(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="ask trainer test me", participant_count=1, enrolled=False)
        assert result["training_mode"] is True

    def test_training_next_sets_training_mode(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="next", participant_count=1, enrolled=True,
            enrollment={"id": "e1", "current_stage": 0, "current_chapter": 1, "role": "hunter"},
        )
        assert result["training_mode"] is True
        assert result["annotation"]["type"] == "training_next"

    @patch("bot.characters.dispatcher._call_triage_llm")
    def test_training_next_channel_ignored(self, mock_triage):
        from bot.characters.dispatcher import dispatch
        mock_triage.return_value = {"respond": True, "signal": {"capture": False, "confidence": 0.0}, "reason": "question"}
        result = dispatch(
            text="next", participant_count=5, enrolled=True,
            enrollment={"id": "e1"},
        )
        assert result["annotation"] is None
        assert result["character"] == "mother_tree"

    def test_mention_sets_must_respond(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="<@UBOT> what's up?", participant_count=5,
            enrolled=False, bot_user_id="UBOT",
        )
        assert result["must_respond"] is True
        assert result["clean_text"] == "what's up?"

    def test_url_detection_routes_to_mother_tree(self):
        from bot.characters.dispatcher import dispatch
        with patch("bot.characters.dispatcher.fetch_and_follow") as mock:
            mock.return_value = "Page content"
            result = dispatch(
                text="check this https://example.com/article",
                participant_count=1, enrolled=False,
            )
        assert result["character"] == "mother_tree"
        assert result["annotation"]["type"] == "url_content"

    def test_exercise_answer_routes_to_training(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="A", participant_count=1, enrolled=True,
            active_exercise={"id": "c1", "exercise": {"content": {"questions": [{}]}}},
        )
        assert result["training_mode"] is True
        assert result["annotation"]["type"] == "answer"
        assert result["annotation"]["answer"] == "A"

    def test_citizen_next_routes_to_mother_tree(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="next", participant_count=1, enrolled=True,
            enrollment={"id": "e1", "role": "citizen", "current_stage": 0, "current_chapter": 0},
        )
        assert result["annotation"]["type"] == "citizen_inspiration"

    @patch("bot.characters.dispatcher._call_triage_llm")
    def test_unmatched_channel_message_goes_to_triage(self, mock_triage):
        from bot.characters.dispatcher import dispatch
        mock_triage.return_value = {"respond": True, "signal": {"capture": False, "confidence": 0.0}, "reason": "question"}
        result = dispatch(
            text="interesting point about the market",
            participant_count=5, enrolled=False,
            recent_messages=[],
        )
        assert result["character"] == "mother_tree"
        mock_triage.assert_called_once()

    @patch("bot.characters.dispatcher._call_triage_llm")
    def test_unmatched_channel_triage_silent(self, mock_triage):
        from bot.characters.dispatcher import dispatch
        mock_triage.return_value = {"respond": False, "signal": {"capture": False, "confidence": 0.0}, "reason": "small talk"}
        result = dispatch(
            text="nice weather", participant_count=5, enrolled=False,
            recent_messages=[],
        )
        assert result["character"] == "silent"

    @patch("bot.characters.dispatcher._call_triage_llm")
    def test_signal_flag_set_from_triage(self, mock_triage):
        from bot.characters.dispatcher import dispatch
        mock_triage.return_value = {"respond": True, "signal": {"capture": True, "confidence": 0.9}, "reason": "prospect"}
        result = dispatch(
            text="met someone at KubeCon", participant_count=5,
            enrolled=False, recent_messages=[],
        )
        assert result["signal_flag"] is True

    def test_dm_unmatched_routes_to_mother_tree_no_triage(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="what do we know about KPN?",
            participant_count=1, enrolled=False,
        )
        assert result["character"] == "mother_tree"
        assert result["must_respond"] is True

    def test_active_thread_skips_triage(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="sounds good",
            participant_count=5, enrolled=False,
            context_type="thread",
            has_bot_participated=True,
        )
        assert result["character"] == "mother_tree"
        assert result["must_respond"] is True

    def test_exercise_pending_passed_through(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="what is our worldview?",
            participant_count=1, enrolled=True,
            active_exercise={"id": "c1", "current_question": 1, "exercise": {"content": {"questions": [{}, {}, {}]}}},
        )
        assert result["exercise_pending"] == {"question_num": 2, "total": 3}

    def test_dispatch_pipeline_global(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="the pipeline", participant_count=1, enrolled=False)
        assert result["character"] == "mother_tree"
        assert result["annotation"]["type"] == "pipeline"
        assert result["annotation"]["scope"] == "global"
        assert result["must_respond"] is True

    def test_dispatch_pipeline_bare(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="pipeline", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "pipeline"
        assert result["annotation"]["scope"] == "global"

    def test_dispatch_my_pipeline(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="my pipeline", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "pipeline"
        assert result["annotation"]["scope"] == "personal"

    def test_dispatch_pipeline_someone(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="pim's pipeline", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "pipeline"
        assert result["annotation"]["scope"] == "other"
        assert result["annotation"]["target"] == "pim"

    def test_dispatch_pipeline_name_suffix(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="pipeline pim", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "pipeline"
        assert result["annotation"]["scope"] == "other"
        assert result["annotation"]["target"] == "pim"

    def test_dispatch_brief(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="brief KPN", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "brief"
        assert result["annotation"]["query"] == "KPN"


class TestPipelineIntegration:
    """Pipeline wired to Dispatcher -> Character."""

    @patch("bot.pipeline._background_extract")
    @patch("bot.pipeline.extract_signal")
    @patch("bot.pipeline.assess_actions")
    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline._resolve_user")
    def test_dm_freeform_uses_mother_tree(
        self, mock_resolve, mock_dispatch, mock_memory, mock_gather, mock_ctx, mock_chat, mock_assess, mock_extract, mock_bg
    ):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "hello", "exercise_pending": None,
        }
        mock_memory.return_value = {"messages": [], "store_type": "dm", "store_id": 1, "user_id": "u-1"}
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Hi there!"
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234.5678"}

        _process_message(
            text="hello", user_slack_id="U123", user_name="Jurg",
            channel_id="D123", context_type="dm", participant_count=1,
            respond=MagicMock(), client=client, thread_ts=None,
            ts="0001.0001", bot_user_id="BXXX",
        )

        mock_chat.assert_called_once()
        client.chat_update.assert_called_once()

    @patch("bot.pipeline._resolve_user")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    def test_channel_silent_deletes_thinking(self, mock_memory, mock_dispatch, mock_resolve):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_dispatch.return_value = {
            "character": "silent", "intent": "freeform",
            "annotation": None, "must_respond": False,
            "training_mode": False, "signal_flag": False,
            "clean_text": "nice", "exercise_pending": None,
        }
        mock_memory.return_value = {"messages": [], "store_type": "channel", "store_id": 1, "channel_id": "C123"}
        client = MagicMock()
        client.reactions_add.return_value = {"ok": True}

        _process_message(
            text="nice", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="channel", participant_count=5,
            respond=MagicMock(), client=client, thread_ts=None,
            ts="0001.0001", bot_user_id="BXXX",
        )

        client.reactions_remove.assert_called_once()

    @patch("bot.pipeline._background_extract")
    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline._resolve_user")
    def test_persona_saga_uses_character_module(self, mock_resolve,
                                                 mock_dispatch, mock_memory,
                                                 mock_gather, mock_ctx, mock_chat, mock_bg):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_dispatch.return_value = {
            "character": "saga", "intent": "persona",
            "annotation": {"type": "persona", "persona": "saga", "question": "what is the change?"},
            "must_respond": True, "training_mode": False,
            "signal_flag": False, "clean_text": "what is the change?",
            "exercise_pending": None,
        }
        mock_memory.return_value = {"messages": [], "store_type": "dm", "store_id": 1, "user_id": "u-1"}
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "The change is about ownership."
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234.5678"}

        _process_message(
            text="ask saga what is the change?", user_slack_id="U123", user_name="Jurg",
            channel_id="D123", context_type="dm", participant_count=1,
            respond=MagicMock(), client=client, thread_ts=None,
            ts="0001.0001", bot_user_id="BXXX",
        )

        mock_chat.assert_called_once()
        # Verify Saga's identity is in the system prompt
        system_prompt = mock_chat.call_args[0][0][0]["content"]
        assert "Saga" in system_prompt
