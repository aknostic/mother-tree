# Training Curriculum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat CHAPTERS dict with role-specific CURRICULA, wire exercise generation through character modules (Seth/Lawrence/Mother Tree), and make training responses properly formatted for Slack.

**Architecture:** `CURRICULA` dict in `training/engine.py` defines stages, chapters, trainers, and CI tables per role. Exercise generation calls the trainer's character module for instruction text. The pipeline's `_training_response` reads the trainer from CURRICULA and routes accordingly. `deliver.py` becomes role-aware for chapter counts and formatting.

**Tech Stack:** Python 3.12, existing character modules (seth.py, lawrence.py, mother_tree.py), Hasura/PostgreSQL

**Spec:** `docs/superpowers/specs/2026-03-25-training-curriculum-design.md`

---

## File Structure

```
jobs/training/curriculum.py     — NEW: CURRICULA dict, lookup functions
jobs/training/engine.py         — modify: use CURRICULA, route to character modules
jobs/training/deliver.py        — modify: role-aware chapter counts and formatting
jobs/bot/pipeline.py            — modify: _training_response reads trainer from CURRICULA
jobs/bot/characters/dispatcher.py — modify: pass enrollment role context
jobs/tests/test_curriculum.py   — NEW: tests for curriculum lookups and exercise generation
```

---

### Task 1: Create curriculum.py with CURRICULA dict and lookup functions

**Files:**
- Create: `jobs/training/curriculum.py`
- Create: `jobs/tests/test_curriculum.py`

- [ ] **Step 1: Write tests for curriculum lookups**

```python
# jobs/tests/test_curriculum.py
"""Tests for training curriculum — role-specific paths."""


class TestCurriculumLookup:
    """Look up stages, chapters, and trainers by role."""

    def test_hunter_has_5_stages(self):
        from training.curriculum import get_stages
        stages = get_stages("hunter")
        assert len(stages) == 5

    def test_gatherer_has_5_stages(self):
        from training.curriculum import get_stages
        stages = get_stages("gatherer")
        assert len(stages) == 5

    def test_farmer_has_5_stages(self):
        from training.curriculum import get_stages
        stages = get_stages("farmer")
        assert len(stages) == 5

    def test_citizen_has_4_stages(self):
        from training.curriculum import get_stages
        stages = get_stages("citizen")
        assert len(stages) == 4

    def test_hunter_stage0_has_5_chapters(self):
        from training.curriculum import get_chapters
        chapters = get_chapters("hunter", 0)
        assert len(chapters) == 5

    def test_gatherer_stage0_has_2_chapters(self):
        from training.curriculum import get_chapters
        chapters = get_chapters("gatherer", 0)
        assert len(chapters) == 2

    def test_farmer_stage0_has_2_chapters(self):
        from training.curriculum import get_chapters
        chapters = get_chapters("farmer", 0)
        assert len(chapters) == 2

    def test_citizen_stage0_has_chapters(self):
        from training.curriculum import get_chapters
        chapters = get_chapters("citizen", 0)
        assert len(chapters) >= 1

    def test_get_chapter_returns_trainer(self):
        from training.curriculum import get_chapter
        ch = get_chapter("hunter", 0, 0)
        assert ch["trainer"] == "seth"
        assert ch["name"] == "The Promise"
        assert "change" in ch["tables"]

    def test_get_chapter_gatherer_stage1(self):
        from training.curriculum import get_chapter
        ch = get_chapter("gatherer", 1, 0)
        assert ch["trainer"] == "lawrence"

    def test_get_chapter_farmer_stage1(self):
        from training.curriculum import get_chapter
        ch = get_chapter("farmer", 1, 0)
        assert ch["trainer"] == "lawrence"

    def test_get_total_chapters(self):
        from training.curriculum import get_total_chapters
        assert get_total_chapters("hunter", 0) == 5
        assert get_total_chapters("gatherer", 0) == 2

    def test_unknown_role_raises(self):
        from training.curriculum import get_stages
        import pytest
        with pytest.raises(KeyError):
            get_stages("nonexistent")

    def test_is_citizen(self):
        from training.curriculum import is_citizen_role
        assert is_citizen_role("citizen") is True
        assert is_citizen_role("hunter") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_curriculum.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create curriculum.py**

```python
# jobs/training/curriculum.py
"""Training curriculum — role-specific stages, chapters, and trainers.

Each role has its own path. Each chapter specifies a trainer (seth, lawrence,
mother_tree) and which CI tables provide source data.
"""

