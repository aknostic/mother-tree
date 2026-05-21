# DM Flow Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the bot DM handler from command-routed to conversation-first — persistent history, CI-grounded answers, URL ingestion, no hallucination.

**Architecture:** Every DM goes through a pipeline: commands (deterministic) → training exercise (if active) → freeform conversation (LLM with history). One persistent conversation record per user (stage -1). URL content is fetched on user request and optionally saved to CI.

**Tech Stack:** Python 3, Slack Bolt (Socket Mode), Scaleway AI (Qwen 3 235B for conversation), PostgreSQL + Hasura GraphQL, httpx + BeautifulSoup (URL fetching).

**Spec:** `docs/superpowers/specs/2026-03-21-dm-flow-redesign.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `jobs/bot/dm_pipeline.py` | The DM message pipeline: command check → exercise check → URL check → conversation. Orchestrates all DM logic. |
| `jobs/bot/dm_conversation.py` | Freeform conversation: build LLM messages from history + CI context, call LLM, append to history. |
| `jobs/bot/dm_url.py` | URL detection, fetching, conversation ingestion, CI save flow. |

### Modified files

| File | Changes |
|------|---------|
| `jobs/bot/bot.py` | Replace `handle_dm` body with call to `dm_pipeline.handle()`. Remove command-routing logic. |
| `jobs/bot/training_dm.py` | Add `is_command()` function. Update `parse_dm_command` to return "conversation" instead of "unknown". |
| `jobs/mothertree/hasura.py` | Add `get_or_create_dm_conversation()`, `append_dm_message()`. Update `cancel_stale_conversations()` to exclude stage -1. Add `slack_user_id` column handling. |
| `jobs/mothertree/llm.py` | Add `chat_conversation()` for multi-turn DM (generation model, 2000 tokens, 0.7 temp). |
| `jobs/mothertree/ask.py` | Add `ask_with_history()` that accepts message history for context-aware answers. |
| `deploy/database/schema.sql` | Add `slack_user_id TEXT` column to conversations table. |
| `jobs/tests/test_training.py` | Add test classes for new modules. |

---

## Task 1: Schema + Hasura for DM conversations

Add `slack_user_id` to conversations and build the persistence functions.

**Files:**
- Modify: `deploy/database/schema.sql`
- Modify: `jobs/mothertree/hasura.py`
- Test: `jobs/tests/test_training.py`

- [ ] **Step 1: Write tests for DM conversation persistence**

Add to `jobs/tests/test_training.py`:

```python
class TestDMConversation:
    """Test freeform DM conversation persistence."""

    @patch("mothertree.hasura.graphql")
    def test_get_or_create_dm_conversation_existing(self, mock_gql):
        from mothertree.hasura import get_or_create_dm_conversation
        mock_gql.return_value = {"conversations": [{
            "id": "c-dm-1", "stage": -1, "state": "active",
            "messages": [{"role": "user", "content": "hello"}],
        }]}
        result = get_or_create_dm_conversation("U123")
        assert result["id"] == "c-dm-1"
        assert result["stage"] == -1

    @patch("mothertree.hasura.graphql")
    def test_get_or_create_dm_conversation_creates_new(self, mock_gql):
        from mothertree.hasura import get_or_create_dm_conversation
        # First call: no existing conversation
        # Second call: insert returns new ID
        mock_gql.side_effect = [
            {"conversations": []},
            {"insert_conversations_one": {"id": "c-dm-new"}},
        ]
        result = get_or_create_dm_conversation("U123")
        assert result["id"] == "c-dm-new"
        assert mock_gql.call_count == 2

    @patch("mothertree.hasura.graphql")
    def test_append_dm_message(self, mock_gql):
        from mothertree.hasura import append_dm_message
        mock_gql.return_value = {"update_conversations_by_pk": {"id": "c-1"}}
        append_dm_message("c-1", role="user", content="hello")
        call_args = mock_gql.call_args
        assert "update_conversations_by_pk" in call_args[0][0]

    @patch("mothertree.hasura.graphql")
    def test_cancel_stale_conversations_excludes_dm(self, mock_gql):
        from mothertree.hasura import cancel_stale_conversations
        mock_gql.return_value = {"update_conversations": {"affected_rows": 1}}
        cancel_stale_conversations(user_id="u-1")
        query = mock_gql.call_args[0][0]
        assert "stage" in query  # must filter out stage -1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMConversation -v`
Expected: ImportError or assertion failure.

- [ ] **Step 3: Add slack_user_id to schema**

