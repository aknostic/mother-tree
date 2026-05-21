"""Tests for debrief ingestion flow."""
from unittest.mock import MagicMock, patch


class TestDebriefDetection:
    def test_detects_debrief_keyword(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            "debrief\nAttendees: Jurg, client team\nDiscussed migration timeline.",
            participant_count=1,
        )
        assert result["intent"] == "debrief"
        assert result["annotation"]["type"] == "debrief"

    def test_detects_meeting_notes(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            "meeting notes\nQ4 review with Sanoma Learning.",
            participant_count=1,
        )
        assert result["intent"] == "debrief"

    def test_detects_service_meeting(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            "service meeting\nMonthly review with the delivery team.",
            participant_count=1,
        )
        assert result["intent"] == "service_meeting"
        assert result["annotation"]["type"] == "service_meeting"

    def test_no_debrief_in_channels(self):
        """Debrief detection only in DMs."""
        with patch("bot.characters.dispatcher._call_triage_llm") as mock_triage:
            mock_triage.return_value = {"respond": False, "signal": {"capture": False}}
            from bot.characters.dispatcher import dispatch
            result = dispatch("debrief\nSome notes.", participant_count=5)
            assert result["intent"] != "debrief"


class TestDebriefSpotter:
    @patch("bot.characters.spotter.chat_conversation")
    def test_debrief_extraction_includes_sensitivity(self, mock_chat):
        mock_chat.return_value = '{"entities": [{"name": "Sarah", "type": "person"}], "pain_signals": [{"signal": "Timeline pressure", "sensitive": false}], "value_hooks": [], "actions": [{"action": "Pim struggled with presentation", "sensitive": true}], "stage": {"current": "signal"}}'
        from bot.characters.spotter import extract_debrief
        result = extract_debrief("Discussed project timeline. Pim struggled with the client presentation. Sarah from client side happy with progress.")
        assert any(item.get("sensitive") for items in [result.get("actions", [])] for item in items)

    @patch("bot.characters.spotter.chat_conversation")
    def test_debrief_extraction_returns_dict(self, mock_chat):
        mock_chat.return_value = '{"entities": [], "pain_signals": [], "value_hooks": [], "actions": [], "stage": {"current": "signal"}}'
        from bot.characters.spotter import extract_debrief
        result = extract_debrief("Quick sync, nothing notable.")
        assert isinstance(result, dict)
        assert "entities" in result


class TestDebriefApprovalFlow:
    @patch("bot.pipeline._send_response")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline._delete_thinking")
    @patch("bot.characters.spotter.extract_debrief")
    def test_debrief_shows_preview(self, mock_extract, mock_delete, mock_think, mock_send):
        mock_think.return_value = "thinking_ts"
        mock_extract.return_value = {
            "entities": [{"name": "ClientCo", "type": "organization", "sensitive": False}],
            "pain_signals": [{"signal": "Timeline pressure", "sensitive": False}],
            "value_hooks": [],
            "actions": [{"action": "Pim struggled with presentation", "sensitive": True}],
            "stage": {"current": "signal"},
        }
        from bot.pipeline import _format_debrief_preview
        preview = _format_debrief_preview(mock_extract.return_value)
        assert "approve" in preview.lower()
        assert "skip" in preview.lower()
        assert "⚠️" in preview

    def test_format_preview_marks_sensitive(self):
        from bot.pipeline import _format_debrief_preview
        extraction = {
            "entities": [{"name": "ClientCo", "type": "organization", "sensitive": False}],
            "pain_signals": [{"signal": "Budget concerns", "sensitive": False}],
            "actions": [{"action": "Dev struggled with deadline", "sensitive": True}],
            "value_hooks": [],
            "stage": {"current": "signal"},
        }
        preview = _format_debrief_preview(extraction)
        assert "⚠️" in preview
        assert "Budget concerns" in preview
        assert "approve" in preview.lower()


class TestIngestDebriefExtraction:
    @patch("mothertree.graphql_client.graphql")
    def test_ingests_non_sensitive_items(self, mock_gql):
        mock_gql.return_value = {"createInteraction": {"interaction": {"id": "i-1"}}}
        from bot.pipeline import _ingest_debrief_extraction
        extraction = {
            "entities": [
                {"name": "JJ", "detail": "Engineering Lead"},
                {"name": "Albert", "sensitive": True},
            ],
            "actions": [
                {"action": "Follow up on IDP timeline"},
            ],
            "pain_signals": [],
            "value_hooks": [],
        }
        count = _ingest_debrief_extraction(extraction, {"id": "user-1", "role": "hunter"})
        assert count == 2  # JJ + action; Albert is sensitive and skipped
        assert mock_gql.call_count == 2

    @patch("mothertree.graphql_client.graphql")
    def test_skips_all_sensitive(self, mock_gql):
        from bot.pipeline import _ingest_debrief_extraction
        extraction = {
            "entities": [{"name": "Secret", "sensitive": True}],
            "pain_signals": [{"signal": "Confidential", "sensitive": True}],
            "value_hooks": [],
            "actions": [],
        }
        count = _ingest_debrief_extraction(extraction, None)
        assert count == 0
        mock_gql.assert_not_called()

    @patch("mothertree.graphql_client.graphql")
    def test_handles_graphql_failure_gracefully(self, mock_gql):
        mock_gql.side_effect = Exception("DB down")
        from bot.pipeline import _ingest_debrief_extraction
        extraction = {
            "entities": [{"name": "ClientCo"}],
            "pain_signals": [],
            "value_hooks": [],
            "actions": [],
        }
        # Should not raise — best-effort ingestion
        count = _ingest_debrief_extraction(extraction, {"id": "user-1", "role": "hunter"})
        assert count == 0


