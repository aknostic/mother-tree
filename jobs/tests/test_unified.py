"""Tests for unified conversation flow components."""
from unittest.mock import MagicMock, patch


class TestChannelMemory:
    """Channel memory CRUD operations."""

    @patch("mothertree.graphql_client.graphql")
    def test_get_or_create_channel_memory_new(self, mock_gql):
        from mothertree.graphql_client import get_or_create_channel_memory
        mock_gql.side_effect = [
            {"channelMemoryByChannelId": None},
            {"createChannelMemory": {"channelMemory": {"id": 1, "channelId": "C123", "channelName": None, "messages": []}}},
        ]
        result = get_or_create_channel_memory("C123")
        assert result["channel_id"] == "C123"
        assert result["messages"] == []

    @patch("mothertree.graphql_client.graphql")
    def test_get_or_create_channel_memory_existing(self, mock_gql):
        from mothertree.graphql_client import get_or_create_channel_memory
        mock_gql.return_value = {"channelMemoryByChannelId": {"id": 1, "channelId": "C123", "channelName": None, "messages": [{"role": "user"}]}}
        result = get_or_create_channel_memory("C123")
        assert len(result["messages"]) == 1

    @patch("mothertree.graphql_client.graphql")
    def test_append_channel_message(self, mock_gql):
        from mothertree.graphql_client import append_channel_message
        mock_gql.return_value = {"appendChannelMessage": {"channelMemory": {"id": 1}}}
        append_channel_message("C123", role="user", name="Jurg", content="hello")
        call_args = mock_gql.call_args[0][0]
        assert "appendChannelMessage" in call_args

    @patch("mothertree.graphql_client.graphql")
    def test_cap_channel_memory(self, mock_gql):
        from mothertree.graphql_client import cap_channel_memory
        messages = [{"role": "user", "content": str(i)} for i in range(210)]
        mock_gql.return_value = {"update_channel_memory_by_pk": {"id": 1}}
        cap_channel_memory(1, messages, max_messages=200)
        assert mock_gql.called


class TestThreadMemory:
    """Thread memory CRUD operations."""

    @patch("mothertree.graphql_client.graphql")
    def test_get_or_create_thread_memory_new(self, mock_gql):
        from mothertree.graphql_client import get_or_create_thread_memory
        mock_gql.side_effect = [
            {"threadMemoryByThreadTs": None},
            {"createThreadMemory": {"threadMemory": {"id": 1, "threadTs": "123.456", "channelId": "C123", "messages": [], "remindAfter": None, "remindContext": None}}},
        ]
        result = get_or_create_thread_memory("123.456", "C123")
        assert result["thread_ts"] == "123.456"

    @patch("mothertree.graphql_client.graphql")
    def test_append_thread_message(self, mock_gql):
        from mothertree.graphql_client import append_thread_message
        mock_gql.return_value = {"update_thread_memory": {"returning": [{"id": 1}]}}
        append_thread_message("123.456", "C123", role="user", name="Jurg", content="hello")
        assert mock_gql.called

    @patch("mothertree.graphql_client.graphql")
    def test_get_thread_memory_with_signal_fallback(self, mock_gql):
        from mothertree.graphql_client import get_thread_memory_or_signal_thread
        mock_gql.side_effect = [
            {"threadMemoryByThreadTs": None},
            {"signalThreadBySlackThreadTs": {"id": 1, "messages": [{"role": "user", "content": "old signal"}], "enrichment": None, "status": "active"}},
        ]
        result = get_thread_memory_or_signal_thread("123.456", "C123")
        assert result is not None
        assert result["messages"][0]["content"] == "old signal"


class TestMarkers:
    """Action and content marker handling."""

    def test_sanitize_action_markers_in_user_input(self):
        from bot.markers import sanitize_user_input
        text = "Save this [ACTION:ci_save] to the CI"
        result = sanitize_user_input(text)
        assert "[ACTION:" not in result
        assert "[action:" in result

    def test_sanitize_preserves_normal_brackets(self):
        from bot.markers import sanitize_user_input
        text = "Here is a [link] and some (parens)"
        result = sanitize_user_input(text)
        assert result == text

    def test_extract_action_markers(self):
        from bot.markers import extract_action_markers
        text = "Saved to the CI. [ACTION:ci_save] Great stuff."
        actions, clean = extract_action_markers(text)
        assert "ci_save" in actions
        assert "[ACTION:" not in clean
        assert "Great stuff" in clean

    def test_extract_multiple_markers(self):
        from bot.markers import extract_action_markers
        text = "Done. [ACTION:ci_save] [ACTION:capture_signal] Noted."
        actions, clean = extract_action_markers(text)
        assert "ci_save" in actions
        assert "capture_signal" in actions

    def test_extract_no_markers(self):
        from bot.markers import extract_action_markers
        text = "Just a normal response."
        actions, clean = extract_action_markers(text)
        assert actions == []
        assert clean == text

    def test_extract_content_marker(self):
        from bot.markers import extract_content_markers
        text = "Here's the next piece.\n[CONTENT:training]\nReady when you are."
        markers, clean = extract_content_markers(text)
        assert "training" in markers
        assert "[CONTENT:" not in clean