Add to `deploy/database/schema.sql` in the conversations table:

```sql
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS slack_user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_conversations_slack_user_id ON conversations(slack_user_id);
```

- [ ] **Step 4: Implement Hasura functions**

Add to `jobs/mothertree/hasura.py` after the existing training section:

```python
# --- DM Conversations ---

def get_or_create_dm_conversation(slack_user_id: str) -> dict:
    """Get or create the persistent freeform DM conversation for a user."""
    result = graphql("""
        query($sid: String!) {
            conversations(
                where: {slack_user_id: {_eq: $sid}, stage: {_eq: -1}},
                limit: 1
            ) { id stage state messages }
        }
    """, {"sid": slack_user_id})
    convs = result["conversations"]
    if convs:
        return convs[0]

    result = graphql("""
        mutation($obj: conversations_insert_input!) {
            insert_conversations_one(object: $obj) { id }
        }
    """, {"obj": {
        "slack_user_id": slack_user_id,
        "stage": -1,
        "state": "active",
        "messages": [],
        "current_question": -1,
    }})
    return {
        "id": result["insert_conversations_one"]["id"],
        "stage": -1,
        "state": "active",
        "messages": [],
    }


def append_dm_message(conversation_id: str, role: str, content: str) -> None:
    """Append a message to the DM conversation history."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    graphql("""
        mutation($id: uuid!, $message: jsonb!) {
            update_conversations_by_pk(
                pk_columns: {id: $id},
                _append: {messages: $message}
            ) { id }
        }
    """, {"id": conversation_id, "message": {"role": role, "content": content, "ts": ts}})


def set_pending_ci_save(conversation_id: str, url: str) -> None:
    """Set a pending CI save flag in the conversation messages."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    graphql("""
        mutation($id: uuid!, $message: jsonb!) {
            update_conversations_by_pk(
                pk_columns: {id: $id},
                _append: {messages: $message}
            ) { id }
        }
    """, {"id": conversation_id, "message": {
        "role": "system", "content": "pending_ci_save", "url": url, "ts": ts,
    }})
```

Also update `cancel_stale_conversations` to exclude stage -1:

```python
def cancel_stale_conversations(user_id: str) -> int:
    """Cancel all non-complete conversations for a user. Excludes freeform DM (stage -1)."""
    result = graphql("""
        mutation($uid: uuid!) {
            update_conversations(
                where: {user_id: {_eq: $uid}, state: {_neq: "complete"}, stage: {_neq: -1}},
                _set: {state: "complete"}
            ) { affected_rows }
        }
    """, {"uid": user_id})
    return result["update_conversations"]["affected_rows"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMConversation -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add deploy/database/schema.sql jobs/mothertree/hasura.py jobs/tests/test_training.py
git commit -m "Add DM conversation persistence: get_or_create, append, exclude from cancel"
```

---

## Task 2: LLM conversation function

Add multi-turn conversation support to the LLM module.

**Files:**
- Modify: `jobs/mothertree/llm.py`
- Test: `jobs/tests/test_training.py`

- [ ] **Step 1: Write tests**

```python
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
        assert call_kwargs["max_tokens"] == 2000

    @patch("mothertree.llm.scaleway")
    def test_chat_conversation_uses_generation_model(self, mock_scaleway):
        from mothertree.llm import chat_conversation
        from mothertree.config import GENERATION_MODEL
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_scaleway.chat.completions.create.return_value = mock_response

        chat_conversation([{"role": "user", "content": "test"}])
        call_kwargs = mock_scaleway.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == GENERATION_MODEL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestLLMConversation -v`

- [ ] **Step 3: Implement chat_conversation**

Add to `jobs/mothertree/llm.py` after the existing `chat()` function (around line 92):

```python
def chat_conversation(messages: list[dict], model: str = None) -> str:
    """Multi-turn conversation for DM freeform chat.

    Uses the generation model with higher token limit and temperature
    than the quick chat() function used for signal threads.
    """
    response = scaleway.chat.completions.create(
        model=model or GENERATION_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=2000,
        timeout=120,
    )
    return response.choices[0].message.content
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestLLMConversation -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/mothertree/llm.py jobs/tests/test_training.py
git commit -m "Add chat_conversation() for multi-turn DM with generation model"
```

---

## Task 3: Conversation-aware ask

Add a variant of `ask()` that accepts message history.

**Files:**
- Modify: `jobs/mothertree/ask.py`
- Test: `jobs/tests/test_training.py`

- [ ] **Step 1: Write tests**