class TestStorePendingExtraction:
    @patch("mothertree.graphql_client.graphql")
    def test_stores_when_dm_context(self, mock_gql):
        mock_gql.return_value = {"updateConversationById": {"conversation": {"id": "conv-1"}}}
        from bot.pipeline import _store_pending_extraction
        memory_ctx = {"store_id": "conv-1", "store_type": "dm"}
        annotation = {"type": "debrief", "content": "Met with Pim about Q2"}
        _store_pending_extraction(memory_ctx, annotation)
        mock_gql.assert_called_once()
        call_args = mock_gql.call_args
        assert call_args[0][1]["patch"]["pendingDebrief"]

    @patch("mothertree.graphql_client.graphql")
    def test_skips_non_dm_context(self, mock_gql):
        from bot.pipeline import _store_pending_extraction
        memory_ctx = {"store_id": "thread-1", "store_type": "thread"}
        annotation = {"type": "debrief", "content": "notes"}
        _store_pending_extraction(memory_ctx, annotation)
        mock_gql.assert_not_called()

    @patch("mothertree.graphql_client.graphql")
    def test_skips_missing_annotation(self, mock_gql):
        from bot.pipeline import _store_pending_extraction
        memory_ctx = {"store_id": "conv-1", "store_type": "dm"}
        _store_pending_extraction(memory_ctx, None)
        mock_gql.assert_not_called()


class TestHandleDebriefApproval:
    def _memory_ctx(self):
        return {"store_id": "conv-abc", "store_type": "dm", "messages": []}

    @patch("mothertree.graphql_client.graphql")
    @patch("bot.pipeline._resolve_thinking")
    def test_skip_clears_pending(self, mock_resolve, mock_gql):
        # get_pending_debrief → returns pending; clear_pending_debrief → mutation
        import json
        mock_gql.side_effect = [
            {"conversationById": {"pendingDebrief": json.dumps({"type": "debrief", "content": "notes"})}},
            {"updateConversationById": {"conversation": {"id": "conv-abc"}}},  # clear
            {"updateConversationById": {"conversation": {"id": "conv-abc"}}},  # append_dm_message
            {"updateConversationById": {"conversation": {"id": "conv-abc"}}},  # append_dm_message
        ]
        from bot.pipeline import _handle_debrief_approval
        memory_ctx = self._memory_ctx()
        result = _handle_debrief_approval("skip", None, memory_ctx, MagicMock(), "C1", None)
        assert result is True
        mock_resolve.assert_called_once()
        args = mock_resolve.call_args[0]
        assert "Discarded" in args[3]

    @patch("mothertree.graphql_client.graphql")
    def test_returns_false_when_no_pending(self, mock_gql):
        mock_gql.return_value = {"conversationById": {"pendingDebrief": None}}
        from bot.pipeline import _handle_debrief_approval
        result = _handle_debrief_approval("approve", None, self._memory_ctx(), MagicMock(), "C1", None)
        assert result is False

    @patch("bot.pipeline._ingest_debrief_extraction")
    @patch("bot.pipeline._resolve_thinking")
    @patch("bot.characters.spotter.extract_debrief")
    @patch("mothertree.graphql_client.graphql")
    def test_approve_ingests_and_clears(self, mock_gql, mock_extract, mock_resolve, mock_ingest):
        import json
        mock_gql.side_effect = [
            {"conversationById": {"pendingDebrief": json.dumps({"type": "debrief", "content": "Met with ClientCo"})}},
            {"updateConversationById": {"conversation": {"id": "conv-abc"}}},  # clear
            {},  # append user message
            {},  # append assistant message
        ]
        mock_extract.return_value = {
            "entities": [{"name": "ClientCo"}],
            "pain_signals": [],
            "value_hooks": [],
            "actions": [],
        }
        mock_ingest.return_value = 1
        from bot.pipeline import _handle_debrief_approval
        result = _handle_debrief_approval(
            "approve", {"id": "u-1", "role": "hunter"},
            self._memory_ctx(), MagicMock(), "C1", None)
        assert result is True
        mock_ingest.assert_called_once()
        resolve_msg = mock_resolve.call_args[0][3]
        assert "Ingested 1" in resolve_msg

    @patch("bot.pipeline._advance_service_meeting")
    @patch("bot.pipeline._ingest_debrief_extraction")
    @patch("bot.pipeline._resolve_thinking")
    @patch("bot.characters.spotter.extract_debrief")
    @patch("mothertree.graphql_client.graphql")
    def test_approve_service_meeting_advances_schedule(
            self, mock_gql, mock_extract, mock_resolve, mock_ingest, mock_advance):
        import json
        mock_gql.side_effect = [
            {"conversationById": {"pendingDebrief": json.dumps({"type": "service_meeting", "content": "Monthly review"})}},
            {"updateConversationById": {"conversation": {"id": "conv-abc"}}},  # clear
            {},  # append user
            {},  # append assistant
        ]
        mock_extract.return_value = {
            "entities": [], "pain_signals": [], "value_hooks": [], "actions": []}
        mock_ingest.return_value = 0
        from bot.pipeline import _handle_debrief_approval
        result = _handle_debrief_approval(
            "approve", {"id": "u-1", "role": "hunter"},
            self._memory_ctx(), MagicMock(), "C1", None)
        assert result is True
        mock_advance.assert_called_once()
        resolve_msg = mock_resolve.call_args[0][3]
        assert "Service meeting recorded" in resolve_msg
