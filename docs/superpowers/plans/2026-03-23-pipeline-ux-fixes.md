# Pipeline UX Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three Slack bot UX issues — thinking indicator flash in channels, thread reply silence, and fact mangling in LLM responses.

**Architecture:** Three independent fixes in two files. Fix 1 changes thinking indicator to a reaction emoji for channel top-level messages. Fix 2 skips triage when Mother Tree already participates in a thread. Fix 3 splits annotations into FACTS (state exactly) and CONTEXT (discuss naturally).

**Tech Stack:** Python, Slack SDK (reactions API), pytest

**Spec:** `docs/superpowers/specs/2026-03-23-pipeline-ux-fixes-design.md`

---

## File Structure

| File | Role |
|------|------|
| `jobs/bot/pipeline.py` | Fix 1 (thinking functions) + Fix 2 (thread eagerness) |
| `jobs/mothertree/ask.py` | Fix 3 (fact preservation) |
| `jobs/tests/test_pipeline_ux.py` | New file — tests for all three fixes |

---

### Task 1: Thinking reaction for channel top-level messages

**Files:**
- Modify: `jobs/bot/pipeline.py:85-139`
- Create: `jobs/tests/test_pipeline_ux.py`

- [ ] **Step 1: Write failing tests for thinking functions**

Create `jobs/tests/test_pipeline_ux.py`:

```python
"""Tests for pipeline UX fixes."""
from unittest.mock import MagicMock, patch, call


class TestThinkingIndicator:
    """Fix 1: Reaction emoji in channels, message in threads/DMs."""

    def _make_client(self):
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234.5678"}
        client.reactions_add.return_value = {"ok": True}
        client.reactions_remove.return_value = {"ok": True}
        client.chat_update.return_value = {"ok": True}
        client.chat_delete.return_value = {"ok": True}
        return client

    def test_thinking_reaction_in_channel(self):
        """Channel top-level: use reaction, not message."""
        from bot.pipeline import _post_thinking
        client = self._make_client()
        result = _post_thinking(client, "C123", thread_ts=None,
                                context_type="channel", message_ts="9999.0001")
        client.reactions_add.assert_called_once_with(
            name="thought_balloon", channel="C123", timestamp="9999.0001")
        client.chat_postMessage.assert_not_called()
        assert result == {"type": "reaction", "ts": "9999.0001"}

    def test_thinking_message_in_thread(self):
        """Thread: post message as before."""
        from bot.pipeline import _post_thinking
        client = self._make_client()
        result = _post_thinking(client, "C123", thread_ts="1111.0001",
                                context_type="thread", message_ts="2222.0001")
        client.chat_postMessage.assert_called_once()
        client.reactions_add.assert_not_called()
        assert result == {"type": "message", "ts": "1234.5678"}

    def test_thinking_message_in_dm(self):
        """DM: post message as before."""
        from bot.pipeline import _post_thinking
        client = self._make_client()
        result = _post_thinking(client, "D123", thread_ts=None,
                                context_type="dm", message_ts="3333.0001")
        client.chat_postMessage.assert_called_once()
        client.reactions_add.assert_not_called()
        assert result == {"type": "message", "ts": "1234.5678"}

    def test_resolve_thinking_reaction(self):
        """Reaction: remove reaction, post response in thread."""
        from bot.pipeline import _resolve_thinking
        client = self._make_client()
        client.chat_postMessage.return_value = {"ts": "5555.0001"}
        info = {"type": "reaction", "ts": "9999.0001"}
        result = _resolve_thinking(client, "C123", info, "Hello world")
        client.reactions_remove.assert_called_once_with(
            name="thought_balloon", channel="C123", timestamp="9999.0001")
        client.chat_postMessage.assert_called_once_with(
            channel="C123", thread_ts="9999.0001", text="Hello world")
        assert result == "5555.0001"

    def test_resolve_thinking_reaction_threads(self):
        """Reaction resolve posts response with thread_ts set."""
        from bot.pipeline import _resolve_thinking
        client = self._make_client()
        info = {"type": "reaction", "ts": "9999.0001"}
        _resolve_thinking(client, "C123", info, "Response text")
        post_call = client.chat_postMessage.call_args
        assert post_call.kwargs.get("thread_ts") == "9999.0001" or \
               (post_call[1].get("thread_ts") == "9999.0001")

    def test_resolve_thinking_message(self):
        """Message: chat_update as before."""
        from bot.pipeline import _resolve_thinking
        client = self._make_client()
        info = {"type": "message", "ts": "1234.5678"}
        result = _resolve_thinking(client, "C123", info, "Hello world")
        client.chat_update.assert_called_once_with(
            channel="C123", ts="1234.5678", text="Hello world")
        client.reactions_remove.assert_not_called()
        assert result == "1234.5678"

    def test_delete_thinking_reaction(self):
        """Reaction: remove reaction."""
        from bot.pipeline import _delete_thinking
        client = self._make_client()
        info = {"type": "reaction", "ts": "9999.0001"}
        _delete_thinking(client, "C123", info)
        client.reactions_remove.assert_called_once_with(
            name="thought_balloon", channel="C123", timestamp="9999.0001")
        client.chat_delete.assert_not_called()

    def test_delete_thinking_message(self):
        """Message: chat_delete as before."""
        from bot.pipeline import _delete_thinking
        client = self._make_client()
        info = {"type": "message", "ts": "1234.5678"}
        _delete_thinking(client, "C123", info)
        client.chat_delete.assert_called_once_with(
            channel="C123", ts="1234.5678")

    def test_thinking_none_handled(self):
        """None thinking_info is handled gracefully."""
        from bot.pipeline import _resolve_thinking, _delete_thinking
        client = self._make_client()
        assert _resolve_thinking(client, "C123", None, "text") is None
        _delete_thinking(client, "C123", None)  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_pipeline_ux.py::TestThinkingIndicator -v`
