# Training Engine Phase B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first end-to-end training loop: Stage 0 instruction with exercise generation, Slack DM delivery, deterministic scoring, and chapter progression.

**Architecture:** CronJob triggers delivery job → queries enrollment → generates exercises via Mistral Small 3.2 on Scaleway → sends DM via Slack bot token → bot handles replies with deterministic MC scoring → updates progression in PostgreSQL via Hasura GraphQL.

**Tech Stack:** Python 3, PostgreSQL 17 (Hasura GraphQL), Scaleway AI (Mistral Small 3.2), Slack Bolt (Socket Mode), Kubernetes CronJob, pytest.

**Spec:** `docs/superpowers/specs/2026-03-21-training-engine-phase-b-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `jobs/training/engine.py` | Exercise generator with stage dispatch. Chapter-to-table mapping, generation prompts, structured JSONB output. |
| `jobs/training/score.py` | Scoring with stage dispatch. Stage 0: deterministic MC (compare answer to correct). Feedback formatting. |
| `jobs/training/deliver.py` | Delivery logic: query enrollment, generate exercises, send DMs via Slack. Called by CronJob and by bot for "next"/"practice". |
| `jobs/tests/test_training.py` | Tests for engine, score, deliver, and DM handler. |
| `deploy/cronjobs/training-deliver.yaml` | Weekday 8 AM CET CronJob. |

### Modified files

| File | Changes |
|------|---------|
| `deploy/database/schema.sql` | Add `exercises`, `responses`, `conversations` tables. Add `enrollment` table (exists in prod, missing from schema file). Add `streak`, `last_activity` columns to enrollment. |
| `jobs/mothertree/hasura.py` | Add training queries: insert/get exercises, responses, conversations. Update enrollment (stage, chapter, streak). |
| `jobs/bot/bot.py` | Replace `handle_dm()` stub with full response handler. Add training DM flow (go, answers, next, practice). |
| `jobs/bot/training_dm.py` | Extracted DM handler logic: command parsing, topic resolution, streak calculation, formatting. |
| `jobs/cli.py` | Add subcommand routing for `train deliver` alongside existing `train seth`/`train onboarding`. |

---

## Task 1: Database schema

Add the three new tables and formalize the enrollment table in `schema.sql`.

**Files:**
- Modify: `deploy/database/schema.sql`

- [ ] **Step 1: Read the current schema**

Read `deploy/database/schema.sql` to find the exact insertion point. New tables go after the `training_progress` table (around line 248), before the indexes section (around line 250).

- [ ] **Step 2: Add enrollment table to schema file**

The enrollment table already exists in production but is missing from the schema file. Add it for completeness, including the new `streak` and `last_activity` columns. Insert before the `training_progress` table.

```sql
-- Training enrollment
CREATE TABLE enrollment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slack_user_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('hunter', 'gatherer', 'farmer', 'citizen')),
    current_stage INTEGER DEFAULT 0,
    current_chapter INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_activity TIMESTAMPTZ,
    enrolled_at TIMESTAMPTZ DEFAULT now(),
    active BOOLEAN DEFAULT true
);
```

- [ ] **Step 3: Add exercises, responses, conversations tables**

Insert after the enrollment table:

```sql
-- Training exercises
CREATE TABLE exercises (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES enrollment(id),
    stage INTEGER NOT NULL,
    chapter INTEGER,
    exercise_type TEXT NOT NULL CHECK (exercise_type IN
        ('instruction', 'multiple_choice', 'practice', 'open', 'scenario', 'prep')),
    content JSONB NOT NULL,
    source_tables TEXT[],
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Training responses (one row per question)
CREATE TABLE responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exercise_id UUID REFERENCES exercises(id),
    user_id UUID REFERENCES enrollment(id),
    response TEXT NOT NULL,
    question_index INTEGER NOT NULL,
    correct BOOLEAN,
    scores JSONB,
    confidence REAL,
    feedback TEXT,
    responded_at TIMESTAMPTZ DEFAULT now()
);

-- Training conversation state (tracks DM flow)
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES enrollment(id),
    exercise_id UUID REFERENCES exercises(id),
    stage INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active', 'waiting_response', 'complete')),
    current_question INTEGER DEFAULT -1,
    messages JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

- [ ] **Step 4: Add indexes for the DM handler lookup**

Add after the existing indexes section:

```sql
-- Training indexes
CREATE INDEX idx_exercises_user_id ON exercises(user_id);
CREATE INDEX idx_responses_exercise_id ON responses(exercise_id);
CREATE INDEX idx_responses_user_id ON responses(user_id);
CREATE INDEX idx_conversations_user_state ON conversations(user_id, state);
```

- [ ] **Step 5: Add updated_at trigger for conversations**

Add to the existing triggers section:

```sql
CREATE TRIGGER set_conversations_updated_at BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

- [ ] **Step 6: Commit**

```bash
git add deploy/database/schema.sql
git commit -m "Add training tables: exercises, responses, conversations, enrollment"
```

**Note for deployment:** The enrollment table already exists in production. Run `ALTER TABLE enrollment ADD COLUMN streak INTEGER DEFAULT 0; ALTER TABLE enrollment ADD COLUMN last_activity TIMESTAMPTZ;` to add the new columns. The other three tables are new — run the CREATE TABLE statements via Hasura console or migration. Then track all four tables in Hasura and configure permissions.

---

## Task 2: Hasura training queries

Add GraphQL queries and mutations for the training tables to the shared Hasura module.

**Files:**
- Modify: `jobs/mothertree/hasura.py`
- Test: `jobs/tests/test_training.py`

- [ ] **Step 1: Write tests for the new Hasura functions**

Create `jobs/tests/test_training.py`. These tests validate the query/mutation strings and return value handling without hitting a real database. Mock the `graphql()` function.

```python
"""Tests for training engine components."""
import json
from unittest.mock import patch, MagicMock
import pytest


# --- Hasura query tests ---

