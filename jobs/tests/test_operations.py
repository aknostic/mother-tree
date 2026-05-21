"""Tests for training operations — enroll, deliver, start, score."""
from datetime import UTC
from unittest.mock import patch

SAMPLE_EXERCISE = {
    "stage": 0,
    "chapter": 0,
    "chapter_name": "The Promise",
    "trainer": "seth",
    "type": "instruction",
    "instruction": "Here is what we actually say about the change.",
    "questions": [
        {
            "question": "A prospect asks what you do. What do you lead with?",
            "options": {"A": "Freedom to operate", "B": "Cost savings", "C": "Our services"},
            "correct": "A",
            "why": "Freedom names the transformation, not the transaction.",
            "redirect": "Ask what change they're really describing.",
        },
        {
            "question": "Which opening frames the conversation correctly?",
            "options": {"A": "We reduce costs", "B": "We remove lock-in", "C": "We do cloud"},
            "correct": "B",
            "why": "Lock-in is the pain; removing it is the change.",
            "redirect": "Describe the before/after, not the service.",
        },
        {
            "question": "What does the customer become after working with you?",
            "options": {"A": "A managed services customer", "B": "Independent", "C": "Cost-efficient"},
            "correct": "B",
            "why": "Independence is the transformation we offer.",
            "redirect": "Complete the sentence: after working with us, they can...",
        },
    ],
    "source_tables": ["change"],
}

SAMPLE_ENROLLMENT = {
    "id": "enroll-1",
    "email": "pim@example.com",
    "name": "Pim",
    "role": "hunter",
    "currentStage": 0,
    "currentChapter": 0,
    "active": True,
    "streak": 0,
    "lastActivity": None,
}

SAMPLE_CONVERSATION = {
    "id": "conv-1",
    "state": "waiting_response",
    "current_question": 0,
    "exercise_id": "ex-1",
    "stage": 0,
    "exercise": {"content": SAMPLE_EXERCISE},
}


class TestEnroll:
    """Test enrollment operations."""

    @patch("training.operations.create_user")
    @patch("training.operations.get_user_by_email")
    def test_enroll_creates_record(self, mock_get, mock_enroll):
        from training.operations import enroll
        mock_get.return_value = None
        mock_enroll.return_value = {"id": "enroll-1", "email": "pim@example.com", "name": "Pim", "role": "hunter"}

        result = enroll("pim@example.com", "Pim", "hunter")

        mock_enroll.assert_called_once_with("pim@example.com", "Pim", "hunter")
        assert "hunter" in result.lower() or "next" in result.lower()

    @patch("training.operations.get_user_by_email")
    def test_enroll_handles_already_enrolled(self, mock_get):
        from training.operations import enroll
        mock_get.return_value = SAMPLE_ENROLLMENT

        result = enroll("pim@example.com", "Pim", "hunter")

        assert "already enrolled" in result
        assert "hunter" in result

    @patch("training.operations.create_user")
    @patch("training.operations.get_user_by_email")
    def test_enroll_success_message_format(self, mock_get, mock_enroll):
        from training.operations import enroll
        mock_get.return_value = None
        mock_enroll.return_value = {"id": "enroll-1", "email": "pim@example.com", "name": "Pim", "role": "gatherer"}

        result = enroll("pim@example.com", "Pim", "gatherer")

        assert "Enrolled as gatherer" in result
        assert "DM" in result or "direct message" in result.lower()

    @patch("training.operations.get_user_by_email")
    def test_enroll_already_enrolled_message_format(self, mock_get):
        from training.operations import enroll
        enrollment = {**SAMPLE_ENROLLMENT, "role": "hunter"}
        mock_get.return_value = enrollment

        result = enroll("pim@example.com", "Pim", "hunter")

        assert result == "You're already enrolled as hunter."


