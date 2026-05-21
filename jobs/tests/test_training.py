"""Tests for training engine components."""
import json
from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest

# --- Hasura query tests ---

class TestTrainingHasura:
    """Test training-related Hasura queries build correct GraphQL and handle responses."""

    @patch("mothertree.graphql_client.graphql")
    def test_insert_exercise(self, mock_gql):
        from mothertree.graphql_client import insert_exercise
        mock_gql.return_value = {"createExercise": {"exercise": {"id": "ex-123"}}}
        content = {"stage": 0, "chapter": 0, "type": "instruction", "questions": []}
        result = insert_exercise(user_id="u-1", stage=0, chapter=0,
                                 exercise_type="instruction", content=content,
                                 source_tables=["change"])
        assert result == "ex-123"
        call_args = mock_gql.call_args
        assert "createExercise" in call_args[0][0]

    @patch("mothertree.graphql_client.graphql")
    def test_insert_response(self, mock_gql):
        from mothertree.graphql_client import insert_response
        mock_gql.return_value = {"createResponse": {"response": {"id": "r-1"}}}
        result = insert_response(exercise_id="ex-1", user_id="u-1",
                                 response="A", question_index=0,
                                 correct=True, feedback="Good")
        assert result == "r-1"

    @patch("mothertree.graphql_client.graphql")
    def test_create_conversation(self, mock_gql):
        from mothertree.graphql_client import create_conversation
        mock_gql.return_value = {"createConversation": {"conversation": {"id": "c-1"}}}
        result = create_conversation(user_id="u-1", exercise_id="ex-1",
                                     stage=0, state="waiting_response")
        assert result == "c-1"

    @patch("mothertree.graphql_client.graphql")
    def test_get_active_conversation(self, mock_gql):
        from mothertree.graphql_client import get_active_conversation
        mock_gql.return_value = {"allConversationsList": [{"id": "c-1", "state": "waiting_response", "currentQuestion": 0, "exerciseId": "ex-1", "stage": 0, "exerciseByExerciseId": None}]}
        result = get_active_conversation(user_id="u-1")
        assert result["id"] == "c-1"

    @patch("mothertree.graphql_client.graphql")
    def test_get_active_conversation_none(self, mock_gql):
        from mothertree.graphql_client import get_active_conversation
        mock_gql.return_value = {"allConversationsList": []}
        result = get_active_conversation(user_id="u-1")
        assert result is None

    @patch("mothertree.graphql_client.graphql")
    def test_update_conversation(self, mock_gql):
        from mothertree.graphql_client import update_conversation
        mock_gql.return_value = {"updateConversationById": {"conversation": {"id": "c-1"}}}
        update_conversation(conversation_id="c-1", state="complete", current_question=3)
        call_args = mock_gql.call_args
        assert "updateConversationById" in call_args[0][0]

    @patch("mothertree.graphql_client.graphql")
    def test_advance_user(self, mock_gql):
        from mothertree.graphql_client import advance_user
        mock_gql.return_value = {"updateUserById": {"user": {"id": "u-1"}}}
        advance_user(user_id="u-1", current_chapter=1)
        call_args = mock_gql.call_args
        assert "updateUserById" in call_args[0][0]

    @patch("mothertree.graphql_client.graphql")
    def test_update_streak(self, mock_gql):
        from mothertree.graphql_client import update_streak
        mock_gql.return_value = {"updateUserById": {"user": {"id": "u-1"}}}
        update_streak(user_id="u-1", streak=5)
        call_args = mock_gql.call_args
        assert "updateUserById" in call_args[0][0]

    @patch("mothertree.graphql_client.graphql")
    def test_get_active_users(self, mock_gql):
        from mothertree.graphql_client import get_active_users
        mock_gql.return_value = {"allUsersList": [
            {"id": "u-1", "email": "pim@example.com", "name": "Pim", "role": "hunter",
             "currentStage": 0, "currentChapter": 0, "streak": 0, "lastActivity": None, "calendarUrl": None}
        ]}
        result = get_active_users()
        assert len(result) == 1
        assert result[0]["email"] == "pim@example.com"

    @patch("mothertree.graphql_client.graphql")
    def test_cancel_stale_conversations(self, mock_gql):
        from mothertree.graphql_client import cancel_stale_conversations
        mock_gql.side_effect = [
            {"allConversationsList": [{"id": "c-1"}, {"id": "c-2"}]},
            {"updateConversationById": {"conversation": {"id": "c-1"}}},
            {"updateConversationById": {"conversation": {"id": "c-2"}}},
        ]
        result = cancel_stale_conversations(user_id="u-1")
        assert result == 2

    @patch("mothertree.graphql_client.graphql")
    def test_get_user_by_email_includes_streak(self, mock_gql):
        from mothertree.graphql_client import get_user_by_email
        mock_gql.return_value = {"allUsersList": [{
            "id": "u-1", "email": "pim@example.com", "name": "Pim",
            "role": "hunter", "currentStage": 0, "currentChapter": 2,
            "active": True, "streak": 5, "lastActivity": "2026-03-20T09:00:00Z",
            "calendarUrl": None,
        }]}
        result = get_user_by_email("pim@example.com")
        assert result["streak"] == 5
        assert result["lastActivity"] is not None

    @patch("mothertree.graphql_client.graphql")
    def test_fetch_foundation_for_chapter(self, mock_gql):
        from mothertree.graphql_client import fetch_foundation_for_chapter
        mock_gql.return_value = {
            "allChangesList": [{"statement": "We offer freedom", "context": "cloud"}]
        }
        result = fetch_foundation_for_chapter(chapter=0)
        assert "change" in result