```python
class TestAskWithHistory:
    """Test conversation-aware ask."""

    @patch("mothertree.ask.chat_conversation")
    @patch("mothertree.ask.fetch_context")
    def test_ask_with_history_includes_messages(self, mock_ctx, mock_chat):
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
        assert "Never fabricate" in messages[0]["content"]
        assert len(messages) >= 4  # system + 2 history + 1 new

    @patch("mothertree.ask.chat_conversation")
    @patch("mothertree.ask.fetch_context")
    def test_ask_with_history_persona(self, mock_ctx, mock_chat):
        from mothertree.ask import ask_with_history
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Seth says..."
        result = ask_with_history("why positioning?", [], persona="seth")
        messages = mock_chat.call_args[0][0]
        assert "Seth Godin" in messages[0]["content"]
        assert "Never fabricate" in messages[0]["content"]

    @patch("mothertree.ask.chat_conversation")
    @patch("mothertree.ask.fetch_context")
    def test_ask_with_history_no_hallucination_rule(self, mock_ctx, mock_chat):
        from mothertree.ask import ask_with_history
        mock_ctx.return_value = "context"
        mock_chat.return_value = "answer"
        ask_with_history("question", [])
        system = mock_chat.call_args[0][0][0]["content"]
        assert "Never fabricate URLs" in system
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestAskWithHistory -v`

- [ ] **Step 3: Implement ask_with_history**

Add to `jobs/mothertree/ask.py` after the existing `ask()` function:

```python
from mothertree.llm import chat_conversation

NO_HALLUCINATION_RULES = """
RULES:
- Never fabricate URLs, links, schedules, or external references.
- If the user asks about something you don't have (an event schedule, a specific article, a competitor's pricing page), say so and ask them to share a link if they'd like you to work with it.
- When the user shares a URL, you will receive its content. Ask if they want to save it to the central intelligence.
- You have the conversation history. Use it. Don't ask for context that was already given."""

DM_SYSTEM_PROMPT = """You are Mother Tree, the central intelligence for a consultative sales team.
You answer from what you know — the foundation (change, worldview, personas, competitors) and narrative (insights, case studies) in the central intelligence.
""" + NO_HALLUCINATION_RULES


def ask_with_history(question: str, history: list[dict],
                     persona: str = None, user_name: str = "you") -> str:
    """Answer a question with conversation history context.

    Used for freeform DM conversations. Includes CI context and
    no-hallucination rules in all calls.
    """
    context = fetch_context()

    if persona and persona in PERSONAS:
        system = PERSONAS[persona] + "\n\n" + NO_HALLUCINATION_RULES
    else:
        system = DM_SYSTEM_PROMPT

    system += f"\n\nCENTRAL INTELLIGENCE:\n{context}"
    system += f"\n\nYou are talking to {user_name}."

    messages = [{"role": "system", "content": system}]

    # Add conversation history (strip timestamps for LLM)
    for msg in history:
        if msg["role"] in ("user", "assistant", "system"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Add the new question
    messages.append({"role": "user", "content": question})

    return chat_conversation(messages)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestAskWithHistory -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/mothertree/ask.py jobs/tests/test_training.py
git commit -m "Add ask_with_history() for conversation-aware DM responses"
```

---

## Task 4: URL handling module

Detect URLs, fetch content, manage CI save flow.

**Files:**
- Create: `jobs/bot/dm_url.py`
- Test: `jobs/tests/test_training.py`

- [ ] **Step 1: Write tests**

```python
class TestDMUrl:
    """Test URL detection, fetching, and CI save flow."""

    def test_detect_url_bare(self):
        from bot.dm_url import detect_url
        assert detect_url("check out https://kubecon.io/schedule") == "https://kubecon.io/schedule"

    def test_detect_url_slack_format(self):
        from bot.dm_url import detect_url
        assert detect_url("look at <https://example.com|example>") == "https://example.com"

    def test_detect_url_no_url(self):
        from bot.dm_url import detect_url
        assert detect_url("no links here") is None

    def test_detect_url_ignores_short(self):
        from bot.dm_url import detect_url
        assert detect_url("A") is None

    def test_has_pending_ci_save(self):
        from bot.dm_url import has_pending_ci_save
        messages = [
            {"role": "user", "content": "https://example.com"},
            {"role": "system", "content": "pending_ci_save", "url": "https://example.com"},
        ]
        assert has_pending_ci_save(messages) == "https://example.com"

    def test_has_pending_ci_save_none(self):
        from bot.dm_url import has_pending_ci_save
        messages = [{"role": "user", "content": "hello"}]
        assert has_pending_ci_save(messages) is None

    def test_is_ci_save_response_yes(self):
        from bot.dm_url import is_ci_save_response
        assert is_ci_save_response("yes") is True
        assert is_ci_save_response("Y") is True
        assert is_ci_save_response("  yes  ") is True

    def test_is_ci_save_response_no(self):
        from bot.dm_url import is_ci_save_response
        assert is_ci_save_response("no") is False
        assert is_ci_save_response("n") is False

    def test_is_ci_save_response_other(self):
        from bot.dm_url import is_ci_save_response
        assert is_ci_save_response("tell me more") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMUrl -v`