class TestTrainingHasura:
    """Test training-related Hasura queries build correct GraphQL and handle responses."""

    @patch("mothertree.hasura.graphql")
    def test_insert_exercise(self, mock_gql):
        from mothertree.hasura import insert_exercise
        mock_gql.return_value = {"insert_exercises_one": {"id": "ex-123"}}
        content = {"stage": 0, "chapter": 0, "type": "instruction", "questions": []}
        result = insert_exercise(user_id="u-1", stage=0, chapter=0,
                                 exercise_type="instruction", content=content,
                                 source_tables=["change"])
        assert result == "ex-123"
        call_args = mock_gql.call_args
        assert "insert_exercises_one" in call_args[0][0]

    @patch("mothertree.hasura.graphql")
    def test_insert_response(self, mock_gql):
        from mothertree.hasura import insert_response
        mock_gql.return_value = {"insert_responses_one": {"id": "r-1"}}
        result = insert_response(exercise_id="ex-1", user_id="u-1",
                                 response="A", question_index=0,
                                 correct=True, feedback="Good")
        assert result == "r-1"

    @patch("mothertree.hasura.graphql")
    def test_create_conversation(self, mock_gql):
        from mothertree.hasura import create_conversation
        mock_gql.return_value = {"insert_conversations_one": {"id": "c-1"}}
        result = create_conversation(user_id="u-1", exercise_id="ex-1",
                                     stage=0, state="waiting_response")
        assert result == "c-1"

    @patch("mothertree.hasura.graphql")
    def test_get_active_conversation(self, mock_gql):
        from mothertree.hasura import get_active_conversation
        mock_gql.return_value = {"conversations": [{"id": "c-1", "state": "waiting_response"}]}
        result = get_active_conversation(user_id="u-1")
        assert result["id"] == "c-1"

    @patch("mothertree.hasura.graphql")
    def test_get_active_conversation_none(self, mock_gql):
        from mothertree.hasura import get_active_conversation
        mock_gql.return_value = {"conversations": []}
        result = get_active_conversation(user_id="u-1")
        assert result is None

    @patch("mothertree.hasura.graphql")
    def test_update_conversation(self, mock_gql):
        from mothertree.hasura import update_conversation
        mock_gql.return_value = {"update_conversations_by_pk": {"id": "c-1"}}
        update_conversation(conversation_id="c-1", state="complete", current_question=3)
        call_args = mock_gql.call_args
        assert "update_conversations_by_pk" in call_args[0][0]

    @patch("mothertree.hasura.graphql")
    def test_advance_enrollment(self, mock_gql):
        from mothertree.hasura import advance_enrollment
        mock_gql.return_value = {"update_enrollment_by_pk": {"id": "u-1"}}
        advance_enrollment(enrollment_id="u-1", current_chapter=1)
        call_args = mock_gql.call_args
        assert "update_enrollment_by_pk" in call_args[0][0]

    @patch("mothertree.hasura.graphql")
    def test_update_streak(self, mock_gql):
        from mothertree.hasura import update_streak
        mock_gql.return_value = {"update_enrollment_by_pk": {"id": "u-1"}}
        update_streak(enrollment_id="u-1", streak=5)
        call_args = mock_gql.call_args
        assert "update_enrollment_by_pk" in call_args[0][0]

    @patch("mothertree.hasura.graphql")
    def test_get_active_enrollments(self, mock_gql):
        from mothertree.hasura import get_active_enrollments
        mock_gql.return_value = {"enrollment": [
            {"id": "u-1", "slack_user_id": "U123", "current_stage": 0, "current_chapter": 0}
        ]}
        result = get_active_enrollments()
        assert len(result) == 1
        assert result[0]["slack_user_id"] == "U123"

    @patch("mothertree.hasura.graphql")
    def test_cancel_stale_conversations(self, mock_gql):
        from mothertree.hasura import cancel_stale_conversations
        mock_gql.return_value = {"update_conversations": {"affected_rows": 2}}
        result = cancel_stale_conversations(user_id="u-1")
        assert result == 2

    @patch("mothertree.hasura.graphql")
    def test_get_enrollment_includes_streak(self, mock_gql):
        from mothertree.hasura import get_enrollment
        mock_gql.return_value = {"enrollment": [{
            "id": "u-1", "slack_user_id": "U123", "name": "Pim",
            "role": "hunter", "current_stage": 0, "current_chapter": 2,
            "active": True, "streak": 5, "last_activity": "2026-03-20T09:00:00Z",
        }]}
        result = get_enrollment("U123")
        assert result["streak"] == 5
        assert result["last_activity"] is not None

    @patch("mothertree.hasura.graphql")
    def test_fetch_foundation_for_chapter(self, mock_gql):
        from mothertree.hasura import fetch_foundation_for_chapter
        mock_gql.return_value = {
            "change": [{"statement": "We offer freedom", "context": "cloud"}]
        }
        result = fetch_foundation_for_chapter(chapter=0)
        assert "change" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestTrainingHasura -v`
Expected: ImportError — functions don't exist yet.

- [ ] **Step 3: Implement the Hasura training queries**

Add to `jobs/mothertree/hasura.py` after the existing enrollment functions (after line 264). Follow the existing pattern: GraphQL string → `graphql()` call → extract result.

First, update the existing `get_enrollment` function to include `streak` and `last_activity` in its GraphQL query fields. Add `streak last_activity` to the query's selection set.

Then add the new functions:

```python
# --- Training ---

def fetch_foundation_for_chapter(chapter: int) -> dict:
    """Fetch foundation data relevant to a specific training chapter."""
    chapter_queries = {
        0: "change(limit: 15, order_by: {confidence: desc_nulls_last}) { statement context }",
        1: """worldview(limit: 15, order_by: {confidence: desc_nulls_last}) { belief pain readiness_signal }
             personas(limit: 10) { name role profile }""",
        2: "personas(limit: 10) { name role profile communication decision_criteria }",
        3: "competitors(limit: 15) { type positioning when_mentioned response }",
        4: "change(limit: 15, where: {context: {_ilike: \"%service%\"}}) { statement context }",
    }
    query_body = chapter_queries.get(chapter, chapter_queries[0])
    result = graphql(f"query {{ {query_body} }}")
    return result