Expected: TypeError — `_post_thinking` doesn't accept the new parameters yet.

- [ ] **Step 3: Implement the thinking function changes**

In `jobs/bot/pipeline.py`, replace lines 85-123 with:

```python
THINKING_EMOJI = "thought_balloon"


def _post_thinking(client, channel_id: str, thread_ts: str | None,
                   context_type: str = "dm", message_ts: str | None = None) -> dict | None:
    """Show thinking indicator. Returns info dict for later resolve/delete.

    Channel top-level: reaction on the user's message.
    Thread/DM: posted message (updated or deleted later).
    """
    try:
        if context_type == "channel" and message_ts:
            client.reactions_add(
                name=THINKING_EMOJI, channel=channel_id, timestamp=message_ts)
            return {"type": "reaction", "ts": message_ts}
        else:
            result = client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="_thinking..._",
            )
            return {"type": "message", "ts": result["ts"]}
    except Exception as e:
        log.warning(f"Failed to post thinking indicator: {e}")
        return None


def _resolve_thinking(client, channel_id: str, thinking_info: dict | None,
                      response: str):
    """Replace thinking indicator with the real response."""
    if not thinking_info:
        return None
    try:
        if thinking_info["type"] == "reaction":
            # Remove reaction, post response as thread reply
            try:
                client.reactions_remove(
                    name=THINKING_EMOJI, channel=channel_id,
                    timestamp=thinking_info["ts"])
            except Exception:
                pass  # reaction may already be removed
            result = client.chat_postMessage(
                channel=channel_id,
                thread_ts=thinking_info["ts"],
                text=response,
            )
            return result["ts"]
        else:
            client.chat_update(
                channel=channel_id,
                ts=thinking_info["ts"],
                text=response,
            )
            return thinking_info["ts"]
    except Exception as e:
        log.warning(f"Failed to resolve thinking indicator: {e}")
        return None


def _delete_thinking(client, channel_id: str, thinking_info: dict | None):
    """Remove thinking indicator (used when deciding not to respond)."""
    if not thinking_info:
        return
    try:
        if thinking_info["type"] == "reaction":
            client.reactions_remove(
                name=THINKING_EMOJI, channel=channel_id,
                timestamp=thinking_info["ts"])
        else:
            client.chat_delete(channel=channel_id, ts=thinking_info["ts"])
    except Exception:
        pass
```