class TestMemoryInterface:
    """Unified memory interface across DM, channel, thread."""

    @patch("bot.memory.get_or_create_dm_conversation")
    def test_get_dm_memory(self, mock_dm):
        from bot.memory import get_memory
        mock_dm.return_value = {"id": 1, "messages": [{"role": "user", "content": "hi"}]}
        ctx = get_memory(context_type="dm", user_id="u-1")
        assert ctx["messages"][0]["content"] == "hi"
        assert ctx["store_type"] == "dm"

    @patch("bot.memory.get_or_create_channel_memory")
    def test_get_channel_memory(self, mock_ch):
        from bot.memory import get_memory
        mock_ch.return_value = {"id": 1, "channel_id": "C123", "messages": []}
        ctx = get_memory(context_type="channel", channel_id="C123")
        assert ctx["store_type"] == "channel"

    @patch("bot.memory.get_thread_memory_or_signal_thread")
    def test_get_thread_memory_with_fallback(self, mock_th):
        from bot.memory import get_memory
        mock_th.return_value = {"thread_ts": "123.456", "messages": [{"role": "user"}], "_legacy": True}
        ctx = get_memory(context_type="thread", thread_ts="123.456", channel_id="C123")
        assert ctx["store_type"] == "thread"
        assert ctx["_legacy"] is True

    def test_window_messages(self):
        from bot.memory import window_messages
        msgs = [{"role": "user", "content": str(i)} for i in range(300)]
        windowed = window_messages(msgs, max_messages=200)
        assert len(windowed) == 200
        assert windowed[0]["content"] == "100"

    @patch("bot.memory.chat_conversation")
    def test_summarize_thread_creates_summary(self, mock_llm):
        from bot.memory import summarize_old_messages
        mock_llm.return_value = "Summary: Jurg discussed KPN migration with Flavia."
        msgs = [{"role": "user", "name": "Jurg", "content": f"msg {i}"} for i in range(120)]
        result = summarize_old_messages(msgs, max_messages=100)
        assert len(result) <= 101
        assert result[0]["role"] == "system"
        assert "Summary" in result[0]["content"]


class TestTriage:
    """Triage: cheap LLM call for respond/signal/silent."""

    @patch("bot.triage._call_triage_llm")
    def test_dm_always_respond(self, mock_llm):
        from bot.triage import triage
        mock_llm.return_value = {"respond": False, "signal": {"capture": False, "confidence": 0.0}, "reason": "test"}
        result = triage("hello", participant_count=1, recent_messages=[])
        assert result["respond"] is True

    @patch("bot.triage._call_triage_llm")
    def test_channel_can_be_silent(self, mock_llm):
        from bot.triage import triage
        mock_llm.return_value = {"respond": False, "signal": {"capture": False, "confidence": 0.0}, "reason": "small talk"}
        result = triage("nice work!", participant_count=5, recent_messages=[])
        assert result["respond"] is False

    @patch("bot.triage._call_triage_llm")
    def test_signal_flag(self, mock_llm):
        from bot.triage import triage
        mock_llm.return_value = {"respond": True, "signal": {"capture": True, "confidence": 0.9}, "reason": "prospect intel"}
        result = triage("met someone at KubeCon", participant_count=5, recent_messages=[])
        assert result["respond"] is True
        assert result["signal"]["capture"] is True
        assert result["signal"]["confidence"] >= 0.8

    @patch("bot.triage._call_triage_llm")
    def test_low_confidence_signal(self, mock_llm):
        from bot.triage import triage
        mock_llm.return_value = {"respond": True, "signal": {"capture": True, "confidence": 0.5}, "reason": "unclear"}
        result = triage("had an interesting chat", participant_count=5, recent_messages=[])
        assert result["signal"]["confidence"] < 0.8

    def test_triage_prompt_includes_participant_count(self):
        from bot.triage import _build_triage_prompt
        prompt = _build_triage_prompt("hello", participant_count=1, recent_messages=[])
        assert "1" in prompt


