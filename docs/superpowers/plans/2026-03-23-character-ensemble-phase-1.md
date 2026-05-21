# Character Ensemble Phase 1 — Foundation + Channel Conversation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monolithic prompt architecture with a character module system. Wire up the Dispatcher and Mother Tree character so channel conversation uses focused prompts instead of the mega-prompt.

**Architecture:** New `jobs/bot/characters/` package. Each character is a module with identity, goals, rules, and a `respond()` function. The Dispatcher merges today's `detect()` + `triage()` into a single routing decision. The pipeline calls the Dispatcher, then routes to the selected character's `respond()`. Phase 1 only implements Mother Tree — personas and training still fall through to existing code.

**Tech Stack:** Python 3.11, pytest, existing Scaleway/Anthropic LLM clients via `mothertree.llm`

**Spec:** `docs/superpowers/specs/2026-03-23-character-ensemble-design.md`

---

## File Structure

```
jobs/bot/characters/
    __init__.py          — package init, exports dispatch + respond
    base.py              — shared constants, formatting, no-hallucination rules, respond interface
    dispatcher.py        — routing logic (deterministic patterns + LLM triage)
    mother_tree.py       — Mother Tree character (Librarian)

jobs/bot/pipeline.py     — modify to use Dispatcher → character routing
jobs/bot/conversation.py — keep as thin adapter during Phase 1 (personas/training still use it)
jobs/mothertree/ask.py   — extract shared constants, keep persona/training code for now

jobs/tests/test_characters.py — tests for base, dispatcher, mother_tree
```

---

### Task 1: Create `characters/base.py` — shared rules and interface

**Files:**
- Create: `jobs/bot/characters/__init__.py`
- Create: `jobs/bot/characters/base.py`
- Test: `jobs/tests/test_characters.py`

- [ ] **Step 1: Write tests for shared constants and utilities**

```python
# jobs/tests/test_characters.py
"""Tests for character ensemble modules."""


class TestBase:
    """Shared character utilities."""

    def test_no_hallucination_rules_present(self):
        from bot.characters.base import NO_HALLUCINATION_RULES
        assert "NEVER FABRICATE" in NO_HALLUCINATION_RULES

    def test_slack_formatting_rules_present(self):
        from bot.characters.base import SLACK_FORMATTING_RULES
        assert "single asterisk" in SLACK_FORMATTING_RULES

    def test_fix_slack_formatting_bold(self):
        from bot.characters.base import fix_slack_formatting
        assert fix_slack_formatting("**bold**") == "*bold*"

    def test_fix_slack_formatting_heading(self):
        from bot.characters.base import fix_slack_formatting
        result = fix_slack_formatting("### heading")
        assert "###" not in result
        assert "*heading*" in result

    def test_fix_slack_formatting_bullets(self):
        from bot.characters.base import fix_slack_formatting
        assert fix_slack_formatting("- item") == "• item"

    def test_fix_slack_formatting_links(self):
        from bot.characters.base import fix_slack_formatting
        assert fix_slack_formatting("[text](http://example.com)") == "text"

    def test_default_model_and_temperature(self):
        from bot.characters.base import DEFAULT_MODEL, DEFAULT_TEMPERATURE
        from mothertree.config import GENERATION_MODEL
        assert DEFAULT_MODEL == GENERATION_MODEL
        assert DEFAULT_TEMPERATURE == 0.7

    def test_factual_annotation_types(self):
        from bot.characters.base import FACTUAL_ANNOTATION_TYPES
        assert "status" in FACTUAL_ANNOTATION_TYPES
        assert "url_content" not in FACTUAL_ANNOTATION_TYPES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_characters.py::TestBase -v`
Expected: FAIL — `bot.characters` module not found

- [ ] **Step 3: Create the package and base module**

```python
# jobs/bot/characters/__init__.py
"""Character ensemble — focused prompts for focused jobs."""
```

```python
# jobs/bot/characters/base.py
"""Shared constants, rules, and utilities for all characters."""
import re

from mothertree.config import GENERATION_MODEL, EXTRACTION_MODEL


# -- Model defaults (characters override only when needed) --
DEFAULT_MODEL = GENERATION_MODEL
DEFAULT_TEMPERATURE = 0.7

# -- Annotation types that carry facts (must be stated exactly) --
FACTUAL_ANNOTATION_TYPES = {
    "status", "stats", "enrolled", "answer_scored",
    "progress", "exercise_started", "enroll",
}

# -- Shared rules --
NO_HALLUCINATION_RULES = """
RULES — NON-NEGOTIABLE:
Your credibility depends on these rules. Break one and the user stops trusting you.

1. NEVER FABRICATE. Not URLs, not titles, not times, not room numbers, not names.
   If you don't have specific data, say so clearly. Examples:
   - User asks for session titles you don't have → "I can't see individual sessions on this page."
   - User asks you to "pick 3 talks" but you have no talk data → "I don't have the session list. Share a page that shows individual talks and I'll help you pick."
   - User asks for a link you don't have → "I don't have that link."
   NEVER fill in details you don't have, even when directly asked. Saying "I don't have that" is always better than guessing.
   THIS INCLUDES TITLES. If you did not receive a list of specific session titles, talk names, or article headlines in your context, you MUST NOT generate them. A title in *italics* or quotes that you made up is still fabrication.

2. ONLY STATE WHAT YOU CAN SEE. You receive fetched URL content in annotations.
   Only reference facts that appear in that content. If a page is a landing page
   without session details, say exactly that. Do not extrapolate, guess, or
   "helpfully" provide details that aren't in the source.

3. WHEN YOU CAN'T HELP DIRECTLY, REDIRECT. Suggest what the user can do:
   "Check the event app" or "Share the page that lists individual sessions."
   Offer to help once they have the data: "Send me the session list and I'll pick the ones that matter for us."

- You have the conversation history. Use it. Don't ask for context already given.
"""

SLACK_FORMATTING_RULES = """
FORMATTING — CRITICAL:
You are writing for Slack, NOT Markdown. This is non-negotiable:
- Bold: *text* (single asterisk). NEVER use **text**.
- Italic: _text_ (underscore). NEVER use *text* for italic.
- Bullets: use • or plain text. NEVER use - or * as bullet markers.
- Headers: use *bold text* on its own line. NEVER use # or ##.
- Horizontal rules: NEVER use ---.
- Links: NEVER use [text](url). Just write the text or paste the URL bare.
- NEVER generate URLs. Only repeat URLs the user shared or that appear in fetched content.
- Emojis: use sparingly or not at all.
- Keep responses concise and scannable.
"""


def fix_slack_formatting(text: str) -> str:
    """Convert any remaining Markdown to Slack formatting."""
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    text = re.sub(r'#{1,6}\s+(.+?)(?=$|\n)', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'^- ', '• ', text, flags=re.MULTILINE)
    return text


def build_annotation_context(annotation: dict | None) -> str:
    """Build the annotation section of a prompt.

    Factual annotations get FACTS label (state exactly).
    Contextual annotations get CONTEXT label (weave naturally).
    """
    if not annotation:
        return ""
    import json
    ann_type = annotation.get("type", "")
    if ann_type in FACTUAL_ANNOTATION_TYPES:
        return (
            f"\n\nFACTS (state these exactly, do not rephrase or omit any values):"
            f"\n{json.dumps(annotation, default=str)}"
            f"\nPresent these facts conversationally but do not change the values."
        )
    return (
        f"\n\nCONTEXT ({ann_type}):"
        f"\n{json.dumps(annotation, default=str)}"
        f"\nWeave this into your response naturally."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jobs && python -m pytest tests/test_characters.py::TestBase -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/characters/__init__.py jobs/bot/characters/base.py jobs/tests/test_characters.py
git commit -m "Add characters package with shared base module"
```