CURRICULA = {
    "hunter": {
        0: {
            "name": "The Foundation",
            "chapters": {
                0: {"name": "The Promise", "tables": ["change"], "trainer": "seth",
                    "purpose": "What transformation do we offer? Not what we do — what the customer becomes."},
                1: {"name": "The Worldview", "tables": ["worldview", "personas"], "trainer": "seth",
                    "purpose": "What does our audience already believe? These beliefs make them ready."},
                2: {"name": "The Audience", "tables": ["personas"], "trainer": "seth",
                    "purpose": "Who specifically? Not everyone. Specific people with specific concerns."},
                3: {"name": "The Difference", "tables": ["competitors"], "trainer": "seth",
                    "purpose": "What's the status quo they leave behind? How are we different?"},
                4: {"name": "The Services", "tables": ["change"], "trainer": "seth",
                    "purpose": "Assess, Build, Operate — the journey from dependent to independent."},
            },
        },
        1: {"name": "The Framework", "chapters": {}},
        2: {"name": "The Conversation", "chapters": {}},
        3: {"name": "The Dance", "chapters": {}},
        4: {"name": "Prep Sessions", "chapters": {}},
    },
    "gatherer": {
        0: {
            "name": "The Change",
            "chapters": {
                0: {"name": "Who We Are", "tables": ["change"], "trainer": "seth",
                    "purpose": "Brief: the transformation we offer. Enough to recognize it."},
                1: {"name": "Who It's For", "tables": ["personas"], "trainer": "seth",
                    "purpose": "The buyers. So you know who matters when you're in a delivery meeting."},
            },
        },
        1: {
            "name": "Signal Recognition",
            "chapters": {
                0: {"name": "What's a Signal", "tables": ["insights", "worldview"], "trainer": "lawrence",
                    "purpose": "When someone mentions cost pressure, lock-in, or compliance — that's a signal."},
                1: {"name": "Listening for Pain", "tables": ["worldview"], "trainer": "lawrence",
                    "purpose": "The pain is rarely stated directly. Here's what to listen for."},
                2: {"name": "Context Matters", "tables": ["personas"], "trainer": "lawrence",
                    "purpose": "A CTO complaining about costs means something different than a developer."},
            },
        },
        2: {
            "name": "The Conversation",
            "chapters": {
                0: {"name": "The Follow-Up", "tables": ["insights"], "trainer": "lawrence",
                    "purpose": "Tell me more about that — how to ask without selling."},
                1: {"name": "Knowing Your Limits", "tables": ["personas"], "trainer": "lawrence",
                    "purpose": "When to listen, when to ask, when to stop and hand off."},
            },
        },
        3: {
            "name": "The Handoff",
            "chapters": {
                0: {"name": "Sharing a Signal", "tables": ["insights"], "trainer": "mother_tree",
                    "purpose": "How to tell Mother Tree what you noticed — natural conversation, not a form."},
                1: {"name": "Building Together", "tables": ["personas", "insights"], "trainer": "mother_tree",
                    "purpose": "Mother Tree asks follow-up questions to structure the signal."},
                2: {"name": "Looping In", "tables": ["personas"], "trainer": "mother_tree",
                    "purpose": "When and how to bring a hunter into the conversation."},
            },
        },
        4: {
            "name": "Stories",
            "chapters": {
                0: {"name": "Delivery as Soil", "tables": ["change", "insights"], "trainer": "seth",
                    "purpose": "Your delivery work creates awareness. How client success becomes the next story."},
                1: {"name": "The Narrative", "tables": ["insights"], "trainer": "seth",
                    "purpose": "How to frame what you did as evidence for the change we offer."},
            },
        },
    },
    "farmer": {
        0: {
            "name": "The Change",
            "chapters": {
                0: {"name": "Who We Are", "tables": ["change"], "trainer": "seth",
                    "purpose": "Brief: what the organization does."},
                1: {"name": "Who It's For", "tables": ["personas"], "trainer": "seth",
                    "purpose": "The people the platform ultimately serves."},
            },
        },
        1: {
            "name": "The Hunter's World",
            "chapters": {
                0: {"name": "Before the Meeting", "tables": ["personas", "competitors"], "trainer": "lawrence",
                    "purpose": "What a hunter goes through before a first conversation."},
                1: {"name": "In the Room", "tables": ["insights", "personas"], "trainer": "lawrence",
                    "purpose": "What happens in a consultative conversation. Why the prep has to be right."},
                2: {"name": "After the Meeting", "tables": ["insights"], "trainer": "lawrence",
                    "purpose": "What a hunter needs from the platform — debrief, signal capture, next steps."},
            },
        },
        2: {
            "name": "The Gatherer's World",
            "chapters": {
                0: {"name": "Spotting a Signal", "tables": ["worldview", "insights"], "trainer": "lawrence",
                    "purpose": "What it feels like to notice something in a delivery meeting."},
                1: {"name": "The Awkward Moment", "tables": ["personas"], "trainer": "lawrence",
                    "purpose": "The gatherer heard something. They're not a salesperson. What do they need?"},
                2: {"name": "The Handoff", "tables": ["insights"], "trainer": "lawrence",
                    "purpose": "What the platform should do when a gatherer shares a signal."},
            },
        },
        3: {
            "name": "The Platform",
            "chapters": {
                0: {"name": "What Mother Tree Does", "tables": ["change", "personas"], "trainer": "mother_tree",
                    "purpose": "How the platform serves hunters and gatherers day-to-day."},
                1: {"name": "What Good Looks Like", "tables": ["insights"], "trainer": "mother_tree",
                    "purpose": "When the platform is working well, this is what the team experiences."},
            },
        },
        4: {
            "name": "Quality",
            "chapters": {
                0: {"name": "Assessing Quality", "tables": ["insights", "change"], "trainer": "mother_tree",
                    "purpose": "How to evaluate what Mother Tree extracts and generates."},
                1: {"name": "Improving the System", "tables": ["change"], "trainer": "mother_tree",
                    "purpose": "How to feed corrections back, tune the pipeline, improve outcomes."},
            },
        },
    },
    "citizen": {
        0: {
            "name": "See the Change",
            "chapters": {
                0: {"name": "The Change", "tables": ["change"], "trainer": "seth",
                    "purpose": "What the organization does and why it matters. One idea at a time."},
            },
        },
        1: {
            "name": "See the Worldview",
            "chapters": {
                0: {"name": "The Worldview", "tables": ["worldview"], "trainer": "seth",
                    "purpose": "What the people we help believe. One belief at a time."},
            },
        },
        2: {
            "name": "See the Signals",
            "chapters": {
                0: {"name": "Noticing", "tables": ["insights"], "trainer": "mother_tree",
                    "purpose": "Start noticing things in your own work that connect to the mission."},
            },
        },
        3: {
            "name": "Become a Gatherer",
            "chapters": {
                0: {"name": "Transition", "tables": [], "trainer": "mother_tree",
                    "purpose": "You've been noticing signals naturally. Want to enroll as a gatherer?"},
            },
        },
    },
}