class TestChannelBuffer:
    """In-memory buffer for lazy persistence of silent channel messages."""

    def test_buffer_stores_messages(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=20)
        buf.add("C123", {"role": "user", "name": "Jurg", "content": "hello"})
        assert len(buf.get("C123")) == 1

    def test_buffer_caps_at_max(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=5)
        for i in range(10):
            buf.add("C123", {"role": "user", "content": str(i)})
        assert len(buf.get("C123")) == 5
        assert buf.get("C123")[0]["content"] == "5"

    def test_flush_returns_and_clears(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=20)
        buf.add("C123", {"role": "user", "content": "hi"})
        msgs = buf.flush("C123")
        assert len(msgs) == 1
        assert len(buf.get("C123")) == 0

    def test_separate_channels(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=20)
        buf.add("C1", {"role": "user", "content": "a"})
        buf.add("C2", {"role": "user", "content": "b"})
        assert len(buf.get("C1")) == 1
        assert len(buf.get("C2")) == 1

    def test_should_flush_when_full(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=5)
        for i in range(5):
            buf.add("C123", {"role": "user", "content": str(i)})
        assert buf.should_flush("C123") is True


class TestDetect:
    """Detect phase: pattern matching and annotation production."""

    def test_strip_mention(self):
        from bot.detect import detect
        result = detect("<@U_BOT> what's our positioning?", participant_count=5, enrolled=False, bot_user_id="U_BOT")
        assert result["must_respond"] is True
        assert result["clean_text"] == "what's our positioning?"

    def test_slash_prefix_not_recognized(self):
        from bot.detect import detect
        result = detect("/mothertree status", participant_count=1, enrolled=True)
        # /mothertree prefix is no longer stripped — not a recognized pattern
        assert result["pattern_matched"] is False

    def test_command_status(self):
        from bot.detect import detect
        enrollment = {"role": "hunter", "current_stage": 0, "current_chapter": 2, "streak": 3}
        result = detect("status", participant_count=1, enrolled=True, enrollment=enrollment, user_id="u-1")
        assert result["annotation"]["type"] == "status"
        assert result["annotation"]["stage"] == 0

    def test_persona_seth(self):
        from bot.detect import detect
        result = detect("ask seth what is the change?", participant_count=1, enrolled=False)
        assert result["persona"] == "seth"
        assert result["clean_text"] == "what is the change?"

    def test_training_next_dm_only(self):
        from bot.detect import detect
        with patch("bot.detect.deliver_next") as mock:
            mock.return_value = {"chapter": "worldview", "content": "..."}
            result = detect("next", participant_count=1, enrolled=True, enrollment={"id": "e1", "current_stage": 0, "current_chapter": 1, "role": "hunter"})
        assert result["annotation"]["type"] == "training_delivered"

    def test_training_next_channel_ignored(self):
        from bot.detect import detect
        result = detect("next", participant_count=5, enrolled=True, enrollment={"id": "e1"})
        assert result["annotation"] is None
        assert result["pattern_matched"] is False

    def test_exercise_answer_dm_only(self):
        from bot.detect import detect
        with patch("bot.detect.score_exercise_answer") as mock:
            mock.return_value = {"correct": True, "feedback": "Right!", "progress": {}}
            result = detect("A", participant_count=1, enrolled=True, active_exercise={"id": "c1", "exercise": {"content": {"questions": [{}]}}})
        assert result["annotation"]["type"] == "answer_scored"

    def test_exercise_answer_channel_ignored(self):
        from bot.detect import detect
        result = detect("A", participant_count=5, enrolled=True, active_exercise={"id": "c1"})
        assert result["annotation"] is None

    def test_bare_a_without_exercise_no_match(self):
        from bot.detect import detect
        result = detect("A", participant_count=1, enrolled=True, active_exercise=None)
        assert result["annotation"] is None
        assert result["pattern_matched"] is False

    def test_url_detection(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_and_follow") as mock:
            mock.return_value = "Page content here"
            result = detect("check this https://example.com/article", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "url_content"

    def test_url_fetch_failure(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_and_follow") as mock:
            mock.return_value = None
            result = detect("check this https://example.com/nope", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "url_failed"

    def test_multiple_urls_fetched(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_and_follow") as mock:
            mock.side_effect = ["Content A", "Content B", None]
            result = detect(
                "check https://example.com/a and https://example.com/b and https://example.com/c",
                participant_count=1, enrolled=False,
            )
        assert result["annotation"]["type"] == "url_content"
        assert "urls" in result["annotation"]
        assert len(result["annotation"]["urls"]) == 2
        assert "Content A" in result["annotation"]["content"]
        assert "Content B" in result["annotation"]["content"]

    def test_max_three_urls(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_and_follow") as mock:
            mock.return_value = "content"
            detect(
                "https://a.com https://b.com https://c.com https://d.com",
                participant_count=1, enrolled=False,
            )
        # Should only fetch 3 (mock called 3 times)
        assert mock.call_count == 3

    def test_citizen_inspiration(self):
        from bot.detect import detect
        with patch("bot.detect.generate_citizen_inspiration") as mock_gen, \
             patch("training.operations.advance_citizen") as mock_adv:
            mock_gen.return_value = {"content": "Here's something to think about...", "advance": True}
            result = detect("next", participant_count=1, enrolled=True, enrollment={"id": "e1", "role": "citizen", "current_stage": 0, "current_chapter": 0})
        assert result["annotation"]["type"] == "citizen_inspiration"
        assert result["annotation"]["content"] == "Here's something to think about..."
        mock_adv.assert_called_once()

    def test_exercise_pending_nudge(self):
        from bot.detect import detect
        result = detect("what is our worldview?", participant_count=1, enrolled=True,
                        active_exercise={"id": "c1", "current_question": 1, "exercise": {"content": {"questions": [{}, {}, {}]}}})
        assert result["exercise_pending"] == {"question_num": 2, "total": 3}
        assert result["pattern_matched"] is False


class TestSignalExtraction:
    """Background signal extraction from conversation exchanges."""

    @patch("bot.characters.spotter.extract")
    @patch("bot.extraction.insert_signal")
    def test_extract_creates_signal(self, mock_insert, mock_spotter):
        from bot.extraction import extract_signal
        mock_spotter.return_value = {
            "entities": [{"type": "person", "name": "Flavia", "organization": "KPN"}],
            "actions": [{"action": "call Flavia", "by_when": "next week"}],
            "pain_signals": [],
            "value_hooks": [],
            "stage": {"current": "Signal", "evidence": []},
        }
        mock_insert.return_value = "sig-1"
        with patch("bot.characters.weaver.resolve") as mock_weaver, \
             patch("mothertree.graphql_client.graphql"):
            mock_weaver.return_value = {"resolved": [], "flags": []}
            extract_signal(
                user_message="Met Flavia from KPN, they're migrating",
                assistant_response="Interesting — how far along?",
                user_name="Jurg",
            )
        assert mock_insert.called

    @patch("bot.characters.spotter.extract")
    def test_extract_handles_failure_gracefully(self, mock_spotter):
        from bot.extraction import extract_signal
        mock_spotter.side_effect = Exception("LLM failed")
        # Should not raise
        with patch("bot.extraction.insert_signal"):
            extract_signal(
                user_message="test",
                assistant_response="test",
                user_name="test",
            )

    @patch("bot.extraction._assess_via_llm")
    def test_assess_actions(self, mock_llm):
        from bot.extraction import assess_actions
        mock_llm.return_value = {"ci_save": True, "capture_signal": False}
        result = assess_actions(
            user_message="yes save it",
            assistant_response="Done!",
        )
        assert result["ci_save"] is True
        assert result["capture_signal"] is False

    @patch("bot.extraction._assess_via_llm")
    def test_assess_actions_failure_returns_safe_defaults(self, mock_llm):
        from bot.extraction import assess_actions
        mock_llm.side_effect = Exception("fail")
        result = assess_actions(
            user_message="test",
            assistant_response="test",
        )
        assert result["ci_save"] is False
        assert result["capture_signal"] is False


class TestModelSelection:
    """Model selection based on annotation type."""

    def test_status_uses_extraction_model(self):
        from mothertree.ask import select_model
        model = select_model(annotation={"type": "status"})
        from mothertree.config import EXTRACTION_MODEL
        assert model == EXTRACTION_MODEL

    def test_freeform_uses_generation_model(self):
        from mothertree.ask import select_model
        model = select_model(annotation=None)
        from mothertree.config import GENERATION_MODEL
        assert model == GENERATION_MODEL

    def test_signal_flag_uses_generation_model(self):
        from mothertree.ask import select_model
        model = select_model(annotation=None, signal_flag=True)
        from mothertree.config import GENERATION_MODEL
        assert model == GENERATION_MODEL

    def test_persona_uses_generation_model(self):
        from mothertree.ask import select_model
        model = select_model(annotation=None, persona="seth")
        from mothertree.config import GENERATION_MODEL
        assert model == GENERATION_MODEL


class TestExtendedPrompt:
    """System prompt includes new sections."""

    def test_prompt_includes_context_awareness(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "CONTEXT AWARENESS" in prompt

    def test_prompt_includes_signal_thread_behavior(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "SIGNAL THREAD BEHAVIOR" in prompt

    def test_prompt_includes_persona_awareness(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "PERSONA AWARENESS" in prompt

    def test_prompt_includes_actions(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "[ACTION:ci_save]" in prompt

    def test_prompt_includes_exercise_awareness(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "EXERCISE AWARENESS" in prompt



class TestConversationEngine:
    """Conversation engine: builds context, calls LLM, handles markers."""

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_freeform_response(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.return_value = "Here's what I know about that."
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        result = converse("what do we know?", memory_ctx=memory, user_name="Jurg")
        assert result["response"] == "Here's what I know about that."
        assert result["actions"] == []

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_action_markers_extracted(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.return_value = "Saved. [ACTION:ci_save] All good."
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        result = converse("yes save it", memory_ctx=memory, user_name="Jurg")
        assert "ci_save" in result["actions"]
        assert "[ACTION:" not in result["response"]

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_content_markers_replaced(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.return_value = "Here's the next piece.\n[CONTENT:training]\nReady?"
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        annotation = {"type": "training_delivered", "content": "Full chapter text here."}
        result = converse("next", memory_ctx=memory, user_name="Jurg", annotation=annotation)
        assert "Full chapter text here." in result["response"]
        assert "[CONTENT:" not in result["response"]

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_fallback_on_llm_failure(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.side_effect = Exception("LLM timeout")
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        annotation = {"type": "status", "role": "hunter", "stage": 0, "chapter": 2, "streak": 3}
        result = converse("status", memory_ctx=memory, user_name="Jurg", annotation=annotation)
        assert "Stage 0" in result["response"]

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_freeform_fallback_on_failure(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.side_effect = Exception("LLM timeout")
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        result = converse("hello", memory_ctx=memory, user_name="Jurg")
        assert "trouble thinking" in result["response"]

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_slack_formatting_applied(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.return_value = "**bold** and ### heading"
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        result = converse("test", memory_ctx=memory, user_name="Jurg")
        assert "**" not in result["response"]
        assert "###" not in result["response"]


class TestPipeline:
    """Full pipeline: dispatch -> character -> extract."""

    @patch("bot.pipeline.assess_actions")
    @patch("bot.pipeline.extract_signal")
    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline._resolve_user")
    def test_dm_freeform(self, mock_resolve, mock_dispatch, mock_memory,
                         mock_gather, mock_ctx, mock_chat, mock_extract, mock_assess):
        from bot.pipeline import handle_message
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
        handle_message(
            text="hello", user_slack_id="U123", user_name="Jurg",
            channel_id="D123", channel_type="im", participant_count=1,
            respond=lambda msg, **kw: None, client=client,
        )
        client.chat_update.assert_called_once()

    @patch("bot.pipeline._resolve_user")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    def test_channel_silent(self, mock_memory, mock_dispatch, mock_resolve):
        from bot.pipeline import handle_message
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
        handle_message(
            text="nice", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", channel_type="channel", participant_count=5,
            respond=lambda msg, **kw: None, client=client, ts="0001.0001",
        )
        client.reactions_remove.assert_called_once()

    @patch("bot.pipeline.extract_signal")
    @patch("bot.pipeline.assess_actions")
    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline._resolve_user")
    def test_channel_signal_capture(self, mock_resolve, mock_dispatch,
                                     mock_memory, mock_gather, mock_ctx, mock_chat, mock_assess, mock_extract):
        from bot.pipeline import handle_message
        mock_resolve.return_value = (None, None, False)
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": True,
            "clean_text": "met Flavia from KPN", "exercise_pending": None,
        }
        mock_memory.return_value = {"messages": [], "store_type": "channel", "store_id": 1, "channel_id": "C123"}
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Tell me more about KPN."
        client = MagicMock()
        client.reactions_add.return_value = {"ok": True}
        client.chat_postMessage.return_value = {"ts": "1234.5678"}
        handle_message(
            text="met Flavia from KPN", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", channel_type="channel", participant_count=5,
            respond=lambda msg, **kw: None, client=client, ts="0001.0001",
        )
        mock_extract.assert_called_once()