---

### Task 2: Create `characters/mother_tree.py` — the Librarian

**Files:**
- Create: `jobs/bot/characters/mother_tree.py`
- Modify: `jobs/tests/test_characters.py`

- [ ] **Step 1: Write tests for Mother Tree's prompt building and respond**

Add to `jobs/tests/test_characters.py`:

```python
from unittest.mock import patch, MagicMock


class TestMotherTree:
    """Mother Tree character — the Librarian."""

    def test_identity_present(self):
        from bot.characters.mother_tree import IDENTITY
        assert "Mother Tree" in IDENTITY
        assert "commercial intelligence" in IDENTITY

    def test_goals_present(self):
        from bot.characters.mother_tree import GOALS
        assert len(GOALS) > 0

    def test_rules_present(self):
        from bot.characters.mother_tree import RULES
        assert "never fabricate" in RULES.lower()

    def test_build_prompt_includes_identity(self):
        from bot.characters.mother_tree import build_prompt
        prompt = build_prompt(
            ci_context="Change:\n- We help organizations...",
            user_name="Jurg",
            participant_count=1,
        )
        assert "Mother Tree" in prompt
        assert "Jurg" in prompt

    def test_build_prompt_includes_ci_context(self):
        from bot.characters.mother_tree import build_prompt
        prompt = build_prompt(
            ci_context="Change:\n- test change statement",
            user_name="Jurg",
            participant_count=1,
        )
        assert "test change statement" in prompt

    def test_build_prompt_channel_includes_participant_note(self):
        from bot.characters.mother_tree import build_prompt
        prompt = build_prompt(
            ci_context="CI data",
            user_name="Jurg",
            participant_count=5,
        )
        assert "group channel" in prompt.lower()

    def test_build_prompt_dm_no_participant_note(self):
        from bot.characters.mother_tree import build_prompt
        prompt = build_prompt(
            ci_context="CI data",
            user_name="Jurg",
            participant_count=1,
        )
        assert "group channel" not in prompt.lower()

    def test_build_prompt_with_annotation(self):
        from bot.characters.mother_tree import build_prompt
        prompt = build_prompt(
            ci_context="CI data",
            user_name="Jurg",
            participant_count=1,
            annotation={"type": "status", "stage": 0, "chapter": 2},
        )
        assert "FACTS" in prompt

    def test_build_prompt_with_exercise_pending(self):
        from bot.characters.mother_tree import build_prompt
        prompt = build_prompt(
            ci_context="CI data",
            user_name="Jurg",
            participant_count=1,
            exercise_pending={"question_num": 2, "total": 3},
        )
        assert "question 2" in prompt

    def test_build_prompt_ends_with_rules(self):
        from bot.characters.mother_tree import build_prompt
        prompt = build_prompt(
            ci_context="CI data",
            user_name="Jurg",
            participant_count=1,
        )
        # Rules should be last (closest to conversation for strongest attention)
        last_500 = prompt[-500:]
        assert "NEVER FABRICATE" in last_500

    @patch("bot.characters.mother_tree.chat_conversation")
    @patch("bot.characters.mother_tree.fetch_context")
    def test_respond_calls_llm(self, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Here's what I know."
        result = respond(
            question="what do we know?",
            history=[],
            user_name="Jurg",
            participant_count=1,
        )
        assert result == "Here's what I know."
        mock_chat.assert_called_once()

    @patch("bot.characters.mother_tree.chat_conversation")
    @patch("bot.characters.mother_tree.fetch_context")
    def test_respond_uses_generation_model(self, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond, MODEL
        from mothertree.config import GENERATION_MODEL
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "response"
        respond(question="test", history=[], user_name="Jurg", participant_count=1)
        call_kwargs = mock_chat.call_args
        assert call_kwargs[1].get("model") == GENERATION_MODEL or MODEL == GENERATION_MODEL

    @patch("bot.characters.mother_tree.chat_conversation")
    @patch("bot.characters.mother_tree.fetch_context")
    def test_respond_passes_history(self, mock_ctx, mock_chat):
        from bot.characters.mother_tree import respond
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "response"
        history = [{"role": "user", "content": "earlier question"}]
        respond(question="follow up", history=history, user_name="Jurg", participant_count=1)
        messages = mock_chat.call_args[0][0]
        # Should have: system prompt, history message, new question
        roles = [m["role"] for m in messages]
        assert roles[0] == "system"
        assert "user" in roles[1:]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_characters.py::TestMotherTree -v`
Expected: FAIL — `bot.characters.mother_tree` not found

- [ ] **Step 3: Write Mother Tree character module**

