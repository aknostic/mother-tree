# Training Operations — Core State Machine (Plan A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the training operations layer that makes all training commands work end-to-end: enroll → next → go → answer → advance → complete.

**Architecture:** New `training/operations.py` module owns all training state transitions and database writes. Dispatcher stripped of side effects (only pattern matching). Pipeline delegates training logic to operations.py. Each operations function takes inputs, performs DB writes, and returns a formatted response string.

**Tech Stack:** Python 3.12, existing hasura.py DB functions, existing character modules, existing training engine

**Spec:** `docs/superpowers/specs/2026-03-29-training-operations-design.md`

**Scope:** This is Plan A — core state machine only. Plan B (proficiency decay, refreshers, CronJob integration) follows.

---

## File Structure

```
jobs/training/operations.py       — NEW: state machine, all training logic
jobs/tests/test_operations.py     — NEW: comprehensive test coverage
jobs/bot/pipeline.py              — modify: delegate to operations.py
jobs/bot/characters/dispatcher.py — modify: strip side effects, simplify annotations
jobs/training/engine.py           — modify: character-voiced exercise generation
```

---

### Task 1: Create operations.py — enroll and deliver_chapter

**Files:**
- Create: `jobs/training/operations.py`
- Create: `jobs/tests/test_operations.py`

The two most important operations: enrolling a user and delivering a chapter. These unblock the entire training flow.

- [ ] **Step 1: Write tests**

```python
# jobs/tests/test_operations.py
"""Tests for training operations — the state machine."""
from unittest.mock import patch, MagicMock


class TestEnroll:
    """Enrollment creates a DB record and returns a welcome message."""

    @patch("training.operations.enroll_user")
    @patch("training.operations.get_enrollment")
    def test_enroll_creates_record(self, mock_get, mock_enroll):
        from training.operations import enroll
        mock_get.return_value = None  # not enrolled yet
        mock_enroll.return_value = "enrollment-id-1"
        result = enroll(slack_user_id="U123", name="Jurg", role="hunter")
        mock_enroll.assert_called_once_with("U123", "Jurg", "hunter")
        assert "enrolled" in result.lower() or "hunter" in result.lower()

    @patch("training.operations.get_enrollment")
    def test_enroll_already_enrolled(self, mock_get):
        from training.operations import enroll
        mock_get.return_value = {"id": "existing", "role": "hunter"}
        result = enroll(slack_user_id="U123", name="Jurg", role="hunter")
        assert "already" in result.lower()


class TestDeliverChapter:
    """Chapter delivery generates exercise and creates conversation."""

    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    def test_deliver_chapter_creates_exercise_and_conversation(
        self, mock_cancel, mock_gen, mock_insert, mock_conv
    ):
        from training.operations import deliver_chapter
        mock_gen.return_value = {
            "stage": 0, "chapter": 0, "chapter_name": "The Promise",
            "trainer": "seth", "type": "instruction",
            "instruction": "Here is the instruction.",
            "questions": [{"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"}] * 3,
            "source_tables": ["change"],
        }
        mock_insert.return_value = "exercise-id-1"
        mock_conv.return_value = "conversation-id-1"

        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 0}
        result = deliver_chapter(enrollment)

        mock_cancel.assert_called_once_with("enr-1")
        mock_gen.assert_called_once_with(role="hunter", stage=0, chapter=0)
        mock_insert.assert_called_once()
        mock_conv.assert_called_once()
        assert "Promise" in result or "instruction" in result.lower()

    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    def test_deliver_chapter_stage_complete(self, mock_cancel, mock_gen):
        from training.operations import deliver_chapter
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 3}
        # Hunter Stage 0 has 3 chapters (0, 1, 2) — chapter 3 is out of range
        result = deliver_chapter(enrollment)
        mock_gen.assert_not_called()
        assert "complete" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_operations.py -v`

- [ ] **Step 3: Create operations.py with enroll and deliver_chapter**