def insert_exercise(user_id: str, stage: int, chapter: int,
                    exercise_type: str, content: dict, source_tables: list) -> str:
    """Insert an exercise and return its ID."""
    result = graphql("""
        mutation($obj: exercises_insert_input!) {
            insert_exercises_one(object: $obj) { id }
        }
    """, {"obj": {
        "user_id": user_id, "stage": stage, "chapter": chapter,
        "exercise_type": exercise_type, "content": content,
        "source_tables": source_tables,
    }})
    return result["insert_exercises_one"]["id"]


def insert_response(exercise_id: str, user_id: str, response: str,
                    question_index: int, correct: bool, feedback: str) -> str:
    """Insert a training response and return its ID."""
    result = graphql("""
        mutation($obj: responses_insert_input!) {
            insert_responses_one(object: $obj) { id }
        }
    """, {"obj": {
        "exercise_id": exercise_id, "user_id": user_id,
        "response": response, "question_index": question_index,
        "correct": correct, "feedback": feedback,
    }})
    return result["insert_responses_one"]["id"]


def create_conversation(user_id: str, exercise_id: str,
                        stage: int, state: str,
                        current_question: int = -1) -> str:
    """Create a conversation record and return its ID.

    current_question: -1 for instruction exercises (waiting for 'go'),
                      0 for practice exercises (first question immediately).
    """
    result = graphql("""
        mutation($obj: conversations_insert_input!) {
            insert_conversations_one(object: $obj) { id }
        }
    """, {"obj": {
        "user_id": user_id, "exercise_id": exercise_id,
        "stage": stage, "state": state,
        "current_question": current_question,
    }})
    return result["insert_conversations_one"]["id"]


def get_active_conversation(user_id: str) -> dict | None:
    """Get the active (waiting_response) conversation for a user, or None."""
    result = graphql("""
        query($uid: uuid!) {
            conversations(
                where: {user_id: {_eq: $uid}, state: {_eq: "waiting_response"}},
                order_by: {created_at: desc},
                limit: 1
            ) {
                id state current_question exercise_id stage
                exercise { content }
            }
        }
    """, {"uid": user_id})
    convs = result["conversations"]
    return convs[0] if convs else None


def update_conversation(conversation_id: str, **kwargs) -> None:
    """Update conversation fields (state, current_question, messages)."""
    sets = ", ".join(f"{k}: ${k}" for k in kwargs)
    var_defs = ", ".join(f"${k}: {_gql_type(k, v)}" for k, v in kwargs.items())
    graphql(f"""
        mutation($id: uuid!, {var_defs}) {{
            update_conversations_by_pk(
                pk_columns: {{id: $id}},
                _set: {{{sets}}}
            ) {{ id }}
        }}
    """, {"id": conversation_id, **kwargs})


def _gql_type(key: str, value) -> str:
    """Infer GraphQL type from Python value for simple cases."""
    if isinstance(value, int):
        return "Int!"
    if isinstance(value, str):
        return "String!"
    if isinstance(value, (dict, list)):
        return "jsonb!"
    return "String!"


def cancel_stale_conversations(user_id: str) -> int:
    """Cancel all non-complete conversations for a user. Returns count."""
    result = graphql("""
        mutation($uid: uuid!) {
            update_conversations(
                where: {user_id: {_eq: $uid}, state: {_neq: "complete"}},
                _set: {state: "complete"}
            ) { affected_rows }
        }
    """, {"uid": user_id})
    return result["update_conversations"]["affected_rows"]


def advance_enrollment(enrollment_id: str, current_chapter: int = None,
                       current_stage: int = None) -> None:
    """Update enrollment progression (chapter and/or stage)."""
    sets = {}
    if current_chapter is not None:
        sets["current_chapter"] = current_chapter
    if current_stage is not None:
        sets["current_stage"] = current_stage
    set_clause = ", ".join(f"{k}: ${k}" for k in sets)
    var_defs = ", ".join(f"${k}: Int!" for k in sets)
    graphql(f"""
        mutation($id: uuid!, {var_defs}) {{
            update_enrollment_by_pk(
                pk_columns: {{id: $id}},
                _set: {{{set_clause}}}
            ) {{ id }}
        }}
    """, {"id": enrollment_id, **sets})


def update_streak(enrollment_id: str, streak: int) -> None:
    """Update streak count and last_activity timestamp."""
    graphql("""
        mutation($id: uuid!, $streak: Int!) {
            update_enrollment_by_pk(
                pk_columns: {id: $id},
                _set: {streak: $streak, last_activity: "now()"}
            ) { id }
        }
    """, {"id": enrollment_id, "streak": streak})


