# Model Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade LLM functions to use Anthropic models (Opus for extraction, Sonnet for conversations, Haiku for classification) while keeping the scoring panel and background extraction on Scaleway.

**Architecture:** Add model routing in `llm.py` — functions detect Claude model IDs and use the Anthropic SDK instead of the Scaleway OpenAI-compatible client. Update config with new model constants. Pin background callers to explicit Scaleway models.

**Tech Stack:** Python, anthropic SDK (already in requirements), OpenAI SDK (Scaleway), pytest.

**Spec:** `docs/superpowers/specs/2026-04-15-model-upgrade-design.md`

---

## File Structure

### Modified Files

| File | Change |
|------|--------|
| `jobs/mothertree/config.py` | Add `CONVERSATION_MODEL`, `FAST_MODEL`, `DEEP_EXTRACTION_MODEL` constants |
| `jobs/mothertree/llm.py` | Add Anthropic routing to all LLM functions, dual streaming |
| `jobs/bot/characters/spotter.py` | Pin to `GENERATION_MODEL` explicitly |
| `jobs/bot/characters/weaver.py` | Pin to `GENERATION_MODEL` explicitly |
| `jobs/bot/characters/archivist.py` | Pin to `GENERATION_MODEL` explicitly |
| `jobs/bot/memory.py` | Pin to `GENERATION_MODEL` explicitly |
| `jobs/ingestion/ingest.py` | Pin consolidation to `GENERATION_MODEL` explicitly |
| `jobs/ingestion/profile.py` | Pin classification to `EXTRACTION_MODEL` explicitly |
| `jobs/bot/pipeline.py` | Pass `on_chunk` to Seth and Lawrence (fix streaming gap) |
| `docs/model-selection-policy.md` | Update policy to reflect new model assignments |

---

## Task 1: Config — New Model Constants

**Files:**
- Modify: `jobs/mothertree/config.py`

- [ ] **Step 1: Add new model constants**

After the existing `EMBEDDING_MODEL` line, add:

```python
# Interactive layer — Anthropic
CONVERSATION_MODEL = os.environ.get("CONVERSATION_MODEL", "claude-sonnet-4-6")
FAST_MODEL = os.environ.get("FAST_MODEL", "claude-haiku-4-5-20251001")
DEEP_EXTRACTION_MODEL = os.environ.get("DEEP_EXTRACTION_MODEL", "claude-opus-4-6")
```

Keep the existing `GENERATION_MODEL`, `EXTRACTION_MODEL`, and Anthropic constants unchanged.

- [ ] **Step 2: Commit**

```bash
git add jobs/mothertree/config.py
git commit -m "config: add Anthropic model constants for interactive layer"
```

---

## Task 2: LLM Routing — Anthropic Backend

**Files:**
- Modify: `jobs/mothertree/llm.py`
- Create: `jobs/tests/test_llm_routing.py`

This is the core change. Each LLM function needs to detect Claude model IDs and route to the Anthropic SDK.

- [ ] **Step 1: Write tests for model routing**

Create `jobs/tests/test_llm_routing.py`:

