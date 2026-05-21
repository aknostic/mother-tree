# Unified Conversation Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the separate DM pipeline and channel signal-capture handler with one unified conversation flow that works identically in DMs, channels, and threads.

**Architecture:** Two-phase pipeline — detect (fast pattern matching producing annotations) feeds into a conversation engine (LLM). Triage decides when to respond in channels. Background signal extraction runs after responses. Three memory stores (DM, channel, thread) with the same interface.

**Tech Stack:** Python 3.12, Slack Bolt, PostgreSQL + Hasura (GraphQL), Scaleway Generative APIs (Mistral Small 3.2, Qwen3 235B), pytest with unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-22-unified-conversation-flow-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `jobs/bot/detect.py` | Detect phase: pattern matching, side effect execution, annotation production |
| `jobs/bot/triage.py` | Triage: cheap LLM call deciding respond/signal/silent |
| `jobs/bot/conversation.py` | Conversation engine: builds context, calls LLM, parses markers, persists |
| `jobs/bot/memory.py` | Memory interface: get/append/cap/summarize for DM, channel, thread stores |
| `jobs/bot/buffer.py` | In-memory channel buffer for lazy persistence of silent messages |
| `jobs/bot/extraction.py` | Background signal extraction: entities, actions, qualification |
| `jobs/bot/markers.py` | Action/content marker parsing and user input sanitization |
| `jobs/tests/test_unified.py` | Tests for all new modules |

### Modified files

| File | Changes |
|------|---------|
| `jobs/bot/bot.py` | Thin entry point: route all channels through unified pipeline, per-channel serialization |
| `jobs/mothertree/ask.py` | Extended system prompt, model selection, `ask_with_history()` accepts annotations |
| `jobs/mothertree/hasura.py` | New CRUD for `channel_memory` and `thread_memory`, `signal_threads` fallback |
| `jobs/reminders/thread_reminders.py` | Query both `signal_threads` and `thread_memory` |
| `deploy/database/schema.sql` | Add `channel_memory` and `thread_memory` table definitions |

### Removed (in final cleanup task)

| File / Function | Replaced by |
|-----------------|-------------|
| `jobs/mothertree/intent.py` | `jobs/bot/triage.py` |
| `jobs/bot/dm_pipeline.py` | `jobs/bot/detect.py` + `jobs/bot/conversation.py` |
| `jobs/bot/dm_conversation.py` | `jobs/bot/conversation.py` |
| `jobs/bot/dm_url.py` | `jobs/bot/detect.py` + `jobs/bot/markers.py` |
| `enrich.py:enrich_signal()` | `jobs/bot/extraction.py` |
| `enrich.py:format_enrichment()` | `jobs/bot/conversation.py` |
| `enrich.py:continue_signal_conversation()` | `jobs/bot/conversation.py` |

### Kept as-is

| File | Reason |
|------|--------|
| `jobs/bot/enrich.py:fetch_url_context()` | URL fetching utility, shared |
| `jobs/bot/enrich.py:extract_urls()` | URL extraction utility, shared |
| `jobs/bot/training_dm.py:calculate_streak()` | Streak logic, called from detect |
| `jobs/bot/training_dm.py:resolve_topic()` | Topic resolution, called from detect |
| `jobs/training/deliver.py` | Training delivery, called from detect |
| `jobs/training/score.py` | Exercise scoring, called from detect |

---

## Task 1: Database tables and Hasura functions

**Files:**
- Modify: `deploy/database/schema.sql`
- Modify: `jobs/mothertree/hasura.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write tests for channel_memory CRUD**

```python
# jobs/tests/test_unified.py
"""Tests for unified conversation flow components."""
from unittest.mock import patch, MagicMock


class TestChannelMemory:
    """Channel memory CRUD operations."""

    @patch("mothertree.hasura.graphql")
    def test_get_or_create_channel_memory_new(self, mock_gql):
        from mothertree.hasura import get_or_create_channel_memory
        mock_gql.side_effect = [
            {"channel_memory": []},  # not found
            {"insert_channel_memory_one": {"id": 1, "channel_id": "C123", "messages": []}},
        ]
        result = get_or_create_channel_memory("C123")
        assert result["channel_id"] == "C123"
        assert result["messages"] == []

    @patch("mothertree.hasura.graphql")
    def test_get_or_create_channel_memory_existing(self, mock_gql):
        from mothertree.hasura import get_or_create_channel_memory
        mock_gql.return_value = {"channel_memory": [{"id": 1, "channel_id": "C123", "messages": [{"role": "user"}]}]}
        result = get_or_create_channel_memory("C123")
        assert len(result["messages"]) == 1

    @patch("mothertree.hasura.graphql")
    def test_append_channel_message(self, mock_gql):
        from mothertree.hasura import append_channel_message
        mock_gql.return_value = {"update_channel_memory": {"returning": [{"id": 1}]}}
        append_channel_message("C123", role="user", name="Jurg", content="hello")
        call_args = mock_gql.call_args[0][0]
        assert "channel_memory" in call_args

    @patch("mothertree.hasura.graphql")
    def test_cap_channel_memory(self, mock_gql):
        from mothertree.hasura import cap_channel_memory
        messages = [{"role": "user", "content": str(i)} for i in range(210)]
        mock_gql.return_value = {"update_channel_memory_by_pk": {"id": 1}}
        cap_channel_memory(1, messages, max_messages=200)
        # Should trim to 200
        call_args = mock_gql.call_args
        written = call_args[1]["variables"]["messages"] if "variables" in call_args[1] else None
        # Verify the mutation was called
        assert mock_gql.called