class TestExerciseGenerator:
    """Test exercise generation logic."""

    def test_hunter_stage0_chapter_mapping_covers_all_chapters(self):
        from training.curriculum import get_chapters
        chapters = get_chapters("hunter", 0)
        assert len(chapters) == 3
        assert all(i in chapters for i in range(3))

    def test_hunter_stage0_chapters_have_required_fields(self):
        from training.curriculum import get_chapters
        for ch in get_chapters("hunter", 0).values():
            assert "name" in ch
            assert "tables" in ch
            assert "purpose" in ch
            assert "trainer" in ch

    @patch("training.engine.generate")
    @patch("training.engine.fetch_foundation_for_chapter")
    def test_generate_exercise_stage_0_instruction(self, mock_fetch, mock_gen):
        from training.engine import generate_exercise
        mock_fetch.return_value = {
            "change": [{"statement": "We offer freedom to operate", "context": "cloud"}]
        }
        mock_gen.return_value = json.dumps({
            "instruction": "Here is what we say...",
            "questions": [
                {"question": "Q1", "options": {"A": "a", "B": "b", "C": "c"},
                 "correct": "A", "why": "because", "redirect": "think about it"},
                {"question": "Q2", "options": {"A": "a", "B": "b", "C": "c"},
                 "correct": "B", "why": "because", "redirect": "think about it"},
                {"question": "Q3", "options": {"A": "a", "B": "b", "C": "c"},
                 "correct": "C", "why": "because", "redirect": "think about it"},
            ]
        })
        result = generate_exercise(role="hunter", stage=0, chapter=0)
        assert result["stage"] == 0
        assert result["chapter"] == 0
        assert result["chapter_name"] == "The Promise"
        assert result["trainer"] == "seth"
        assert result["type"] == "instruction"
        assert len(result["questions"]) == 3
        assert "instruction" in result

    @patch("training.engine.generate")
    @patch("training.engine.fetch_foundation_for_chapter")
    def test_generate_exercise_stage_0_practice(self, mock_fetch, mock_gen):
        from training.engine import generate_exercise
        mock_fetch.return_value = {
            "change": [{"statement": "We offer freedom", "context": "cloud"}]
        }
        mock_gen.return_value = json.dumps({
            "questions": [
                {"question": "Q1", "options": {"A": "a", "B": "b", "C": "c"},
                 "correct": "A", "why": "because", "redirect": "think about it"},
                {"question": "Q2", "options": {"A": "a", "B": "b", "C": "c"},
                 "correct": "B", "why": "because", "redirect": "think about it"},
                {"question": "Q3", "options": {"A": "a", "B": "b", "C": "c"},
                 "correct": "C", "why": "because", "redirect": "think about it"},
            ]
        })
        result = generate_exercise(role="hunter", stage=0, chapter=0, practice=True)
        assert result["type"] == "practice"
        assert "instruction" not in result

    def test_hunter_stage1_is_the_offering(self):
        from training.curriculum import get_chapter
        ch = get_chapter("hunter", 1, 0)
        assert ch["trainer"] == "seth"
        assert ch["name"] == "The Services"

    @patch("training.engine.generate")
    @patch("training.engine.fetch_foundation_for_chapter")
    def test_generate_exercise_validates_questions(self, mock_fetch, mock_gen):
        from training.engine import generate_exercise
        mock_fetch.return_value = {"change": [{"statement": "x", "context": "y"}]}
        mock_gen.return_value = json.dumps({
            "instruction": "text",
            "questions": [
                {"question": "Q1", "options": {"A": "a", "B": "b", "C": "c"},
                 "correct": "A", "why": "w", "redirect": "r"},
            ]
        })
        with pytest.raises(ValueError, match="Expected 3 questions"):
            generate_exercise(role="hunter", stage=0, chapter=0)