- [ ] **Step 3: Implement dm_url.py**

Create `jobs/bot/dm_url.py`:

```python
"""URL detection, fetching, and CI save flow for DM conversations."""
import re


# Match bare URLs and Slack-formatted <url|label> links
_URL_RE = re.compile(r'<(https?://[^|>]+)(?:\|[^>]*)?>|(https?://\S+)')


def detect_url(text: str) -> str | None:
    """Extract the first URL from a message, or None."""
    match = _URL_RE.search(text)
    if not match:
        return None
    return match.group(1) or match.group(2)


def has_pending_ci_save(messages: list[dict]) -> str | None:
    """Check if the last system message is a pending CI save. Returns the URL or None."""
    for msg in reversed(messages):
        if msg.get("role") == "system" and msg.get("content") == "pending_ci_save":
            return msg.get("url")
        if msg.get("role") in ("user", "assistant"):
            break  # only check the most recent system message
    return None


def is_ci_save_response(text: str) -> bool | None:
    """Check if text is a yes/no response to CI save prompt.

    Returns True (yes), False (no), or None (not a yes/no response).
    """
    clean = text.strip().lower()
    if clean in ("yes", "y", "ja", "sure", "ok"):
        return True
    if clean in ("no", "n", "nee", "nope"):
        return False
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMUrl -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/dm_url.py jobs/tests/test_training.py
git commit -m "Add URL detection and CI save flow for DM conversations"
```

---

## Task 5: DM conversation module

Build the freeform conversation handler that ties history + CI context + LLM together.

**Files:**
- Create: `jobs/bot/dm_conversation.py`
- Test: `jobs/tests/test_training.py`

- [ ] **Step 1: Write tests**

```python
class TestDMConversationHandler:
    """Test freeform DM conversation flow."""

    @patch("bot.dm_conversation.append_dm_message")
    @patch("bot.dm_conversation.ask_with_history")
    @patch("bot.dm_conversation.get_or_create_dm_conversation")
    def test_handle_conversation(self, mock_get, mock_ask, mock_append):
        from bot.dm_conversation import handle_conversation
        mock_get.return_value = {
            "id": "c-1", "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ]
        }
        mock_ask.return_value = "Here is what I know..."
        respond = MagicMock()

        handle_conversation("U123", "what is our change?", respond, user_name="Jurg")

        mock_ask.assert_called_once()
        assert mock_append.call_count == 2  # user message + assistant response
        respond.assert_called_once_with("Here is what I know...")

    @patch("bot.dm_conversation.append_dm_message")
    @patch("bot.dm_conversation.ask_with_history")
    @patch("bot.dm_conversation.get_or_create_dm_conversation")
    def test_handle_conversation_with_persona(self, mock_get, mock_ask, mock_append):
        from bot.dm_conversation import handle_conversation
        mock_get.return_value = {"id": "c-1", "messages": []}
        mock_ask.return_value = "Seth says..."
        respond = MagicMock()

        handle_conversation("U123", "question", respond, persona="seth")

        call_kwargs = mock_ask.call_args[1]
        assert call_kwargs.get("persona") == "seth"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMConversationHandler -v`

- [ ] **Step 3: Implement dm_conversation.py**

Create `jobs/bot/dm_conversation.py`:

```python
"""Freeform DM conversation handler.

Manages conversation history, CI context, and LLM calls for
the default conversational DM experience.
"""
import logging

from mothertree.hasura import get_or_create_dm_conversation, append_dm_message
from mothertree.ask import ask_with_history

log = logging.getLogger(__name__)


def handle_conversation(slack_user_id: str, text: str, respond,
                        persona: str = None, user_name: str = "you") -> None:
    """Handle a freeform DM message. Fetches history, calls LLM, persists."""
    dm_conv = get_or_create_dm_conversation(slack_user_id)

    # Append user message to history
    append_dm_message(dm_conv["id"], role="user", content=text)

    # Call LLM with history
    answer = ask_with_history(
        question=text,
        history=dm_conv["messages"],
        persona=persona,
        user_name=user_name,
    )

    # Append assistant response to history
    append_dm_message(dm_conv["id"], role="assistant", content=answer)

    respond(answer)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMConversationHandler -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/dm_conversation.py jobs/tests/test_training.py
git commit -m "Add freeform DM conversation handler with history and CI context"
```