```python
"""Tests for LLM model routing — Claude models use Anthropic SDK."""
from unittest.mock import MagicMock, patch


class TestIsClaudeModel:
    def test_claude_sonnet(self):
        from mothertree.llm import _is_claude
        assert _is_claude("claude-sonnet-4-6") is True

    def test_claude_haiku(self):
        from mothertree.llm import _is_claude
        assert _is_claude("claude-haiku-4-5-20251001") is True

    def test_claude_opus(self):
        from mothertree.llm import _is_claude
        assert _is_claude("claude-opus-4-6") is True

    def test_qwen(self):
        from mothertree.llm import _is_claude
        assert _is_claude("qwen3.5-397b-a17b") is False

    def test_mistral(self):
        from mothertree.llm import _is_claude
        assert _is_claude("mistral-small-3.2-24b-instruct-2506") is False


class TestAnthropicGenerate:
    @patch("mothertree.llm.anthropic_client")
    def test_generate_routes_to_anthropic(self, mock_client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello from Sonnet")]
        mock_client.messages.create.return_value = mock_response
        from mothertree.llm import _anthropic_generate
        result = _anthropic_generate("system", "user", "claude-sonnet-4-6")
        assert result == "Hello from Sonnet"
        mock_client.messages.create.assert_called_once()


class TestAnthropicExtract:
    @patch("mothertree.llm.anthropic_client")
    def test_extract_routes_to_anthropic(self, mock_client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"entities": []}')]
        mock_client.messages.create.return_value = mock_response
        from mothertree.llm import _anthropic_extract
        result = _anthropic_extract("content", "instruction", "claude-haiku-4-5-20251001")
        assert result == {"entities": []}


class TestAnthropicChat:
    @patch("mothertree.llm.anthropic_client")
    def test_chat_routes_to_anthropic(self, mock_client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Quick reply")]
        mock_client.messages.create.return_value = mock_response
        from mothertree.llm import _anthropic_chat
        result = _anthropic_chat(
            [{"role": "user", "content": "hello"}],
            "claude-haiku-4-5-20251001",
        )
        assert result == "Quick reply"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_llm_routing.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Add routing helper and Anthropic backend functions to llm.py**

At the top of `llm.py`, after the existing imports, add the new config imports:

```python
from mothertree.config import (
    ANTHROPIC_API_KEY,
    ARBITRATION_MODEL,
    CONVERSATION_MODEL,
    DEEP_EXTRACTION_MODEL,
    EXTRACTION_MODEL,
    FAST_MODEL,
    GENERATION_MODEL,
    SCALEWAY_AI_API_KEY,
    SCALEWAY_AI_BASE_URL,
    TRIAGE_MODEL,
)
```

After the client initialization section, add:

```python
def _is_claude(model: str) -> bool:
    """Check if a model ID is a Claude model (routes to Anthropic)."""
    return model.startswith("claude-")
```

Add Anthropic backend functions before the existing `extract()`:

```python
def _anthropic_extract(content: str, instruction: str, model: str) -> dict | list:
    """Extract structured data using an Anthropic model."""
    response = anthropic_client.messages.create(
        model=model,
        max_tokens=4096,
        system="You extract structured data from documents. Always respond with valid JSON only, no markdown fences, no explanation.",
        messages=[{"role": "user", "content": f"{instruction}\n\n---\n\n{content}"}],
    )
    text = response.content[0].text
    if not text:
        raise RuntimeError(f"Empty response from {model}")
    return _parse_json(text)


def _anthropic_extract_deep(content: str, instruction: str, model: str) -> dict | list:
    """Extract structured data using an Anthropic model with extended thinking."""
    response = anthropic_client.messages.create(
        model=model,
        max_tokens=16000,
        thinking={"type": "enabled", "budget_tokens": 10000},
        system="You extract structured data from documents. Always respond with valid JSON only, no markdown fences, no explanation.",
        messages=[{"role": "user", "content": f"{instruction}\n\n---\n\n{content}"}],
        temperature=1.0,  # required by Anthropic when thinking is enabled
    )
    # With thinking enabled, response has thinking blocks + text blocks
    text_blocks = [b.text for b in response.content if b.type == "text"]
    text = text_blocks[0] if text_blocks else ""
    if not text:
        raise RuntimeError(f"Empty response from {model} (thinking may have consumed all tokens)")
    return _parse_json(text)


def _anthropic_generate(system_prompt: str, user_prompt: str, model: str) -> str:
    """Generate text using an Anthropic model."""
    response = anthropic_client.messages.create(
        model=model,
        max_tokens=8000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = response.content[0].text
    if not text:
        raise RuntimeError(f"Empty response from {model}")
    return text


def _anthropic_chat(messages: list[dict], model: str, max_tokens: int = 300) -> str:
    """Quick chat using an Anthropic model."""
    # Anthropic requires system prompt separate from messages
    system = ""
    chat_messages = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            chat_messages.append(m)
    response = anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "You are Mother Tree, a helpful assistant.",
        messages=chat_messages or [{"role": "user", "content": "hello"}],
    )
    return response.content[0].text.strip()


def _anthropic_chat_conversation(messages: list[dict], model: str, on_chunk=None) -> str:
    """Multi-turn conversation using an Anthropic model, with optional streaming."""
    system = ""
    chat_messages = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            chat_messages.append(m)

    if not chat_messages:
        chat_messages = [{"role": "user", "content": "hello"}]

    if on_chunk:
        import time
        text = ""
        last_update = 0
        with anthropic_client.messages.stream(
            model=model,
            max_tokens=8000,
            system=system or "You are Mother Tree.",
            messages=chat_messages,
        ) as stream:
            for chunk in stream.text_stream:
                text += chunk
                now = time.time()
                if now - last_update > 0.8 and len(text) > 20:
                    on_chunk(text)
                    last_update = now
        if text:
            on_chunk(text)
        if not text:
            raise RuntimeError(f"Empty response from {model}")
        return text

    response = anthropic_client.messages.create(
        model=model,
        max_tokens=8000,
        system=system or "You are Mother Tree.",
        messages=chat_messages,
    )
    text = response.content[0].text
    if not text:
        raise RuntimeError(f"Empty response from {model}")
    return text