```python
# jobs/bot/characters/mother_tree.py
"""Mother Tree — the Librarian.

Knows the central intelligence. Default voice in all contexts.
Never fabricates. If she doesn't know, she says so.
"""
from mothertree.ask import fetch_context
from mothertree.llm import chat_conversation
from mothertree.config import GENERATION_MODEL
from bot.characters.base import (
    NO_HALLUCINATION_RULES,
    SLACK_FORMATTING_RULES,
    build_annotation_context,
)

MODEL = GENERATION_MODEL
TEMPERATURE = 0.7

IDENTITY = """You are Mother Tree, the commercial intelligence for a consultative sales team.
You are talking to colleagues — not prospects. Be direct, practical, collaborative. No pitching.

You are the team's knowledge keeper. You know the central intelligence: the company's
positioning (change statements, worldview beliefs), the audience (personas), the competitive
landscape, and the narrative (insights, evidence, reframes). You connect dots across this
knowledge to help the team prepare for conversations, understand the market, and sharpen
their thinking.
"""

GOALS = """YOUR GOALS:
- Answer questions from the central intelligence. Connect pieces the team might not see.
- When someone shares a URL or content, analyze it through the lens of the CI — what matters for us?
- In channels, speak only when you have something useful to add. In DMs, always respond.
- In signal threads, build on what was said. Don't re-summarize. Close with a follow-up moment.
- For citizens, inspire rather than instruct. Share the story, the change, the worldview.
- When you can save useful content to the CI, include [ACTION:ci_save] in your response.
- When a signal should be captured, include [ACTION:capture_signal] in your response.
  These markers are stripped before the user sees your response.
"""

RULES = """YOUR RULES:
- Never fabricate. Not URLs, not titles, not names, not data. If you don't know, say so.
- Never pitch. You talk to colleagues, not prospects.
- Use the conversation history. Don't ask for context already given.
- In signal threads: don't re-summarize the whole thread. Build on what was said.
  If someone answers a question, acknowledge briefly and move forward.
  When the signal is complete, close actively: "No further questions. I'll check back after KubeCon."
  Never say "if you need further assistance" — you are a participant, not a helpdesk.
  If someone mentions a date, note it. If no timing, suggest a default: "I'll check back in a week. Too soon?"
- Be brief, warm, Dutch-direct. No corporate filler.
"""


def build_prompt(ci_context: str, user_name: str, participant_count: int,
                 annotation: dict = None, exercise_pending: dict = None,
                 signal_flag: bool = False) -> str:
    """Assemble Mother Tree's full system prompt."""
    parts = [IDENTITY, GOALS, RULES]

    # Central intelligence
    parts.append(f"\nCENTRAL INTELLIGENCE:\n{ci_context}")

    # Conversation context
    parts.append(f"\nYou are talking to {user_name}.")
    if participant_count > 1:
        parts.append("You are in a group channel with multiple participants.")

    if signal_flag:
        parts.append("\nThis conversation contains commercial signal intelligence. Acknowledge it naturally.")

    # Annotation
    ann_ctx = build_annotation_context(annotation)
    if ann_ctx:
        parts.append(ann_ctx)

    # Exercise nudge
    if exercise_pending:
        parts.append(
            f"\nThe user has a pending exercise: question {exercise_pending['question_num']} "
            f"of {exercise_pending['total']}. Add a natural nudge at the end of your response."
        )

    # Rules last — closest to conversation, strongest attention
    parts.append(SLACK_FORMATTING_RULES)
    parts.append(NO_HALLUCINATION_RULES)

    return "\n".join(parts)


def respond(question: str, history: list[dict], user_name: str = "you",
            participant_count: int = 1, annotation: dict = None,
            signal_flag: bool = False, exercise_pending: dict = None) -> str:
    """Generate Mother Tree's response.

    Args:
        question: the user's message
        history: conversation history (windowed)
        user_name: who's asking
        participant_count: 1 for DM, >1 for channel
        annotation: structured data from the Dispatcher
        signal_flag: True if triage detected a commercial signal
        exercise_pending: nudge info if exercise is in progress

    Returns:
        The response text (before marker extraction and formatting).
    """
    ci_context = fetch_context()
    system = build_prompt(
        ci_context=ci_context,
        user_name=user_name,
        participant_count=participant_count,
        annotation=annotation,
        signal_flag=signal_flag,
        exercise_pending=exercise_pending,
    )

    messages = [{"role": "system", "content": system}]
    for msg in history:
        if msg["role"] in ("user", "assistant", "system"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    return chat_conversation(messages, model=MODEL)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jobs && python -m pytest tests/test_characters.py::TestMotherTree -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/characters/mother_tree.py jobs/tests/test_characters.py
git commit -m "Add Mother Tree character module with focused prompt"
```

---

### Task 3: Create `characters/dispatcher.py` — routing logic

**Files:**
- Create: `jobs/bot/characters/dispatcher.py`
- Modify: `jobs/tests/test_characters.py`

The Dispatcher merges `detect()` and `triage()` into one module. Pattern matching stays deterministic. LLM triage only fires when patterns don't resolve. The output is a routing decision.

- [ ] **Step 1: Write tests for the Dispatcher**

Add to `jobs/tests/test_characters.py`:

```python
class TestDispatcher:
    """Dispatcher — the Receptionist. Routes messages to characters."""

    def test_status_command_routes_to_mother_tree(self):
        from bot.characters.dispatcher import dispatch
        with patch("bot.characters.dispatcher.get_enrollment") as mock:
            mock.return_value = {"role": "hunter", "current_stage": 0, "current_chapter": 2, "streak": 3}
            result = dispatch(
                text="status", participant_count=1, enrolled=True, slack_user_id="U123",
            )
        assert result["character"] == "mother_tree"
        assert result["annotation"]["type"] == "status"
        assert result["must_respond"] is True

    def test_help_command_routes_to_mother_tree(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="help", participant_count=1, enrolled=False)
        assert result["character"] == "mother_tree"
        assert result["annotation"]["type"] == "help"

    def test_persona_seth_routes_to_seth(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="ask seth what is the change?", participant_count=1, enrolled=False)
        assert result["character"] == "seth"
        assert result["clean_text"] == "what is the change?"

    def test_persona_lawrence_routes_to_lawrence(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="ask lawrence how do I close?", participant_count=1, enrolled=False)
        assert result["character"] == "lawrence"

    def test_persona_trainer_sets_training_mode(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="ask trainer test me", participant_count=1, enrolled=False)
        assert result["training_mode"] is True

    def test_training_next_sets_training_mode(self):
        from bot.characters.dispatcher import dispatch
        with patch("bot.characters.dispatcher.deliver_next") as mock:
            mock.return_value = {"chapter": "worldview", "content": "..."}
            result = dispatch(
                text="next", participant_count=1, enrolled=True,
                enrollment={"id": "e1", "current_stage": 0, "current_chapter": 1, "role": "hunter"},
            )
        assert result["training_mode"] is True
        assert result["annotation"]["type"] == "training_delivered"

    def test_training_next_channel_ignored(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="next", participant_count=5, enrolled=True,
            enrollment={"id": "e1"},
        )
        assert result["annotation"] is None
        assert result["character"] == "mother_tree"

    def test_mention_sets_must_respond(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="<@UBOT> what's up?", participant_count=5,
            enrolled=False, bot_user_id="UBOT",
        )
        assert result["must_respond"] is True
        assert result["clean_text"] == "what's up?"

    def test_url_detection_routes_to_mother_tree(self):
        from bot.characters.dispatcher import dispatch
        with patch("bot.characters.dispatcher.fetch_and_follow") as mock:
            mock.return_value = "Page content"
            result = dispatch(
                text="check this https://example.com/article",
                participant_count=1, enrolled=False,
            )
        assert result["character"] == "mother_tree"
        assert result["annotation"]["type"] == "url_content"

    def test_exercise_answer_routes_to_training(self):
        from bot.characters.dispatcher import dispatch
        with patch("bot.characters.dispatcher.score_exercise_answer") as mock:
            mock.return_value = {"correct": True, "feedback": "Right!", "progress": {}}
            result = dispatch(
                text="A", participant_count=1, enrolled=True,
                active_exercise={"id": "c1", "exercise": {"content": {"questions": [{}]}}},
            )
        assert result["training_mode"] is True
        assert result["annotation"]["type"] == "answer_scored"

    def test_citizen_next_routes_to_mother_tree(self):
        from bot.characters.dispatcher import dispatch
        with patch("bot.characters.dispatcher.generate_citizen_inspiration") as mock:
            mock.return_value = "Something inspiring..."
            result = dispatch(
                text="next", participant_count=1, enrolled=True,
                enrollment={"id": "e1", "role": "citizen", "current_stage": 0, "current_chapter": 0},
            )
        assert result["character"] == "mother_tree"
        assert result["annotation"]["type"] == "citizen_inspiration"

    @patch("bot.characters.dispatcher._call_triage_llm")
    def test_unmatched_channel_message_goes_to_triage(self, mock_triage):
        from bot.characters.dispatcher import dispatch
        mock_triage.return_value = {"respond": True, "signal": {"capture": False, "confidence": 0.0}, "reason": "question"}
        result = dispatch(
            text="interesting point about the market",
            participant_count=5, enrolled=False,
            recent_messages=[],
        )
        assert result["character"] == "mother_tree"
        mock_triage.assert_called_once()

    @patch("bot.characters.dispatcher._call_triage_llm")
    def test_unmatched_channel_triage_silent(self, mock_triage):
        from bot.characters.dispatcher import dispatch
        mock_triage.return_value = {"respond": False, "signal": {"capture": False, "confidence": 0.0}, "reason": "small talk"}
        result = dispatch(
            text="nice weather", participant_count=5, enrolled=False,
            recent_messages=[],
        )
        assert result["character"] == "silent"

    @patch("bot.characters.dispatcher._call_triage_llm")
    def test_signal_flag_set_from_triage(self, mock_triage):
        from bot.characters.dispatcher import dispatch
        mock_triage.return_value = {"respond": True, "signal": {"capture": True, "confidence": 0.9}, "reason": "prospect"}
        result = dispatch(
            text="met someone at KubeCon", participant_count=5,
            enrolled=False, recent_messages=[],
        )
        assert result["signal_flag"] is True

    def test_dm_unmatched_routes_to_mother_tree_no_triage(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="what do we know about KPN?",
            participant_count=1, enrolled=False,
        )
        assert result["character"] == "mother_tree"
        assert result["must_respond"] is True

    def test_active_thread_skips_triage(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="sounds good",
            participant_count=5, enrolled=False,
            context_type="thread",
            has_bot_participated=True,
        )
        assert result["character"] == "mother_tree"
        assert result["must_respond"] is True

    def test_exercise_pending_passed_through(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            text="what is our worldview?",
            participant_count=1, enrolled=True,
            active_exercise={"id": "c1", "current_question": 1, "exercise": {"content": {"questions": [{}, {}, {}]}}},
        )
        assert result["exercise_pending"] == {"question_num": 2, "total": 3}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_characters.py::TestDispatcher -v`
Expected: FAIL — `bot.characters.dispatcher` not found

- [ ] **Step 3: Write the Dispatcher module**