```

- [ ] **Step 2: Write tests for thread_memory CRUD**

```python
class TestThreadMemory:
    """Thread memory CRUD operations."""

    @patch("mothertree.hasura.graphql")
    def test_get_or_create_thread_memory_new(self, mock_gql):
        from mothertree.hasura import get_or_create_thread_memory
        mock_gql.side_effect = [
            {"thread_memory": []},
            {"insert_thread_memory_one": {"id": 1, "thread_ts": "123.456", "channel_id": "C123", "messages": []}},
        ]
        result = get_or_create_thread_memory("123.456", "C123")
        assert result["thread_ts"] == "123.456"

    @patch("mothertree.hasura.graphql")
    def test_append_thread_message(self, mock_gql):
        from mothertree.hasura import append_thread_message
        mock_gql.return_value = {"update_thread_memory": {"returning": [{"id": 1}]}}
        append_thread_message("123.456", "C123", role="user", name="Jurg", content="hello")
        assert mock_gql.called

    @patch("mothertree.hasura.graphql")
    def test_get_thread_memory_with_signal_fallback(self, mock_gql):
        from mothertree.hasura import get_thread_memory_or_signal_thread
        # First call: no thread_memory. Second call: signal_threads has it.
        mock_gql.side_effect = [
            {"thread_memory": []},
            {"signal_threads": [{"id": 1, "messages": [{"role": "user", "content": "old signal"}]}]},
        ]
        result = get_thread_memory_or_signal_thread("123.456", "C123")
        assert result is not None
        assert result["messages"][0]["content"] == "old signal"
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py -v`
Expected: ImportError — functions don't exist yet.

- [ ] **Step 4: Add table definitions to schema.sql**

Add to `deploy/database/schema.sql`:

```sql
-- Channel conversation memory (top-level messages, capped at ~200)
CREATE TABLE channel_memory (
    id SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL UNIQUE,
    channel_name TEXT,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Thread conversation memory (per-thread, capped at ~100 with summarization)
CREATE TABLE thread_memory (
    id SERIAL PRIMARY KEY,
    thread_ts TEXT NOT NULL UNIQUE,
    channel_id TEXT NOT NULL,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    remind_after TIMESTAMPTZ,
    remind_context TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 5: Implement Hasura functions in hasura.py**

Add to `jobs/mothertree/hasura.py`:

```python
# --- Channel memory ---

def get_or_create_channel_memory(channel_id: str, channel_name: str = None) -> dict:
    """Get or create a channel memory record."""
    result = graphql("""
    query GetChannelMemory($channel_id: String!) {
        channel_memory(where: {channel_id: {_eq: $channel_id}}) {
            id channel_id channel_name messages
        }
    }
    """, {"channel_id": channel_id})
    rows = result["channel_memory"]
    if rows:
        return rows[0]
    result = graphql("""
    mutation CreateChannelMemory($channel_id: String!, $channel_name: String) {
        insert_channel_memory_one(object: {channel_id: $channel_id, channel_name: $channel_name}) {
            id channel_id channel_name messages
        }
    }
    """, {"channel_id": channel_id, "channel_name": channel_name})
    return result["insert_channel_memory_one"]


def append_channel_message(channel_id: str, role: str, content: str, name: str = None) -> None:
    """Append a message to channel memory."""
    from datetime import datetime, timezone
    msg = {"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()}
    if name:
        msg["name"] = name
    graphql("""
    mutation AppendChannelMsg($channel_id: String!, $msg: jsonb!) {
        update_channel_memory(
            where: {channel_id: {_eq: $channel_id}},
            _append: {messages: $msg}
        ) { returning { id } }
    }
    """, {"channel_id": channel_id, "msg": msg})


def cap_channel_memory(memory_id: int, messages: list, max_messages: int = 200) -> None:
    """Trim channel memory to max_messages, keeping the newest."""
    if len(messages) <= max_messages:
        return
    trimmed = messages[-max_messages:]
    graphql("""
    mutation CapChannelMemory($id: Int!, $messages: jsonb!) {
        update_channel_memory_by_pk(pk_columns: {id: $id}, _set: {messages: $messages}) { id }
    }
    """, {"id": memory_id, "messages": trimmed})


# --- Thread memory ---

def get_or_create_thread_memory(thread_ts: str, channel_id: str) -> dict:
    """Get or create a thread memory record."""
    result = graphql("""
    query GetThreadMemory($thread_ts: String!) {
        thread_memory(where: {thread_ts: {_eq: $thread_ts}}) {
            id thread_ts channel_id messages remind_after remind_context
        }
    }
    """, {"thread_ts": thread_ts})
    rows = result["thread_memory"]
    if rows:
        return rows[0]
    result = graphql("""
    mutation CreateThreadMemory($thread_ts: String!, $channel_id: String!) {
        insert_thread_memory_one(object: {thread_ts: $thread_ts, channel_id: $channel_id}) {
            id thread_ts channel_id messages remind_after remind_context
        }
    }
    """, {"thread_ts": thread_ts, "channel_id": channel_id})
    return result["insert_thread_memory_one"]


def append_thread_message(thread_ts: str, channel_id: str, role: str, content: str, name: str = None) -> None:
    """Append a message to thread memory (creates record if needed)."""
    from datetime import datetime, timezone
    get_or_create_thread_memory(thread_ts, channel_id)
    msg = {"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()}
    if name:
        msg["name"] = name
    graphql("""
    mutation AppendThreadMsg($thread_ts: String!, $msg: jsonb!) {
        update_thread_memory(
            where: {thread_ts: {_eq: $thread_ts}},
            _append: {messages: $msg}
        ) { returning { id } }
    }
    """, {"thread_ts": thread_ts, "msg": msg})


def get_thread_memory_or_signal_thread(thread_ts: str, channel_id: str) -> dict | None:
    """Get thread memory, falling back to signal_threads for legacy threads."""
    result = graphql("""
    query GetThreadMemory($thread_ts: String!) {
        thread_memory(where: {thread_ts: {_eq: $thread_ts}}) {
            id thread_ts channel_id messages remind_after remind_context
        }
    }
    """, {"thread_ts": thread_ts})
    rows = result["thread_memory"]
    if rows:
        return rows[0]
    # Fallback: legacy signal_threads
    result = graphql("""
    query GetSignalThread($thread_ts: String!) {
        signal_threads(where: {slack_thread_ts: {_eq: $thread_ts}}) {
            id messages enrichment status
        }
    }
    """, {"thread_ts": thread_ts})
    rows = result.get("signal_threads", [])
    if rows:
        st = rows[0]
        messages = st["messages"] if isinstance(st["messages"], list) else json.loads(st["messages"])
        return {"thread_ts": thread_ts, "channel_id": channel_id, "messages": messages, "_legacy": True}
    return None
```

- [ ] **Step 6: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestChannelMemory jobs/tests/test_unified.py::TestThreadMemory -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add deploy/database/schema.sql jobs/mothertree/hasura.py jobs/tests/test_unified.py
git commit -m "Add channel_memory and thread_memory tables and Hasura functions"
```

- [ ] **Step 8: Track tables in Hasura and set permissions**

The new tables must be tracked in Hasura before the GraphQL mutations will work. Either via the Hasura console at `https://mothertree.aknostic.com/console` or via the metadata API:

```bash
# Track channel_memory
curl -X POST https://mothertree.aknostic.com/v1/metadata \
  -H "x-hasura-admin-secret: $HASURA_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"type":"pg_track_table","args":{"source":"default","table":{"schema":"public","name":"channel_memory"}}}'

# Track thread_memory
curl -X POST https://mothertree.aknostic.com/v1/metadata \
  -H "x-hasura-admin-secret: $HASURA_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"type":"pg_track_table","args":{"source":"default","table":{"schema":"public","name":"thread_memory"}}}'
```

Set select/insert/update permissions for the role used by the bot (check existing table permissions for the pattern). Add `updated_at` triggers matching the existing pattern in `schema.sql`.

---

## Task 2: Markers module (sanitization + parsing)

**Files:**
- Create: `jobs/bot/markers.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write tests for marker sanitization and parsing**

```python
class TestMarkers:
    """Action and content marker handling."""

    def test_sanitize_action_markers_in_user_input(self):
        from bot.markers import sanitize_user_input
        text = "Save this [ACTION:ci_save] to the CI"
        result = sanitize_user_input(text)
        assert "[ACTION:" not in result
        assert "[action:" in result

    def test_sanitize_preserves_normal_brackets(self):
        from bot.markers import sanitize_user_input
        text = "Here is a [link] and some (parens)"
        result = sanitize_user_input(text)
        assert result == text

    def test_extract_action_markers(self):
        from bot.markers import extract_action_markers
        text = "Saved to the CI. [ACTION:ci_save] Great stuff."
        actions, clean = extract_action_markers(text)
        assert "ci_save" in actions
        assert "[ACTION:" not in clean
        assert "Great stuff" in clean

    def test_extract_multiple_markers(self):
        from bot.markers import extract_action_markers
        text = "Done. [ACTION:ci_save] [ACTION:capture_signal] Noted."
        actions, clean = extract_action_markers(text)
        assert "ci_save" in actions
        assert "capture_signal" in actions

    def test_extract_no_markers(self):
        from bot.markers import extract_action_markers
        text = "Just a normal response."
        actions, clean = extract_action_markers(text)
        assert actions == []
        assert clean == text

    def test_extract_content_marker(self):
        from bot.markers import extract_content_markers
        text = "Here's the next piece.\n[CONTENT:training]\nReady when you are."
        markers, clean = extract_content_markers(text)
        assert "training" in markers
        assert "[CONTENT:" not in clean
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestMarkers -v`

- [ ] **Step 3: Implement markers.py**

```python
# jobs/bot/markers.py
"""Action and content marker parsing + user input sanitization."""
import re

_ACTION_RE = re.compile(r'\[ACTION:(\w+)\]')
_CONTENT_RE = re.compile(r'\[CONTENT:(\w+)\]')


def sanitize_user_input(text: str) -> str:
    """Escape action marker patterns in user input to prevent injection."""
    return text.replace("[ACTION:", "[action:")


def extract_action_markers(text: str) -> tuple[list[str], str]:
    """Extract [ACTION:*] markers from LLM response.

    Returns (list of action names, cleaned text with markers removed).
    """
    actions = _ACTION_RE.findall(text)
    clean = _ACTION_RE.sub("", text).strip()
    # Clean up double spaces left by marker removal
    clean = re.sub(r'  +', ' ', clean)
    return actions, clean


def extract_content_markers(text: str) -> tuple[list[str], str]:
    """Extract [CONTENT:*] markers from LLM response.

    Returns (list of content types, cleaned text with markers removed).
    """
    markers = _CONTENT_RE.findall(text)
    clean = _CONTENT_RE.sub("", text).strip()
    return markers, clean
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestMarkers -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/markers.py jobs/tests/test_unified.py
git commit -m "Add marker parsing and user input sanitization"
```

---

## Task 3: Memory interface

**Files:**
- Create: `jobs/bot/memory.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write tests for the unified memory interface**

```python
class TestMemoryInterface:
    """Unified memory interface across DM, channel, thread."""

    @patch("mothertree.hasura.get_or_create_dm_conversation")
    def test_get_dm_memory(self, mock_dm):
        from bot.memory import get_memory
        mock_dm.return_value = {"id": 1, "messages": [{"role": "user", "content": "hi"}]}
        ctx = get_memory(context_type="dm", slack_user_id="U123")
        assert ctx["messages"][0]["content"] == "hi"
        assert ctx["store_type"] == "dm"

    @patch("mothertree.hasura.get_or_create_channel_memory")
    def test_get_channel_memory(self, mock_ch):
        from bot.memory import get_memory
        mock_ch.return_value = {"id": 1, "channel_id": "C123", "messages": []}
        ctx = get_memory(context_type="channel", channel_id="C123")
        assert ctx["store_type"] == "channel"

    @patch("mothertree.hasura.get_thread_memory_or_signal_thread")
    def test_get_thread_memory_with_fallback(self, mock_th):
        from bot.memory import get_memory
        mock_th.return_value = {"thread_ts": "123.456", "messages": [{"role": "user"}], "_legacy": True}
        ctx = get_memory(context_type="thread", thread_ts="123.456", channel_id="C123")
        assert ctx["store_type"] == "thread"
        assert ctx["_legacy"] is True

    def test_window_messages(self):
        from bot.memory import window_messages
        msgs = [{"role": "user", "content": str(i)} for i in range(300)]
        windowed = window_messages(msgs, max_messages=200)
        assert len(windowed) == 200
        assert windowed[0]["content"] == "100"  # oldest kept

    @patch("bot.memory.chat_conversation")
    def test_summarize_thread_creates_summary(self, mock_llm):
        from bot.memory import summarize_old_messages
        mock_llm.return_value = "Summary: Jurg discussed KPN migration with Flavia."
        msgs = [{"role": "user", "name": "Jurg", "content": f"msg {i}"} for i in range(120)]
        result = summarize_old_messages(msgs, max_messages=100)
        assert len(result) <= 101  # 1 summary + 100 recent
        assert result[0]["role"] == "system"
        assert "Summary" in result[0]["content"]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestMemoryInterface -v`

- [ ] **Step 3: Implement memory.py**

```python
# jobs/bot/memory.py
"""Unified memory interface for DM, channel, and thread contexts."""
from mothertree.hasura import (
    get_or_create_dm_conversation, append_dm_message,
    get_or_create_channel_memory, append_channel_message, cap_channel_memory,
    get_or_create_thread_memory, append_thread_message,
    get_thread_memory_or_signal_thread,
)

# Default max messages per context. Configurable via environment.
import os
DM_MAX_MESSAGES = int(os.environ.get("DM_MAX_MESSAGES", "200"))
CHANNEL_MAX_MESSAGES = int(os.environ.get("CHANNEL_MAX_MESSAGES", "200"))
THREAD_MAX_MESSAGES = int(os.environ.get("THREAD_MAX_MESSAGES", "100"))


def get_memory(context_type: str, **kwargs) -> dict:
    """Get conversation memory for a context.

    Returns dict with keys: messages, store_type, store_id, and context-specific fields.
    """
    if context_type == "dm":
        conv = get_or_create_dm_conversation(kwargs["slack_user_id"])
        return {
            "messages": conv["messages"],
            "store_type": "dm",
            "store_id": conv["id"],
            "slack_user_id": kwargs["slack_user_id"],
        }
    elif context_type == "channel":
        mem = get_or_create_channel_memory(kwargs["channel_id"], kwargs.get("channel_name"))
        return {
            "messages": mem["messages"],
            "store_type": "channel",
            "store_id": mem["id"],
            "channel_id": kwargs["channel_id"],
        }
    elif context_type == "thread":
        mem = get_thread_memory_or_signal_thread(kwargs["thread_ts"], kwargs["channel_id"])
        if mem is None:
            mem = get_or_create_thread_memory(kwargs["thread_ts"], kwargs["channel_id"])
        return {
            "messages": mem.get("messages", []),
            "store_type": "thread",
            "store_id": mem.get("id"),
            "thread_ts": kwargs["thread_ts"],
            "channel_id": kwargs["channel_id"],
            "_legacy": mem.get("_legacy", False),
        }
    raise ValueError(f"Unknown context_type: {context_type}")


def append_message(memory_ctx: dict, role: str, content: str, name: str = None, annotation: dict = None) -> None:
    """Append a message to the appropriate memory store."""
    if memory_ctx["store_type"] == "dm":
        append_dm_message(memory_ctx["store_id"], role=role, content=content)
    elif memory_ctx["store_type"] == "channel":
        append_channel_message(memory_ctx["channel_id"], role=role, content=content, name=name)
    elif memory_ctx["store_type"] == "thread":
        append_thread_message(memory_ctx["thread_ts"], memory_ctx["channel_id"], role=role, content=content, name=name)


def window_messages(messages: list[dict], max_messages: int = 200) -> list[dict]:
    """Return the last max_messages from a message list."""
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


def get_max_messages(context_type: str) -> int:
    """Get the max message window for a context type."""
    return {"dm": DM_MAX_MESSAGES, "channel": CHANNEL_MAX_MESSAGES, "thread": THREAD_MAX_MESSAGES}[context_type]


def summarize_old_messages(messages: list[dict], max_messages: int = 100) -> list[dict]:
    """Summarize oldest messages when a thread exceeds max_messages.

    Keeps the newest max_messages and summarizes the rest into a single
    system message prepended to the list.
    """
    if len(messages) <= max_messages:
        return messages
    old = messages[:-max_messages]
    recent = messages[-max_messages:]
    # Summarize old messages via LLM
    from mothertree.llm import chat_conversation
    summary_prompt = [
        {"role": "system", "content": "Summarize this conversation history. Preserve: who said what, key decisions, open questions, action items. Be concise."},
        {"role": "user", "content": "\n".join(f"[{m.get('name', m['role'])}]: {m['content']}" for m in old if m.get('content'))},
    ]
    try:
        summary = chat_conversation(summary_prompt, model=None)  # uses generation model
    except Exception:
        # On failure, just truncate without summary
        return recent
    summary_msg = {"role": "system", "content": f"Summary of earlier conversation:\n{summary}"}
    return [summary_msg] + recent
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestMemoryInterface -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/memory.py jobs/tests/test_unified.py
git commit -m "Add unified memory interface for DM, channel, thread"
```

---

## Task 4: Detect phase

**Files:**
- Create: `jobs/bot/detect.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write tests for detect phase**

```python
class TestDetect:
    """Detect phase: pattern matching and annotation production."""

    def test_strip_mention(self):
        from bot.detect import detect
        result = detect("<@U_BOT> what's our positioning?", participant_count=5, enrolled=False, bot_user_id="U_BOT")
        assert result["must_respond"] is True
        assert result["clean_text"] == "what's our positioning?"

    def test_strip_mothertree_prefix(self):
        from bot.detect import detect
        result = detect("/mothertree status", participant_count=1, enrolled=True)
        assert result["must_respond"] is True
        assert result["annotation"]["type"] == "status"

    def test_command_status(self):
        from bot.detect import detect
        with patch("bot.detect.get_enrollment") as mock:
            mock.return_value = {"role": "hunter", "current_stage": 0, "current_chapter": 2, "streak": 3}
            result = detect("status", participant_count=1, enrolled=True, slack_user_id="U123")
        assert result["annotation"]["type"] == "status"
        assert result["annotation"]["stage"] == 0

    def test_persona_seth(self):
        from bot.detect import detect
        result = detect("ask seth what is the change?", participant_count=1, enrolled=False)
        assert result["persona"] == "seth"
        assert result["clean_text"] == "what is the change?"

    def test_training_next_dm_only(self):
        from bot.detect import detect
        # In DM: should match
        with patch("bot.detect.deliver_next") as mock:
            mock.return_value = {"chapter": "worldview", "content": "..."}
            result = detect("next", participant_count=1, enrolled=True, enrollment={"id": "e1", "current_stage": 0, "current_chapter": 1, "role": "hunter"})
        assert result["annotation"]["type"] == "training_delivered"

    def test_training_next_channel_ignored(self):
        from bot.detect import detect
        # In channel: should NOT match, falls through
        result = detect("next", participant_count=5, enrolled=True, enrollment={"id": "e1"})
        assert result["annotation"] is None
        assert result["pattern_matched"] is False

    def test_exercise_answer_dm_only(self):
        from bot.detect import detect
        with patch("bot.detect.score_exercise_answer") as mock:
            mock.return_value = {"correct": True, "feedback": "Right!", "progress": {}}
            result = detect("A", participant_count=1, enrolled=True, active_exercise={"id": "c1", "exercise": {"content": {"questions": [{}]}}})
        assert result["annotation"]["type"] == "answer_scored"

    def test_exercise_answer_channel_ignored(self):
        from bot.detect import detect
        result = detect("A", participant_count=5, enrolled=True, active_exercise={"id": "c1"})
        assert result["annotation"] is None

    def test_bare_a_without_exercise_no_match(self):
        from bot.detect import detect
        result = detect("A", participant_count=1, enrolled=True, active_exercise=None)
        assert result["annotation"] is None
        assert result["pattern_matched"] is False

    def test_url_detection(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_url_content") as mock:
            mock.return_value = "Page content here"
            result = detect("check this https://example.com/article", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "url_content"

    def test_url_fetch_failure(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_url_content") as mock:
            mock.return_value = None
            result = detect("check this https://example.com/nope", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "url_failed"

    def test_citizen_inspiration(self):
        from bot.detect import detect
        with patch("bot.detect.generate_citizen_inspiration") as mock:
            mock.return_value = "Here's something to think about..."
            result = detect("next", participant_count=1, enrolled=True, enrollment={"id": "e1", "role": "citizen", "current_stage": 0, "current_chapter": 0})
        assert result["annotation"]["type"] == "citizen_inspiration"

    def test_exercise_pending_nudge(self):
        from bot.detect import detect
        result = detect("what is our worldview?", participant_count=1, enrolled=True,
                        active_exercise={"id": "c1", "current_question": 1, "exercise": {"content": {"questions": [{}, {}, {}]}}})
        assert result["exercise_pending"] == {"question_num": 2, "total": 3}
        assert result["pattern_matched"] is False  # falls through to conversation
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestDetect -v`

- [ ] **Step 3: Implement detect.py**

Create `jobs/bot/detect.py`. This file implements the full detect phase. Key design decisions:
- Returns a dict with: `annotation`, `persona`, `must_respond`, `clean_text`, `pattern_matched`, `exercise_pending`
- DM-only patterns guarded by `participant_count == 1`
- Side effects executed inline (enrollment, scoring, delivery)
- URL fetching via existing `fetch_url_context()` from `enrich.py`
- Citizen check on `next`/`go`/`practice` when `enrollment.role == "citizen"`

Reference these existing functions:
- `bot/enrich.py:fetch_url_context()` — URL fetching
- `bot/enrich.py:extract_urls()` — URL extraction from Slack format
- `bot/training_dm.py:resolve_topic()` — practice topic resolution
- `bot/training_dm.py:calculate_streak()` — streak calculation
- `training/score.py:score_response()` — exercise scoring
- `training/deliver.py:deliver_to_user_on_demand()` — training delivery
- `mothertree/hasura.py:get_enrollment()` — enrollment lookup
- `mothertree/hasura.py:get_active_conversation()` — active exercise lookup
- `mothertree/hasura.py:cancel_stale_conversations()` — stale cleanup

The detect function signature:

```python
def detect(text: str, participant_count: int, enrolled: bool = False,
           enrollment: dict = None, active_exercise: dict = None,
           slack_user_id: str = None, bot_user_id: str = None) -> dict:
```

Returns:

```python
{
    "annotation": dict | None,      # e.g. {"type": "status", "stage": 0, ...}
    "persona": str | None,          # "seth", "lawrence", "trainer"
    "must_respond": bool,           # True if @mention or /mothertree
    "clean_text": str,              # text with prefixes stripped
    "pattern_matched": bool,        # True if any pattern matched
    "exercise_pending": dict | None, # {"question_num": 2, "total": 5}
}
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestDetect -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/detect.py jobs/tests/test_unified.py
git commit -m "Add detect phase with DM-scoped training and annotation production"
```

---

## Task 5: Triage function

**Files:**
- Create: `jobs/bot/triage.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write tests for triage**

```python
class TestTriage:
    """Triage: cheap LLM call for respond/signal/silent."""

    @patch("bot.triage._call_triage_llm")
    def test_dm_always_respond(self, mock_llm):
        from bot.triage import triage
        # Even if LLM says silent, DM overrides to respond
        mock_llm.return_value = {"respond": False, "signal": {"capture": False, "confidence": 0.0}, "reason": "test"}
        result = triage("hello", participant_count=1, recent_messages=[])
        assert result["respond"] is True

    @patch("bot.triage._call_triage_llm")
    def test_channel_can_be_silent(self, mock_llm):
        from bot.triage import triage
        mock_llm.return_value = {"respond": False, "signal": {"capture": False, "confidence": 0.0}, "reason": "small talk"}
        result = triage("nice work!", participant_count=5, recent_messages=[])
        assert result["respond"] is False

    @patch("bot.triage._call_triage_llm")
    def test_signal_flag(self, mock_llm):
        from bot.triage import triage
        mock_llm.return_value = {"respond": True, "signal": {"capture": True, "confidence": 0.9}, "reason": "prospect intel"}
        result = triage("met someone at KubeCon", participant_count=5, recent_messages=[])
        assert result["respond"] is True
        assert result["signal"]["capture"] is True
        assert result["signal"]["confidence"] >= 0.8

    @patch("bot.triage._call_triage_llm")
    def test_low_confidence_signal(self, mock_llm):
        from bot.triage import triage
        mock_llm.return_value = {"respond": True, "signal": {"capture": True, "confidence": 0.5}, "reason": "unclear"}
        result = triage("had an interesting chat", participant_count=5, recent_messages=[])
        assert result["signal"]["confidence"] < 0.8

    def test_triage_prompt_includes_participant_count(self):
        from bot.triage import _build_triage_prompt
        prompt = _build_triage_prompt("hello", participant_count=1, recent_messages=[])
        assert "1 participant" in prompt or "DM" in prompt
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestTriage -v`

- [ ] **Step 3: Implement triage.py**

```python
# jobs/bot/triage.py
"""Triage: cheap LLM call deciding respond/signal/silent."""
import json
import logging
from mothertree.llm import extract
from mothertree.config import EXTRACTION_MODEL

log = logging.getLogger(__name__)

TRIAGE_SYSTEM = """You decide whether Mother Tree should respond to a message and whether it contains commercial signal intelligence.

Return JSON only:
{"respond": true/false, "signal": {"capture": true/false, "confidence": 0.0-1.0}, "reason": "one sentence"}

Rules:
- If this is a DM (1 participant), respond is ALWAYS true.
- Respond when: direct question, request for help, Mother Tree has something useful to add.
- Stay silent when: people talking to each other, small talk, reactions, greetings between colleagues.
- Signal capture: intelligence about a prospect, client, market, competitor, or event.
- Be conservative in channels — if unsure, stay silent."""


def _build_triage_prompt(text: str, participant_count: int, recent_messages: list[dict]) -> str:
    """Build the triage prompt with context."""
    context = ""
    if recent_messages:
        context = "\nRecent messages:\n" + "\n".join(
            f"- [{m.get('name', 'someone')}]: {m['content'][:100]}"
            for m in recent_messages[-5:]
        )
    return f"Participants: {participant_count}\n{context}\n\nNew message: {text}"


def _call_triage_llm(prompt: str) -> dict:
    """Make the triage LLM call."""
    return extract(prompt, TRIAGE_SYSTEM)


def triage(text: str, participant_count: int, recent_messages: list[dict]) -> dict:
    """Run triage on a message. Returns {respond, signal, reason}."""
    prompt = _build_triage_prompt(text, participant_count, recent_messages)
    try:
        result = _call_triage_llm(prompt)
    except Exception as e:
        log.warning(f"Triage LLM failed: {e}")
        # Fail open in DM, fail closed in channel
        return {
            "respond": participant_count == 1,
            "signal": {"capture": False, "confidence": 0.0},
            "reason": "triage failed",
        }

    # DM override: always respond
    if participant_count == 1:
        result["respond"] = True

    return result
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestTriage -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/triage.py jobs/tests/test_unified.py
git commit -m "Add triage function with DM-always-respond override"
```

---

## Task 6: Extended system prompt and model selection in ask.py

**Files:**
- Modify: `jobs/mothertree/ask.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write tests for model selection and extended prompt**

```python
class TestModelSelection:
    """Model selection based on annotation type."""

    def test_status_uses_extraction_model(self):
        from mothertree.ask import select_model
        model = select_model(annotation={"type": "status"})
        from mothertree.config import EXTRACTION_MODEL
        assert model == EXTRACTION_MODEL

    def test_freeform_uses_generation_model(self):
        from mothertree.ask import select_model
        model = select_model(annotation=None)
        from mothertree.config import GENERATION_MODEL
        assert model == GENERATION_MODEL

    def test_signal_flag_uses_generation_model(self):
        from mothertree.ask import select_model
        model = select_model(annotation=None, signal_flag=True)
        from mothertree.config import GENERATION_MODEL
        assert model == GENERATION_MODEL

    def test_persona_uses_generation_model(self):
        from mothertree.ask import select_model
        model = select_model(annotation=None, persona="seth")
        from mothertree.config import GENERATION_MODEL
        assert model == GENERATION_MODEL


class TestExtendedPrompt:
    """System prompt includes new sections."""

    def test_prompt_includes_context_awareness(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "CONTEXT AWARENESS" in prompt

    def test_prompt_includes_signal_thread_behavior(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "SIGNAL THREAD BEHAVIOR" in prompt

    def test_prompt_includes_persona_awareness(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "PERSONA AWARENESS" in prompt

    def test_prompt_includes_actions(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "[ACTION:ci_save]" in prompt

    def test_prompt_includes_exercise_awareness(self):
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "EXERCISE AWARENESS" in prompt
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestModelSelection jobs/tests/test_unified.py::TestExtendedPrompt -v`

- [ ] **Step 3: Add model selection and extended prompt to ask.py**

Add to `jobs/mothertree/ask.py`:

- `select_model(annotation, persona, signal_flag)` function that returns `EXTRACTION_MODEL` for simple annotations, `GENERATION_MODEL` for conversation/persona/signal
- `build_system_prompt()` function that returns the full system prompt with all new sections (CONTEXT AWARENESS, SIGNAL THREAD BEHAVIOR, PERSONA AWARENESS, ACTIONS, EXERCISE AWARENESS)
- Update `ask_with_history()` to accept `annotation`, `signal_flag`, `participant_count`, and `exercise_pending` parameters
- Add `fetch_context()` caching with a simple TTL cache (e.g., `cachetools.TTLCache(maxsize=1, ttl=90)` or a manual timestamp check). `functools.lru_cache` does not support TTL. Cache for 60-120 seconds per the spec.

Reference the exact prompt text from the spec's "System prompt" section.

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestModelSelection jobs/tests/test_unified.py::TestExtendedPrompt -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/mothertree/ask.py jobs/tests/test_unified.py
git commit -m "Add model selection and extended system prompt for unified flow"
```

---

## Task 7: Conversation engine

**Files:**
- Create: `jobs/bot/conversation.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write tests for conversation engine**

```python
class TestConversationEngine:
    """Conversation engine: builds context, calls LLM, handles markers."""

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_freeform_response(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.return_value = "Here's what I know about that."
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        result = converse("what do we know?", memory_ctx=memory, user_name="Jurg")
        assert result["response"] == "Here's what I know about that."
        assert result["actions"] == []

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_action_markers_extracted(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.return_value = "Saved. [ACTION:ci_save] All good."
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        result = converse("yes save it", memory_ctx=memory, user_name="Jurg")
        assert "ci_save" in result["actions"]
        assert "[ACTION:" not in result["response"]

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_content_markers_replaced(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.return_value = "Here's the next piece.\n[CONTENT:training]\nReady?"
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        annotation = {"type": "training_delivered", "content": "Full chapter text here."}
        result = converse("next", memory_ctx=memory, user_name="Jurg", annotation=annotation)
        assert "Full chapter text here." in result["response"]
        assert "[CONTENT:" not in result["response"]

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_fallback_on_llm_failure(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.side_effect = Exception("LLM timeout")
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        annotation = {"type": "status", "role": "hunter", "stage": 0, "chapter": 2, "streak": 3}
        result = converse("status", memory_ctx=memory, user_name="Jurg", annotation=annotation)
        # Should return fallback, not raise
        assert "Stage 0" in result["response"]

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_freeform_fallback_on_failure(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.side_effect = Exception("LLM timeout")
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        result = converse("hello", memory_ctx=memory, user_name="Jurg")
        assert "trouble thinking" in result["response"]

    @patch("bot.conversation.ask_with_history")
    @patch("bot.conversation.append_message")
    def test_slack_formatting_applied(self, mock_append, mock_ask):
        from bot.conversation import converse
        mock_ask.return_value = "**bold** and ### heading"
        memory = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        result = converse("test", memory_ctx=memory, user_name="Jurg")
        assert "**" not in result["response"]
        assert "###" not in result["response"]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestConversationEngine -v`

- [ ] **Step 3: Implement conversation.py**

Create `jobs/bot/conversation.py`. This is the core conversation engine. Key responsibilities:
- Build LLM messages from system prompt + CI + memory + annotation + new message
- Select model based on annotation type
- Call LLM via `ask_with_history()`
- Extract action markers and content markers
- Apply Slack formatting fix (move `_fix_slack_formatting` from `dm_conversation.py`)
- Replace `[CONTENT:training]` with full content from annotation
- Return `{response, actions}` dict
- On LLM failure, return static fallback response based on annotation type
- Persist exchange to memory via `memory.append_message()`

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestConversationEngine -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/conversation.py jobs/tests/test_unified.py
git commit -m "Add conversation engine with fallbacks, markers, model selection"
```

---

## Task 8: Background signal extraction

**Files:**
- Create: `jobs/bot/extraction.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write tests for signal extraction**

```python
class TestSignalExtraction:
    """Background signal extraction from conversation exchanges."""

    @patch("bot.extraction._extract_structured_data")
    @patch("mothertree.hasura.insert_signal")
    def test_extract_creates_signal(self, mock_insert, mock_extract):
        from bot.extraction import extract_signal
        mock_extract.return_value = {
            "entities": [{"type": "person", "name": "Flavia", "company": "KPN"}],
            "actions": [{"who": "Jurg", "what": "call Flavia", "by_when": "next week"}],
            "stage": "signal",
        }
        mock_insert.return_value = "sig-1"
        extract_signal(
            user_message="Met Flavia from KPN, they're migrating",
            assistant_response="Interesting — how far along?",
            user_name="Jurg",
        )
        assert mock_insert.called

    @patch("bot.extraction._extract_structured_data")
    def test_extract_handles_failure_gracefully(self, mock_extract):
        from bot.extraction import extract_signal
        mock_extract.side_effect = Exception("LLM failed")
        # Should not raise
        extract_signal(
            user_message="test",
            assistant_response="test",
            user_name="test",
        )
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestSignalExtraction -v`

- [ ] **Step 3: Implement extraction.py**

Create `jobs/bot/extraction.py`. Responsibilities:
- `extract_signal(user_message, assistant_response, user_name)` — main entry point
- Calls extraction model to get entities, actions, qualification from conversation
- Creates `signals` record via `insert_signal()`
- Creates/updates contacts and companies via `process_entities()`
- Creates `interactions` record with `next_action` if detected
- Creates/updates `opportunities` if qualification suggests it
- Wrapped in try/except — background extraction must never crash the main flow
- `assess_actions(user_message, assistant_response)` — dual-path safety net: independently assesses whether a CI save or signal capture should happen based on conversation content, regardless of action markers. Called from the pipeline when action markers are present (to verify) and when they're absent (to catch missed ones). Returns `{"ci_save": True/False, "capture_signal": True/False}`. For destructive actions (creating opportunities, advancing stages), both the marker AND the assessment must agree.

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestSignalExtraction -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/extraction.py jobs/tests/test_unified.py
git commit -m "Add background signal extraction from conversation exchanges"
```

---

## Task 9: Lazy persistence buffer for channel messages

**Files:**
- Create: `jobs/bot/buffer.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write tests for the channel buffer**

```python
class TestChannelBuffer:
    """In-memory buffer for lazy persistence of silent channel messages."""

    def test_buffer_stores_messages(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=20)
        buf.add("C123", {"role": "user", "name": "Jurg", "content": "hello"})
        assert len(buf.get("C123")) == 1

    def test_buffer_caps_at_max(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=5)
        for i in range(10):
            buf.add("C123", {"role": "user", "content": str(i)})
        assert len(buf.get("C123")) == 5
        assert buf.get("C123")[0]["content"] == "5"  # oldest kept

    def test_flush_returns_and_clears(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=20)
        buf.add("C123", {"role": "user", "content": "hi"})
        msgs = buf.flush("C123")
        assert len(msgs) == 1
        assert len(buf.get("C123")) == 0

    def test_separate_channels(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=20)
        buf.add("C1", {"role": "user", "content": "a"})
        buf.add("C2", {"role": "user", "content": "b"})
        assert len(buf.get("C1")) == 1
        assert len(buf.get("C2")) == 1

    def test_should_flush_when_full(self):
        from bot.buffer import ChannelBuffer
        buf = ChannelBuffer(max_size=5)
        for i in range(5):
            buf.add("C123", {"role": "user", "content": str(i)})
        assert buf.should_flush("C123") is True
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestChannelBuffer -v`

- [ ] **Step 3: Implement buffer.py**

```python
# jobs/bot/buffer.py
"""In-memory channel buffer for lazy persistence of silent messages."""
import threading
from collections import defaultdict


class ChannelBuffer:
    """Thread-safe in-memory buffer for channel messages.

    Messages are buffered here instead of written to the database immediately.
    Flushed when: Mother Tree responds, buffer is full, or on periodic interval.
    """

    def __init__(self, max_size: int = 20):
        self._max_size = max_size
        self._buffers: dict[str, list[dict]] = defaultdict(list)
        self._lock = threading.Lock()

    def add(self, channel_id: str, message: dict) -> None:
        with self._lock:
            buf = self._buffers[channel_id]
            buf.append(message)
            if len(buf) > self._max_size:
                self._buffers[channel_id] = buf[-self._max_size:]

    def get(self, channel_id: str) -> list[dict]:
        with self._lock:
            return list(self._buffers.get(channel_id, []))

    def flush(self, channel_id: str) -> list[dict]:
        with self._lock:
            msgs = list(self._buffers.get(channel_id, []))
            self._buffers[channel_id] = []
            return msgs

    def should_flush(self, channel_id: str) -> bool:
        with self._lock:
            return len(self._buffers.get(channel_id, [])) >= self._max_size
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestChannelBuffer -v`

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/buffer.py jobs/tests/test_unified.py
git commit -m "Add in-memory channel buffer for lazy persistence"
```

---

## Task 10: Unified pipeline integration

**Files:**
- Modify: `jobs/bot/bot.py`
- Create: `jobs/bot/pipeline.py`
- Test: `jobs/tests/test_unified.py`

This is the integration task. A new `pipeline.py` orchestrates detect → triage → converse → extract. `bot.py` becomes a thin routing layer.

- [ ] **Step 1: Write tests for the pipeline**

```python
class TestPipeline:
    """Full pipeline: detect -> triage -> converse -> extract."""

    @patch("bot.pipeline.converse")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.detect")
    def test_dm_freeform(self, mock_detect, mock_memory, mock_converse):
        from bot.pipeline import handle_message
        mock_detect.return_value = {"annotation": None, "persona": None, "must_respond": False, "clean_text": "hello", "pattern_matched": False, "exercise_pending": None}
        mock_memory.return_value = {"messages": [], "store_type": "dm", "store_id": 1, "slack_user_id": "U123"}
        mock_converse.return_value = {"response": "Hi there!", "actions": []}
        responses = []
        handle_message(
            text="hello", user_slack_id="U123", user_name="Jurg",
            channel_id="D123", channel_type="im", participant_count=1,
            respond=lambda msg, **kw: responses.append(msg),
            client=MagicMock(),
        )
        assert len(responses) == 1
        assert responses[0] == "Hi there!"

    @patch("bot.pipeline.converse")
    @patch("bot.pipeline.triage")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.detect")
    def test_channel_silent(self, mock_detect, mock_memory, mock_triage, mock_converse):
        from bot.pipeline import handle_message
        mock_detect.return_value = {"annotation": None, "persona": None, "must_respond": False, "clean_text": "nice", "pattern_matched": False, "exercise_pending": None}
        mock_memory.return_value = {"messages": [], "store_type": "channel", "store_id": 1, "channel_id": "C123"}
        mock_triage.return_value = {"respond": False, "signal": {"capture": False, "confidence": 0.0}, "reason": "small talk"}
        responses = []
        handle_message(
            text="nice", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", channel_type="channel", participant_count=5,
            respond=lambda msg, **kw: responses.append(msg),
            client=MagicMock(),
        )
        assert len(responses) == 0  # silent
        mock_converse.assert_not_called()

    @patch("bot.pipeline.extract_signal")
    @patch("bot.pipeline.converse")
    @patch("bot.pipeline.triage")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.detect")
    def test_channel_signal_capture(self, mock_detect, mock_memory, mock_triage, mock_converse, mock_extract):
        from bot.pipeline import handle_message
        mock_detect.return_value = {"annotation": None, "persona": None, "must_respond": False, "clean_text": "met Flavia from KPN", "pattern_matched": False, "exercise_pending": None}
        mock_memory.return_value = {"messages": [], "store_type": "channel", "store_id": 1, "channel_id": "C123"}
        mock_triage.return_value = {"respond": True, "signal": {"capture": True, "confidence": 0.9}, "reason": "prospect"}
        mock_converse.return_value = {"response": "Tell me more about KPN.", "actions": []}
        responses = []
        handle_message(
            text="met Flavia from KPN", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", channel_type="channel", participant_count=5,
            respond=lambda msg, **kw: responses.append(msg),
            client=MagicMock(),
        )
        assert len(responses) == 1
        mock_extract.assert_called_once()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestPipeline -v`

- [ ] **Step 3: Implement pipeline.py**

Create `jobs/bot/pipeline.py`. Orchestrates the full flow:

```python
def handle_message(text, user_slack_id, user_name, channel_id, channel_type,
                   participant_count, respond, client, thread_ts=None, ts=None,
                   bot_user_id=None):
```

Flow:
1. Sanitize user input (`markers.sanitize_user_input()`)
2. Look up enrollment and active exercise (only if participant_count == 1)
3. Run detect phase
4. Determine memory context (DM, channel, or thread based on `thread_ts`)
5. If pattern matched or must_respond → skip triage, go to converse
6. Else → run triage (parallel with `fetch_context()` if possible)
7. If triage says silent → add message to in-memory channel buffer (not database). If buffer is full, flush to database. Return.
8. Run converse with detect results
9. Respond to user (in-channel or in thread based on `thread_ts` and whether this is a first response)
10. If signal flag or `capture_signal` action → run `extract_signal()` in background. Also run `assess_actions()` as dual-path safety net — verify action markers match conversation intent.
11. When responding in a channel, flush the channel buffer to database first (so memory is current for next message)

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_unified.py::TestPipeline -v`

- [ ] **Step 5: Update bot.py to use the unified pipeline**

Modify `jobs/bot/bot.py`:
- `handle_message()` becomes a thin wrapper that calls `pipeline.handle_message()`
- Route ALL channels through the pipeline, not just #signals
- Add per-channel serialization (simple dict of `threading.Lock` per channel_id)
- Keep `member_joined_channel` handler as-is
- Keep `/mothertree` slash command handler, but route through pipeline after ack()
- Remove: intent classification, enrichment flow, old signal capture logic
- Add startup hook: on bot start, backfill the in-memory channel buffer from Slack API (`conversations.history`, last ~20 messages per channel). Fallback: read from `channel_memory` table if Slack API fails.
- Note on concurrency: the bot uses Slack Bolt with threading (not async). Use `threading.Lock` per channel for serialization.

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/ -v`
Expected: All tests pass. Some existing tests in `test_training.py` and `test_validate.py` may need updates if they test removed functions — update as needed.

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/pipeline.py jobs/bot/bot.py jobs/tests/test_unified.py
git commit -m "Integrate unified pipeline into bot.py with per-channel serialization"
```

---

## Task 11: Thread reminders update

**Files:**
- Modify: `jobs/reminders/thread_reminders.py`
- Test: `jobs/tests/test_unified.py`

- [ ] **Step 1: Write test for dual-table reminder query**

```python
class TestThreadReminders:
    """Thread reminders query both signal_threads and thread_memory."""

    @patch("mothertree.hasura.graphql")
    def test_gets_reminders_from_both_tables(self, mock_gql):
        from reminders.thread_reminders import get_threads_due_reminder
        mock_gql.side_effect = [
            {"signal_threads": [{"id": 1, "slack_thread_ts": "old.123", "messages": []}]},
            {"thread_memory": [{"id": 2, "thread_ts": "new.456", "channel_id": "C1", "messages": [], "remind_context": "check back"}]},
        ]
        results = get_threads_due_reminder()
        assert len(results) == 2
```

- [ ] **Step 2: Run test, verify it fails**

- [ ] **Step 3: Update thread_reminders.py**

Modify to query both `signal_threads` (legacy, existing `get_active_threads_due_reminder()`) and `thread_memory` (new, where `remind_after <= now()`). Merge results. When posting a reminder to a `thread_memory` thread, update `thread_memory` instead of `signal_threads`.

- [ ] **Step 4: Run test, verify it passes**

- [ ] **Step 5: Commit**

```bash
git add jobs/reminders/thread_reminders.py jobs/tests/test_unified.py
git commit -m "Update thread reminders to query both legacy and new memory tables"
```

---

## Task 12: Cleanup

**Files:**
- Remove: `jobs/mothertree/intent.py`
- Remove: `jobs/bot/dm_pipeline.py`
- Remove: `jobs/bot/dm_conversation.py`
- Remove: `jobs/bot/dm_url.py`
- Modify: `jobs/bot/enrich.py` (remove `enrich_signal`, `format_enrichment`, `continue_signal_conversation`)
- Modify: `jobs/tests/test_validate.py` (update tests that reference removed modules)
- Modify: `jobs/tests/test_training.py` (update tests that reference removed modules)

- [ ] **Step 1: Run full test suite to establish baseline**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/ -v`
Expected: All pass (from Task 9).

- [ ] **Step 2: Remove old files**

```bash
rm jobs/mothertree/intent.py
rm jobs/bot/dm_pipeline.py
rm jobs/bot/dm_conversation.py
rm jobs/bot/dm_url.py
```

- [ ] **Step 3: Clean up enrich.py**

Remove `enrich_signal()`, `format_enrichment()`, and `continue_signal_conversation()` from `jobs/bot/enrich.py`. Keep `extract_urls()`, `fetch_url_context()`.

- [ ] **Step 4: Update existing tests**

Update `jobs/tests/test_validate.py` and `jobs/tests/test_training.py`:
- Remove or rewrite tests that import from removed modules (`dm_pipeline`, `dm_conversation`, `dm_url`, `intent`)
- Tests for `classify_dm`, `TestDMPipeline`, `TestDMConversationHandler` → replaced by `TestDetect`, `TestPipeline`, `TestConversationEngine` in `test_unified.py`
- Keep all training, scoring, delivery, and validation tests intact

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Remove old pipeline files and update tests for unified flow"
```

---

## Task 13: Final verification

- [ ] **Step 1: Run full deterministic test suite**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/ -v`
Expected: All pass.

- [ ] **Step 2: Verify no broken imports**

Run: `cd /Users/jurg/Projects/mother-tree && python -c "from bot.pipeline import handle_message; from bot.detect import detect; from bot.triage import triage; from bot.conversation import converse; from bot.extraction import extract_signal; from bot.memory import get_memory; from bot.markers import sanitize_user_input; print('All imports OK')"`

- [ ] **Step 3: Verify bot starts**

Run: `cd /Users/jurg/Projects/mother-tree && python -c "from bot.bot import app; print('Bot app created OK')"`

- [ ] **Step 4: Review the unified pipeline end-to-end**

Check that:
- `bot.py` routes all channels through `pipeline.handle_message()`
- `pipeline.py` orchestrates detect → triage → converse → extract
- `detect.py` scopes training to DM only
- `triage.py` never returns silent for DM
- `conversation.py` uses model selection and fallback responses
- `memory.py` handles DM, channel, and thread contexts
- `markers.py` sanitizes user input and extracts action markers
- `extraction.py` runs in background, never crashes main flow
- `ask.py` has the extended system prompt with all new sections
- `hasura.py` has signal_threads fallback for legacy threads
- `thread_reminders.py` queries both tables

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "Final verification of unified conversation flow"
```