```

- [ ] **Step 4: Update existing functions to route based on model**

Update `extract()` to use `FAST_MODEL` as default and route:

```python
def extract(content: str, instruction: str, model: str = None) -> dict | list:
    """Extract structured data using the fast model."""
    model = model or FAST_MODEL
    if _is_claude(model) and anthropic_client:
        return _anthropic_extract(content, instruction, model)
    # ... existing Scaleway implementation
```

Update `extract_deep()` to use `DEEP_EXTRACTION_MODEL` as default and route:

```python
def extract_deep(content: str, instruction: str, model: str = None) -> dict | list:
    """Extract structured data using the deep extraction model."""
    model = model or DEEP_EXTRACTION_MODEL
    if _is_claude(model) and anthropic_client:
        return _anthropic_extract_deep(content, instruction, model)
    # ... existing Scaleway implementation
```

Update `generate()` to use `CONVERSATION_MODEL` as default and route:

```python
def generate(system_prompt: str, user_prompt: str, model: str = None) -> str:
    """Generate text using the conversation model."""
    model = model or CONVERSATION_MODEL
    if _is_claude(model) and anthropic_client:
        return _anthropic_generate(system_prompt, user_prompt, model)
    # ... existing Scaleway implementation
```

Update `chat()` to use `FAST_MODEL` as default and route:

```python
def chat(messages: list[dict], model: str = None) -> str:
    """Multi-turn chat using the fast model."""
    model = model or FAST_MODEL
    if _is_claude(model) and anthropic_client:
        return _anthropic_chat(messages, model)
    # ... existing Scaleway implementation
```

Update `chat_conversation()` to use `CONVERSATION_MODEL` as default and route:

```python
def chat_conversation(messages: list[dict], model: str = None, on_chunk=None) -> str:
    """Multi-turn conversation using the conversation model."""
    model = model or CONVERSATION_MODEL
    if _is_claude(model) and anthropic_client:
        return _anthropic_chat_conversation(messages, model, on_chunk)
    # ... existing Scaleway implementation
```

Update `consolidate()` — keep `GENERATION_MODEL` as default (Scaleway):

```python
def consolidate(messages: list[dict], model: str = None) -> dict | list:
    """LLM call for consolidation — stays on Scaleway by default."""
    # No routing change — GENERATION_MODEL (Qwen) is the default