---

## Task 6: DM pipeline

Build the main pipeline that routes every DM through the spec's decision tree. Wire it into bot.py.

**Files:**
- Create: `jobs/bot/dm_pipeline.py`
- Modify: `jobs/bot/bot.py`
- Modify: `jobs/bot/training_dm.py`
- Test: `jobs/tests/test_training.py`

- [ ] **Step 1: Write tests for the pipeline routing**

```python
class TestDMPipeline:
    """Test DM message pipeline routing."""

    def test_is_global_command(self):
        from bot.dm_pipeline import classify_dm
        assert classify_dm("enroll hunter", enrolled=False) == ("command", "enroll", ["hunter"])
        assert classify_dm("status", enrolled=False) == ("command", "status", [])
        assert classify_dm("help", enrolled=False) == ("command", "help", [])
        assert classify_dm("stats", enrolled=False) == ("command", "stats", [])

    def test_is_training_command_enrolled(self):
        from bot.dm_pipeline import classify_dm
        assert classify_dm("next", enrolled=True) == ("training", "next", None)
        assert classify_dm("go", enrolled=True) == ("training", "go", None)
        assert classify_dm("practice worldview", enrolled=True) == ("training", "practice", "worldview")

    def test_training_command_unenrolled_falls_through(self):
        from bot.dm_pipeline import classify_dm
        assert classify_dm("next", enrolled=False)[0] == "conversation"
        assert classify_dm("go", enrolled=False)[0] == "conversation"

    def test_persona_invocation(self):
        from bot.dm_pipeline import classify_dm
        assert classify_dm("ask seth about positioning", enrolled=False) == ("persona", "seth", "about positioning")
        assert classify_dm("ask lawrence how to qualify", enrolled=True) == ("persona", "lawrence", "how to qualify")
        assert classify_dm("ask trainer", enrolled=True) == ("persona", "trainer", "")

    def test_exercise_answer(self):
        from bot.dm_pipeline import classify_dm
        assert classify_dm("A", enrolled=True) == ("training", "answer", "A")
        assert classify_dm("b", enrolled=True) == ("training", "answer", "B")

    def test_mothertree_prefix_stripped(self):
        from bot.dm_pipeline import classify_dm
        assert classify_dm("/mothertree status", enrolled=False) == ("command", "status", [])
        assert classify_dm("/mothertree ask seth why", enrolled=False) == ("persona", "seth", "why")

    def test_everything_else_is_conversation(self):
        from bot.dm_pipeline import classify_dm
        assert classify_dm("what is our worldview?", enrolled=True)[0] == "conversation"
        assert classify_dm("tell me about the change", enrolled=False)[0] == "conversation"

    @patch("bot.dm_pipeline.handle_conversation")
    @patch("bot.dm_pipeline.get_active_conversation")
    @patch("bot.dm_pipeline.get_or_create_dm_conversation")
    @patch("bot.dm_pipeline.get_enrollment")
    def test_mid_exercise_question_gets_nudge(self, mock_enroll, mock_dm_conv,
                                               mock_active, mock_converse):
        from bot.dm_pipeline import handle
        mock_enroll.return_value = {"id": "u-1", "current_stage": 0, "current_chapter": 0}
        mock_dm_conv.return_value = {"id": "dm-1", "messages": []}
        mock_active.return_value = {"id": "ex-1", "current_question": 1,
                                     "exercise": {"content": {"questions": []}}}
        event = {"channel_type": "im", "user": "U123", "text": "what does worldview mean?"}
        client = MagicMock()
        client.users_info.return_value = {"user": {"real_name": "Jurg"}}

        handle(event, client)

        mock_converse.assert_called_once()
        # The respond function should append the nudge
        respond_fn = mock_converse.call_args[0][2]  # third positional arg
        respond_fn("Here is what worldview means...")
        sent_text = client.chat_postMessage.call_args[1]["text"]
        assert "question waiting" in sent_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMPipeline -v`

- [ ] **Step 3: Implement dm_pipeline.py**