- [ ] **Step 4: Update the call site in `_process_message`**

In `jobs/bot/pipeline.py`, at line 139 (inside `_process_message`), change:

```python
# Before
    thinking_ts = _post_thinking(client, channel_id, reply_thread_ts)

# After
    thinking_info = _post_thinking(client, channel_id, reply_thread_ts,
                                   context_type=context_type, message_ts=ts)
```

Then find-and-replace all other references to `thinking_ts` in `_process_message`:

- Line 191: `_delete_thinking(client, channel_id, thinking_ts)` → `_delete_thinking(client, channel_id, thinking_info)`
- Line 219: `updated = _resolve_thinking(client, channel_id, thinking_ts, result["response"])` → `updated = _resolve_thinking(client, channel_id, thinking_info, result["response"])`

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_pipeline_ux.py::TestThinkingIndicator -v`
Expected: All 9 pass.

- [ ] **Step 6: Run full suite to check for regressions**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/ -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/pipeline.py jobs/tests/test_pipeline_ux.py
git commit -m "Use reaction emoji for thinking indicator in channel top-level"
```

---

### Task 2: Thread reply eagerness

**Files:**
- Modify: `jobs/bot/pipeline.py:186-187`
- Modify: `jobs/tests/test_pipeline_ux.py`

- [ ] **Step 1: Write failing tests**

Append to `jobs/tests/test_pipeline_ux.py`:

```python
class TestThreadEagerness:
    """Fix 2: Always respond in threads where Mother Tree participated."""

    @patch("bot.pipeline.triage")
    @patch("bot.pipeline.converse")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.detect")
    def test_thread_always_responds_when_participated(
        self, mock_detect, mock_memory, mock_converse, mock_triage
    ):
        """In a thread with prior assistant messages, skip triage, respond."""
        from bot.pipeline import _process_message
        mock_detect.return_value = {
            "annotation": None, "persona": None, "must_respond": False,
            "clean_text": "sounds good", "pattern_matched": False,
            "exercise_pending": None,
        }
        mock_memory.return_value = {
            "store_type": "thread",
            "messages": [
                {"role": "user", "name": "Jurg", "content": "check this"},
                {"role": "assistant", "content": "Got it."},
                {"role": "user", "name": "Pim", "content": "sounds good"},
            ],
        }
        mock_converse.return_value = {"response": "Great!", "actions": []}
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234"}
        client.reactions_add.return_value = {"ok": True}

        _process_message(
            text="sounds good", user_slack_id="U123", user_name="Pim",
            channel_id="C123", context_type="thread", participant_count=3,
            respond=MagicMock(), client=client, thread_ts="1111.0001",
            ts="2222.0001", bot_user_id="BXXX",
        )

        mock_triage.assert_not_called()
        mock_converse.assert_called_once()

    @patch("bot.pipeline.triage")
    @patch("bot.pipeline.converse")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.detect")
    def test_thread_triages_when_not_participated(
        self, mock_detect, mock_memory, mock_converse, mock_triage
    ):
        """In a thread with no assistant messages, triage runs normally."""
        from bot.pipeline import _process_message
        mock_detect.return_value = {
            "annotation": None, "persona": None, "must_respond": False,
            "clean_text": "hello", "pattern_matched": False,
            "exercise_pending": None,
        }
        mock_memory.return_value = {
            "store_type": "thread",
            "messages": [
                {"role": "user", "name": "Jurg", "content": "hello"},
            ],
        }
        mock_triage.return_value = {"respond": False, "signal": {"capture": False}}
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234"}
        client.reactions_add.return_value = {"ok": True}

        _process_message(
            text="hello", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="thread", participant_count=3,
            respond=MagicMock(), client=client, thread_ts="1111.0001",
            ts="2222.0001", bot_user_id="BXXX",
        )

        mock_triage.assert_called_once()

    @patch("bot.pipeline.triage")
    @patch("bot.pipeline.converse")
    @patch("bot.pipeline.get_memory")
    @patch("bot.pipeline.detect")
    def test_channel_still_triages(
        self, mock_detect, mock_memory, mock_converse, mock_triage
    ):
        """Channel top-level always triages, even with assistant messages in memory."""
        from bot.pipeline import _process_message
        mock_detect.return_value = {
            "annotation": None, "persona": None, "must_respond": False,
            "clean_text": "hey", "pattern_matched": False,
            "exercise_pending": None,
        }
        mock_memory.return_value = {
            "store_type": "channel",
            "messages": [
                {"role": "assistant", "content": "Hi there."},
                {"role": "user", "name": "Jurg", "content": "hey"},
            ],
        }
        mock_triage.return_value = {"respond": False, "signal": {"capture": False}}
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "1234"}
        client.reactions_add.return_value = {"ok": True}

        _process_message(
            text="hey", user_slack_id="U123", user_name="Jurg",
            channel_id="C123", context_type="channel", participant_count=5,
            respond=MagicMock(), client=client, thread_ts=None,
            ts="3333.0001", bot_user_id="BXXX",
        )

        mock_triage.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_pipeline_ux.py::TestThreadEagerness -v`