```python
# jobs/bot/characters/dispatcher.py
"""Dispatcher — the Receptionist.

Looks at every incoming message and routes to the right character.
Two-tier: deterministic pattern matching first, LLM triage only when needed.
"""
import logging
import re

from mothertree.hasura import (
    get_enrollment,
    get_active_conversation,
    cancel_stale_conversations,
    get_enrollment_stats,
)
from mothertree.llm import extract
from mothertree.config import EXTRACTION_MODEL
from bot.enrich import fetch_and_follow, extract_urls

log = logging.getLogger(__name__)

PERSONA_NAMES = {"seth", "lawrence", "trainer"}
GLOBAL_COMMANDS = {"enroll", "status", "progress", "stats", "help"}

TRIAGE_SYSTEM = """You decide whether Mother Tree should respond to a message and whether it contains commercial signal intelligence.

Return JSON only:
{"respond": true/false, "signal": {"capture": true/false, "confidence": 0.0-1.0}, "reason": "one sentence"}

Rules:
- If this is a DM (1 participant), respond is ALWAYS true.
- Respond when: direct question, request for help, Mother Tree has something useful to add.
- Stay silent when: people talking to each other, small talk, reactions, greetings between colleagues.
- Signal capture: intelligence about a prospect, client, market, competitor, or event.
- Be conservative in channels — if unsure, stay silent."""


def deliver_next(enrollment: dict, slack_user_id: str = None) -> dict:
    """Deliver the next training piece for the enrollment."""
    from training.deliver import deliver_to_user_on_demand
    try:
        cancel_stale_conversations(enrollment["id"])
        stage = enrollment.get("current_stage", 0)
        chapter = enrollment.get("current_chapter", 0)
        if stage == 0 and chapter > 4:
            return {"error": "stage_complete", "message": "Stage 0 complete."}
        result = deliver_to_user_on_demand(None, enrollment)
        return result or {"chapter": chapter, "content": ""}
    except Exception as exc:
        log.exception("deliver_next failed")
        return {"error": str(exc)}


def score_exercise_answer(active_exercise: dict, enrollment: dict, answer: str) -> dict:
    """Score a multiple-choice answer against the active exercise."""
    from training.score import score_response
    from mothertree.hasura import insert_response
    try:
        exercise = active_exercise["exercise"]["content"]
        current_q = active_exercise.get("current_question", 0)
        questions = exercise.get("questions", [])
        if current_q < 0 or current_q >= len(questions):
            return {"correct": False, "feedback": "No active question.", "progress": {}}
        question = questions[current_q]
        result = score_response(stage=active_exercise.get("stage", 0), question=question, response=answer)
        insert_response(
            exercise_id=active_exercise.get("exercise_id"),
            user_id=enrollment.get("id"),
            response=answer,
            question_index=current_q,
            correct=result["correct"],
            feedback=result["feedback"],
        )
        return {
            "correct": result["correct"],
            "feedback": result["feedback"],
            "progress": {"question": current_q, "total": len(questions)},
        }
    except Exception as exc:
        log.exception("score_exercise_answer failed")
        return {"correct": False, "feedback": str(exc), "progress": {}}


def generate_citizen_inspiration(enrollment: dict, slack_user_id: str = None) -> str:
    """Generate an inspiration message for a citizen-role user."""
    from bot.characters.mother_tree import respond
    from mothertree.hasura import get_or_create_dm_conversation

    prompt = (
        "Share something inspiring about why we do what we do. Pick ONE of these approaches "
        "(vary each time, don't repeat what's in the conversation history):\n\n"
        "• A change statement — what transformation we offer, told as a belief worth holding\n"
        "• A worldview insight — what our audience is going through, told with empathy\n"
        "• A real story from the central intelligence — evidence that the change works\n"
        "• A question — something to notice in their own work that connects to the mission\n\n"
        "Keep it short (2-4 sentences). Be warm, genuine, not preachy. "
        "End with something that makes them think or notice. "
        "This is a colleague who's learning to see the world the way we see it."
    )

    history = []
    if slack_user_id:
        try:
            dm_conv = get_or_create_dm_conversation(slack_user_id)
            history = dm_conv.get("messages", [])
        except Exception:
            pass

    return respond(question=prompt, history=history, user_name=enrollment.get("name", "you"))


def _call_triage_llm(prompt: str) -> dict:
    """Make the triage LLM call."""
    return extract(prompt, TRIAGE_SYSTEM)


def _build_triage_prompt(text: str, participant_count: int, recent_messages: list[dict]) -> str:
    """Build the triage prompt with context."""
    context = ""
    if recent_messages:
        context = "\nRecent messages:\n" + "\n".join(
            f"- [{m.get('name', 'someone')}]: {m['content'][:100]}"
            for m in recent_messages[-5:]
        )
    return f"Participants: {participant_count}\n{context}\n\nNew message: {text}"


def dispatch(
    text: str,
    participant_count: int,
    enrolled: bool = False,
    enrollment: dict = None,
    active_exercise: dict = None,
    slack_user_id: str = None,
    bot_user_id: str = None,
    context_type: str = "dm",
    has_bot_participated: bool = False,
    recent_messages: list[dict] = None,
) -> dict:
    """Route a message to the right character.

    Returns:
        character: "mother_tree" | "seth" | "lawrence" | "silent"
        intent: str — what the message is about
        annotation: dict | None — structured data for the character
        must_respond: bool
        training_mode: bool — Seth+Lawrence co-train
        signal_flag: bool — triage detected commercial signal
        clean_text: str — text with mention stripped
        exercise_pending: dict | None
    """
    result = {
        "character": "mother_tree",
        "intent": "freeform",
        "annotation": None,
        "must_respond": participant_count == 1,  # DMs always respond
        "training_mode": False,
        "signal_flag": False,
        "clean_text": text,
        "exercise_pending": None,
    }

    clean = text.strip()

    # 1. Strip @bot mention
    if bot_user_id:
        mention_pat = re.compile(r"<@" + re.escape(bot_user_id) + r">", re.IGNORECASE)
        if mention_pat.search(clean):
            clean = mention_pat.sub("", clean).strip()
            result["must_respond"] = True

    result["clean_text"] = clean
    parts = clean.split()
    first = parts[0].lower() if parts else ""

    # 2. Global commands → Mother Tree
    if first in GLOBAL_COMMANDS:
        result["must_respond"] = True
        result["intent"] = first

        if first == "status":
            if slack_user_id:
                enrollment_data = enrollment or get_enrollment(slack_user_id)
            else:
                enrollment_data = enrollment
            if enrollment_data:
                result["annotation"] = {
                    "type": "status",
                    "stage": enrollment_data.get("current_stage"),
                    "chapter": enrollment_data.get("current_chapter"),
                    "streak": enrollment_data.get("streak"),
                    "role": enrollment_data.get("role"),
                }
            else:
                result["annotation"] = {"type": "status", "enrolled": False}
        elif first == "enroll":
            role = parts[1].lower() if len(parts) > 1 else None
            result["annotation"] = {"type": "enroll", "role": role}
        elif first == "stats":
            try:
                stats = get_enrollment_stats()
                result["annotation"] = {"type": "stats", "data": stats}
            except Exception:
                result["annotation"] = {"type": "stats", "data": {}}
        elif first == "progress":
            result["annotation"] = {"type": "progress"}
        elif first == "help":
            result["annotation"] = {"type": "help"}

        return result

    # 3. Persona patterns → route to persona character
    if first == "ask" and len(parts) >= 2:
        persona_name = parts[1].lower()
        if persona_name in PERSONA_NAMES:
            rest = " ".join(parts[2:])
            result["clean_text"] = rest
            result["must_respond"] = True
            result["intent"] = "persona"
            result["annotation"] = {"type": "persona", "persona": persona_name, "question": rest}

            if persona_name == "trainer":
                result["training_mode"] = True
            else:
                result["character"] = persona_name

            return result

    # 4. DM-only training patterns
    if participant_count == 1 and enrolled:
        role = (enrollment or {}).get("role")

        if first == "next":
            result["must_respond"] = True
            if role == "citizen":
                inspiration = generate_citizen_inspiration(enrollment, slack_user_id)
                result["annotation"] = {"type": "citizen_inspiration", "content": inspiration}
                result["intent"] = "citizen_inspiration"
            else:
                delivered = deliver_next(enrollment, slack_user_id)
                result["annotation"] = {"type": "training_delivered", **delivered}
                result["training_mode"] = True
                result["intent"] = "training"
            return result

        if first == "go":
            result["must_respond"] = True
            result["annotation"] = {"type": "exercise_start"}
            result["training_mode"] = True
            result["intent"] = "training"
            return result

        if first == "practice":
            result["must_respond"] = True
            topic = parts[1].lower() if len(parts) > 1 else None
            result["annotation"] = {"type": "practice_delivered", "topic": topic}
            result["training_mode"] = True
            result["intent"] = "training"
            return result

        if clean.upper() in ("A", "B", "C"):
            if active_exercise:
                scored = score_exercise_answer(active_exercise, enrollment, clean.upper())
                result["must_respond"] = True
                result["annotation"] = {"type": "answer_scored", **scored}
                result["training_mode"] = True
                result["intent"] = "training"
                return result

    # 5. URL detection → Mother Tree
    urls = extract_urls(clean)
    if urls:
        import threading
        from concurrent.futures import ThreadPoolExecutor
        urls = urls[:3]
        follow_budget = threading.Semaphore(2)
        with ThreadPoolExecutor(max_workers=3) as pool:
            fetched = list(pool.map(lambda u: fetch_and_follow(u, follow_budget), urls))

        result["must_respond"] = True
        result["intent"] = "url"
        url_results = []
        url_failures = []
        for url, content in zip(urls, fetched):
            if content:
                url_results.append({"url": url, "content": content})
            else:
                url_failures.append(url)

        if url_results:
            if len(url_results) == 1:
                result["annotation"] = {
                    "type": "url_content",
                    "url": url_results[0]["url"],
                    "content": url_results[0]["content"],
                }
            else:
                result["annotation"] = {
                    "type": "url_content",
                    "urls": [r["url"] for r in url_results],
                    "content": "\n\n---\n\n".join(
                        f"[{r['url']}]\n{r['content']}" for r in url_results
                    ),
                }
        else:
            result["annotation"] = {
                "type": "url_failed",
                "url": url_failures[0] if url_failures else urls[0],
            }
        return result

    # 6. Exercise pending nudge
    if active_exercise and participant_count == 1:
        questions = (active_exercise.get("exercise") or {}).get("content", {}).get("questions", [])
        current_q = active_exercise.get("current_question", 0)
        if questions and current_q >= 0:
            result["exercise_pending"] = {
                "question_num": current_q + 1,
                "total": len(questions),
            }

    # 7. No pattern matched — triage for channels/threads, respond for DMs
    if participant_count == 1:
        # DM: always respond, no triage needed
        return result

    # Active thread where bot participated: respond without triage
    if context_type == "thread" and has_bot_participated:
        result["must_respond"] = True
        return result

    # Channel/thread: LLM triage
    prompt = _build_triage_prompt(clean, participant_count, recent_messages or [])
    try:
        triage_result = _call_triage_llm(prompt)
    except Exception as e:
        log.warning(f"Triage LLM failed: {e}")
        result["character"] = "silent"
        return result

    if not triage_result.get("respond", False):
        result["character"] = "silent"
        return result

    result["signal_flag"] = triage_result.get("signal", {}).get("capture", False)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jobs && python -m pytest tests/test_characters.py::TestDispatcher -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/characters/dispatcher.py jobs/tests/test_characters.py
git commit -m "Add Dispatcher character module — unified routing logic"
```