class TestDeliverChapter:
    """Test chapter delivery operations."""

    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    def test_deliver_chapter_creates_exercise_and_conversation(
        self, mock_cancel, mock_gen, mock_insert, mock_create
    ):
        from training.operations import deliver_chapter
        mock_gen.return_value = SAMPLE_EXERCISE
        mock_insert.return_value = "ex-1"
        mock_create.return_value = "conv-1"

        result = deliver_chapter(SAMPLE_ENROLLMENT)

        mock_cancel.assert_called_once_with(SAMPLE_ENROLLMENT["id"])
        mock_gen.assert_called_once_with(role="hunter", stage=0, chapter=0)
        mock_insert.assert_called_once()
        mock_create.assert_called_once()
        assert result is not None

    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    def test_deliver_chapter_formats_instruction(
        self, mock_cancel, mock_gen, mock_insert, mock_create
    ):
        from training.operations import deliver_chapter
        mock_gen.return_value = SAMPLE_EXERCISE
        mock_insert.return_value = "ex-1"
        mock_create.return_value = "conv-1"

        result = deliver_chapter(SAMPLE_ENROLLMENT)

        assert "*Chapter 1 of 3: The Promise*" in result
        assert "Here is what we actually say" in result
        assert "*go*" in result

    @patch("training.operations.cancel_stale_conversations")
    def test_deliver_chapter_handles_stage_complete(self, mock_cancel):
        from training.operations import deliver_chapter
        enrollment = {**SAMPLE_ENROLLMENT, "currentChapter": 3}  # stage 0 has 3 chapters

        result = deliver_chapter(enrollment)

        assert result is None

    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    def test_deliver_chapter_passes_user_id_to_insert(
        self, mock_cancel, mock_gen, mock_insert, mock_create
    ):
        from training.operations import deliver_chapter
        mock_gen.return_value = SAMPLE_EXERCISE
        mock_insert.return_value = "ex-1"
        mock_create.return_value = "conv-1"

        deliver_chapter(SAMPLE_ENROLLMENT)

        insert_call = mock_insert.call_args
        assert insert_call[1]["user_id"] == "enroll-1"

    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    def test_deliver_chapter_creates_conversation_with_minus_one(
        self, mock_cancel, mock_gen, mock_insert, mock_create
    ):
        from training.operations import deliver_chapter
        mock_gen.return_value = SAMPLE_EXERCISE
        mock_insert.return_value = "ex-1"
        mock_create.return_value = "conv-1"

        deliver_chapter(SAMPLE_ENROLLMENT)

        create_call = mock_create.call_args
        assert create_call[1]["current_question"] == -1


class TestStartExercises:
    """Test 'go' command — transition from instruction to questions."""

    @patch("training.operations.update_conversation")
    def test_start_exercises_transitions_to_first_question(self, mock_update):
        from training.operations import start_exercises
        conv = {**SAMPLE_CONVERSATION, "current_question": -1}

        result = start_exercises(conv)

        mock_update.assert_called_once_with(conv["id"], current_question=0)
        assert result is not None

    @patch("training.operations.update_conversation")
    def test_start_exercises_formats_first_question(self, mock_update):
        from training.operations import start_exercises
        conv = {**SAMPLE_CONVERSATION, "current_question": -1}

        result = start_exercises(conv)

        assert "*Question 1 of 3*" in result
        assert "A prospect asks" in result
        assert "A) Freedom to operate" in result

    def test_start_exercises_returns_none_when_no_conversation(self):
        from training.operations import start_exercises

        result = start_exercises(None)

        assert result is None