def get_stages(role: str) -> dict:
    """Get all stages for a role. Raises KeyError for unknown roles."""
    return CURRICULA[role]


def get_chapters(role: str, stage: int) -> dict:
    """Get all chapters for a role's stage."""
    return CURRICULA[role][stage]["chapters"]


def get_chapter(role: str, stage: int, chapter: int) -> dict:
    """Get a specific chapter: name, tables, trainer, purpose."""
    return CURRICULA[role][stage]["chapters"][chapter]


def get_total_chapters(role: str, stage: int) -> int:
    """Get the number of chapters in a stage."""
    return len(CURRICULA[role][stage]["chapters"])


def get_stage_name(role: str, stage: int) -> str:
    """Get the name of a stage."""
    return CURRICULA[role][stage]["name"]


def is_citizen_role(role: str) -> bool:
    """Citizens get inspiration, not exercises."""
    return role == "citizen"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jobs && python -m pytest tests/test_curriculum.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/training/curriculum.py jobs/tests/test_curriculum.py
git commit -m "Add CURRICULA dict with role-specific training paths"
```

---

### Task 2: Update engine.py to use CURRICULA and character modules

**Files:**
- Modify: `jobs/training/engine.py`
- Modify: `jobs/tests/test_curriculum.py` (add exercise generation tests)

- [ ] **Step 1: Write tests for updated exercise generation**

Add to `jobs/tests/test_curriculum.py`:

```python
from unittest.mock import patch, MagicMock