def get_active_enrollments() -> list:
    """Get all active enrollments for training delivery."""
    result = graphql("""
        query {
            enrollment(where: {active: {_eq: true}}) {
                id slack_user_id name role
                current_stage current_chapter
                streak last_activity
            }
        }
    """)
    return result["enrollment"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestTrainingHasura -v`
Expected: All 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add jobs/mothertree/hasura.py jobs/tests/test_training.py
git commit -m "Add Hasura queries for training: exercises, responses, conversations"
```

---

## Task 3: Exercise generator

Build the exercise generator with stage dispatch and Stage 0 implementation.

**Files:**
- Create: `jobs/training/engine.py`
- Test: `jobs/tests/test_training.py` (add TestExerciseGenerator class)

- [ ] **Step 1: Write tests for the exercise generator**

Add to `jobs/tests/test_training.py`:

```python
class TestExerciseGenerator:
    """Test exercise generation logic."""

    def test_chapter_mapping_covers_all_chapters(self):
        from training.engine import CHAPTERS
        assert len(CHAPTERS) == 5
        assert all(i in CHAPTERS for i in range(5))

    def test_chapter_mapping_has_required_fields(self):
        from training.engine import CHAPTERS
        for ch in CHAPTERS.values():
            assert "name" in ch
            assert "tables" in ch
            assert "purpose" in ch

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
        result = generate_exercise(stage=0, chapter=0)
        assert result["stage"] == 0
        assert result["chapter"] == 0
        assert result["chapter_name"] == "The Promise"
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
        result = generate_exercise(stage=0, chapter=0, practice=True)
        assert result["type"] == "practice"
        assert "instruction" not in result

    def test_generate_exercise_stage_1_not_implemented(self):
        from training.engine import generate_exercise
        with pytest.raises(NotImplementedError):
            generate_exercise(stage=1, chapter=0)

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
            generate_exercise(stage=0, chapter=0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestExerciseGenerator -v`
Expected: ImportError — `training.engine` doesn't exist yet.

- [ ] **Step 3: Implement the exercise generator**

Create `jobs/training/engine.py`:

```python
"""Exercise generator with stage dispatch.

Generates structured training exercises from the central intelligence.
Stage 0 (instruction) is implemented. Stages 1-4 raise NotImplementedError.
"""
import json
import logging

from mothertree.hasura import fetch_foundation_for_chapter
from mothertree.llm import generate, _parse_json

log = logging.getLogger(__name__)

CHAPTERS = {
    0: {
        "name": "The Promise",
        "tables": ["change"],
        "purpose": "What change we offer and why it matters.",
    },
    1: {
        "name": "The Worldview",
        "tables": ["worldview", "personas"],
        "purpose": "What the audience believes, what they feel, what tensions drive them.",
    },
    2: {
        "name": "The Audience",
        "tables": ["personas"],
        "purpose": "The specific people, their roles, how they make decisions.",
    },
    3: {
        "name": "The Difference",
        "tables": ["competitors"],
        "purpose": "How we compare to alternatives, what makes us unique.",
    },
    4: {
        "name": "The Services",
        "tables": ["change"],
        "purpose": "Assess, Build, Operate — what each phase delivers and why.",
    },
}


def generate_exercise(stage: int, chapter: int, practice: bool = False) -> dict:
    """Generate a structured exercise for the given stage and chapter.

    Returns a dict ready to be stored as JSONB in the exercises table.
    Raises NotImplementedError for stages > 0.
    Raises ValueError if the LLM output doesn't validate.
    """
    if stage != 0:
        raise NotImplementedError(f"Stage {stage} not yet implemented")

    ch = CHAPTERS[chapter]
    data = fetch_foundation_for_chapter(chapter)
    source_data = _format_source_data(data)

    if practice:
        prompt = _practice_prompt(ch, source_data)
    else:
        prompt = _instruction_prompt(ch, source_data)

    system = (
        "You generate training material for a consultative sales team. "
        "Always respond with valid JSON only. No markdown fences."
    )
    raw = generate(system, prompt)
    content = _parse_json(raw)
    _validate_exercise(content, practice)

    exercise = {
        "stage": stage,
        "chapter": chapter,
        "chapter_name": ch["name"],
        "type": "practice" if practice else "instruction",
        "questions": content["questions"],
        "source_tables": ch["tables"],
    }
    if not practice:
        exercise["instruction"] = content["instruction"]

    return exercise


def _instruction_prompt(chapter: dict, source_data: str) -> str:
    return f"""Generate training material for the chapter: {chapter["name"]}.

PURPOSE OF THIS CHAPTER:
{chapter["purpose"]}

SOURCE DATA:
{source_data}

GENERATE a JSON object with:
1. "instruction": Teaching text (300-500 words). Teach this as a practitioner would explain it to a new colleague. Direct, concrete, no jargon overload. Use the actual data — real statements, real beliefs, real details. This isn't theory, it's what we actually say.

2. "questions": An array of exactly 3 multiple-choice questions that test understanding, not memorization. Each question presents a realistic situation where the trainee applies what they just learned. Each question object has:
   - "question": A scenario (not "which of the following...")
   - "options": {{"A": "...", "B": "...", "C": "..."}} (one correct, two plausible but wrong)
   - "correct": The letter of the correct answer ("A", "B", or "C")
   - "why": One sentence on why the correct answer is stronger
   - "redirect": A thinking prompt the trainee can carry into real conversations (one sentence)"""


def _practice_prompt(chapter: dict, source_data: str) -> str:
    return f"""Generate practice questions for the chapter: {chapter["name"]}.

PURPOSE OF THIS CHAPTER:
{chapter["purpose"]}

SOURCE DATA:
{source_data}

GENERATE a JSON object with:
"questions": An array of exactly 3 multiple-choice questions. These are practice questions for someone who has already read the instruction material. Each question presents a realistic situation. Each question object has:
   - "question": A scenario (not "which of the following...")
   - "options": {{"A": "...", "B": "...", "C": "..."}} (one correct, two plausible but wrong)
   - "correct": The letter of the correct answer ("A", "B", or "C")
   - "why": One sentence on why the correct answer is stronger
   - "redirect": A thinking prompt the trainee can carry into real conversations (one sentence)"""


def _format_source_data(data: dict) -> str:
    """Format foundation query results into readable text for the prompt."""
    parts = []
    for table, rows in data.items():
        if not rows:
            continue
        parts.append(f"### {table}")
        for row in rows:
            fields = ", ".join(f"{k}: {v}" for k, v in row.items() if v)
            parts.append(f"- {fields}")
    return "\n".join(parts)


def _validate_exercise(content: dict, practice: bool) -> None:
    """Validate the LLM-generated exercise structure."""
    if not practice and "instruction" not in content:
        raise ValueError("Missing instruction text in exercise")
    if "questions" not in content:
        raise ValueError("Missing questions in exercise")
    if len(content["questions"]) != 3:
        raise ValueError(f"Expected 3 questions, got {len(content['questions'])}")
    for i, q in enumerate(content["questions"]):
        for field in ("question", "options", "correct", "why", "redirect"):
            if field not in q:
                raise ValueError(f"Question {i} missing field: {field}")
        if q["correct"] not in ("A", "B", "C"):
            raise ValueError(f"Question {i} correct answer must be A, B, or C")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestExerciseGenerator -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add jobs/training/engine.py jobs/tests/test_training.py
git commit -m "Add exercise generator with stage dispatch and Stage 0 implementation"
```

---

## Task 4: Scoring

Build the scoring module with stage dispatch and Stage 0 deterministic MC scoring.

**Files:**
- Create: `jobs/training/score.py`
- Test: `jobs/tests/test_training.py` (add TestScoring class)

- [ ] **Step 1: Write tests for scoring**

Add to `jobs/tests/test_training.py`:

```python
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
        assert question["why"] in result["feedback"]
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestScoring -v`
Expected: ImportError — `training.score` doesn't exist yet.

- [ ] **Step 3: Implement scoring**

Create `jobs/training/score.py`:

```python
"""Scoring with stage dispatch.

Stage 0: deterministic multiple-choice (compare answer to correct).
Stages 1-4: raise NotImplementedError.
"""


def score_response(stage: int, question: dict, response: str) -> dict:
    """Score a trainee's response to a question.

    Returns dict with:
        correct: bool
        feedback: str (formatted for Slack DM)
    """
    if stage != 0:
        raise NotImplementedError(f"Scoring for stage {stage} not yet implemented")

    return _score_mc(question, response)


def _score_mc(question: dict, response: str) -> dict:
    """Score a multiple-choice response. Deterministic: compare to correct answer."""
    answer = response.strip().upper()
    correct_letter = question["correct"]

    if answer not in ("A", "B", "C"):
        return {
            "correct": False,
            "feedback": f"Please reply with A, B, or C.\n\nThe answer is {correct_letter}.",
        }

    if answer == correct_letter:
        return {
            "correct": True,
            "feedback": f"\u2713 Right.\n\n{question['why']}",
        }

    correct_text = question["options"][correct_letter]
    return {
        "correct": False,
        "feedback": (
            f"Not quite \u2014 it's {correct_letter}.\n\n"
            f"\"{correct_text}\" is stronger because {question['why'].lower()}\n\n"
            f"Try this: {question['redirect']}"
        ),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestScoring -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add jobs/training/score.py jobs/tests/test_training.py
git commit -m "Add scoring with stage dispatch — Stage 0 deterministic MC"
```

---

## Task 5: Delivery logic + CLI + CronJob

Build the delivery module that orchestrates exercise generation and Slack DM sending. Wire up the CLI command and create the CronJob manifest.

**Files:**
- Create: `jobs/training/deliver.py`
- Create: `deploy/cronjobs/training-deliver.yaml`
- Modify: `jobs/cli.py`
- Test: `jobs/tests/test_training.py` (add TestDelivery class)

- [ ] **Step 1: Write tests for delivery**

Add to `jobs/tests/test_training.py`:

```python
class TestDelivery:
    """Test exercise delivery logic."""

    @patch("training.deliver.WebClient")
    @patch("training.deliver.insert_exercise")
    @patch("training.deliver.create_conversation")
    @patch("training.deliver.generate_exercise")
    @patch("training.deliver.get_active_conversation")
    @patch("training.deliver.get_active_enrollments")
    def test_deliver_sends_dm(self, mock_enrollments, mock_conv, mock_gen,
                              mock_create_conv, mock_insert, mock_webclient):
        from training.deliver import deliver_training
        mock_enrollments.return_value = [{
            "id": "u-1", "slack_user_id": "U123",
            "current_stage": 0, "current_chapter": 0,
            "name": "Pim", "streak": 0, "last_activity": None,
        }]
        mock_conv.return_value = None  # no active conversation
        mock_gen.return_value = {
            "stage": 0, "chapter": 0, "chapter_name": "The Promise",
            "type": "instruction", "instruction": "Learn this.",
            "questions": [{"question": "Q", "options": {}, "correct": "A",
                           "why": "w", "redirect": "r"}] * 3,
            "source_tables": ["change"],
        }
        mock_insert.return_value = "ex-1"
        mock_create_conv.return_value = "c-1"
        slack = MagicMock()
        mock_webclient.return_value = slack

        deliver_training()

        slack.chat_postMessage.assert_called_once()
        call_kwargs = slack.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "U123"
        assert "The Promise" in call_kwargs["text"]

    @patch("training.deliver.WebClient")
    @patch("training.deliver.get_active_conversation")
    @patch("training.deliver.get_active_enrollments")
    def test_deliver_skips_user_with_active_conversation(self, mock_enrollments,
                                                         mock_conv, mock_webclient):
        from training.deliver import deliver_training
        mock_enrollments.return_value = [{
            "id": "u-1", "slack_user_id": "U123",
            "current_stage": 0, "current_chapter": 0,
            "name": "Pim", "streak": 0, "last_activity": None,
        }]
        mock_conv.return_value = {"id": "c-1", "state": "waiting_response"}
        slack = MagicMock()
        mock_webclient.return_value = slack

        deliver_training()

        slack.chat_postMessage.assert_not_called()

    def test_format_instruction_dm(self):
        from training.deliver import format_instruction_dm
        exercise = {
            "chapter": 2, "chapter_name": "The Audience",
            "instruction": "Here is what you need to know.",
        }
        text = format_instruction_dm(exercise)
        assert "Chapter 3 of 5" in text  # 1-indexed display
        assert "The Audience" in text
        assert "Here is what you need to know" in text
        assert "go" in text.lower()

    def test_format_question_dm(self):
        from training.deliver import format_question_dm
        question = {
            "question": "What is the change?",
            "options": {"A": "Freedom", "B": "Cost", "C": "Speed"},
        }
        text = format_question_dm(question, question_num=1, total=3)
        assert "Question 1 of 3" in text
        assert "Freedom" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDelivery -v`
Expected: ImportError — `training.deliver` doesn't exist yet.

- [ ] **Step 3: Implement the delivery module**

Create `jobs/training/deliver.py`:

```python
"""Training delivery: generate exercises and send via Slack DM.

Called by CronJob (daily) and by bot (for 'next'/'practice' commands).
"""
import logging

from slack_sdk import WebClient

from mothertree.config import SLACK_BOT_TOKEN
from mothertree.hasura import (
    get_active_enrollments, get_active_conversation,
    insert_exercise, create_conversation,
)
from training.engine import generate_exercise

log = logging.getLogger(__name__)


def deliver_training() -> None:
    """Deliver training exercises to all active enrollments that need one."""
    slack = WebClient(token=SLACK_BOT_TOKEN)
    enrollments = get_active_enrollments()
    log.info("Found %d active enrollments", len(enrollments))

    for user in enrollments:
        try:
            _deliver_to_user(slack, user)
        except Exception:
            log.exception("Failed to deliver training to %s", user["name"])


def _deliver_to_user(slack: WebClient, user: dict) -> None:
    """Deliver one exercise to one user, if they need it."""
    # Skip if user has an active conversation
    active = get_active_conversation(user["id"])
    if active is not None:
        log.info("Skipping %s — active conversation exists", user["name"])
        return

    stage = user["current_stage"]
    chapter = user["current_chapter"]

    # Stage 0 has 5 chapters (0-4). If chapter > 4, they've completed Stage 0.
    if stage == 0 and chapter > 4:
        log.info("Skipping %s — Stage 0 complete, Stage 1 not yet available", user["name"])
        return

    exercise = generate_exercise(stage=stage, chapter=chapter)

    exercise_id = insert_exercise(
        user_id=user["id"], stage=stage, chapter=chapter,
        exercise_type=exercise["type"],
        content=exercise, source_tables=exercise["source_tables"],
    )

    create_conversation(
        user_id=user["id"], exercise_id=exercise_id,
        stage=stage, state="waiting_response",
    )

    text = format_instruction_dm(exercise)
    slack.chat_postMessage(channel=user["slack_user_id"], text=text)
    log.info("Delivered chapter %d to %s", chapter, user["name"])


def deliver_to_user_on_demand(slack: WebClient, user: dict,
                              chapter: int = None, practice: bool = False) -> None:
    """Deliver an exercise on demand ('next' or 'practice' command).

    If chapter is None, uses user's current_chapter.
    """
    if chapter is None:
        chapter = user["current_chapter"]

    stage = user["current_stage"]
    exercise = generate_exercise(stage=stage, chapter=chapter, practice=practice)

    exercise_id = insert_exercise(
        user_id=user["id"], stage=stage, chapter=chapter,
        exercise_type=exercise["type"],
        content=exercise, source_tables=exercise["source_tables"],
    )

    # Practice exercises start at question 0 (no instruction text / "go" step)
    create_conversation(
        user_id=user["id"], exercise_id=exercise_id,
        stage=stage, state="waiting_response",
        current_question=0 if practice else -1,
    )

    if practice:
        text = format_question_dm(
            exercise["questions"][0], question_num=1, total=3
        )
    else:
        text = format_instruction_dm(exercise)

    slack.chat_postMessage(channel=user["slack_user_id"], text=text)


def format_instruction_dm(exercise: dict) -> str:
    """Format the instruction + 'go' prompt for Slack DM."""
    display_num = exercise["chapter"] + 1  # 1-indexed for users
    return (
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"Chapter {display_num} of 5: {exercise['chapter_name']}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"{exercise['instruction']}\n\n"
        f"Ready for the questions? Reply *go* when you've read this."
    )


def format_question_dm(question: dict, question_num: int, total: int) -> str:
    """Format a single MC question for Slack DM."""
    opts = "\n".join(
        f"{letter}) {text}" for letter, text in question["options"].items()
    )
    return (
        f"Question {question_num} of {total}\n\n"
        f"{question['question']}\n\n"
        f"{opts}"
    )


def main():
    """CLI entry point for CronJob."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    deliver_training()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDelivery -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Wire up the CLI**

Modify `jobs/cli.py` to add subcommand routing for `train`. The existing `train` command passes through to `training.generate.main()`. Add `train deliver` as a subcommand.

Find the `train` handler in `cli.py` (around line 65) and replace it:

```python
    elif cmd == "train":
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "deliver":
            from training.deliver import main as deliver_main
            deliver_main()
        else:
            # Existing behavior: pass to generate.py (seth, onboarding)
            sys.argv = ["train"] + args[1:]
            from training.generate import main as gen_main
            gen_main()
```

- [ ] **Step 6: Create the CronJob manifest**

Create `deploy/cronjobs/training-deliver.yaml` following the thread-reminders pattern:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: training-deliver
  namespace: mother-tree
spec:
  schedule: "0 7 * * 1-5"  # 07:00 UTC = 08:00 CET weekdays
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          imagePullSecrets:
            - name: gitlab-registry
          containers:
            - name: training-deliver
              image: registry.gitlab.aknostic.com/aknostic/mother-tree/jobs:latest # {"$imagepolicy": "mother-tree:jobs"}
              args: ["train", "deliver"]
              env:
                - name: HASURA_URL
                  value: "http://hasura:8080/v1/graphql"
                - name: HASURA_ADMIN_SECRET
                  valueFrom:
                    secretKeyRef:
                      name: hasura-admin-secret
                      key: admin-secret
                - name: SCALEWAY_AI_API_KEY
                  valueFrom:
                    secretKeyRef:
                      name: scaleway-ai
                      key: secret-key
                - name: SLACK_BOT_TOKEN
                  valueFrom:
                    secretKeyRef:
                      name: slack-credentials
                      key: bot-token
              resources:
                requests: {cpu: 50m, memory: 128Mi}
                limits: {cpu: 500m, memory: 256Mi}
          restartPolicy: Never
```

- [ ] **Step 7: Run all tests so far**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py -v`
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add jobs/training/deliver.py jobs/cli.py deploy/cronjobs/training-deliver.yaml jobs/tests/test_training.py
git commit -m "Add training delivery: CronJob, CLI command, Slack DM formatting"
```

---

## Task 6: Bot DM response handler

Replace the stub DM handler with the full training response flow: go, answers, next, practice.

**Files:**
- Modify: `jobs/bot/bot.py`
- Test: `jobs/tests/test_training.py` (add TestDMHandler class)

- [ ] **Step 1: Write tests for the DM handler logic**

Add to `jobs/tests/test_training.py`. Test the handler logic by extracting it into a testable function, not by testing the Slack event directly.

```python
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
        assert cmd == "unknown"

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
        from bot.training_dm import calculate_streak
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        # Last activity today — streak stays the same
        assert calculate_streak(current_streak=3, last_activity=now.isoformat()) == 3

    def test_streak_calculation_next_day(self):
        from bot.training_dm import calculate_streak
        from datetime import datetime, timezone, timedelta
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert calculate_streak(current_streak=3, last_activity=yesterday.isoformat()) == 4

    def test_streak_calculation_broken(self):
        from bot.training_dm import calculate_streak
        from datetime import datetime, timezone, timedelta
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        assert calculate_streak(current_streak=10, last_activity=three_days_ago.isoformat()) == 1

    def test_streak_calculation_first_activity(self):
        from bot.training_dm import calculate_streak
        assert calculate_streak(current_streak=0, last_activity=None) == 1

    def test_format_chapter_complete_stage_0_done_has_coming_soon(self):
        """Verify 'next' after final chapter shows Stage 1 coming soon."""
        from bot.training_dm import format_chapter_complete
        text = format_chapter_complete(chapter=4, chapter_name="The Services", streak=7)
        assert "Stage 0 complete" in text
        assert "coming soon" in text.lower()
        assert "practice" in text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMHandler -v`
Expected: ImportError — `bot.training_dm` doesn't exist yet.

- [ ] **Step 3: Create the training DM handler module**

Create `jobs/bot/training_dm.py` — extracted logic that `bot.py` will call:

```python
"""Training DM handler logic.

Extracted from bot.py for testability. Handles: go, answers, next, practice.
"""
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from training.engine import CHAPTERS

log = logging.getLogger(__name__)

TOPIC_MAP = {
    "promise": 0, "worldview": 1, "audience": 2,
    "difference": 3, "services": 4,
}


def parse_dm_command(text: str) -> tuple[str, str | None]:
    """Parse a DM message into a command and optional argument.

    Returns (command, arg) where command is one of:
        "go", "next", "practice", "answer", "unknown"
    """
    text = text.strip()
    lower = text.lower()

    if lower == "go":
        return "go", None
    if lower == "next":
        return "next", None
    if lower.startswith("practice"):
        parts = lower.split(maxsplit=1)
        topic = parts[1] if len(parts) > 1 else None
        return "practice", topic
    if text.upper() in ("A", "B", "C"):
        return "answer", text.upper()

    return "unknown", None


def resolve_topic(topic: str) -> int | None:
    """Resolve a topic string to a chapter number, or None if unrecognized."""
    return TOPIC_MAP.get(topic.lower())


def calculate_streak(current_streak: int, last_activity: str | None) -> int:
    """Calculate updated streak based on last activity timestamp.

    Uses Europe/Amsterdam timezone for calendar day boundaries (handles CET/CEST).
    """
    if last_activity is None:
        return 1

    tz = ZoneInfo("Europe/Amsterdam")
    now_cet = datetime.now(tz)
    last = datetime.fromisoformat(last_activity)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    last_cet = last.astimezone(tz)

    days_diff = (now_cet.date() - last_cet.date()).days

    if days_diff == 0:
        return current_streak  # same day, no change
    if days_diff == 1:
        return current_streak + 1  # consecutive day
    return 1  # streak broken


def format_chapter_complete(chapter: int, chapter_name: str, streak: int) -> str:
    """Format the chapter completion message."""
    display = chapter + 1  # 1-indexed
    lines = [
        "\u2501" * 20,
        f"Chapter {display} complete \u2014 {chapter_name} \u2713",
        f"Streak: {streak} day{'s' if streak != 1 else ''}",
        "\u2501" * 20,
    ]

    if chapter < 4:
        next_ch = CHAPTERS[chapter + 1]
        next_display = chapter + 2
        lines.append(f"\nTomorrow: Chapter {next_display} \u2014 {next_ch['name']}")
        lines.append(
            f"\nWant to keep going? Say *next* for chapter {next_display}, "
            f"or *practice {chapter_name.lower().replace('the ', '')}* "
            f"to do more on this one."
        )
    else:
        lines.append(
            "\nStage 0 complete! Stage 1 \u2014 the marketing framework "
            "\u2014 is coming soon.\n\n"
            "In the meantime, say *practice [topic]* to keep sharpening. "
            "Topics: promise, worldview, audience, difference, services."
        )

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMHandler -v`
Expected: All 14 tests PASS.

- [ ] **Step 5: Wire up the bot DM handler**

Modify `jobs/bot/bot.py`. Replace the `handle_dm` function (lines 338-364) with the full training DM flow. Add these imports at the top of the file:

```python
from bot.training_dm import (
    parse_dm_command, resolve_topic, calculate_streak, format_chapter_complete,
)
from training.score import score_response
from training.deliver import (
    deliver_to_user_on_demand, format_question_dm,
)
from mothertree.hasura import (
    get_active_conversation, update_conversation, cancel_stale_conversations,
    insert_response, advance_enrollment, update_streak,
)
```

Replace `handle_dm` with:

```python
@app.event("message")
def handle_dm(event, client):
    """Handle DM messages for training responses."""
    if event.get("channel_type") != "im":
        return
    if event.get("bot_id"):
        return

    user_slack_id = event["user"]
    text = event.get("text", "").strip()
    if not text:
        return

    enrollment = get_enrollment(user_slack_id)
    if not enrollment:
        client.chat_postMessage(
            channel=user_slack_id,
            text="You're not enrolled yet. Use `/mothertree enroll <role>` to get started.",
        )
        return

    conv = get_active_conversation(enrollment["id"])
    cmd, arg = parse_dm_command(text)

    # --- No active conversation ---
    if conv is None:
        if cmd == "next":
            cancel_stale_conversations(enrollment["id"])
            stage = enrollment["current_stage"]
            chapter = enrollment["current_chapter"]
            if stage == 0 and chapter > 4:
                client.chat_postMessage(
                    channel=user_slack_id,
                    text="You've completed Stage 0. Stage 1 \u2014 the marketing framework "
                         "\u2014 is coming soon.\n\nSay *practice [topic]* to keep sharpening.",
                )
                return
            deliver_to_user_on_demand(client, enrollment)
        elif cmd == "practice":
            cancel_stale_conversations(enrollment["id"])
            if arg:
                chapter = resolve_topic(arg)
                if chapter is None:
                    client.chat_postMessage(
                        channel=user_slack_id,
                        text="I don't have a chapter called that. "
                             "Try: promise, worldview, audience, difference, or services.",
                    )
                    return
            else:
                chapter = enrollment["current_chapter"]
            deliver_to_user_on_demand(client, enrollment, chapter=chapter, practice=True)
        else:
            client.chat_postMessage(
                channel=user_slack_id,
                text="No active exercise. Say *next* to continue training, "
                     "or *practice [topic]* to drill a topic.",
            )
        return

    # --- Active conversation ---
    exercise = conv["exercise"]["content"]
    current_q = conv["current_question"]
    questions = exercise["questions"]

    if current_q == -1:
        # Waiting for "go" after instruction text
        if cmd == "go":
            update_conversation(conv["id"], current_question=0)
            text = format_question_dm(questions[0], question_num=1, total=len(questions))
            client.chat_postMessage(channel=user_slack_id, text=text)
        else:
            client.chat_postMessage(
                channel=user_slack_id,
                text="Reply *go* when you've read the instruction text.",
            )
        return

    # Answering a question
    if cmd != "answer":
        client.chat_postMessage(
            channel=user_slack_id,
            text="Reply with *A*, *B*, or *C*.",
        )
        return

    question = questions[current_q]
    result = score_response(stage=conv["stage"], question=question, response=arg)

    insert_response(
        exercise_id=conv["exercise_id"], user_id=enrollment["id"],
        response=arg, question_index=current_q,
        correct=result["correct"], feedback=result["feedback"],
    )

    next_q = current_q + 1
    if next_q < len(questions):
        # More questions
        update_conversation(conv["id"], current_question=next_q)
        feedback_text = result["feedback"]
        question_text = format_question_dm(
            questions[next_q], question_num=next_q + 1, total=len(questions)
        )
        client.chat_postMessage(
            channel=user_slack_id,
            text=f"{feedback_text}\n\n{question_text}",
        )
    else:
        # Chapter complete
        update_conversation(conv["id"], current_question=next_q, state="complete")

        chapter = exercise["chapter"]
        chapter_name = exercise["chapter_name"]
        streak = calculate_streak(
            enrollment.get("streak", 0),
            enrollment.get("last_activity"),
        )
        update_streak(enrollment["id"], streak)

        is_practice = exercise.get("type") == "practice"
        if not is_practice:
            new_chapter = chapter + 1
            if new_chapter > 4:
                advance_enrollment(enrollment["id"], current_chapter=new_chapter, current_stage=1)
            else:
                advance_enrollment(enrollment["id"], current_chapter=new_chapter)

        complete_text = format_chapter_complete(chapter, chapter_name, streak)
        client.chat_postMessage(
            channel=user_slack_id,
            text=f"{result['feedback']}\n\n{complete_text}",
        )
```

- [ ] **Step 6: Run all tests**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/training_dm.py jobs/bot/bot.py jobs/tests/test_training.py
git commit -m "Add training DM handler: go, answers, next, practice commands"
```

---

## Task 7: Bot consistency tests

Update the existing bot consistency tests to cover the new DM training commands.

**Files:**
- Modify: `jobs/tests/test_validate.py`
- Test: `jobs/tests/test_training.py` (add integration-level test)

- [ ] **Step 1: Add a test that validates the training DM commands are complete**

Add to `jobs/tests/test_training.py`:

```python
class TestTrainingConsistency:
    """Validate training components are consistent with each other."""

    def test_chapters_match_topic_map(self):
        from training.engine import CHAPTERS
        from bot.training_dm import TOPIC_MAP
        # Every chapter should have a topic keyword
        for i, ch in CHAPTERS.items():
            # Strip "The " prefix and lowercase
            topic = ch["name"].lower().replace("the ", "")
            assert topic in TOPIC_MAP, f"Chapter {i} ({ch['name']}) has no topic keyword"
            assert TOPIC_MAP[topic] == i

    def test_all_chapters_have_unique_names(self):
        from training.engine import CHAPTERS
        names = [ch["name"] for ch in CHAPTERS.values()]
        assert len(names) == len(set(names))

    def test_score_handles_all_option_letters(self):
        from training.score import score_response
        q = {"question": "Q", "options": {"A": "a", "B": "b", "C": "c"},
             "correct": "A", "why": "w", "redirect": "r"}
        for letter in ("A", "B", "C"):
            result = score_response(stage=0, question=q, response=letter)
            assert isinstance(result["correct"], bool)
            assert isinstance(result["feedback"], str)
```

- [ ] **Step 2: Run the full test suite**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/ -v`
Expected: All tests PASS (both existing test_validate.py and new test_training.py).

- [ ] **Step 3: Commit**

```bash
git add jobs/tests/test_training.py
git commit -m "Add training consistency tests: chapter-topic mapping, scoring completeness"
```

---

## Task 8: Final integration check

Verify everything works together and the deployment manifests are correct.

- [ ] **Step 1: Run the full test suite one more time**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 2: Verify CronJob manifest is valid YAML**

Run: `python -c "import yaml; yaml.safe_load(open('deploy/cronjobs/training-deliver.yaml'))"`
Expected: No errors.

- [ ] **Step 3: Verify all new imports resolve**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -c "from training.engine import generate_exercise; from training.score import score_response; from training.deliver import deliver_training; from bot.training_dm import parse_dm_command; print('All imports OK')"`
Expected: "All imports OK"

- [ ] **Step 4: Review the git log**

Run: `git log --oneline -10`
Expected: Clean sequence of commits matching the task progression.

- [ ] **Step 5: Final commit if any cleanup needed**

If any files were missed or cleanup is needed, commit now.

---

## Deployment notes

After implementation, deploy in this order:

1. **Database migration** — Run the ALTER TABLE for enrollment (add streak, last_activity) and CREATE TABLE for exercises, responses, conversations via Hasura console.
2. **Track tables in Hasura** — Track all four tables and configure select/insert/update permissions. Configure object relationship from `conversations` to `exercises` (on `exercise_id`) so the nested `exercise { content }` query works.
3. **Deploy bot** — The updated bot.py with DM handler ships with the next image push (Flux auto-deploys).
4. **Deploy CronJob** — Apply `deploy/cronjobs/training-deliver.yaml` (Flux picks it up from the repo).
5. **Test** — Enroll a test user, trigger delivery manually via `kubectl exec`, verify DM flow end-to-end.