Create `jobs/bot/dm_pipeline.py`:

```python
"""DM message pipeline.

Routes every DM through: commands → training → URL → conversation.
This is the single entry point for all DM handling.
"""
import logging

from mothertree.hasura import (
    get_enrollment, get_active_conversation, cancel_stale_conversations,
    update_conversation, insert_response, advance_enrollment, update_streak,
    get_or_create_dm_conversation, append_dm_message,
)
from mothertree.ask import parse_ask_args, PERSONAS
from bot.dm_conversation import handle_conversation
from bot.dm_url import detect_url, has_pending_ci_save, is_ci_save_response
from bot.training_dm import calculate_streak, format_chapter_complete
from training.score import score_response
from training.deliver import deliver_to_user_on_demand, format_question_dm

log = logging.getLogger(__name__)

GLOBAL_COMMANDS = {"enroll", "status", "progress", "stats", "help"}
TRAINING_COMMANDS = {"next", "go", "practice"}


def classify_dm(text: str, enrolled: bool = False) -> tuple:
    """Classify a DM message into a routing category.

    Returns (category, action, arg) where category is one of:
        "command", "training", "persona", "conversation"
    """
    clean = text.strip()

    # Strip /mothertree prefix
    lower = clean.lower()
    if lower.startswith("/mothertree"):
        clean = clean[len("/mothertree"):].strip()
        lower = clean.lower()

    parts = clean.split()
    first = parts[0].lower() if parts else ""

    # Global commands
    if first in GLOBAL_COMMANDS:
        return ("command", first, parts[1:])

    # Persona invocation: "ask seth ...", "ask lawrence ...", etc.
    if first == "ask" and len(parts) >= 2:
        persona_name = parts[1].lower()
        if persona_name in PERSONAS or persona_name == "trainer":
            rest = " ".join(parts[2:])
            return ("persona", persona_name, rest)

    # Training commands (require enrollment)
    if enrolled:
        if first == "next":
            return ("training", "next", None)
        if first == "go":
            return ("training", "go", None)
        if first == "practice":
            topic = parts[1].lower() if len(parts) > 1 else None
            return ("training", "practice", topic)
        # Exercise answer
        if clean.upper() in ("A", "B", "C"):
            return ("training", "answer", clean.upper())

    # Everything else is conversation
    return ("conversation", None, clean)


def handle(event, client):
    """Main DM handler. Called from bot.py for every DM message."""
    if event.get("channel_type") != "im":
        return
    if event.get("bot_id"):
        return

    user_slack_id = event["user"]
    text = event.get("text", "").strip()
    if not text:
        return

    def respond(msg):
        client.chat_postMessage(channel=user_slack_id, text=msg)

    # Get user info
    user_info = client.users_info(user=user_slack_id)
    user_name = user_info["user"].get("real_name", user_slack_id)

    enrollment = get_enrollment(user_slack_id)
    enrolled = enrollment is not None

    # --- Check for pending CI save ---
    dm_conv = get_or_create_dm_conversation(user_slack_id)
    pending_url = has_pending_ci_save(dm_conv["messages"])
    if pending_url:
        ci_response = is_ci_save_response(text)
        if ci_response is True:
            _save_to_ci(pending_url, dm_conv["messages"], respond)
            _clear_pending_ci_save(dm_conv["id"], dm_conv["messages"])
            return
        elif ci_response is False:
            respond("OK, keeping it in our conversation only.")
            _clear_pending_ci_save(dm_conv["id"], dm_conv["messages"])
            return
        else:
            # User moved on, clear flag silently
            _clear_pending_ci_save(dm_conv["id"], dm_conv["messages"])
            # Fall through to normal processing

    # --- Classify message ---
    category, action, arg = classify_dm(text, enrolled=enrolled)

    # --- Commands ---
    if category == "command":
        _handle_command(action, arg, user_slack_id, user_name, respond)
        return

    # --- Persona ---
    if category == "persona":
        handle_conversation(user_slack_id, arg or action, respond,
                            persona=action, user_name=user_name)
        return

    # --- Training ---
    if category == "training":
        _handle_training(action, arg, enrollment, user_slack_id, client, respond)
        return

    # --- Active exercise + not a training command? Answer from CI, then nudge ---
    if enrolled and category == "conversation":
        active_exercise = get_active_conversation(enrollment["id"])
        if active_exercise:
            handle_conversation(user_slack_id, text, lambda msg: respond(
                f"{msg}\n\n_By the way, you still have a question waiting — reply A, B, or C when ready._"
            ), user_name=user_name)
            return

    # --- URL detection ---
    url = detect_url(text)
    if url:
        _handle_url(url, text, user_slack_id, dm_conv, respond, user_name)
        return

    # --- Freeform conversation ---
    handle_conversation(user_slack_id, text, respond, user_name=user_name)


def _handle_command(action, args, user_slack_id, user_name, respond):
    """Route to the appropriate command handler."""
    # Import here to avoid circular imports
    from bot.bot import handle_enroll, handle_status, handle_progress, handle_stats, handle_help
    if action == "enroll":
        handle_enroll(user_slack_id, user_name, args, respond)
    elif action == "status":
        handle_status(user_slack_id, respond)
    elif action == "progress":
        handle_progress(respond)
    elif action == "stats":
        handle_stats(respond)
    elif action == "help":
        handle_help(respond)


def _handle_training(action, arg, enrollment, user_slack_id, client, respond):
    """Handle training commands: next, go, practice, answer."""
    conv = get_active_conversation(enrollment["id"])

    if action == "next":
        cancel_stale_conversations(enrollment["id"])
        stage = enrollment["current_stage"]
        chapter = enrollment["current_chapter"]
        if stage == 0 and chapter > 4:
            respond("You've completed Stage 0. Stage 1 \u2014 the marketing framework "
                    "\u2014 is coming soon.\n\nSay *practice [topic]* to keep sharpening.")
            return
        deliver_to_user_on_demand(client, enrollment)

    elif action == "go":
        if conv and conv["current_question"] == -1:
            update_conversation(conv["id"], current_question=0)
            exercise = conv["exercise"]["content"]
            questions = exercise["questions"]
            msg = format_question_dm(questions[0], question_num=1, total=len(questions))
            respond(msg)
        else:
            respond("Reply *go* when you've received instruction text.")

    elif action == "practice":
        cancel_stale_conversations(enrollment["id"])
        if arg:
            from bot.training_dm import resolve_topic
            chapter = resolve_topic(arg)
            if chapter is None:
                respond("I don't have a chapter called that. "
                        "Try: promise, worldview, audience, difference, or services.")
                return
        else:
            chapter = enrollment["current_chapter"]
        deliver_to_user_on_demand(client, enrollment, chapter=chapter, practice=True)

    elif action == "answer":
        if not conv:
            # No active exercise — route to conversation instead
            handle_conversation(user_slack_id, arg, respond)
            return
        _score_and_progress(conv, enrollment, arg, user_slack_id, respond)


def _score_and_progress(conv, enrollment, answer, user_slack_id, respond):
    """Score an exercise answer and handle progression."""
    exercise = conv["exercise"]["content"]
    current_q = conv["current_question"]
    questions = exercise["questions"]

    if current_q == -1:
        respond("Reply *go* when you've read the instruction text.")
        return

    question = questions[current_q]
    result = score_response(stage=conv["stage"], question=question, response=answer)

    insert_response(
        exercise_id=conv["exercise_id"], user_id=enrollment["id"],
        response=answer, question_index=current_q,
        correct=result["correct"], feedback=result["feedback"],
    )

    next_q = current_q + 1
    if next_q < len(questions):
        update_conversation(conv["id"], current_question=next_q)
        question_text = format_question_dm(
            questions[next_q], question_num=next_q + 1, total=len(questions)
        )
        respond(f"{result['feedback']}\n\n{question_text}")
    else:
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
        respond(f"{result['feedback']}\n\n{complete_text}")


def _handle_url(url, text, user_slack_id, dm_conv, respond, user_name):
    """Fetch URL content, add to conversation, ask about CI save."""
    from bot.enrich import fetch_url_context

    content = fetch_url_context(url)
    if content is None:
        respond("I couldn't reach that URL \u2014 it might be behind a login or unavailable.")
        # Still route the text to conversation
        handle_conversation(user_slack_id, text, respond, user_name=user_name)
        return

    # Add fetched content to conversation history
    append_dm_message(dm_conv["id"], role="system",
                      content=f"Content from {url}:\n{content}")
    # Set pending CI save flag
    set_pending_ci_save(dm_conv["id"], url)

    # Answer grounded in the content, then ask about CI save
    def respond_with_ci_prompt(msg):
        respond(f"{msg}\n\nWant me to save this to the central intelligence too?")

    handle_conversation(user_slack_id, text, respond_with_ci_prompt, user_name=user_name)


def _save_to_ci(url, dm_conv_messages, respond):
    """Run URL content through the content pipeline and save to CI.

    Retrieves the already-fetched content from conversation history
    rather than re-fetching the URL.
    """
    # Find the fetched content in conversation history
    content = None
    for msg in reversed(dm_conv_messages):
        if msg.get("role") == "system" and msg.get("content", "").startswith(f"Content from {url}:"):
            content = msg["content"].split(":\n", 1)[1] if ":\n" in msg["content"] else None
            break

    if content is None:
        respond("I can't find the fetched content. Try sharing the URL again.")
        return

    from mothertree.llm import extract
    try:
        result = extract(content, "Extract insights from this content. Return a JSON array of objects with: category, reframe, evidence, trigger, next_step.")
        from mothertree.hasura import graphql
        if isinstance(result, list):
            for insight in result:
                graphql("""
                    mutation($obj: insights_insert_input!) {
                        insert_insights_one(object: $obj) { id }
                    }
                """, {"obj": {**insight, "source": url}})
        respond(f"Saved to the central intelligence ({len(result) if isinstance(result, list) else 0} insights extracted).")
    except Exception as e:
        log.exception("Failed to save URL content to CI")
        respond(f"Couldn't extract insights from that content: {e}")


def _clear_pending_ci_save(conversation_id, messages):
    """Remove the pending_ci_save flag from conversation messages."""
    cleaned = [m for m in messages if m.get("content") != "pending_ci_save"]
    from mothertree.hasura import update_conversation
    update_conversation(conversation_id, messages=cleaned)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py::TestDMPipeline -v`

