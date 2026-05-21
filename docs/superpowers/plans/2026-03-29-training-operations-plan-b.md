# Training Operations Plan B — Proficiency Decay, Refreshers, CronJob

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add proficiency tracking with time-based decay, refresher delivery, streak tracking, and unify the CronJob through operations.py.

**Architecture:** Proficiency per chapter stored in `training_progress`. A pure `calculate_decay()` function computes current proficiency using half-life formula. The daily CronJob calls operations.py for all delivery: next chapters, refreshers, nudges, and streak updates. `deliver.py` is replaced by operations.py for the CronJob path.

**Tech Stack:** Python 3.12, existing operations.py, existing hasura.py

**Spec:** `docs/superpowers/specs/2026-03-29-training-operations-design.md` (Proficiency and Decay + CronJob Integration sections)

**Depends on:** Plan A (core state machine) — completed.

---

## File Structure

```
jobs/training/operations.py      — modify: add proficiency, refresher, daily_check, stage advancement
jobs/training/deliver.py         — rewrite: CronJob entry point calls operations.py
jobs/mothertree/hasura.py        — modify: add proficiency CRUD, fix training_progress for all roles
jobs/deploy/database/schema.sql  — modify: document training_progress schema update
jobs/tests/test_operations.py    — modify: add proficiency, refresher, CronJob tests
```

---

### Task 1: Proficiency calculation — pure function

**Files:**
- Modify: `jobs/training/operations.py`
- Modify: `jobs/tests/test_operations.py`

The decay formula is pure math — no DB, no mocking needed.

- [ ] **Step 1: Write tests for decay calculation**

```python
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

    def test_below_threshold(self):
        from training.operations import calculate_proficiency, PROFICIENCY_THRESHOLD
        result = calculate_proficiency(initial_score=0.7, days_elapsed=30, half_life=14)
        assert result < PROFICIENCY_THRESHOLD
```

- [ ] **Step 2: Implement decay functions**

Add to `jobs/training/operations.py`:

```python
PROFICIENCY_THRESHOLD = 0.6

STAGE_HALF_LIVES = {
    0: 30,   # foundation knowledge
    1: 14,   # conversation/offering skills
    2: 14,   # conversation/offering skills
    3: 21,   # applied skills
    4: 21,   # applied skills
}


def calculate_proficiency(initial_score: float, days_elapsed: float, half_life: int) -> float:
    """Calculate current proficiency using half-life decay."""
    if days_elapsed <= 0:
        return initial_score
    return initial_score * (0.5 ** (days_elapsed / half_life))


def get_half_life(stage: int) -> int:
    """Get the half-life in days for a given stage."""
    return STAGE_HALF_LIVES.get(stage, 21)
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "Add proficiency decay calculation — pure function with half-life formula"
```

---

### Task 2: Proficiency DB operations

**Files:**
- Modify: `jobs/mothertree/hasura.py`
- Modify: `jobs/tests/test_operations.py`

The `training_progress` table uses `hunter_id` (TEXT) and `area` (TEXT). We'll use `hunter_id` as the enrollment ID (it's a UUID stored as text — works) and `area` as a chapter key like `"hunter:0:0"` (role:stage:chapter).

- [ ] **Step 1: Write tests for proficiency CRUD**

```python
class TestProficiencyDB:
    """Proficiency storage and retrieval."""

    @patch("training.operations.upsert_training_progress")
    def test_record_chapter_score(self, mock_upsert):
        from training.operations import record_chapter_score
        record_chapter_score(
            enrollment_id="enr-1", role="hunter", stage=0, chapter=0, score=0.8
        )
        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args[1]
        assert call_args["area"] == "hunter:0:0"
        assert call_args["score"] == 0.8

    @patch("training.operations.get_training_progress")
    def test_get_decayed_chapters(self, mock_progress):
        from training.operations import get_decayed_chapters
        from datetime import datetime, timezone, timedelta
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        mock_progress.return_value = [
            {"area": "hunter:0:0", "score": 0.8, "updated_at": old_date},
            {"area": "hunter:0:1", "score": 0.9, "updated_at": old_date},
        ]
        decayed = get_decayed_chapters("enr-1")
        # After 30 days with half_life=30, score 0.8 → ~0.4 (below 0.6)
        assert len(decayed) >= 1
```

- [ ] **Step 2: Add hasura functions**

Add to `jobs/mothertree/hasura.py`:

```python
def upsert_training_progress(hunter_id: str, area: str, score: float, **kwargs) -> None:
    """Insert or update a training progress record."""
    obj = {"hunter_id": hunter_id, "area": area, "score": score, **kwargs}
    graphql("""
    mutation($obj: training_progress_insert_input!) {
        insert_training_progress_one(
            object: $obj,
            on_conflict: {
                constraint: training_progress_hunter_id_area_key,
                update_columns: [score, last_refresher, exercises_completed, updated_at]
            }
        ) { id }
    }
    """, {"obj": {k: v for k, v in obj.items() if v is not None}})


def get_training_progress(hunter_id: str) -> list[dict]:
    """Get all training progress records for an enrollment."""
    result = graphql("""
    query($hid: String!) {
        training_progress(where: {hunter_id: {_eq: $hid}}) {
            area score last_refresher exercises_completed updated_at
        }
    }
    """, {"hid": hunter_id})
    return result["training_progress"]
```

- [ ] **Step 3: Add operations functions**

Add to `jobs/training/operations.py`:

```python
from datetime import datetime, timezone
from mothertree.hasura import get_training_progress, upsert_training_progress


def record_chapter_score(enrollment_id: str, role: str, stage: int,
                          chapter: int, score: float) -> None:
    """Record proficiency score for a completed chapter."""
    area = f"{role}:{stage}:{chapter}"
    upsert_training_progress(
        hunter_id=enrollment_id, area=area, score=score,
        exercises_completed=1,
    )


def get_decayed_chapters(enrollment_id: str) -> list[dict]:
    """Find chapters where proficiency has decayed below threshold."""
    progress = get_training_progress(enrollment_id)
    now = datetime.now(timezone.utc)
    decayed = []
    for p in progress:
        parts = p["area"].split(":")
        if len(parts) != 3:
            continue
        stage = int(parts[1])
        half_life = get_half_life(stage)
        updated = datetime.fromisoformat(p["updated_at"])
        days = (now - updated).total_seconds() / 86400
        current = calculate_proficiency(p["score"], days, half_life)
        if current < PROFICIENCY_THRESHOLD:
            decayed.append({
                "area": p["area"],
                "role": parts[0],
                "stage": stage,
                "chapter": int(parts[2]),
                "current_proficiency": round(current, 2),
                "original_score": p["score"],
                "days_since_activity": round(days),
            })
    return sorted(decayed, key=lambda x: x["current_proficiency"])
```

- [ ] **Step 4: Update score_answer to record proficiency**

In `score_answer`, after chapter completion, calculate and record the score:

```python
# After advance_enrollment in score_answer:
correct_count = sum(1 for ... )  # count correct answers
# Simpler: pass the score from the last question result
record_chapter_score(
    enrollment_id=enrollment["id"],
    role=enrollment["role"],
    stage=active_conversation["stage"],
    chapter=enrollment["current_chapter"],
    score=chapter_score,
)
```

Actually, we need to track correct answers across the chapter. Simplest: count from the responses table or track in the conversation. For now, record 1.0 for all-correct, 0.67 for 2/3, 0.33 for 1/3.

- [ ] **Step 5: Run tests, commit**

```bash
git commit -m "Add proficiency tracking: record scores, detect decay"
```

---

### Task 3: Refresher delivery

**Files:**
- Modify: `jobs/training/operations.py`
- Modify: `jobs/tests/test_operations.py`

- [ ] **Step 1: Write tests**

```python
class TestRefresher:
    """Refresher delivery for decayed chapters."""

    @patch("training.operations.create_conversation")
    @patch("training.operations.insert_exercise")
    @patch("training.operations.generate_exercise")
    @patch("training.operations.cancel_stale_conversations")
    def test_deliver_refresher(self, mock_cancel, mock_gen, mock_insert, mock_conv):
        from training.operations import deliver_refresher
        mock_gen.return_value = {
            "stage": 0, "chapter": 0, "chapter_name": "The Promise",
            "trainer": "seth", "type": "practice",
            "questions": [{"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"}] * 3,
            "source_tables": ["change"],
        }
        mock_insert.return_value = "ex-1"
        mock_conv.return_value = "conv-1"
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 1, "current_chapter": 0}
        result = deliver_refresher(enrollment, stage=0, chapter=0)
        mock_gen.assert_called_once_with(role="hunter", stage=0, chapter=0, practice=True)
        assert "refresher" in result.lower() or "Question 1" in result
```

- [ ] **Step 2: Implement deliver_refresher**