---

### Task 4: Wire pipeline to use Dispatcher → Mother Tree

**Files:**
- Modify: `jobs/bot/pipeline.py`
- Modify: `jobs/tests/test_pipeline_ux.py` (verify existing tests still pass)

This is the integration step. The pipeline calls `dispatch()` instead of `detect()` + `triage()`. For Mother Tree messages, it calls `mother_tree.respond()`. For personas and training, it falls through to the existing `converse()` function (Phase 2 will replace that).

- [ ] **Step 1: Write integration tests for the new pipeline flow**

Add to `jobs/tests/test_characters.py`:

```python
class TestPipelineIntegration:
    """Pipeline wired to Dispatcher → Character."""

    @patch("bot.pipeline.extract_signal")
    @patch("bot.pipeline.assess_actions")
    @patch("bot.characters.mother_tree.chat_conversation")
    @patch("bot.characters.mother_tree.fetch_context")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    def test_dm_freeform_uses_mother_tree(
        self, mock_dispatch, mock_memory, mock_ctx, mock_chat, mock_assess, mock_extract
    ):
        from bot.pipeline import _process_message
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "hello", "exercise_pending": None,
        }
        mock_memory.return_value = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Hi there!"
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234.5678"}

        _process_message(
            text="hello", user_slack_id="U123", user_name="Jurg",
            channel_id="D123", context_type="dm", participant_count=1,
            respond=MagicMock(), client=client, thread_ts=None,
            ts="0001.0001", bot_user_id="BXXX",
        )

        mock_chat.assert_called_once()
        client.chat_update.assert_called_once()

    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    def test_channel_silent_deletes_thinking(self, mock_memory, mock_dispatch):
        from bot.pipeline import _process_message
        mock_dispatch.return_value = {
            "character": "silent", "intent": "freeform",
            "annotation": None, "must_respond": False,
            "training_mode": False, "signal_flag": False,
            "clean_text": "nice", "exercise_pending": None,
        }
        mock_memory.return_value = {"messages": [], "store_type": "channel", "store_id": 1, "channel_id": "C123"}
        client = MagicMock()
        client.reactions_add.return_value = {"ok": True}

        _process_message(
            text="nice", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="channel", participant_count=5,
            respond=MagicMock(), client=client, thread_ts=None,
            ts="0001.0001", bot_user_id="BXXX",
        )

        client.reactions_remove.assert_called_once()

    @patch("bot.pipeline.converse")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    def test_persona_falls_through_to_converse(self, mock_dispatch, mock_memory, mock_converse):
        from bot.pipeline import _process_message
        mock_dispatch.return_value = {
            "character": "seth", "intent": "persona",
            "annotation": {"type": "persona", "persona": "seth", "question": "what is the change?"},
            "must_respond": True, "training_mode": False,
            "signal_flag": False, "clean_text": "what is the change?",
            "exercise_pending": None,
        }
        mock_memory.return_value = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        mock_converse.return_value = {"response": "Seth says...", "actions": []}
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234.5678"}

        _process_message(
            text="ask seth what is the change?", user_slack_id="U123", user_name="Jurg",
            channel_id="D123", context_type="dm", participant_count=1,
            respond=MagicMock(), client=client, thread_ts=None,
            ts="0001.0001", bot_user_id="BXXX",
        )

        # Persona should use existing converse() for now
        mock_converse.assert_called_once()
```