- [ ] **Step 5: Update training_dm.py**

Update `parse_dm_command` in `jobs/bot/training_dm.py` to return "conversation" instead of "unknown":

Change line that returns `return "unknown", None` to `return "conversation", None`.

- [ ] **Step 6: Wire into bot.py**

Replace the entire `handle_dm` function in `jobs/bot/bot.py` with:

```python
@app.event("message")
def handle_dm(event, client):
    """Handle DM messages — routes through the DM pipeline."""
    from bot.dm_pipeline import handle
    handle(event, client)
```

And update the signal handler's DM routing (around line 58):

```python
    # DMs go to pipeline
    if channel_type in ("im",):
        from bot.dm_pipeline import handle
        handle(message, client)
        return
```

Remove the old imports that were only used by the old handle_dm (training_dm imports, score import, etc. that are now in dm_pipeline.py).

- [ ] **Step 7: Run all tests**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py -v`
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add jobs/bot/dm_pipeline.py jobs/bot/bot.py jobs/bot/training_dm.py jobs/tests/test_training.py
git commit -m "Rewrite DM handler as conversation-first pipeline"
```

---

## Task 7: Database migration + deploy

Apply the schema change and push.

- [ ] **Step 1: Add slack_user_id column to production**

```bash
KUBECONFIG=kubeconfig-mother-tree.yaml kubectl get secret hasura-admin-secret -n mother-tree -o jsonpath='{.data.admin-secret}' | base64 -d
```