class TestScoreAnswer:
    """Test answer scoring and progression."""

    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_correct_answer_advances_question(self, mock_score, mock_insert, mock_update):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "✓ Right.\n\nFreedom names the transformation."}
        mock_insert.return_value = "resp-1"
        conv = {**SAMPLE_CONVERSATION, "current_question": 0}

        result = score_answer(conv, SAMPLE_ENROLLMENT, "A")

        mock_update.assert_called_once_with(conv["id"], current_question=1)
        assert "✓ Right" in result
        assert "*Question 2 of 3*" in result

    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_wrong_answer_also_advances(self, mock_score, mock_insert, mock_update):
        from training.operations import score_answer
        mock_score.return_value = {"correct": False, "feedback": "Not quite — it's A."}
        mock_insert.return_value = "resp-1"
        conv = {**SAMPLE_CONVERSATION, "current_question": 0}

        result = score_answer(conv, SAMPLE_ENROLLMENT, "B")

        mock_update.assert_called_once_with(conv["id"], current_question=1)
        assert "Not quite" in result

    @patch("training.operations.record_chapter_score")
    @patch("training.operations.advance_user")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_last_answer_completes_chapter(self, mock_score, mock_insert, mock_update, mock_advance, mock_record):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "✓ Right.\n\nIndependence is the goal."}
        mock_insert.return_value = "resp-1"
        mock_record.return_value = 1.0
        conv = {**SAMPLE_CONVERSATION, "current_question": 2}  # last question (0-indexed)

        result = score_answer(conv, SAMPLE_ENROLLMENT, "B")

        mock_update.assert_called_once_with(conv["id"], state="complete")
        mock_advance.assert_called_once()
        assert "Chapter complete" in result
        assert "*next*" in result

    @patch("training.operations.record_chapter_score")
    @patch("training.operations.advance_user")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_last_answer_advances_enrollment(self, mock_score, mock_insert, mock_update, mock_advance, mock_record):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "✓ Right."}
        mock_insert.return_value = "resp-1"
        mock_record.return_value = 1.0
        conv = {**SAMPLE_CONVERSATION, "current_question": 2}

        score_answer(conv, SAMPLE_ENROLLMENT, "A")

        mock_advance.assert_called_once_with(
            SAMPLE_ENROLLMENT["id"],
            current_chapter=1,
        )

    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_score_answer_persists_response(self, mock_score, mock_insert, mock_update):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "✓ Right."}
        mock_insert.return_value = "resp-1"
        conv = {**SAMPLE_CONVERSATION, "current_question": 0}

        score_answer(conv, SAMPLE_ENROLLMENT, "A")

        mock_insert.assert_called_once()
        insert_call = mock_insert.call_args
        assert insert_call[1]["response"] == "A"
        assert insert_call[1]["question_index"] == 0

    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_continuation_message_format(self, mock_score, mock_insert, mock_update):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "✓ Right.\n\nGood."}
        mock_insert.return_value = "resp-1"
        conv = {**SAMPLE_CONVERSATION, "current_question": 0}

        result = score_answer(conv, SAMPLE_ENROLLMENT, "A")

        # feedback \n\n next_question
        assert "✓ Right" in result
        assert "*Question 2 of 3*" in result

    @patch("training.operations.record_chapter_score")
    @patch("training.operations.advance_user")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_completion_message_format(self, mock_score, mock_insert, mock_update, mock_advance, mock_record):
        from training.operations import score_answer
        feedback = "✓ Right.\n\nIndependence is the goal."
        mock_score.return_value = {"correct": True, "feedback": feedback}
        mock_insert.return_value = "resp-1"
        mock_record.return_value = 1.0
        conv = {**SAMPLE_CONVERSATION, "current_question": 2}

        result = score_answer(conv, SAMPLE_ENROLLMENT, "B")

        expected = f"{feedback}\n\n*Chapter complete.* I'll have the next chapter ready tomorrow. Or reply *next* if you want to continue."
        assert result == expected