class TestShuffleOptions:
    """Correct answer position should be randomized."""

    def test_shuffle_preserves_correct_answer(self):
        from training.engine import _shuffle_options
        q = {"question": "Q?", "options": {"A": "right", "B": "wrong1", "C": "wrong2"},
             "correct": "A", "why": "w", "redirect": "r"}
        shuffled = _shuffle_options(q)
        # Correct answer text is still at the correct letter
        assert shuffled["options"][shuffled["correct"]] == "right"
        # All options still present
        assert set(shuffled["options"].values()) == {"right", "wrong1", "wrong2"}

    def test_shuffle_varies_position_over_many_runs(self):
        from training.engine import _shuffle_options
        q = {"question": "Q?", "options": {"A": "right", "B": "wrong1", "C": "wrong2"},
             "correct": "A", "why": "w", "redirect": "r"}
        positions = set()
        for _ in range(30):
            shuffled = _shuffle_options(q)
            positions.add(shuffled["correct"])
        # Over 30 runs, should hit at least 2 different positions
        assert len(positions) >= 2

    @patch("training.engine.generate")
    @patch("training.engine.fetch_foundation_for_chapter")
    def test_exercise_questions_are_shuffled(self, mock_fetch, mock_gen):
        """All-B input should not produce all-B output consistently."""
        from training.engine import generate_exercise
        mock_fetch.return_value = {"change": [{"statement": "x", "context": "y"}]}
        mock_gen.return_value = json.dumps({
            "instruction": "text",
            "questions": [
                {"question": "Q1", "options": {"A": "a", "B": "b", "C": "c"},
                 "correct": "B", "why": "w", "redirect": "r"},
                {"question": "Q2", "options": {"A": "d", "B": "e", "C": "f"},
                 "correct": "B", "why": "w", "redirect": "r"},
                {"question": "Q3", "options": {"A": "g", "B": "h", "C": "i"},
                 "correct": "B", "why": "w", "redirect": "r"},
            ]
        })
        # Run multiple times — at least once should NOT be all-B
        all_b_count = 0
        for _ in range(10):
            result = generate_exercise(role="hunter", stage=0, chapter=0)
            answers = [q["correct"] for q in result["questions"]]
            if answers == ["B", "B", "B"]:
                all_b_count += 1
        assert all_b_count < 10  # Statistically impossible to be all-B every time