```python
# jobs/training/operations.py
"""Training operations — state machine for all training interactions.

Every training command flows through here. This module owns all state
transitions and database writes. The Dispatcher routes, the pipeline
calls, operations.py acts.
"""
import logging

from mothertree.hasura import (
    cancel_stale_conversations,
    create_conversation,
    enroll_user,
    get_enrollment,
    insert_exercise,
)
from training.curriculum import get_chapter, get_total_chapters
from training.engine import generate_exercise

log = logging.getLogger(__name__)


def enroll(slack_user_id: str, name: str, role: str) -> str:
    """Enroll a user. Returns a response string for Slack."""
    existing = get_enrollment(slack_user_id)
    if existing:
        return f"You're already enrolled as {existing['role']}."

    enroll_user(slack_user_id, name, role)
    return f"Enrolled as {role}. Reply *next* to start your first chapter."


def deliver_chapter(enrollment: dict) -> str:
    """Generate and deliver a chapter instruction. Returns formatted response."""
    role = enrollment.get("role", "hunter")
    stage = enrollment.get("current_stage", 0)
    chapter = enrollment.get("current_chapter", 0)
    enrollment_id = enrollment["id"]

    # Check if stage is complete
    total = get_total_chapters(role, stage)
    if chapter >= total:
        return f"Stage {stage} complete. No more chapters available in this stage yet."

    # Cancel any stale conversations
    cancel_stale_conversations(enrollment_id)

    # Generate exercise
    try:
        exercise = generate_exercise(role=role, stage=stage, chapter=chapter)
    except Exception as e:
        log.exception("Exercise generation failed")
        return f"Sorry, I couldn't generate the exercise. Error: {e}"

    # Persist exercise and create conversation
    exercise_id = insert_exercise(
        user_id=enrollment_id, stage=stage, chapter=chapter,
        exercise_type=exercise["type"],
        content=exercise, source_tables=exercise["source_tables"],
    )
    create_conversation(
        user_id=enrollment_id, exercise_id=exercise_id,
        stage=stage, state="waiting_response",
        current_question=-1,
    )

    # Format response
    display_ch = chapter + 1
    return (
        f"*Chapter {display_ch} of {total}: {exercise['chapter_name']}*\n\n"
        f"{exercise['instruction']}\n\n"
        f"Ready for the questions? Reply *go* when you've read this."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add jobs/training/operations.py jobs/tests/test_operations.py
git commit -m "Add training operations: enroll and deliver_chapter"
```

---

### Task 2: Add start_exercises and score_answer to operations.py

**Files:**
- Modify: `jobs/training/operations.py`
- Modify: `jobs/tests/test_operations.py`

- [ ] **Step 1: Write tests**

Add to `jobs/tests/test_operations.py`:

```python
class TestStartExercises:
    """'go' transitions from instruction to first question."""

    @patch("training.operations.update_conversation")
    def test_start_exercises_returns_first_question(self, mock_update):
        from training.operations import start_exercises
        active_conversation = {
            "id": "conv-1",
            "state": "waiting_response",
            "current_question": -1,
            "exercise": {"content": {
                "questions": [
                    {"question": "What is the change?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                    {"question": "Q2?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "B", "why": "w", "redirect": "r"},
                    {"question": "Q3?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "C", "why": "w", "redirect": "r"},
                ],
            }},
        }
        result = start_exercises(active_conversation)
        mock_update.assert_called_once_with("conv-1", state="waiting_response", current_question=0)
        assert "Question 1 of 3" in result
        assert "What is the change?" in result

    @patch("training.operations.update_conversation")
    def test_start_exercises_no_active_conversation(self, mock_update):
        from training.operations import start_exercises
        result = start_exercises(None)
        mock_update.assert_not_called()
        assert "no active" in result.lower() or "next" in result.lower()


class TestScoreAnswer:
    """Answer scoring, question advancement, and chapter completion."""

    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_score_correct_answer_advances(self, mock_score, mock_insert, mock_update):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "Right!"}
        active = {
            "id": "conv-1", "current_question": 0, "exercise_id": "ex-1",
            "exercise": {"content": {"questions": [
                {"question": "Q1?", "options": {"A": "a"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q2?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q3?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
            ]}},
            "stage": 0,
        }
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 0}
        result = score_answer(active, enrollment, "A")
        mock_insert.assert_called_once()
        mock_update.assert_called_once_with("conv-1", current_question=1)
        assert "Right!" in result
        assert "Question 2" in result

    @patch("training.operations.advance_enrollment")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_last_answer_completes_chapter(self, mock_score, mock_insert, mock_update, mock_advance):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "Great!"}
        active = {
            "id": "conv-1", "current_question": 2, "exercise_id": "ex-1",
            "exercise": {"content": {"questions": [
                {"question": "Q1?", "options": {"A": "a"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q2?", "options": {"A": "a"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q3?", "options": {"A": "a"}, "correct": "A", "why": "w", "redirect": "r"},
            ]}},
            "stage": 0,
        }
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 0}
        result = score_answer(active, enrollment, "A")
        mock_update.assert_called_once_with("conv-1", state="complete", current_question=3)
        mock_advance.assert_called_once_with("enr-1", current_chapter=1)
        assert "complete" in result.lower() or "done" in result.lower()
```

- [ ] **Step 2: Implement start_exercises and score_answer**

