"""Tests for pipeline UX fixes."""
from unittest.mock import MagicMock, patch


class TestThinkingIndicator:
    """Fix 1: Reaction emoji in channels, message in threads/DMs."""

    def _make_client(self):
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234.5678"}
        client.reactions_add.return_value = {"ok": True}
        client.reactions_remove.return_value = {"ok": True}
        client.chat_update.return_value = {"ok": True}
        client.chat_delete.return_value = {"ok": True}
        return client

    def test_thinking_reaction_in_channel(self):
        from bot.pipeline import _post_thinking
        client = self._make_client()
        result = _post_thinking(client, "C123", thread_ts=None,
                                context_type="channel", message_ts="9999.0001")
        client.reactions_add.assert_called_once_with(
            name="thought_balloon", channel="C123", timestamp="9999.0001")
        client.chat_postMessage.assert_not_called()
        assert result == {"type": "reaction", "ts": "9999.0001"}

    def test_thinking_message_in_thread(self):
        from bot.pipeline import _post_thinking
        client = self._make_client()
        result = _post_thinking(client, "C123", thread_ts="1111.0001",
                                context_type="thread", message_ts="2222.0001")
        client.chat_postMessage.assert_called_once()
        client.reactions_add.assert_not_called()
        assert result == {"type": "message", "ts": "1234.5678"}

    def test_thinking_message_in_dm(self):
        from bot.pipeline import _post_thinking
        client = self._make_client()
        result = _post_thinking(client, "D123", thread_ts=None,
                                context_type="dm", message_ts="3333.0001")
        client.chat_postMessage.assert_called_once()
        client.reactions_add.assert_not_called()
        assert result == {"type": "message", "ts": "1234.5678"}

    def test_resolve_thinking_reaction(self):
        from bot.pipeline import _resolve_thinking
        client = self._make_client()
        client.chat_postMessage.return_value = {"ts": "5555.0001"}
        info = {"type": "reaction", "ts": "9999.0001"}
        result = _resolve_thinking(client, "C123", info, "Hello world")
        client.reactions_remove.assert_called_once_with(
            name="thought_balloon", channel="C123", timestamp="9999.0001")
        client.chat_postMessage.assert_called_once_with(
            channel="C123", thread_ts="9999.0001", text="Hello world")
        assert result == "5555.0001"

    def test_resolve_thinking_reaction_threads(self):
        from bot.pipeline import _resolve_thinking
        client = self._make_client()
        info = {"type": "reaction", "ts": "9999.0001"}
        _resolve_thinking(client, "C123", info, "Response text")
        post_call = client.chat_postMessage.call_args
        assert post_call.kwargs.get("thread_ts") == "9999.0001" or \
               (post_call[1].get("thread_ts") == "9999.0001")

    def test_resolve_thinking_message(self):
        from bot.pipeline import _resolve_thinking
        client = self._make_client()
        info = {"type": "message", "ts": "1234.5678"}
        result = _resolve_thinking(client, "C123", info, "Hello world")
        client.chat_update.assert_called_once_with(
            channel="C123", ts="1234.5678", text="Hello world")
        client.reactions_remove.assert_not_called()
        assert result == "1234.5678"

    def test_delete_thinking_reaction(self):
        from bot.pipeline import _delete_thinking
        client = self._make_client()
        info = {"type": "reaction", "ts": "9999.0001"}
        _delete_thinking(client, "C123", info)
        client.reactions_remove.assert_called_once_with(
            name="thought_balloon", channel="C123", timestamp="9999.0001")
        client.chat_delete.assert_not_called()

    def test_delete_thinking_message(self):
        from bot.pipeline import _delete_thinking
        client = self._make_client()
        info = {"type": "message", "ts": "1234.5678"}
        _delete_thinking(client, "C123", info)
        client.chat_delete.assert_called_once_with(
            channel="C123", ts="1234.5678")

    def test_thinking_none_handled(self):
        from bot.pipeline import _delete_thinking, _resolve_thinking
        client = self._make_client()
        assert _resolve_thinking(client, "C123", None, "text") is None
        _delete_thinking(client, "C123", None)