```

- [ ] **Step 5: Run tests**

Run: `cd jobs && python -m pytest tests/test_llm_routing.py -v`
Expected: PASS

Run: `cd jobs && python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add jobs/mothertree/llm.py jobs/tests/test_llm_routing.py
git commit -m "feat: route LLM calls to Anthropic for Claude models, add streaming support"
```

---

## Task 3: Pin Background Callers to Scaleway

**Files:**
- Modify: `jobs/bot/characters/spotter.py`
- Modify: `jobs/bot/characters/weaver.py`
- Modify: `jobs/bot/characters/archivist.py`
- Modify: `jobs/bot/memory.py`
- Modify: `jobs/ingestion/ingest.py`
- Modify: `jobs/ingestion/profile.py`

These callers must explicitly pass the Scaleway model to keep running on European infrastructure.

- [ ] **Step 1: Pin Spotter to GENERATION_MODEL**

In `jobs/bot/characters/spotter.py`, find the `chat_conversation` calls and add `model=GENERATION_MODEL`:

```python
from mothertree.config import GENERATION_MODEL
# ... in each chat_conversation call:
result = chat_conversation(messages, model=GENERATION_MODEL)
```

- [ ] **Step 2: Pin Weaver to GENERATION_MODEL**

Same pattern in `jobs/bot/characters/weaver.py`.

- [ ] **Step 3: Pin Archivist to GENERATION_MODEL**

Same pattern in `jobs/bot/characters/archivist.py`.

- [ ] **Step 4: Pin memory summarization to GENERATION_MODEL**

In `jobs/bot/memory.py`, find the `chat_conversation` call and add `model=GENERATION_MODEL`.

- [ ] **Step 5: Pin consolidation to GENERATION_MODEL**

In `jobs/ingestion/ingest.py`, find the `consolidate` call and add `model=GENERATION_MODEL`.

- [ ] **Step 6: Pin document classification to EXTRACTION_MODEL**

In `jobs/ingestion/profile.py`, find the `extract` calls and add `model=EXTRACTION_MODEL`.

- [ ] **Step 7: Run tests**

Run: `cd jobs && python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add jobs/bot/characters/spotter.py jobs/bot/characters/weaver.py jobs/bot/characters/archivist.py jobs/bot/memory.py jobs/ingestion/ingest.py jobs/ingestion/profile.py
git commit -m "pin: background callers to Scaleway models explicitly"
```

---

## Task 4: Fix Streaming Gap — Seth and Lawrence

**Files:**
- Modify: `jobs/bot/pipeline.py`

- [ ] **Step 1: Find where Seth and Lawrence are called in _get_response**

Find the character dispatch section in `_get_response()`. Seth and Lawrence's `respond()` calls do not receive `on_chunk`. Pass it through.

- [ ] **Step 2: Pass on_chunk to Seth and Lawrence**

Change the Seth and Lawrence respond calls to include `on_chunk=on_chunk` in the kwargs.

- [ ] **Step 3: Update Seth and Lawrence respond() to forward on_chunk**

In `jobs/bot/characters/seth.py` and `jobs/bot/characters/lawrence.py`, find the `respond()` function and ensure it passes `on_chunk` to `character_respond()` (from `base.py`). Check `base.py:character_respond` to confirm it accepts and forwards `on_chunk` to `chat_conversation`.

- [ ] **Step 4: Run tests**

Run: `cd jobs && python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/pipeline.py jobs/bot/characters/seth.py jobs/bot/characters/lawrence.py
git commit -m "fix: stream Seth and Lawrence responses to Slack (was blocking)"
```

---

## Task 5: Update Model Selection Policy

**Files:**
- Modify: `docs/model-selection-policy.md`

- [ ] **Step 1: Update the policy document**

Update the model roles section:
- Add Opus 4.6 for deep extraction
- Update Sonnet 4.6 role to include conversations + strategic output
- Update Haiku 4.5 role to include triage + fast classification + nudges
- Update the pipeline flow diagram
- Update the sovereignty posture section

Principle 4 changes from "Anthropic for coordination and arbitration only" to "Anthropic for the interactive layer, extraction, and arbitration. Scaleway for scoring, background extraction, and consolidation."

- [ ] **Step 2: Commit**

```bash
git add docs/model-selection-policy.md
git commit -m "docs: update model selection policy for Anthropic upgrade"
```

---

## Task 6: Deploy Configuration

**Files:**
- Modify: `deploy/slack-bot/deployment.yaml`
- Modify: all CronJob manifests that use `SCALEWAY_AI_API_KEY`

- [ ] **Step 1: Add ANTHROPIC_API_KEY to slack-bot deployment**

The slack-bot deployment needs `ANTHROPIC_API_KEY` env var (it currently only has Scaleway). Add:

```yaml
- name: ANTHROPIC_API_KEY
  valueFrom:
    secretKeyRef:
      name: anthropic-credentials
      key: api-key
```

- [ ] **Step 2: Add ANTHROPIC_API_KEY to CronJob manifests that need it**

CronJobs that call `generate()`, `extract()`, or `extract_deep()` now need the Anthropic key:
- `discipline-weekly-review.yaml`
- `discipline-monthly-retro.yaml`
- `discipline-qbr-review.yaml`
- `discipline-calendar-sync.yaml`
- `training-deliver.yaml`
- `pulse-scan.yaml`
- All ingestion CronJobs (foundation, narrative)

- [ ] **Step 3: Create Anthropic credentials secret**

Create `deploy/secrets/anthropic-credentials.yaml` (SOPS-encrypted):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: anthropic-credentials
  namespace: mother-tree
type: Opaque
stringData:
  api-key: <ANTHROPIC_API_KEY>
```

Encrypt with: `sops encrypt --age age1ny5rpz82l25pxw3esxrv6e2g5wy3j09uwgmwu6ygh6q9k6jajp3srl0ru5 --encrypted-regex '^(data|stringData)$' --in-place deploy/secrets/anthropic-credentials.yaml`

- [ ] **Step 4: Add to kustomization.yaml**

- [ ] **Step 5: Commit**

```bash
git add deploy/
git commit -m "deploy: add Anthropic credentials to bot + CronJobs"
```