Expected: `test_thread_always_responds_when_participated` fails — triage is still called.

- [ ] **Step 3: Implement thread eagerness check**

In `jobs/bot/pipeline.py`, replace the triage call block (around line 186-187):

```python
# Before
        triage_result = triage(clean_text, participant_count, memory_ctx["messages"][-5:])

# After
        # Always respond in threads where Mother Tree already participates
        in_active_thread = (
            context_type == "thread"
            and any(m.get("role") == "assistant" for m in memory_ctx["messages"])
        )
        if in_active_thread:
            triage_result = {
                "respond": True,
                "signal": {"capture": False, "confidence": 0.0},
                "reason": "active thread participant",
            }
        else:
            triage_result = triage(clean_text, participant_count, memory_ctx["messages"][-5:])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_pipeline_ux.py::TestThreadEagerness -v`
Expected: All 3 pass.

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/pipeline.py jobs/tests/test_pipeline_ux.py
git commit -m "Always respond in threads where Mother Tree already participates"
```

---

### Task 3: Fact preservation in prompts

**Files:**
- Modify: `jobs/mothertree/ask.py:322-331, 407-411`
- Modify: `jobs/tests/test_pipeline_ux.py`

- [ ] **Step 1: Write failing tests**

Append to `jobs/tests/test_pipeline_ux.py`:

```python
class TestFactPreservation:
    """Fix 3: FACTS vs CONTEXT annotation labeling."""

    def test_factual_annotation_uses_facts_label(self):
        """Status annotation should use FACTS label."""
        from mothertree.ask import FACTUAL_ANNOTATION_TYPES
        assert "status" in FACTUAL_ANNOTATION_TYPES
        assert "stats" in FACTUAL_ANNOTATION_TYPES
        assert "enrolled" in FACTUAL_ANNOTATION_TYPES
        assert "answer_scored" in FACTUAL_ANNOTATION_TYPES

    def test_contextual_types_not_in_factual(self):
        """URL content and training should NOT be factual."""
        from mothertree.ask import FACTUAL_ANNOTATION_TYPES
        assert "url_content" not in FACTUAL_ANNOTATION_TYPES
        assert "training_delivered" not in FACTUAL_ANNOTATION_TYPES
        assert "citizen_inspiration" not in FACTUAL_ANNOTATION_TYPES

    @patch("mothertree.ask.fetch_context")
    @patch("mothertree.ask.chat_conversation")
    def test_factual_prompt_says_state_exactly(self, mock_chat, mock_ctx):
        """Factual annotation injects FACTS with 'state these exactly'."""
        from mothertree.ask import ask_with_history
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Welcome!"

        ask_with_history(
            question="enroll hunter",
            history=[],
            annotation={"type": "enrolled", "role": "hunter", "name": "Jurg"},
        )

        system_prompt = mock_chat.call_args[0][0][0]["content"]
        assert "FACTS" in system_prompt
        assert "state these exactly" in system_prompt
        assert "SYSTEM ANNOTATION" not in system_prompt

    @patch("mothertree.ask.fetch_context")
    @patch("mothertree.ask.chat_conversation")
    def test_contextual_prompt_says_weave_naturally(self, mock_chat, mock_ctx):
        """Contextual annotation injects CONTEXT with 'weave naturally'."""
        from mothertree.ask import ask_with_history
        mock_ctx.return_value = "CI context"
        mock_chat.return_value = "Interesting page!"

        ask_with_history(
            question="check this url",
            history=[],
            annotation={"type": "url_content", "url": "https://example.com", "content": "Page text"},
        )

        system_prompt = mock_chat.call_args[0][0][0]["content"]
        assert "CONTEXT" in system_prompt
        assert "Weave this into your response naturally" in system_prompt
        assert "FACTS" not in system_prompt

    def test_context_awareness_updated(self):
        """build_system_prompt contains updated FACTS/CONTEXT guidance."""
        from mothertree.ask import build_system_prompt
        prompt = build_system_prompt()
        assert "State FACTS exactly" in prompt
        assert "Weave these into your response naturally" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_pipeline_ux.py::TestFactPreservation -v`
Expected: ImportError for `FACTUAL_ANNOTATION_TYPES`, assertion failures for prompt content.

- [ ] **Step 3: Add FACTUAL_ANNOTATION_TYPES constant**

In `jobs/mothertree/ask.py`, add after the existing imports (around line 20, near other constants):

```python
FACTUAL_ANNOTATION_TYPES = {
    "status", "stats", "enrolled", "answer_scored",
    "progress", "exercise_started", "enroll",
}
```

- [ ] **Step 4: Update annotation injection in `ask_with_history`**

In `jobs/mothertree/ask.py`, replace lines 407-411:

```python
# Before
    # Annotation context
    if annotation:
        ann_type = annotation.get("type", "")
        system += f"\n\nSYSTEM ANNOTATION ({ann_type}):\n{json.dumps(annotation, default=str)}"
        system += "\nWeave this data into your response naturally."