```python
def deliver_refresher(enrollment: dict, stage: int, chapter: int) -> str:
    """Deliver a refresher (practice questions) for a specific chapter."""
    role = enrollment["role"]
    cancel_stale_conversations(enrollment["id"])

    exercise = generate_exercise(role=role, stage=stage, chapter=chapter, practice=True)

    exercise_id = insert_exercise(
        user_id=enrollment["id"], stage=stage, chapter=chapter,
        exercise_type="refresher", content=exercise,
        source_tables=exercise["source_tables"],
    )
    create_conversation(
        user_id=enrollment["id"], exercise_id=exercise_id,
        stage=stage, state="waiting_response", current_question=0,
    )

    question = exercise["questions"][0]
    total = len(exercise["questions"])
    header = f"*Refresher: {exercise['chapter_name']}*\nYour proficiency has dropped. Let's sharpen up.\n\n"
    return header + _format_question(question, 1, total)
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "Add refresher delivery for decayed chapters"
```

---

### Task 4: Daily CronJob via operations.py

**Files:**
- Rewrite: `jobs/training/deliver.py`
- Modify: `jobs/tests/test_operations.py`

- [ ] **Step 1: Write tests**

```python
class TestDailyCheck:
    """CronJob daily check per enrollment."""

    @patch("training.operations.deliver_chapter")
    @patch("training.operations.get_active_conversation")
    def test_skips_active_conversation(self, mock_active, mock_deliver):
        from training.operations import daily_check
        mock_active.return_value = {"id": "conv-1"}  # active
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 1}
        daily_check(enrollment)
        mock_deliver.assert_not_called()

    @patch("training.operations.deliver_chapter")
    @patch("training.operations.get_active_conversation")
    def test_delivers_next_chapter_when_idle(self, mock_active, mock_deliver):
        from training.operations import daily_check
        mock_active.return_value = None  # idle
        mock_deliver.return_value = "Chapter delivered"
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 0, "current_chapter": 1, "slack_user_id": "U123"}
        result = daily_check(enrollment)
        mock_deliver.assert_called_once()

    @patch("training.operations.deliver_refresher")
    @patch("training.operations.get_decayed_chapters")
    @patch("training.operations.deliver_chapter")
    @patch("training.operations.get_active_conversation")
    def test_delivers_refresher_when_decayed(self, mock_active, mock_deliver, mock_decayed, mock_refresher):
        from training.operations import daily_check
        mock_active.return_value = None
        mock_deliver.return_value = None  # stage complete
        mock_decayed.return_value = [{"role": "hunter", "stage": 0, "chapter": 0, "current_proficiency": 0.3}]
        mock_refresher.return_value = "Refresher delivered"
        enrollment = {"id": "enr-1", "role": "hunter", "current_stage": 2, "current_chapter": 0, "slack_user_id": "U123"}
        result = daily_check(enrollment)
        mock_refresher.assert_called_once()
```

- [ ] **Step 2: Implement daily_check**

```python
from mothertree.hasura import get_active_conversation, update_streak


def daily_check(enrollment: dict) -> str | None:
    """Daily CronJob check for one enrollment. Returns message to send, or None."""
    enrollment_id = enrollment["id"]

    # Skip if mid-chapter
    active = get_active_conversation(enrollment_id)
    if active:
        return None

    # Try delivering next chapter
    result = deliver_chapter(enrollment)
    if result:
        return result

    # Stage complete — check for decayed chapters
    decayed = get_decayed_chapters(enrollment_id)
    if decayed:
        worst = decayed[0]  # lowest proficiency first
        return deliver_refresher(enrollment, worst["stage"], worst["chapter"])

    # Nothing to do
    return None
```

- [ ] **Step 3: Rewrite deliver.py as CronJob entry point**

```python
# jobs/training/deliver.py
"""Training delivery CronJob — daily check for all enrollments."""
import logging

from slack_sdk import WebClient

from mothertree.config import SLACK_BOT_TOKEN
from mothertree.hasura import get_active_enrollments, update_streak
from training.operations import daily_check

log = logging.getLogger(__name__)


def deliver_training() -> None:
    """Daily CronJob: check all enrollments, deliver chapters or refreshers."""
    slack = WebClient(token=SLACK_BOT_TOKEN)
    enrollments = get_active_enrollments()
    log.info("Daily check: %d active enrollments", len(enrollments))

    for user in enrollments:
        try:
            message = daily_check(user)
            if message:
                slack.chat_postMessage(channel=user["slack_user_id"], text=message)
                log.info("Delivered to %s", user["name"])
                # Update streak
                streak = (user.get("streak") or 0) + 1
                update_streak(user["id"], streak)
            else:
                log.info("Nothing to deliver to %s", user["name"])
        except Exception:
            log.exception("Failed daily check for %s", user["name"])


def main():
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    deliver_training()
```

- [ ] **Step 4: Run full test suite and lint**

- [ ] **Step 5: Commit**

```bash
git commit -m "Daily CronJob via operations.py: chapters, refreshers, streaks"
```

