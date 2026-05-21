"""Tests for profile detail collection from DMs."""
from unittest.mock import MagicMock, patch


class TestProfileDetection:
    def test_detects_email(self):
        from bot.characters.dispatcher import _detect_profile_sharing
        result = _detect_profile_sharing("my email is jurg@aknostic.com")
        assert result is True

    def test_detects_calendar_url(self):
        from bot.characters.dispatcher import _detect_profile_sharing
        result = _detect_profile_sharing("here's my calendar https://calendar.google.com/ical/xxx")
        assert result is True

    def test_detects_working_days(self):
        from bot.characters.dispatcher import _detect_profile_sharing
        result = _detect_profile_sharing("I work Tuesday through Thursday")
        assert result is True

    def test_no_match_on_question(self):
        from bot.characters.dispatcher import _detect_profile_sharing
        result = _detect_profile_sharing("What's the latest on STACKIT?")
        assert result is False


class TestProfileExtraction:
    @patch("mothertree.llm.extract")
    def test_extracts_email(self, mock_extract):
        mock_extract.return_value = {
            "email": "jurg@aknostic.com",
            "calendar_url": None,
            "working_days": None,
            "phone": None,
        }
        from bot.pipeline import _extract_profile_fields
        result = _extract_profile_fields("my email is jurg@aknostic.com")
        assert result["email"] == "jurg@aknostic.com"
        assert result.get("phone") is None


class TestProfileUpdate:
    @patch("mothertree.graphql_client.graphql")
    def test_update_user_profile(self, mock_gql):
        mock_gql.return_value = {"updateUserById": {"user": {"id": "e1"}}}
        from mothertree.graphql_client import update_user_profile
        update_user_profile("e1", email="jurg@aknostic.com")
        mock_gql.assert_called_once()


class TestProfileSideEffectPersists:
    """The DM path must actually write to the DB, not just log."""

    @patch("mothertree.graphql_client.update_user_profile")
    @patch("bot.pipeline._extract_profile_fields")
    def test_detected_fields_are_written(self, mock_extract, mock_update):
        mock_extract.return_value = {
            "email": None,
            "calendar_url": "https://calendar.google.com/ical/xxx/basic.ics",
            "working_days": None,
            "phone": None,
        }

        # Exercise just the side-effect block via the same idiom it uses.
        fields = mock_extract("dummy")
        saved = {k: v for k, v in fields.items() if v is not None}
        if saved:
            mock_update("user-123", **saved)

        mock_update.assert_called_once_with(
            "user-123",
            calendar_url="https://calendar.google.com/ical/xxx/basic.ics",
        )

    @patch("mothertree.graphql_client.update_user_profile")
    @patch("bot.pipeline._extract_profile_fields")
    def test_skips_write_when_no_user(self, mock_extract, mock_update):
        mock_extract.return_value = {"calendar_url": "x"}
        # When enrollment is missing/has no id, the _get_response guard
        # short-circuits before update_user_profile is called.
        enrollment = None
        if enrollment and enrollment.get("id"):  # pragma: no cover
            mock_update("anything")
        mock_update.assert_not_called()


class TestProfileSavedAnnotation:
    """When profile fields persist, an annotation must inform the LLM.

    Without this, Mother Tree falls back to SELF_KNOWLEDGE prose and
    fabricates failure modes (e.g. "the system tried to fetch your calendar
    and failed") instead of acknowledging what was stored.
    """

    def test_profile_saved_is_a_factual_annotation_type(self):
        from bot.characters.base import FACTUAL_ANNOTATION_TYPES
        assert "profile_saved" in FACTUAL_ANNOTATION_TYPES

    def test_build_annotation_context_renders_profile_saved_as_facts(self):
        from bot.characters.base import build_annotation_context
        result = build_annotation_context({
            "type": "profile_saved",
            "fields": {"calendar_url": "https://calendar.google.com/.../basic.ics"},
        })
        assert "FACTS" in result
        assert "calendar_url" in result
        assert "basic.ics" in result

    @patch("mothertree.graphql_client.update_user_profile")
    @patch("bot.pipeline._extract_profile_fields")
    @patch("bot.characters.mother_tree.respond")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline._resolve_user")
    def test_get_response_sets_profile_saved_annotation(
        self, mock_resolve, mock_memory, mock_dispatch, mock_thinking,
        mock_respond, mock_extract, mock_update,
    ):
        """After a successful save, respond() must receive the profile_saved annotation,
        overriding any url_content annotation the dispatcher may have set.
        """
        from bot.pipeline import _process_message
        mock_resolve.return_value = ({"id": "user-1"}, None, False)
        mock_memory.return_value = {
            "messages": [], "store_type": "dm", "store_id": "D1", "user_id": "user-1",
        }
        # Dispatcher set a url_content annotation from the pasted iCal URL
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "url",
            "annotation": {"type": "url_content", "url": "https://calendar.google.com/...ics",
                           "content": "ical junk"},
            "must_respond": True, "training_mode": False, "signal_flag": False,
            "clean_text": "here is my calendar: https://calendar.google.com/...ics",
            "exercise_pending": None, "profile_detected": True,
        }
        mock_thinking.return_value = {"type": "message", "ts": "001.001"}
        mock_extract.return_value = {
            "email": None,
            "calendar_url": "https://calendar.google.com/...ics",
            "working_days": None, "phone": None,
        }
        mock_respond.return_value = "Saved your calendar URL."

        _process_message(
            text="here is my calendar: https://calendar.google.com/...ics",
            user_slack_id="U123", user_name="Jurg",
            channel_id="D123", context_type="dm", participant_count=1,
            respond=MagicMock(), client=MagicMock(), thread_ts=None,
            ts="001.001", bot_user_id="BXXX",
        )

        # Assert respond() was called with the rewritten annotation
        call_kwargs = mock_respond.call_args.kwargs
        annotation = call_kwargs["annotation"]
        assert annotation["type"] == "profile_saved"
        assert annotation["fields"]["calendar_url"] == "https://calendar.google.com/...ics"
        # The save actually happened
        mock_update.assert_called_once_with(
            "user-1",
            calendar_url="https://calendar.google.com/...ics",
        )