Add to `jobs/training/operations.py`:

```python
from mothertree.hasura import (
    advance_enrollment,
    insert_response,
    update_conversation,
)
from training.score import score_response


def start_exercises(active_conversation: dict | None) -> str:
    """'go' command — transition to first question."""
    if not active_conversation:
        return "No active chapter. Reply *next* to start one."

    if active_conversation.get("current_question", -1) >= 0:
        return "You're already in the exercises. Answer the current question."

    questions = active_conversation["exercise"]["content"]["questions"]
    conv_id = active_conversation["id"]

    update_conversation(conv_id, state="waiting_response", current_question=0)

    return _format_question(questions[0], 1, len(questions))


def score_answer(active_conversation: dict, enrollment: dict, answer: str) -> str:
    """Score an answer, advance or complete."""
    conv_id = active_conversation["id"]
    exercise = active_conversation["exercise"]["content"]
    questions = exercise["questions"]
    current_q = active_conversation["current_question"]
    stage = active_conversation.get("stage", 0)

    if current_q < 0 or current_q >= len(questions):
        return "No active question."

    question = questions[current_q]
    result = score_response(stage=stage, question=question, response=answer)

    # Record the response
    insert_response(
        exercise_id=active_conversation.get("exercise_id"),
        user_id=enrollment["id"],
        response=answer,
        question_index=current_q,
        correct=result["correct"],
        feedback=result["feedback"],
    )

    feedback = result["feedback"]
    next_q = current_q + 1

    if next_q >= len(questions):
        # Chapter complete
        update_conversation(conv_id, state="complete", current_question=next_q)

        # Advance enrollment to next chapter
        next_chapter = enrollment["current_chapter"] + 1
        advance_enrollment(enrollment["id"], current_chapter=next_chapter)

        return (
            f"{feedback}\n\n"
            f"*Chapter complete.* "
            f"I'll have the next chapter ready tomorrow. Or reply *next* if you want to continue."
        )

    # More questions — advance and show next
    update_conversation(conv_id, current_question=next_q)

    next_question = _format_question(questions[next_q], next_q + 1, len(questions))
    return f"{feedback}\n\n{next_question}"


def _format_question(question: dict, num: int, total: int) -> str:
    """Format a single MC question for Slack."""
    opts = "\n".join(f"{letter}) {text}" for letter, text in question["options"].items())
    return f"*Question {num} of {total}*\n\n{question['question']}\n\n{opts}"
```

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add jobs/training/operations.py jobs/tests/test_operations.py
git commit -m "Add start_exercises and score_answer to operations"
```

---

### Task 3: Wire pipeline to operations.py

**Files:**
- Modify: `jobs/bot/pipeline.py`

Replace `_training_response` to delegate to operations.py based on annotation type.

- [ ] **Step 1: Rewrite _training_response in pipeline.py**

```python
def _training_response(text: str, history: list, user_name: str,
                        participant_count: int, annotation: dict,
                        exercise_pending: dict,
                        enrollment: dict = None,
                        active_conversation: dict = None) -> str:
    """Training mode — delegate to operations.py for state transitions."""
    from training import operations

    if not annotation:
        # Freeform message during training — route to trainer
        return _trainer_character_response(text, history, user_name,
                                            participant_count, annotation)

    ann_type = annotation.get("type", "")

    if ann_type == "enroll":
        role = annotation.get("role")
        if not role:
            return "Which role? Reply: *enroll hunter*, *enroll gatherer*, *enroll farmer*, or *enroll citizen*."
        return operations.enroll(
            slack_user_id=annotation.get("slack_user_id", ""),
            name=user_name,
            role=role,
        )

    if ann_type == "training_next":
        if not enrollment:
            return "You're not enrolled yet. Reply *enroll hunter* to get started."
        return operations.deliver_chapter(enrollment)

    if ann_type == "exercise_go":
        return operations.start_exercises(active_conversation)

    if ann_type == "answer":
        if not active_conversation or not enrollment:
            return "No active exercise. Reply *next* to start a chapter."
        return operations.score_answer(
            active_conversation, enrollment, annotation.get("answer", "")
        )

    if ann_type == "practice":
        return "Practice mode coming soon."

    # Fallback: freeform training conversation
    return _trainer_character_response(text, history, user_name,
                                        participant_count, annotation)


def _trainer_character_response(text, history, user_name, participant_count, annotation):
    """Route freeform training messages to the trainer character."""
    trainer = "seth"
    if annotation and annotation.get("trainer"):
        trainer = annotation["trainer"]
    if trainer == "lawrence":
        from bot.characters.lawrence import respond
    elif trainer == "mother_tree":
        from bot.characters.mother_tree import respond
    else:
        from bot.characters.seth import respond
    return respond(question=text, history=history,
                   user_name=user_name, participant_count=participant_count,
                   annotation=annotation)