class TestFullChapterFlow:
    """End-to-end: enroll → next → go → A → B → C → chapter complete."""

    @patch("training.operations.record_chapter_score")
    @patch("training.operations.advance_user")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    @patch("training.operations.create_user")
    @patch("training.operations.get_user_by_email")
    def test_full_chapter_flow(self, mock_get_enroll, mock_enroll,
                                mock_cancel, mock_gen, mock_insert_ex,
                                mock_create_conv, mock_score,
                                mock_insert_resp, mock_update_conv,
                                mock_advance, mock_record):
        from training.operations import deliver_chapter, enroll, score_answer, start_exercises

        # 1. Enroll
        mock_get_enroll.return_value = None
        mock_enroll.return_value = {"id": "enr-1", "email": "jurg@example.com", "name": "Jurg", "role": "hunter"}
        result = enroll("jurg@example.com", "Jurg", "hunter")
        assert "hunter" in result.lower()
        mock_enroll.assert_called_once()

        # 2. Deliver chapter
        mock_gen.return_value = {
            "stage": 0, "chapter": 0, "chapter_name": "The Promise",
            "trainer": "seth", "type": "instruction",
            "instruction": "The promise is the transformation.",
            "questions": [
                {"question": "Q1?", "options": {"A": "opt a", "B": "opt b", "C": "opt c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q2?", "options": {"A": "opt a", "B": "opt b", "C": "opt c"}, "correct": "B", "why": "w", "redirect": "r"},
                {"question": "Q3?", "options": {"A": "opt a", "B": "opt b", "C": "opt c"}, "correct": "C", "why": "w", "redirect": "r"},
            ],
            "source_tables": ["change"],
        }
        mock_insert_ex.return_value = "ex-1"
        mock_create_conv.return_value = "conv-1"
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 0}
        result = deliver_chapter(enrollment)
        assert "Promise" in result
        assert "go" in result.lower()

        # 3. Start exercises (go)
        active = {
            "id": "conv-1", "current_question": -1, "exercise_id": "ex-1", "stage": 0,
            "exercise": {"content": mock_gen.return_value},
        }
        result = start_exercises(active)
        assert "Question 1" in result
        mock_update_conv.assert_called_with("conv-1", current_question=0)

        # 4-6. Answer all 3 questions
        mock_score.return_value = {"correct": True, "feedback": "Correct!"}
        mock_record.return_value = 1.0
        for q in range(3):
            active["current_question"] = q
            result = score_answer(active, enrollment, ["A", "B", "C"][q])
            assert "Correct!" in result

        # After last answer: chapter complete, enrollment advanced
        mock_advance.assert_called_once_with("enr-1", current_chapter=1)
        assert "complete" in result.lower()


class TestRefresher:
    """Refresher delivery for decayed chapters."""

    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    @patch("training.operations.get_decayed_chapters", return_value=[])
    def test_deliver_refresher(self, mock_decayed, mock_cancel, mock_gen, mock_insert, mock_conv):
        from training.operations import deliver_refresher
        mock_gen.return_value = {
            "stage": 0, "chapter": 0, "chapter_name": "The Promise",
            "trainer": "seth", "type": "practice",
            "questions": [
                {"question": "Q1?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q2?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "B", "why": "w", "redirect": "r"},
                {"question": "Q3?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "C", "why": "w", "redirect": "r"},
            ],
            "source_tables": ["change"],
        }
        mock_insert.return_value = "ex-1"
        mock_conv.return_value = "conv-1"
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 1, "current_chapter": 0}
        result = deliver_refresher(enrollment, stage=0, chapter=0)
        mock_gen.assert_called_once_with(role="hunter", stage=0, chapter=0, practice=True)
        mock_conv.assert_called_once()
        # Verify current_question=0 (skips instruction)
        conv_call = mock_conv.call_args
        assert conv_call[1]["current_question"] == 0 or conv_call.kwargs.get("current_question") == 0
        assert "The Promise" in result
        assert "Question 1" in result

    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    @patch("training.operations.get_decayed_chapters", return_value=[])
    def test_refresher_uses_practice_mode(self, mock_decayed, mock_cancel, mock_gen, mock_insert, mock_conv):
        from training.operations import deliver_refresher
        mock_gen.return_value = {
            "stage": 0, "chapter": 0, "chapter_name": "The Promise",
            "trainer": "seth", "type": "practice",
            "questions": [{"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"}] * 3,
            "source_tables": ["change"],
        }
        mock_insert.return_value = "ex-1"
        mock_conv.return_value = "conv-1"
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 0}
        deliver_refresher(enrollment, stage=0, chapter=0)
        assert mock_gen.call_args[1]["practice"] is True