# After
    # Annotation context — factual data gets FACTS label, rest gets CONTEXT
    if annotation:
        ann_type = annotation.get("type", "")
        if ann_type in FACTUAL_ANNOTATION_TYPES:
            system += f"\n\nFACTS (state these exactly, do not rephrase or omit any values):\n{json.dumps(annotation, default=str)}"
            system += "\nPresent these facts conversationally but do not change the values."
        else:
            system += f"\n\nCONTEXT ({ann_type}):\n{json.dumps(annotation, default=str)}"
            system += "\nWeave this into your response naturally."
```

- [ ] **Step 5: Update CONTEXT AWARENESS in `build_system_prompt`**

In `jobs/mothertree/ask.py`, replace lines 326-331:

```python
# Before
CONTEXT AWARENESS:
You may receive annotations from the system — command results, exercise
scores, URL content, enrollment data. Weave these into your response
naturally. You are a person sharing information, not a system displaying
output. A status check gets a warm update, not a formatted table. An
exercise gets an introduction, not a card drop.

# After
CONTEXT AWARENESS:
You may receive FACTS or CONTEXT from the system. State FACTS exactly
as given — do not rephrase values, numbers, or status information.
Discuss CONTEXT naturally. You are a person sharing information, not
a system displaying output.
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_pipeline_ux.py::TestFactPreservation -v`
Expected: All 5 pass.

- [ ] **Step 7: Run full suite**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/ -v`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add jobs/mothertree/ask.py jobs/tests/test_pipeline_ux.py
git commit -m "Split annotations into FACTS (state exactly) and CONTEXT (weave naturally)"
```