```

Also update `_process_message` to pass enrollment and active_conversation to `_training_response`.

- [ ] **Step 2: Run full test suite**

- [ ] **Step 3: Commit**

```bash
git add jobs/bot/pipeline.py
git commit -m "Wire pipeline training delegation to operations.py"
```

---

### Task 4: Simplify Dispatcher — strip side effects

**Files:**
- Modify: `jobs/bot/characters/dispatcher.py`

Remove `deliver_next()`, `score_exercise_answer()`, `generate_citizen_inspiration()`. Replace with simple annotation production. The pipeline + operations.py handle everything.

- [ ] **Step 1: Simplify training command annotations**

The Dispatcher should produce these annotations (no function calls, no DB writes):

```python
# "enroll hunter"
{"type": "enroll", "role": "hunter", "slack_user_id": slack_user_id}

# "next" (enrolled)
{"type": "training_next"}

# "go" (has active conversation)
{"type": "exercise_go"}

# "A"/"B"/"C" (has active exercise)
{"type": "answer", "answer": "A"}

# "practice worldview"
{"type": "practice", "topic": "worldview"}
```

The Dispatcher reads enrollment state and active conversation (for routing decisions) but writes nothing.

- [ ] **Step 2: Remove deliver_next, score_exercise_answer, generate_citizen_inspiration**

These functions move to operations.py. The Dispatcher becomes pure pattern matching.

- [ ] **Step 3: Update tests**

Tests that mock dispatcher side-effect functions need updating.

- [ ] **Step 4: Run full test suite**

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/characters/dispatcher.py jobs/tests/test_characters.py
git commit -m "Strip Dispatcher of side effects — pure pattern matching"
```

---

### Task 5: End-to-end test and cleanup

**Files:**
- Modify: `jobs/tests/test_operations.py`
- Remove dead code from `jobs/training/deliver.py` (keep format functions if needed)

- [ ] **Step 1: Add end-to-end test**

```python
class TestFullChapterFlow:
    """End-to-end: enroll → next → go → A → B → C → chapter complete."""

    @patch("training.operations.advance_enrollment")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    @patch("training.operations.enroll_user")
    @patch("training.operations.get_enrollment")
    def test_full_chapter_flow(self, mock_get_enroll, mock_enroll,
                                mock_cancel, mock_gen, mock_insert_ex,
                                mock_create_conv, mock_score,
                                mock_insert_resp, mock_update_conv,
                                mock_advance):
        from training.operations import enroll, deliver_chapter, start_exercises, score_answer

        # 1. Enroll
        mock_get_enroll.return_value = None
        mock_enroll.return_value = "enr-1"
        result = enroll("U123", "Jurg", "hunter")
        assert "hunter" in result.lower()

        # 2. Deliver chapter
        mock_gen.return_value = {
            "stage": 0, "chapter": 0, "chapter_name": "The Promise",
            "trainer": "seth", "type": "instruction",
            "instruction": "The promise is the transformation.",
            "questions": [
                {"question": "Q1?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"},
                {"question": "Q2?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "B", "why": "w", "redirect": "r"},
                {"question": "Q3?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "C", "why": "w", "redirect": "r"},
            ],
            "source_tables": ["change"],
        }
        mock_insert_ex.return_value = "ex-1"
        mock_create_conv.return_value = "conv-1"
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 0}
        result = deliver_chapter(enrollment)
        assert "Promise" in result

        # 3. Start exercises
        active = {
            "id": "conv-1", "current_question": -1, "exercise_id": "ex-1", "stage": 0,
            "exercise": {"content": mock_gen.return_value},
        }
        result = start_exercises(active)
        assert "Question 1" in result

        # 4-6. Answer all 3 questions
        mock_score.return_value = {"correct": True, "feedback": "Correct!"}
        for q in range(3):
            active["current_question"] = q
            result = score_answer(active, enrollment, "A")
            assert "Correct!" in result

        # Verify chapter completed
        mock_advance.assert_called_once_with("enr-1", current_chapter=1)
```

- [ ] **Step 2: Run full test suite**

Run: `cd jobs && python -m pytest tests/ -v`

- [ ] **Step 3: Clean up deliver.py**

Remove delivery logic from deliver.py that's now in operations.py. Keep `format_question_dm` and `format_instruction_dm` if still referenced by CronJob path (Plan B).

- [ ] **Step 4: Run ruff**

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "End-to-end training flow: enroll → next → go → answer → complete"
```