class TestThreadEagerness:
    """Fix 2: Always respond in threads where Mother Tree participated."""

    @patch("bot.characters.base.chat_conversation")
    @patch("bot.characters.base.format_context_for_prompt")
    @patch("bot.characters.base.gather_context")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline._resolve_user")
    def test_thread_always_responds_when_participated(
        self, mock_resolve, mock_dispatch, mock_memory, mock_gather, mock_ctx, mock_chat
    ):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "sounds good", "exercise_pending": None,
        }
        mock_memory.return_value = {
            "store_type": "thread",
            "messages": [
                {"role": "user", "name": "Jurg", "content": "check this"},
                {"role": "assistant", "content": "Got it."},
                {"role": "user", "name": "Pim", "content": "sounds good"},
            ],
        }
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Great!"
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234"}
        client.reactions_add.return_value = {"ok": True}

        _process_message(
            text="sounds good", user_slack_id="U123", user_name="Pim",
            channel_id="C123", context_type="thread", participant_count=3,
            respond=MagicMock(), client=client, thread_ts="1111.0001",
            ts="2222.0001", bot_user_id="BXXX",
        )

        # Dispatch was called with has_bot_participated=True (bot in thread history)
        assert mock_dispatch.call_args[1]["has_bot_participated"] is True
        mock_chat.assert_called_once()

    @patch("bot.pipeline._resolve_user")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    def test_thread_triages_when_not_participated(
        self, mock_memory, mock_dispatch, mock_resolve
    ):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_dispatch.return_value = {
            "character": "silent", "intent": "freeform",
            "annotation": None, "must_respond": False,
            "training_mode": False, "signal_flag": False,
            "clean_text": "hello", "exercise_pending": None,
        }
        mock_memory.return_value = {
            "store_type": "thread",
            "messages": [
                {"role": "user", "name": "Jurg", "content": "hello"},
            ],
        }
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234"}
        client.reactions_add.return_value = {"ok": True}

        _process_message(
            text="hello", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="thread", participant_count=3,
            respond=MagicMock(), client=client, thread_ts="1111.0001",
            ts="2222.0001", bot_user_id="BXXX",
        )

        # Dispatch was called with has_bot_participated=False (no assistant in history)
        assert mock_dispatch.call_args[1]["has_bot_participated"] is False

    @patch("bot.pipeline._resolve_user")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    def test_channel_still_triages(
        self, mock_memory, mock_dispatch, mock_resolve
    ):
        from bot.pipeline import _process_message
        mock_resolve.return_value = (None, None, False)
        mock_dispatch.return_value = {
            "character": "silent", "intent": "freeform",
            "annotation": None, "must_respond": False,
            "training_mode": False, "signal_flag": False,
            "clean_text": "hey", "exercise_pending": None,
        }
        mock_memory.return_value = {
            "store_type": "channel",
            "messages": [
                {"role": "assistant", "content": "Hi there."},
                {"role": "user", "name": "Jurg", "content": "hey"},
            ],
        }
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234"}
        client.reactions_add.return_value = {"ok": True}

        _process_message(
            text="hey", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="channel", participant_count=5,
            respond=MagicMock(), client=client, thread_ts=None,
            ts="3333.0001", bot_user_id="BXXX",
        )

        # Dispatch was called — it handles triage internally
        mock_dispatch.assert_called_once()


class TestFactPreservation:
    """Fix 3: FACTS vs CONTEXT annotation labeling."""

    def test_factual_annotation_uses_facts_label(self):
        from mothertree.ask import FACTUAL_ANNOTATION_TYPES
        assert "status" in FACTUAL_ANNOTATION_TYPES
        assert "stats" in FACTUAL_ANNOTATION_TYPES
        assert "enrolled" in FACTUAL_ANNOTATION_TYPES
        assert "answer" in FACTUAL_ANNOTATION_TYPES

    def test_contextual_types_not_in_factual(self):
        from mothertree.ask import FACTUAL_ANNOTATION_TYPES
        assert "url_content" not in FACTUAL_ANNOTATION_TYPES
        assert "training_delivered" not in FACTUAL_ANNOTATION_TYPES
        assert "citizen_inspiration" not in FACTUAL_ANNOTATION_TYPES

    @patch("mothertree.ask.gather_context")
    @patch("mothertree.ask.format_context_for_prompt")
    @patch("mothertree.ask.chat_conversation")
    def test_factual_prompt_says_state_exactly(self, mock_chat, mock_ctx, mock_gather):
        from mothertree.ask import ask_with_history
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Welcome!"

        ask_with_history(
            question="enroll hunter",
            history=[],
            annotation={"type": "enrolled", "role": "hunter", "name": "Jurg"},
        )

        system_prompt = mock_chat.call_args[0][0][0]["content"]
        assert "FACTS" in system_prompt
        assert "state these exactly" in system_prompt
        assert "SYSTEM ANNOTATION" not in system_prompt

    @patch("mothertree.ask.gather_context")
    @patch("mothertree.ask.format_context_for_prompt")
    @patch("mothertree.ask.chat_conversation")
    def test_contextual_prompt_says_weave_naturally(self, mock_chat, mock_ctx, mock_gather):
        from mothertree.ask import ask_with_history
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Interesting page!"

        ask_with_history(
            question="check this url",
            history=[],
            annotation={"type": "url_content", "url": "https://example.com", "content": "Page text"},
        )

        system_prompt = mock_chat.call_args[0][0][0]["content"]
        assert "CONTEXT" in system_prompt
        assert "Weave this into your response naturally" in system_prompt
        assert "FACTS (state these exactly" not in system_prompt

    def test_context_awareness_updated(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "State FACTS exactly" in prompt
        assert "Weave these into your response naturally" not in prompt