class TestFormatQuestion:
    """Test question formatting helper."""

    def test_format_question_basic(self):
        from training.operations import _format_question
        question = SAMPLE_EXERCISE["questions"][0]

        result = _format_question(question, num=1, total=3)

        assert "*Question 1 of 3*" in result
        assert question["question"] in result
        assert "A) Freedom to operate" in result
        assert "B) Cost savings" in result
        assert "C) Our services" in result

    def test_format_question_uses_slack_bold(self):
        from training.operations import _format_question
        question = SAMPLE_EXERCISE["questions"][0]

        result = _format_question(question, num=2, total=3)

        assert "*Question 2 of 3*" in result
        assert "**" not in result  # Slack uses *, not **

    def test_format_question_second_question(self):
        from training.operations import _format_question
        question = SAMPLE_EXERCISE["questions"][1]

        result = _format_question(question, num=2, total=3)

        assert "*Question 2 of 3*" in result
        assert "Which opening frames" in result


class TestDailyCheck:
    """CronJob daily check per enrollment."""

    @patch("training.operations.deliver_chapter")
    @patch("training.operations.get_active_conversation")
    def test_skips_active_conversation(self, mock_active, mock_deliver):
        from training.operations import daily_check
        mock_active.return_value = {"id": "conv-1"}
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 1}
        result = daily_check(enrollment)
        assert result is None
        mock_deliver.assert_not_called()

    @patch("training.operations.deliver_chapter")
    @patch("training.operations.get_active_conversation")
    def test_delivers_next_chapter_when_idle(self, mock_active, mock_deliver):
        from training.operations import daily_check
        mock_active.return_value = None
        mock_deliver.return_value = "Chapter delivered"
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 1}
        result = daily_check(enrollment)
        assert result == "Chapter delivered"

    @patch("training.operations.deliver_refresher")
    @patch("training.operations.get_decayed_chapters")
    @patch("training.operations.deliver_chapter")
    @patch("training.operations.get_active_conversation")
    def test_delivers_refresher_when_stage_complete(self, mock_active, mock_deliver, mock_decayed, mock_refresher):
        from training.operations import daily_check
        mock_active.return_value = None
        mock_deliver.return_value = None  # stage complete
        mock_decayed.return_value = [{"role": "hunter", "stage": 0, "chapter": 0, "current_proficiency": 0.3}]
        mock_refresher.return_value = "Refresher: The Promise"
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 2, "current_chapter": 0}
        result = daily_check(enrollment)
        assert "Refresher" in result
        mock_refresher.assert_called_once_with(enrollment, 0, 0)

    @patch("training.operations.get_decayed_chapters")
    @patch("training.operations.deliver_chapter")
    @patch("training.operations.get_active_conversation")
    def test_returns_none_when_nothing_to_do(self, mock_active, mock_deliver, mock_decayed):
        from training.operations import daily_check
        mock_active.return_value = None
        mock_deliver.return_value = None
        mock_decayed.return_value = []
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 2, "current_chapter": 0}
        result = daily_check(enrollment)
        assert result is None


class TestProficiencyDecay:
    """Proficiency decay using half-life formula."""

    def test_no_decay_at_zero_days(self):
        from training.operations import calculate_proficiency
        assert calculate_proficiency(initial_score=0.9, days_elapsed=0, half_life=14) == 0.9

    def test_half_at_half_life(self):
        from training.operations import calculate_proficiency
        result = calculate_proficiency(initial_score=1.0, days_elapsed=14, half_life=14)
        assert abs(result - 0.5) < 0.01

    def test_quarter_at_double_half_life(self):
        from training.operations import calculate_proficiency
        result = calculate_proficiency(initial_score=1.0, days_elapsed=28, half_life=14)
        assert abs(result - 0.25) < 0.01

    def test_foundation_half_life_30_days(self):
        from training.operations import get_half_life
        assert get_half_life(stage=0) == 30

    def test_conversation_half_life_14_days(self):
        from training.operations import get_half_life
        assert get_half_life(stage=1) == 14
        assert get_half_life(stage=2) == 14

    def test_applied_half_life_21_days(self):
        from training.operations import get_half_life
        assert get_half_life(stage=3) == 21
        assert get_half_life(stage=4) == 21

    def test_below_threshold_after_decay(self):
        from training.operations import PROFICIENCY_THRESHOLD, calculate_proficiency
        result = calculate_proficiency(initial_score=0.7, days_elapsed=30, half_life=14)
        assert result < PROFICIENCY_THRESHOLD