class TestExerciseGeneration:
    """Exercise generation uses CURRICULA and character modules."""

    @patch("training.engine.fetch_foundation_for_chapter")
    @patch("training.engine.generate")
    def test_generate_uses_curriculum_chapter(self, mock_gen, mock_fetch):
        from training.engine import generate_exercise
        mock_fetch.return_value = {"change": [{"statement": "test", "context": "test"}]}
        mock_gen.return_value = '{"instruction": "Learn this.", "questions": [{"question": "Q1?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "because", "redirect": "think"}, {"question": "Q2?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "B", "why": "because", "redirect": "think"}, {"question": "Q3?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "C", "why": "because", "redirect": "think"}]}'
        result = generate_exercise(role="hunter", stage=0, chapter=0)
        assert result["chapter_name"] == "The Promise"
        assert result["trainer"] == "seth"
        assert len(result["questions"]) == 3

    @patch("training.engine.fetch_foundation_for_chapter")
    @patch("training.engine.generate")
    def test_generate_gatherer_stage0(self, mock_gen, mock_fetch):
        from training.engine import generate_exercise
        mock_fetch.return_value = {"change": [{"statement": "test"}]}
        mock_gen.return_value = '{"instruction": "Learn.", "questions": [{"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"}, {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"}, {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"}]}'
        result = generate_exercise(role="gatherer", stage=0, chapter=0)
        assert result["chapter_name"] == "Who We Are"
        assert result["trainer"] == "seth"

    @patch("training.engine.fetch_foundation_for_chapter")
    @patch("training.engine.generate")
    def test_generate_includes_trainer_in_result(self, mock_gen, mock_fetch):
        from training.engine import generate_exercise
        mock_fetch.return_value = {"change": [{"statement": "test"}]}
        mock_gen.return_value = '{"instruction": "Learn.", "questions": [{"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"}, {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"}, {"question": "Q?", "options": {"A": "a", "B": "b", "C": "c"}, "correct": "A", "why": "w", "redirect": "r"}]}'
        result = generate_exercise(role="hunter", stage=0, chapter=0)
        assert "trainer" in result
```

- [ ] **Step 2: Update engine.py**

Replace `CHAPTERS` usage with `CURRICULA` lookups. The `generate_exercise` function now takes `role` as a parameter:

```python
# Key changes to engine.py:

# Remove CHAPTERS dict (replaced by curriculum.py)

# Update generate_exercise signature:
def generate_exercise(role: str, stage: int, chapter: int, practice: bool = False) -> dict:
    """Generate a structured exercise for the given role, stage, and chapter."""
    from training.curriculum import get_chapter

    ch = get_chapter(role, stage, chapter)
    data = fetch_foundation_for_chapter(chapter, ch["tables"])
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

    return {
        "stage": stage,
        "chapter": chapter,
        "chapter_name": ch["name"],
        "trainer": ch["trainer"],
        "type": "practice" if practice else "instruction",
        "questions": content["questions"],
        "source_tables": ch["tables"],
        **({"instruction": content["instruction"]} if not practice else {}),
    }
```

Also update `fetch_foundation_for_chapter` to accept a `tables` parameter instead of hardcoded chapter-to-query mapping:

```python
def fetch_foundation_for_chapter(chapter: int, tables: list[str] = None) -> dict:
    """Fetch foundation data for training. Uses tables list from curriculum."""
    if tables is None:
        # Backward compatibility: old chapter-based lookup
        tables = {"change": [0, 4], "worldview": [1], "personas": [1, 2], "competitors": [3]}.get(...)
        # ... keep old logic as fallback

    queries = {
        "change": "change(limit: 15, order_by: {confidence: desc_nulls_last}) { statement context }",
        "worldview": "worldview(limit: 15, order_by: {confidence: desc_nulls_last}) { belief pain readiness_signal }",
        "personas": "personas(limit: 10) { name role profile communication decision_criteria }",
        "competitors": "competitors(limit: 15) { type positioning when_mentioned response }",
        "insights": "insights(limit: 10, order_by: {confidence: desc}) { category reframe evidence }",
    }
    query_parts = [queries[t] for t in tables if t in queries]
    if not query_parts:
        return {}
    result = graphql(f"query {{ {' '.join(query_parts)} }}")
    return result
```

- [ ] **Step 3: Run tests**

Run: `cd jobs && python -m pytest tests/test_curriculum.py tests/test_training.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add jobs/training/engine.py jobs/tests/test_curriculum.py
git commit -m "Wire exercise generation through CURRICULA with role and trainer"
```

---

### Task 3: Update deliver.py for role-aware delivery

**Files:**
- Modify: `jobs/training/deliver.py`

- [ ] **Step 1: Update deliver.py**

Key changes:
- `generate_exercise` now takes `role` parameter
- `format_instruction_dm` uses dynamic chapter count from CURRICULA
- The dispatcher's `deliver_next` also needs updating

```python
# In deliver.py, update calls to generate_exercise:
exercise = generate_exercise(role=user["role"], stage=stage, chapter=chapter)

# Update format_instruction_dm to use dynamic total:
def format_instruction_dm(exercise: dict, total_chapters: int) -> str:
    display_num = exercise["chapter"] + 1
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Chapter {display_num} of {total_chapters}: {exercise['chapter_name']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{exercise['instruction']}\n\n"
        f"Ready for the questions? Reply *go* when you've read this."
    )