class TestScoring:
    """Test deterministic MC scoring for Stage 0."""

    def test_score_correct_answer(self):
        from training.score import score_response
        question = {
            "question": "What is the change?",
            "options": {"A": "Freedom", "B": "Cost savings", "C": "Speed"},
            "correct": "A",
            "why": "Freedom names the real change.",
            "redirect": "Ask what change they're really offering.",
        }
        result = score_response(stage=0, question=question, response="A")
        assert result["correct"] is True
        assert "Right" in result["feedback"]

    def test_score_wrong_answer(self):
        from training.score import score_response
        question = {
            "question": "What is the change?",
            "options": {"A": "Freedom", "B": "Cost savings", "C": "Speed"},
            "correct": "A",
            "why": "Freedom names the real change.",
            "redirect": "Ask what change they're really offering.",
        }
        result = score_response(stage=0, question=question, response="B")
        assert result["correct"] is False
        assert "A" in result["feedback"]
        assert question["why"].rstrip(".").lower() in result["feedback"]
        assert question["redirect"] in result["feedback"]

    def test_score_case_insensitive(self):
        from training.score import score_response
        question = {
            "question": "Q", "options": {"A": "a", "B": "b", "C": "c"},
            "correct": "A", "why": "w", "redirect": "r",
        }
        result = score_response(stage=0, question=question, response="a")
        assert result["correct"] is True

    def test_score_stage_1_not_implemented(self):
        from training.score import score_response
        with pytest.raises(NotImplementedError):
            score_response(stage=1, question={}, response="A")

    def test_score_invalid_response(self):
        from training.score import score_response
        question = {
            "question": "Q", "options": {"A": "a", "B": "b", "C": "c"},
            "correct": "A", "why": "w", "redirect": "r",
        }
        result = score_response(stage=0, question=question, response="D")
        assert result["correct"] is False
        assert "A, B, or C" in result["feedback"]


class TestDelivery:
    """Test exercise delivery CronJob."""

    @patch("training.deliver.get_slack_user_id")
    @patch("training.deliver.update_streak")
    @patch("training.deliver.daily_check")
    @patch("training.deliver.WebClient")
    @patch("training.deliver.get_active_users")
    def test_deliver_sends_dm(self, mock_enrollments, mock_webclient,
                              mock_check, mock_streak, mock_slack_id):
        from training.deliver import deliver_training
        mock_enrollments.return_value = [{
            "id": "u-1", "email": "pim@example.com",
            "name": "Pim", "role": "hunter", "streak": 0, "lastActivity": None,
        }]
        mock_check.return_value = "*Chapter 1 of 3: The Promise*\n\nLearn this.\n\nReady for the questions? Reply *go* when you've read this."
        mock_slack_id.return_value = "U123"
        slack = MagicMock()
        mock_webclient.return_value = slack

        deliver_training()

        slack.chat_postMessage.assert_called_once()
        call_kwargs = slack.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "U123"
        assert "The Promise" in call_kwargs["text"]

    @patch("training.deliver.get_slack_user_id")
    @patch("training.deliver.update_streak")
    @patch("training.deliver.daily_check")
    @patch("training.deliver.WebClient")
    @patch("training.deliver.get_active_users")
    def test_deliver_skips_user_with_active_conversation(self, mock_enrollments,
                                                         mock_webclient, mock_check,
                                                         mock_streak, mock_slack_id):
        from training.deliver import deliver_training
        mock_enrollments.return_value = [{
            "id": "u-1", "email": "pim@example.com",
            "name": "Pim", "role": "hunter", "streak": 0, "lastActivity": None,
        }]
        mock_check.return_value = None  # active conversation → nothing to send
        mock_slack_id.return_value = "U123"
        slack = MagicMock()
        mock_webclient.return_value = slack

        deliver_training()

        slack.chat_postMessage.assert_not_called()