class TestStageAdvancement:
    """Stage and program completion."""

    @patch("training.operations.record_chapter_score")
    @patch("training.operations.advance_user")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_last_chapter_in_stage_advances_stage(self, mock_score, mock_insert_resp,
                                                    mock_update_conv, mock_advance,
                                                    mock_record):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "Great!"}
        mock_record.return_value = 1.0
        # Hunter Stage 0 has 3 chapters (0,1,2). This is last Q of chapter 2.
        active = {
            "id": "conv-1", "current_question": 2, "exercise_id": "ex-1", "stage": 0,
            "exercise": {"content": {"questions": [
                {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
            ]}},
        }
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 2}
        result = score_answer(active, enrollment, "A")
        # Chapter 3 >= total (3) → advance stage
        mock_advance.assert_called_once_with("enr-1", current_chapter=0, current_stage=1)
        assert "Stage complete" in result
        assert "The Offering" in result  # Hunter Stage 1 name

    @patch("training.operations.record_chapter_score")
    @patch("training.operations.advance_user")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_last_stage_completes_program(self, mock_score, mock_insert_resp,
                                           mock_update_conv, mock_advance,
                                           mock_record):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "Perfect!"}
        mock_record.return_value = 1.0
        # Hunter Stage 4 (last) has 3 chapters. Last Q of last chapter.
        active = {
            "id": "conv-1", "current_question": 2, "exercise_id": "ex-1", "stage": 4,
            "exercise": {"content": {"questions": [
                {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
            ]}},
        }
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 4, "current_chapter": 2}
        result = score_answer(active, enrollment, "A")
        assert "Congratulations" in result
        assert "training program" in result.lower()

    @patch("training.operations.record_chapter_score")
    @patch("training.operations.advance_user")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_mid_stage_advances_chapter(self, mock_score, mock_insert_resp,
                                         mock_update_conv, mock_advance,
                                         mock_record):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "Good!"}
        mock_record.return_value = 0.67
        active = {
            "id": "conv-1", "current_question": 2, "exercise_id": "ex-1", "stage": 0,
            "exercise": {"content": {"questions": [
                {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
            ]}},
        }
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 0}
        result = score_answer(active, enrollment, "A")
        mock_advance.assert_called_once_with("enr-1", current_chapter=1)
        assert "Chapter complete" in result