Then run via Hasura API:

```sql
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS slack_user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_conversations_slack_user_id ON conversations(slack_user_id);
```

- [ ] **Step 2: Reload Hasura metadata**

POST to `https://mothertree.aknostic.com/v1/metadata`:
```json
{"type": "reload_metadata", "args": {}}
```

- [ ] **Step 3: Run the full test suite one final time**

Run: `cd /Users/jurg/Projects/mother-tree/jobs && python -m pytest tests/test_training.py -v`

- [ ] **Step 4: Push to GitLab**

```bash
git push origin main
```

Wait for CI to build and Flux to deploy. Then restart the bot:

```bash
KUBECONFIG=kubeconfig-mother-tree.yaml kubectl rollout restart deployment/slack-bot -n mother-tree
```

- [ ] **Step 5: Test end-to-end**

DM the bot:
1. "hello" → should get a conversational response from CI
2. "what is our worldview?" → should answer from CI
3. "tell me more" → should use conversation history
4. "ask seth about our positioning" → should route to Seth persona
5. "enroll hunter" → should enroll
6. "next" → should start training
7. Paste a URL → should fetch and ask about CI save
8. "yes" → should save to CI

---

## Deployment notes

1. **Schema migration:** `ALTER TABLE conversations ADD COLUMN slack_user_id TEXT` + index
2. **Hasura metadata reload** to pick up the new column
3. **Push to GitLab** → CI builds new image → Flux deploys
4. **Restart bot** to pick up new image
5. **Test** DM flow end-to-end