class TestDMHandler:
    """Test DM response handling logic."""

    def test_parse_dm_command_next(self):
        from bot.training_dm import parse_dm_command
        cmd, topic = parse_dm_command("next")
        assert cmd == "next"
        assert topic is None

    def test_parse_dm_command_practice_with_topic(self):
        from bot.training_dm import parse_dm_command
        cmd, topic = parse_dm_command("practice worldview")
        assert cmd == "practice"
        assert topic == "worldview"

    def test_parse_dm_command_practice_no_topic(self):
        from bot.training_dm import parse_dm_command
        cmd, topic = parse_dm_command("practice")
        assert cmd == "practice"
        assert topic is None

    def test_parse_dm_command_go(self):
        from bot.training_dm import parse_dm_command
        cmd, topic = parse_dm_command("go")
        assert cmd == "go"

    def test_parse_dm_command_answer(self):
        from bot.training_dm import parse_dm_command
        cmd, topic = parse_dm_command("B")
        assert cmd == "answer"
        assert topic == "B"

    def test_parse_dm_command_unknown(self):
        from bot.training_dm import parse_dm_command
        cmd, topic = parse_dm_command("hello there")
        assert cmd == "conversation"

    def test_resolve_topic_valid(self):
        from bot.training_dm import resolve_topic
        assert resolve_topic("worldview") == 1
        assert resolve_topic("PROMISE") == 0
        assert resolve_topic("services") == 4

    def test_resolve_topic_invalid(self):
        from bot.training_dm import resolve_topic
        assert resolve_topic("kubernetes") is None

    def test_chapter_complete_message(self):
        from bot.training_dm import format_chapter_complete
        text = format_chapter_complete(chapter=2, chapter_name="The Audience", streak=4)
        assert "Chapter 3 complete" in text  # 1-indexed
        assert "Streak: 4" in text
        assert "Chapter 4" in text  # next chapter teaser

    def test_chapter_complete_last_chapter(self):
        from bot.training_dm import format_chapter_complete
        text = format_chapter_complete(chapter=4, chapter_name="The Services", streak=5)
        assert "Stage 0 complete" in text
        assert "coming soon" in text.lower()

    def test_streak_calculation_same_day(self):
        from datetime import datetime

        from bot.training_dm import calculate_streak
        now = datetime.now(UTC)
        assert calculate_streak(current_streak=3, last_activity=now.isoformat()) == 3

    def test_streak_calculation_next_day(self):
        from datetime import datetime, timedelta

        from bot.training_dm import calculate_streak
        yesterday = datetime.now(UTC) - timedelta(days=1)
        assert calculate_streak(current_streak=3, last_activity=yesterday.isoformat()) == 4

    def test_streak_calculation_broken(self):
        from datetime import datetime, timedelta

        from bot.training_dm import calculate_streak
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        assert calculate_streak(current_streak=10, last_activity=three_days_ago.isoformat()) == 1

    def test_streak_calculation_first_activity(self):
        from bot.training_dm import calculate_streak
        assert calculate_streak(current_streak=0, last_activity=None) == 1

    def test_format_chapter_complete_stage_0_done_has_coming_soon(self):
        from bot.training_dm import format_chapter_complete
        text = format_chapter_complete(chapter=4, chapter_name="The Services", streak=7)
        assert "Stage 0 complete" in text
        assert "coming soon" in text.lower()
        assert "practice" in text.lower()


class TestDMConversation:
    """Test freeform DM conversation persistence."""

    @patch("mothertree.graphql_client.graphql")
    def test_get_or_create_dm_conversation_existing(self, mock_gql):
        from mothertree.graphql_client import get_or_create_dm_conversation
        mock_gql.return_value = {"allConversationsList": [{
            "id": "c-dm-1", "stage": -1, "state": "active",
            "messages": [{"role": "user", "content": "hello"}],
        }]}
        result = get_or_create_dm_conversation("U123")
        assert result["id"] == "c-dm-1"
        assert result["stage"] == -1

    @patch("mothertree.graphql_client.graphql")
    def test_get_or_create_dm_conversation_creates_new(self, mock_gql):
        from mothertree.graphql_client import get_or_create_dm_conversation
        mock_gql.side_effect = [
            {"allConversationsList": []},
            {"createConversation": {"conversation": {"id": "c-dm-new"}}},
        ]
        result = get_or_create_dm_conversation("U123")
        assert result["id"] == "c-dm-new"
        assert mock_gql.call_count == 2

    @patch("mothertree.graphql_client.graphql")
    def test_append_dm_message(self, mock_gql):
        from mothertree.graphql_client import append_dm_message
        mock_gql.return_value = {"appendConversationMessage": {"conversation": {"id": "c-1"}}}
        append_dm_message("c-1", role="user", content="hello")
        call_args = mock_gql.call_args
        assert "appendConversationMessage" in call_args[0][0]

    @patch("mothertree.graphql_client.graphql")
    def test_cancel_stale_conversations_excludes_dm(self, mock_gql):
        from mothertree.graphql_client import cancel_stale_conversations
        mock_gql.return_value = {"update_conversations": {"affected_rows": 1}}
        cancel_stale_conversations(user_id="u-1")
        query = mock_gql.call_args[0][0]
        assert "stage" in query  # must filter out stage -1