class TestProficiencyDB:
    """Proficiency storage and retrieval."""

    @patch("training.operations.upsert_training_progress")
    @patch("training.operations.get_responses_for_exercise")
    def test_record_chapter_score(self, mock_responses, mock_upsert):
        from training.operations import record_chapter_score
        mock_responses.return_value = [
            {"correct": True, "question_index": 0},
            {"correct": True, "question_index": 1},
            {"correct": False, "question_index": 2},
        ]
        score = record_chapter_score("enr-1", "hunter", 0, 0, "ex-1")
        assert abs(score - 0.67) < 0.01
        mock_upsert.assert_called_once()
        call_kwargs = mock_upsert.call_args[1]
        assert call_kwargs["area"] == "hunter:0:0"

    @patch("training.operations.upsert_training_progress")
    @patch("training.operations.get_responses_for_exercise")
    def test_record_chapter_score_no_responses(self, mock_responses, mock_upsert):
        from training.operations import record_chapter_score
        mock_responses.return_value = []
        score = record_chapter_score("enr-1", "hunter", 0, 0, "ex-1")
        assert score == 0.0
        mock_upsert.assert_not_called()

    @patch("training.operations.get_training_progress")
    def test_get_decayed_chapters(self, mock_progress):
        from datetime import datetime, timedelta

        from training.operations import get_decayed_chapters
        old_date = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        mock_progress.return_value = [
            {"area": "hunter:0:0", "score": 0.8, "updated_at": old_date, "last_refresher": None, "exercises_completed": 1},
            {"area": "hunter:0:1", "score": 0.9, "updated_at": old_date, "last_refresher": None, "exercises_completed": 1},
        ]
        decayed = get_decayed_chapters("enr-1")
        assert len(decayed) >= 1
        assert decayed[0]["current_proficiency"] < 0.6

    @patch("training.operations.get_training_progress")
    def test_no_decay_for_recent_chapters(self, mock_progress):
        from datetime import datetime

        from training.operations import get_decayed_chapters
        recent = datetime.now(UTC).isoformat()
        mock_progress.return_value = [
            {"area": "hunter:0:0", "score": 0.8, "updated_at": recent, "last_refresher": None, "exercises_completed": 1},
        ]
        decayed = get_decayed_chapters("enr-1")
        assert len(decayed) == 0

    @patch("training.operations.get_training_progress")
    def test_decayed_sorted_by_proficiency(self, mock_progress):
        from datetime import datetime, timedelta

        from training.operations import get_decayed_chapters
        old_date = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        mock_progress.return_value = [
            {"area": "hunter:0:1", "score": 0.9, "updated_at": old_date, "last_refresher": None, "exercises_completed": 1},
            {"area": "hunter:0:0", "score": 0.7, "updated_at": old_date, "last_refresher": None, "exercises_completed": 1},
        ]
        decayed = get_decayed_chapters("enr-1")
        assert len(decayed) == 2
        assert decayed[0]["current_proficiency"] <= decayed[1]["current_proficiency"]

    @patch("training.operations.get_training_progress")
    def test_decayed_area_parts_unpacked(self, mock_progress):
        from datetime import datetime, timedelta

        from training.operations import get_decayed_chapters
        old_date = (datetime.now(UTC) - timedelta(days=45)).isoformat()
        mock_progress.return_value = [
            {"area": "hunter:1:2", "score": 0.8, "updated_at": old_date, "last_refresher": None, "exercises_completed": 1},
        ]
        decayed = get_decayed_chapters("enr-1")
        assert len(decayed) == 1
        assert decayed[0]["role"] == "hunter"
        assert decayed[0]["stage"] == 1
        assert decayed[0]["chapter"] == 2


class TestCitizenProgression:
    """Citizen inspiration flow — stage-aware, 5 interactions per stage."""

    @patch("training.operations.advance_user")
    def test_advance_citizen_increments_chapter(self, mock_advance):
        from training.operations import advance_citizen
        enrollment = {"id": "e1", "current_stage": 0, "current_chapter": 2}
        advance_citizen(enrollment)
        mock_advance.assert_called_once_with("e1", current_chapter=3)

    @patch("training.operations.advance_user")
    def test_advance_citizen_stage_at_5(self, mock_advance):
        from training.operations import advance_citizen
        enrollment = {"id": "e1", "current_stage": 0, "current_chapter": 4}
        advance_citizen(enrollment)
        mock_advance.assert_called_once_with("e1", current_chapter=0, current_stage=1)

    @patch("training.operations.advance_user")
    def test_advance_citizen_last_stage_stays(self, mock_advance):
        from training.operations import advance_citizen
        enrollment = {"id": "e1", "current_stage": 3, "current_chapter": 4}
        advance_citizen(enrollment)
        # Past last stage — stays at chapter 5
        mock_advance.assert_called_once_with("e1", current_chapter=5)

    @patch("training.operations.advance_citizen")
    @patch("bot.detect.generate_citizen_inspiration")
    def test_citizen_daily_check(self, mock_gen, mock_advance):
        from training.operations import citizen_daily_check
        mock_gen.return_value = {"content": "Here's something...", "advance": True}
        enrollment = {"id": "e1", "slack_user_id": "U123", "current_stage": 0, "current_chapter": 0}
        result = citizen_daily_check(enrollment)
        assert result == "Here's something..."
        mock_advance.assert_called_once()

    @patch("training.operations.advance_citizen")
    @patch("bot.detect.generate_citizen_inspiration")
    def test_citizen_daily_check_no_advance_when_false(self, mock_gen, mock_advance):
        from training.operations import citizen_daily_check
        mock_gen.return_value = {"content": "Done!", "advance": False}
        enrollment = {"id": "e1", "slack_user_id": "U123", "current_stage": 4, "current_chapter": 0}
        result = citizen_daily_check(enrollment)
        assert result == "Done!"
        mock_advance.assert_not_called()