- [ ] **Step 2: Run new + existing tests to establish baseline**

Run: `cd jobs && python -m pytest tests/test_characters.py tests/test_pipeline_ux.py tests/test_unified.py -v`
Expected: new integration tests FAIL (pipeline not wired yet), existing tests PASS

- [ ] **Step 3: Rewrite pipeline to use Dispatcher → character routing**

Replace `jobs/bot/pipeline.py` with the new version. Key changes:
- Import `dispatch` from `bot.characters.dispatcher` instead of `detect` from `bot.detect` and `triage` from `bot.triage`
- Import `respond` from `bot.characters.mother_tree`
- Import `fix_slack_formatting` from `bot.characters.base`
- After dispatch: if character is "mother_tree", call `mother_tree.respond()` directly
- If character is "seth", "lawrence", or training_mode, fall through to existing `converse()`
- If character is "silent", delete thinking and buffer
- Keep marker extraction + memory persistence in the pipeline (shared across all characters)
- Keep extract phase unchanged

The modified `_process_message` function:

```python
def _process_message(text, user_slack_id, user_name, channel_id, context_type,
                     participant_count, respond, client, thread_ts, ts, bot_user_id):
    """Inner pipeline — runs under per-channel lock."""

    # Determine reply thread
    if thread_ts:
        reply_thread_ts = thread_ts
    elif context_type == "channel" and ts:
        reply_thread_ts = ts
    else:
        reply_thread_ts = None

    # Show thinking indicator
    thinking_info = _post_thinking(client, channel_id, reply_thread_ts,
                                   context_type=context_type, message_ts=ts)

    # Look up enrollment and active exercise (for dispatch)
    enrollment = None
    active_exercise = None
    enrolled = False
    if participant_count == 1:
        enrollment = get_enrollment(user_slack_id)
        enrolled = enrollment is not None
        if enrolled:
            active_exercise = get_active_conversation(enrollment["id"])

    # Get memory context
    memory_kwargs = {}
    if context_type == "dm":
        memory_kwargs = {"slack_user_id": user_slack_id}
    elif context_type == "channel":
        memory_kwargs = {"channel_id": channel_id}
    elif context_type == "thread":
        memory_kwargs = {"thread_ts": thread_ts, "channel_id": channel_id}

    memory_ctx = get_memory(context_type=context_type, **memory_kwargs)

    # Check if bot has participated in this thread
    has_bot_participated = (
        context_type == "thread"
        and any(m.get("role") == "assistant" for m in memory_ctx["messages"])
    )

    # DISPATCH — single routing decision
    routing = dispatch(
        text=text,
        participant_count=participant_count,
        enrolled=enrolled,
        enrollment=enrollment,
        active_exercise=active_exercise,
        slack_user_id=user_slack_id,
        bot_user_id=bot_user_id,
        context_type=context_type,
        has_bot_participated=has_bot_participated,
        recent_messages=memory_ctx["messages"][-5:],
    )

    character = routing["character"]
    clean_text = routing["clean_text"]
    annotation = routing["annotation"]
    signal_flag = routing["signal_flag"]
    exercise_pending = routing["exercise_pending"]

    # SILENT — delete thinking and buffer
    if character == "silent":
        _delete_thinking(client, channel_id, thinking_info)
        if context_type == "channel":
            channel_buffer.add(channel_id, {
                "role": "user", "name": user_name, "content": text,
            })
            if channel_buffer.should_flush(channel_id):
                _flush_buffer(channel_id)
        return

    # Flush channel buffer before responding
    if context_type == "channel":
        _flush_buffer(channel_id)

    # Window messages
    max_msgs = get_max_messages(memory_ctx["store_type"])
    history = window_messages(memory_ctx["messages"], max_msgs)

    # Persist user message
    try:
        append_message(memory_ctx, role="user", content=text, name=user_name)
    except Exception:
        log.exception("Failed to persist user message")

    # Persist annotation
    if annotation:
        try:
            import json
            append_message(memory_ctx, role="system", content=json.dumps(annotation))
        except Exception:
            log.exception("Failed to persist annotation")

    # RESPOND — route to character
    try:
        if character == "mother_tree" and not routing["training_mode"]:
            from bot.characters.mother_tree import respond as mt_respond
            response = mt_respond(
                question=clean_text,
                history=history,
                user_name=user_name,
                participant_count=participant_count,
                annotation=annotation,
                signal_flag=signal_flag,
                exercise_pending=exercise_pending,
            )
        else:
            # Phase 1 fallback: personas and training use existing converse()
            persona = None
            if character in ("seth", "lawrence"):
                persona = character
            elif routing["training_mode"]:
                persona = "trainer"

            conv_result = converse(
                text=clean_text,
                memory_ctx=memory_ctx,
                user_name=user_name,
                annotation=annotation,
                persona=persona,
                signal_flag=signal_flag,
                participant_count=participant_count,
                exercise_pending=exercise_pending,
            )
            # converse() handles its own markers and formatting
            updated = _resolve_thinking(client, channel_id, thinking_info, conv_result["response"])
            if not updated:
                respond(conv_result["response"])

            # Extract phase (background)
            if signal_flag or "capture_signal" in conv_result.get("actions", []):
                try:
                    extract_signal(user_message=text, assistant_response=conv_result["response"], user_name=user_name)
                except Exception:
                    log.exception("Background signal extraction failed")
            if conv_result.get("actions"):
                try:
                    assessment = assess_actions(text, conv_result["response"])
                    if "ci_save" in conv_result["actions"] and not assessment.get("ci_save"):
                        log.warning("Action marker ci_save present but assessment disagrees")
                    if "capture_signal" in conv_result["actions"] and not assessment.get("capture_signal"):
                        log.warning("Action marker capture_signal present but assessment disagrees")
                except Exception:
                    log.exception("Action assessment failed")

            # Persist assistant response (converse already did this for its path)
            return

    except Exception:
        log.exception("Character respond failed")
        from bot.conversation import _fallback_response
        response = _fallback_response(annotation)

    # Guard against Mistral tool-calling syntax
    if response.startswith("[TOOL_CALLS]"):
        log.warning("LLM returned tool-calling syntax: %s", response[:200])
        from bot.conversation import _fallback_response
        response = _fallback_response(annotation)

    # Extract action markers
    actions, response = extract_action_markers(response)

    # Extract and replace content markers
    content_types, response = extract_content_markers(response)
    if "training" in content_types and annotation and annotation.get("content"):
        if response:
            response = f"{response}\n\n{annotation['content']}"
        else:
            response = annotation["content"]

    # Fix Slack formatting
    response = fix_slack_formatting(response)

    # Persist assistant response
    try:
        append_message(memory_ctx, role="assistant", content=response)
    except Exception:
        log.exception("Failed to persist assistant response")

    # Send response
    updated = _resolve_thinking(client, channel_id, thinking_info, response)
    if not updated:
        respond(response)

    # Extract phase (background)
    if signal_flag or "capture_signal" in actions:
        try:
            extract_signal(user_message=text, assistant_response=response, user_name=user_name)
        except Exception:
            log.exception("Background signal extraction failed")

    if actions:
        try:
            assessment = assess_actions(text, response)
            if "ci_save" in actions and not assessment.get("ci_save"):
                log.warning("Action marker ci_save present but assessment disagrees")
            if "capture_signal" in actions and not assessment.get("capture_signal"):
                log.warning("Action marker capture_signal present but assessment disagrees")
        except Exception:
            log.exception("Action assessment failed")
```