```

- [ ] **Step 2: Update dispatcher's deliver_next**

In `jobs/bot/characters/dispatcher.py`, update `deliver_next` to pass role:

```python
def deliver_next(enrollment: dict, slack_user_id: str = None) -> dict:
    from training.deliver import deliver_to_user_on_demand
    try:
        cancel_stale_conversations(enrollment["id"])
        role = enrollment.get("role", "hunter")
        stage = enrollment.get("current_stage", 0)
        chapter = enrollment.get("current_chapter", 0)
        from training.curriculum import get_total_chapters
        total = get_total_chapters(role, stage)
        if chapter >= total:
            return {"error": "stage_complete", "message": f"Stage {stage} complete."}
        result = deliver_to_user_on_demand(None, enrollment)
        return result or {"chapter": chapter, "content": ""}
    except Exception as exc:
        log.exception("deliver_next failed")
        return {"error": str(exc)}
```

- [ ] **Step 3: Run full test suite**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add jobs/training/deliver.py jobs/bot/characters/dispatcher.py
git commit -m "Role-aware training delivery with dynamic chapter counts"
```

---

### Task 4: Update pipeline _training_response to use CURRICULA trainer

**Files:**
- Modify: `jobs/bot/pipeline.py`

- [ ] **Step 1: Update _training_response**

```python
def _training_response(text: str, history: list, user_name: str,
                        participant_count: int, annotation: dict,
                        exercise_pending: dict) -> str:
    """Training mode — route to the chapter's trainer character."""
    # Get trainer from annotation context (set by dispatcher)
    trainer = "seth"  # default for Stage 0
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

- [ ] **Step 2: Update dispatcher to include trainer in annotations**

In the training patterns section of dispatcher.py, add trainer info to annotations:

```python
# For "next" command, after deliver_next:
if delivered and not delivered.get("error"):
    from training.curriculum import get_chapter
    role = (enrollment or {}).get("role", "hunter")
    stage = enrollment.get("current_stage", 0)
    chapter = enrollment.get("current_chapter", 0)
    try:
        ch = get_chapter(role, stage, chapter)
        delivered["trainer"] = ch["trainer"]
    except (KeyError, IndexError):
        pass
```

- [ ] **Step 3: Run tests**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add jobs/bot/pipeline.py jobs/bot/characters/dispatcher.py
git commit -m "Training responses route through character based on CURRICULA trainer"
```

---

### Task 5: Update hasura.py fetch_foundation_for_chapter

**Files:**
- Modify: `jobs/mothertree/hasura.py`

- [ ] **Step 1: Update fetch_foundation_for_chapter to accept tables list**

```python
def fetch_foundation_for_chapter(chapter: int = None, tables: list[str] = None) -> dict:
    """Fetch foundation data for training.

    If tables is provided (from CURRICULA), query those specific tables.
    If only chapter is provided, use legacy chapter-to-table mapping.
    """
    TABLE_QUERIES = {
        "change": "change(limit: 15, order_by: {confidence: desc_nulls_last}) { statement context }",
        "worldview": "worldview(limit: 15, order_by: {confidence: desc_nulls_last}) { belief pain readiness_signal }",
        "personas": "personas(limit: 10) { name role profile communication decision_criteria }",
        "competitors": "competitors(limit: 15) { type positioning when_mentioned response }",
        "insights": "insights(limit: 10, order_by: {confidence: desc}) { category reframe evidence }",
    }

    if tables is None:
        # Legacy: chapter-based mapping
        chapter_tables = {
            0: ["change"], 1: ["worldview", "personas"],
            2: ["personas"], 3: ["competitors"], 4: ["change"],
        }
        tables = chapter_tables.get(chapter, ["change"])

    query_parts = [TABLE_QUERIES[t] for t in tables if t in TABLE_QUERIES]
    if not query_parts:
        return {}
    return graphql(f"query {{ {' '.join(query_parts)} }}")
```

- [ ] **Step 2: Run tests**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add jobs/mothertree/hasura.py
git commit -m "fetch_foundation_for_chapter accepts tables list from CURRICULA"
```

---

### Task 6: Smoke test training in Slack

- [ ] **Step 1: Test hunter Stage 0**

In DM: "next" — should deliver Chapter 1 of 5 with Seth's voice.

- [ ] **Step 2: Test gatherer enrollment**

In DM: "enroll gatherer" then "next" — should deliver Chapter 1 of 2 (Who We Are), Seth's voice.

- [ ] **Step 3: Verify formatting**

All training responses should use Slack formatting (no markdown).