---

### Task 5: Stage advancement logic

**Files:**
- Modify: `jobs/training/operations.py`

Currently `score_answer` always increments `current_chapter`. But when the last chapter of a stage is completed, it should advance to the next stage. And when the last stage is completed, it should acknowledge program completion.

- [ ] **Step 1: Write tests**

```python
class TestStageAdvancement:
    """Stage and program completion."""

    @patch("training.operations.advance_enrollment")
    @patch("training.operations.update_conversation")
    @patch("training.operations.insert_response")
    @patch("training.operations.score_response")
    def test_last_chapter_advances_stage(self, mock_score, mock_insert, mock_update, mock_advance):
        from training.operations import score_answer
        mock_score.return_value = {"correct": True, "feedback": "Great!"}
        # Hunter Stage 0 has 3 chapters (0,1,2). This is last question of chapter 2.
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
        # Chapter 3 is beyond Stage 0's total (3 chapters: 0,1,2)
        # Should advance to Stage 1, Chapter 0
        mock_advance.assert_called_once_with("enr-1", current_chapter=0, current_stage=1)
```

- [ ] **Step 2: Update score_answer for stage advancement**

In `score_answer`, after chapter completion:

```python
if is_last:
    update_conversation(active_conversation["id"], state="complete")

    next_chapter = enrollment["current_chapter"] + 1
    total_chapters = get_total_chapters(enrollment["role"], stage)

    if next_chapter >= total_chapters:
        # Stage complete — advance to next stage
        next_stage = stage + 1
        from training.curriculum import get_stages
        total_stages = len(get_stages(enrollment["role"]))
        if next_stage >= total_stages:
            # Program complete
            advance_enrollment(enrollment["id"], current_chapter=next_chapter)
            return f"{feedback}\n\n*Congratulations!* You've completed the full training program. Refreshers will keep your skills sharp."
        else:
            advance_enrollment(enrollment["id"], current_chapter=0, current_stage=next_stage)
            from training.curriculum import get_stage_name
            next_stage_name = get_stage_name(enrollment["role"], next_stage)
            return f"{feedback}\n\n*Stage complete!* Next up: *{next_stage_name}*. Reply *next* when you're ready."
    else:
        advance_enrollment(enrollment["id"], current_chapter=next_chapter)
        return f"{feedback}\n\n*Chapter complete.* I'll have the next chapter ready tomorrow. Or reply *next* if you want to continue."
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "Add stage advancement and program completion logic"
```

---

### Task 6: Smoke test

- [ ] **Step 1: Reset enrollment and test full flow**
- [ ] **Step 2: Verify stage advancement works**
- [ ] **Step 3: Verify CronJob delivery via `cli.py train deliver`**

---

## Review Fixes (address before implementing)

### Score calculation (Task 2, Step 4)

In `score_answer`, track correct count by counting responses for the exercise:

```python
# After marking chapter complete, calculate score:
from mothertree.hasura import get_responses_for_exercise
responses = get_responses_for_exercise(active_conversation["exercise_id"])
correct_count = sum(1 for r in responses if r.get("correct"))
chapter_score = correct_count / len(questions) if questions else 0.0
record_chapter_score(enrollment["id"], enrollment["role"], stage, enrollment["current_chapter"], chapter_score)
```

Add `get_responses_for_exercise` to hasura.py.

### Refresher conversation state

Refreshers skip instruction — go straight to questions. Set `current_question=0`:

```python
create_conversation(
    user_id=enrollment["id"], exercise_id=exercise_id,
    stage=stage, state="waiting_response", current_question=0,
)
```

### 7-day nudge and streak reset (Task 4)

Add to `deliver_training()` in deliver.py:

```python
from datetime import datetime, timezone, timedelta

for user in enrollments:
    # Streak: reset if no activity yesterday
    last = user.get("last_activity")
    if last:
        last_dt = datetime.fromisoformat(last)
        if (now - last_dt).days > 1:
            update_streak(user["id"], 0)

    # Nudge if idle 7+ days
    if last and (now - last_dt).days >= 7:
        slack.chat_postMessage(
            channel=user["slack_user_id"],
            text="How's it going? Reply *next* to continue training.",
        )
        continue

    # Normal daily check
    message = daily_check(user)
    ...
```

### exercises_completed increment

Use Hasura `_inc` instead of `_set` for exercises_completed. Or track it separately.

### Constraint name verification

Before testing Task 2: verify `training_progress_hunter_id_area_key` exists in Hasura metadata.

### Test patches for Task 5

Add `@patch("training.operations.get_total_chapters")` and `@patch("training.operations.get_stages")` to stage advancement tests.