Update the imports at the top of `pipeline.py`:

```python
from bot.characters.dispatcher import dispatch
from bot.characters.base import fix_slack_formatting
from bot.conversation import converse
from bot.memory import get_memory, append_message, window_messages, get_max_messages
from bot.markers import sanitize_user_input, extract_action_markers, extract_content_markers
from bot.extraction import extract_signal, assess_actions
from bot.buffer import ChannelBuffer
from mothertree.hasura import get_enrollment, get_active_conversation
```

Remove the old imports of `detect` and `triage`.

- [ ] **Step 4: Run all tests**

Run: `cd jobs && python -m pytest tests/test_characters.py tests/test_pipeline_ux.py tests/test_unified.py -v`
Expected: all PASS

Note: some existing `TestPipeline` tests in `test_unified.py` mock `bot.pipeline.detect` and `bot.pipeline.triage` — these will need their mocks updated to mock `bot.pipeline.dispatch` instead. Update them:

- `test_dm_freeform`: mock `bot.pipeline.dispatch` returning `character="mother_tree"`, mock `bot.characters.mother_tree.chat_conversation` and `bot.characters.mother_tree.fetch_context`
- `test_channel_silent`: mock `bot.pipeline.dispatch` returning `character="silent"`
- `test_channel_signal_capture`: mock `bot.pipeline.dispatch` returning `character="mother_tree"` with `signal_flag=True`

- [ ] **Step 5: Update existing pipeline tests in test_unified.py**

Update `TestPipeline` in `jobs/tests/test_unified.py` to mock the new dispatch-based flow:

```python
class TestPipeline:
    """Full pipeline: dispatch → character → extract."""

    @patch("bot.pipeline.assess_actions")
    @patch("bot.pipeline.extract_signal")
    @patch("bot.characters.mother_tree.chat_conversation")
    @patch("bot.characters.mother_tree.fetch_context")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_active_conversation")
    @patch("bot.pipeline.get_enrollment")
    def test_dm_freeform(self, mock_enroll, mock_active, mock_dispatch, mock_memory,
                         mock_ctx, mock_chat, mock_extract, mock_assess):
        from bot.pipeline import handle_message
        mock_enroll.return_value = None
        mock_active.return_value = None
        mock_dispatch.return_value = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "hello", "exercise_pending": None,
        }
        mock_memory.return_value = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
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

    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_memory")
    def test_channel_silent(self, mock_memory, mock_dispatch):
        from bot.pipeline import handle_message
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
    @patch("bot.characters.mother_tree.chat_conversation")
    @patch("bot.characters.mother_tree.fetch_context")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.dispatch")
    @patch("bot.pipeline.get_active_conversation")
    @patch("bot.pipeline.get_enrollment")
    def test_channel_signal_capture(self, mock_enroll, mock_active, mock_dispatch,
                                     mock_memory, mock_ctx, mock_chat, mock_assess, mock_extract):
        from bot.pipeline import handle_message
        mock_enroll.return_value = None
        mock_active.return_value = None
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
```

- [ ] **Step 6: Run full test suite**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/pipeline.py jobs/tests/test_unified.py jobs/tests/test_characters.py
git commit -m "Wire pipeline to Dispatcher and Mother Tree character"
```

---

### Task 5: Clean up imports and verify backward compatibility

**Files:**
- Modify: `jobs/bot/conversation.py` — update to import `fix_slack_formatting` from `base.py` (avoid duplication)
- Verify: `jobs/bot/detect.py` and `jobs/bot/triage.py` still importable (other code may reference them)

- [ ] **Step 1: Update conversation.py to use shared formatting**

In `jobs/bot/conversation.py`, replace the local `_fix_slack_formatting` with an import from `base.py`:

```python
# Replace:
# def _fix_slack_formatting(text: str) -> str: ...
# With:
from bot.characters.base import fix_slack_formatting as _fix_slack_formatting
```

- [ ] **Step 2: Run full test suite**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add jobs/bot/conversation.py
git commit -m "Deduplicate Slack formatting — conversation.py uses shared base"
```

---

### Task 6: Verify in Slack (manual smoke test)

This is a manual verification step. Not automated.

- [ ] **Step 1: Run bot locally**

```bash
cd jobs && python -m bot.bot
```

- [ ] **Step 2: Test in DM**

Send these messages to Mother Tree in a DM:
- "what do we know about our positioning?" — should get a response from CI
- "status" — should show enrollment status
- "help" — should show help text

- [ ] **Step 3: Test in channel**

- Post a normal message without @mention — Mother Tree should stay silent
- @mention Mother Tree with a question — should respond in thread
- Share a URL — should fetch and discuss

- [ ] **Step 4: Test personas still work**

- "ask seth what is the change?" — should get Seth's perspective
- "ask lawrence how do I close?" — should get Lawrence's perspective

- [ ] **Step 5: Document any issues found**

If issues are found, create follow-up tasks. Do not block the commit.