class TestLLMConversation:
    """Test multi-turn conversation LLM call."""

    @patch("mothertree.llm.scaleway")
    def test_chat_conversation_returns_text(self, mock_scaleway):
        from mothertree.llm import chat_conversation
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello back"))]
        mock_scaleway.chat.completions.create.return_value = mock_response

        result = chat_conversation([
            {"role": "system", "content": "You are Mother Tree."},
            {"role": "user", "content": "Hello"},
        ])
        assert result == "Hello back"
        call_kwargs = mock_scaleway.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 8000

    @patch("mothertree.llm.scaleway")
    def test_chat_conversation_uses_conversation_model(self, mock_scaleway):
        from mothertree.llm import chat_conversation
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_scaleway.chat.completions.create.return_value = mock_response

        chat_conversation([{"role": "user", "content": "test"}], model="qwen3.5-397b-a17b")
        call_kwargs = mock_scaleway.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "qwen3.5-397b-a17b"


class TestTrainingConsistency:
    """Validate training components are consistent with each other."""

    def test_hunter_stage0_chapters_match_topic_map(self):
        from bot.training_dm import TOPIC_MAP
        from training.curriculum import get_chapters
        for i, ch in get_chapters("hunter", 0).items():
            topic = ch["name"].lower().replace("the ", "")
            assert topic in TOPIC_MAP, f"Chapter {i} ({ch['name']}) has no topic keyword"
            assert TOPIC_MAP[topic] == i

    def test_hunter_stage0_all_chapters_have_unique_names(self):
        from training.curriculum import get_chapters
        names = [ch["name"] for ch in get_chapters("hunter", 0).values()]
        assert len(names) == len(set(names))

    def test_score_handles_all_option_letters(self):
        from training.score import score_response
        q = {"question": "Q", "options": {"A": "a", "B": "b", "C": "c"},
             "correct": "A", "why": "w", "redirect": "r"}
        for letter in ("A", "B", "C"):
            result = score_response(stage=0, question=q, response=letter)
            assert isinstance(result["correct"], bool)
            assert isinstance(result["feedback"], str)


class TestAskWithHistory:
    """Test conversation-aware ask."""

    @patch("mothertree.ask.gather_context")
    @patch("mothertree.ask.chat_conversation")
    @patch("mothertree.ask.format_context_for_prompt")
    def test_ask_with_history_includes_messages(self, mock_ctx, mock_chat, mock_gather):
        from mothertree.ask import ask_with_history
        mock_ctx.return_value = "CI context here"
        mock_chat.return_value = "Mother Tree says hello"
        history = [
            {"role": "user", "content": "what is our change?"},
            {"role": "assistant", "content": "We offer freedom to operate."},
        ]
        result = ask_with_history("what about the worldview?", history)
        assert result == "Mother Tree says hello"
        messages = mock_chat.call_args[0][0]
        # System prompt + CI context + history + new question
        assert messages[0]["role"] == "system"
        assert "NEVER FABRICATE" in messages[0]["content"]
        assert len(messages) >= 4  # system + 2 history + 1 new

    @patch("mothertree.ask.gather_context")
    @patch("mothertree.ask.chat_conversation")
    @patch("mothertree.ask.format_context_for_prompt")
    def test_ask_with_history_persona(self, mock_ctx, mock_chat, mock_gather):
        from mothertree.ask import ask_with_history
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Seth says..."
        ask_with_history("why positioning?", [], persona="seth")
        messages = mock_chat.call_args[0][0]
        assert "Seth Godin" in messages[0]["content"]
        assert "NEVER FABRICATE" in messages[0]["content"]

    @patch("mothertree.ask.gather_context")
    @patch("mothertree.ask.chat_conversation")
    @patch("mothertree.ask.format_context_for_prompt")
    def test_ask_with_history_no_hallucination_rule(self, mock_ctx, mock_chat, mock_gather):
        from mothertree.ask import ask_with_history
        mock_ctx.return_value = "context"
        mock_chat.return_value = "answer"
        ask_with_history("question", [])
        system = mock_chat.call_args[0][0][0]["content"]
        assert "NEVER FABRICATE" in system


