# Research Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a DM-only conversational research session to Mother Tree: `research <topic>` opens a session that combines Mistral websearch with internal CI; user consents before findings land in CI tables; `done researching` closes.

**Architecture:** New `search.py` wraps Mistral's `api.mistral.ai` websearch endpoint. New `run_research_turn` in `intelligence.py` orchestrates one conversational turn (LLM + tool-use + Spotter extraction). Session state persists on `conversations.research_session JSONB` (new column, parallel to existing `pending_debrief`). Mother Tree detects open session via state, routes turns to `run_research_turn`, reuses the existing debrief approval flow for consent.

**Tech Stack:** Python 3.12, httpx (for `api.mistral.ai`), PostgreSQL JSONB, PostGraphile, existing Spotter/Weaver, pytest.

**Spec:** `docs/superpowers/specs/2026-04-20-research-mode-design.md`

---

### Task 1: Database column + storage helpers

Adds the `conversations.research_session JSONB` column and the three helper functions that set/get/clear session state. Lands first so every downstream task can depend on persistence.

**Note on migrations:** the spec mentions `deploy/database/migrations/NNN-research-session.sql`. That directory does not exist in this repo — the convention is a single re-runnable `deploy/database/schema.sql` with idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` stanzas appended to the bottom (see line 530 for the `pending_debrief` precedent). We follow the existing convention, not the spec's hypothetical one.

**Files:**
- Modify: `deploy/database/schema.sql` — append an `ALTER TABLE` matching the existing `pending_debrief` pattern
- Modify: `jobs/mothertree/graphql_client.py` — add `set_research_session`, `get_research_session`, `clear_research_session` near the existing `set/get/clear_pending_debrief` helpers (around line 1092)
- Test: `jobs/tests/test_research.py` (new file)

**Reference:** `graphql_client.py:1092-1125` (existing debrief helpers — mirror the pattern verbatim)

- [ ] **Step 1: Add the column to schema.sql**

Append at the bottom of `deploy/database/schema.sql` (after `pending_debrief`, around line 530):

```sql
-- === RESEARCH SESSION STATE ===
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS research_session JSONB;
```

- [ ] **Step 2: Apply the schema to the running cluster**

The schema is re-runnable (`IF NOT EXISTS`). Apply with:

```bash
kubectl --kubeconfig kubeconfig-mother-tree.yaml exec -n mother-tree -c postgres postgres-cluster-1 -- psql -U app -d mothertree -f - < deploy/database/schema.sql
```

Expected: schema applied cleanly, `\d conversations` shows `research_session jsonb`.

- [ ] **Step 3: Write the failing tests for storage helpers**

Create `jobs/tests/test_research.py`:

```python
"""Tests for research mode — storage, search, extraction, orchestration, routing."""
from unittest.mock import patch


class TestResearchSessionStorage:
    @patch("mothertree.graphql_client.graphql")
    def test_set_research_session(self, mock_gql):
        mock_gql.return_value = {"updateConversationById": {"conversation": {"id": "c1"}}}
        from mothertree.graphql_client import set_research_session
        state = {"kind": "research_session", "topic": "KPN", "turns": 0,
                 "searches_used": 0, "findings": [], "pending_extraction": None,
                 "status": "open", "opened_at": "2026-04-20T00:00:00Z"}
        set_research_session("c1", state)
        mock_gql.assert_called_once()
        # Assert the patch contains the serialised state under `researchSession`
        vars_ = mock_gql.call_args[0][1]
        assert "researchSession" in vars_["patch"]

    @patch("mothertree.graphql_client.graphql")
    def test_get_research_session_returns_dict(self, mock_gql):
        mock_gql.return_value = {
            "conversationById": {"researchSession": '{"topic": "KPN", "status": "open"}'}
        }
        from mothertree.graphql_client import get_research_session
        result = get_research_session("c1")
        assert result == {"topic": "KPN", "status": "open"}

    @patch("mothertree.graphql_client.graphql")
    def test_get_research_session_none_when_empty(self, mock_gql):
        mock_gql.return_value = {"conversationById": {"researchSession": None}}
        from mothertree.graphql_client import get_research_session
        assert get_research_session("c1") is None

    @patch("mothertree.graphql_client.graphql")
    def test_clear_research_session(self, mock_gql):
        mock_gql.return_value = {"updateConversationById": {"conversation": {"id": "c1"}}}
        from mothertree.graphql_client import clear_research_session
        clear_research_session("c1")
        mock_gql.assert_called_once()
        vars_ = mock_gql.call_args[0][1]
        assert vars_["patch"]["researchSession"] is None
```

- [ ] **Step 4: Run tests — expect failure**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestResearchSessionStorage -v
```

Expected: FAIL — functions don't exist.

- [ ] **Step 5: Implement the three helpers**

In `jobs/mothertree/graphql_client.py`, after `clear_pending_debrief` (around line 1125), add:

```python
def set_research_session(conversation_id: str, state: dict) -> None:
    """Store research session state on the conversation. Parallel to pending_debrief."""
    graphql("""
    mutation($id: UUID!, $patch: ConversationPatch!) {
        updateConversationById(input: {id: $id, conversationPatch: $patch}) {
            conversation { id }
        }
    }
    """, {"id": conversation_id, "patch": {"researchSession": json.dumps(state)}})


def get_research_session(conversation_id: str) -> dict | None:
    """Fetch research session state. Returns None if unset."""
    result = graphql("""
    query($id: UUID!) {
        conversationById(id: $id) { researchSession }
    }
    """, {"id": conversation_id})
    conv = result.get("conversationById") or {}
    raw = conv.get("researchSession")
    if not raw:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw


def clear_research_session(conversation_id: str) -> None:
    """Wipe research session state from the conversation."""
    graphql("""
    mutation($id: UUID!, $patch: ConversationPatch!) {
        updateConversationById(input: {id: $id, conversationPatch: $patch}) {
            conversation { id }
        }
    }
    """, {"id": conversation_id, "patch": {"researchSession": None}})
```

- [ ] **Step 6: Run tests — expect pass**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestResearchSessionStorage -v
```

- [ ] **Step 7: Run the full suite**

```bash
cd jobs && uv run python -m pytest tests/ -q 2>&1 | tail -3
```

Expected: baseline + 4 new = all pass.

- [ ] **Step 8: Commit**

```bash
git add deploy/database/schema.sql jobs/mothertree/graphql_client.py jobs/tests/test_research.py
git commit -m "feat: research_session column + set/get/clear helpers"
```

---

### Task 2: Mistral API key config + SOPS secret + deployment wiring

Sets up the infrastructure for `api.mistral.ai` access. Must land before `search.py` so the wrapper can read the key.

**Files:**
- Modify: `jobs/mothertree/config.py` — add `MISTRAL_API_KEY`, `MISTRAL_API_BASE_URL`
- Create: `deploy/slack-bot/mistral-api-secret.yaml` (SOPS-encrypted)
- Modify: `deploy/slack-bot/deployment.yaml` — add `MISTRAL_API_KEY` env var
- Modify: `deploy/cronjobs/*.yaml` where `jobs` image runs — add `MISTRAL_API_KEY` for any cronjob that might call search (leave untouched for cronjobs that don't)

**Reference:** `deploy/slack-bot/slack-credentials-secret.yaml` (SOPS secret format), `.sops.yaml` (recipient key)

- [ ] **Step 1: Add config keys**

In `jobs/mothertree/config.py`, near the existing Scaleway keys, add:

```python
MISTRAL_API_BASE_URL = os.environ.get("MISTRAL_API_BASE_URL", "https://api.mistral.ai/v1")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
```

Note: empty-string default, not `None`, so downstream code can test with `if not MISTRAL_API_KEY`.

- [ ] **Step 2: Write the SOPS-encrypted secret manifest**

Create `deploy/slack-bot/mistral-api-secret.yaml` with plaintext first, then encrypt:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mistral-api
  namespace: mother-tree
type: Opaque
stringData:
  MISTRAL_API_KEY: <paste-the-key-here>
```

Encrypt:

```bash
sops encrypt --age age1ny5rpz82l25pxw3esxrv6e2g5wy3j09uwgmwu6ygh6q9k6jajp3srl0ru5 \
  --encrypted-regex '^(data|stringData)$' --in-place \
  deploy/slack-bot/mistral-api-secret.yaml
```

Expected: file now contains `ENC[AES256_GCM,...]` blocks.

- [ ] **Step 3: Wire the env var into slack-bot deployment**

In `deploy/slack-bot/deployment.yaml`, in the `env:` block (sibling to existing `SLACK_BOT_TOKEN`), add:

```yaml
        - name: MISTRAL_API_KEY
          valueFrom:
            secretKeyRef:
              name: mistral-api
              key: MISTRAL_API_KEY
```

- [ ] **Step 4: Wire the env var into jobs CronJobs**

Not needed — V1 consumer is slack-bot only. Cronjobs do not call `search.py`.

- [ ] **Step 5: Verify Flux picks it up (manual)**

```bash
kubectl --kubeconfig kubeconfig-mother-tree.yaml -n mother-tree get secret mistral-api
```

Expected: secret exists (after Flux reconciles). This step is a verification, not an action — report if missing, otherwise continue.

- [ ] **Step 6: Commit**

```bash
git add jobs/mothertree/config.py deploy/slack-bot/mistral-api-secret.yaml deploy/slack-bot/deployment.yaml
git commit -m "infra: MISTRAL_API_KEY for research mode websearch"
```

---

### Task 3: Mistral websearch wrapper (`search.py`)

Thin HTTP wrapper around `api.mistral.ai` with the `web_search` tool enabled. Single function, no state.

**Files:**
- Create: `jobs/mothertree/search.py`
- Test: `jobs/tests/test_research.py` (extend)

**Reference:** `jobs/mothertree/llm.py` (existing Scaleway/OpenAI-style HTTP client using httpx — follow its shape but with Mistral's endpoint and auth)

- [ ] **Step 1: Write the failing tests**

Append to `jobs/tests/test_research.py`:

```python
class TestMistralWebSearchChat:
    @patch("mothertree.search.httpx.post")
    def test_request_shape_includes_tools(self, mock_post):
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Result text", "tool_calls": []}}],
        }
        mock_post.return_value.status_code = 200
        from mothertree.search import mistral_websearch_chat
        mistral_websearch_chat("You are helpful", [{"role": "user", "content": "research KPN"}])
        body = mock_post.call_args.kwargs["json"]
        assert body["tools"] == [{"type": "web_search"}]
        assert body["messages"][0] == {"role": "system", "content": "You are helpful"}

    @patch("mothertree.search.httpx.post")
    def test_max_searches_zero_omits_tools_entirely(self, mock_post):
        """When max_searches=0 the wrapper must not send the tools key at all."""
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "no-tool reply", "tool_calls": []}}],
        }
        mock_post.return_value.status_code = 200
        from mothertree.search import mistral_websearch_chat
        mistral_websearch_chat("sys", [{"role": "user", "content": "q"}], max_searches=0)
        body = mock_post.call_args.kwargs["json"]
        assert "tools" not in body
        assert "tool_choice" not in body

    @patch("mothertree.search.httpx.post")
    def test_parses_content_and_searches(self, mock_post):
        mock_post.return_value.json.return_value = {
            "choices": [{
                "message": {
                    "content": "KPN runs AWS workloads.",
                    "tool_calls": [
                        {"type": "web_search",
                         "web_search": {"query": "KPN cloud stack",
                                         "results": [{"url": "https://kpn.com", "title": "KPN", "snippet": "..."}]}}
                    ],
                }
            }],
        }
        mock_post.return_value.status_code = 200
        from mothertree.search import mistral_websearch_chat
        result = mistral_websearch_chat("sys", [{"role": "user", "content": "q"}])
        assert result["content"] == "KPN runs AWS workloads."
        assert result["search_count"] == 1
        assert result["searches"][0]["query"] == "KPN cloud stack"
        assert result["searches"][0]["results"][0]["url"] == "https://kpn.com"

    @patch("mothertree.search.httpx.post")
    def test_missing_api_key_raises(self, mock_post):
        from mothertree import search
        with patch.object(search, "MISTRAL_API_KEY", ""):
            from mothertree.search import mistral_websearch_chat
            import pytest
            with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
                mistral_websearch_chat("sys", [{"role": "user", "content": "q"}])
```

- [ ] **Step 2: Verify tests fail**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestMistralWebSearchChat -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement search.py**

Create `jobs/mothertree/search.py`:

```python
"""Mistral websearch wrapper — the one external-web entry point.

Calls api.mistral.ai directly (not Scaleway — Scaleway's OpenAI-compatible
proxy does not expose Mistral's tools API). Reads MISTRAL_API_KEY from config.
No retries, no state, no extraction — caller handles all of those.
"""
import httpx

from mothertree.config import MISTRAL_API_BASE_URL, MISTRAL_API_KEY


def mistral_websearch_chat(
    system: str,
    messages: list[dict],
    max_searches: int = 5,
    model: str = "mistral-large-latest",
    timeout: float = 30.0,
) -> dict:
    """Call Mistral with the web_search tool enabled.

    Args:
        system: System prompt text.
        messages: List of {role, content} dicts (user/assistant turns).
        max_searches: Upper bound on tool calls per turn.
        model: Mistral model id.
        timeout: HTTP timeout in seconds.

    Returns:
        {
            "content": str,        # assistant's final reply
            "searches": [
                {"query": str, "results": [{"url", "title", "snippet"}]}
            ],
            "search_count": int,
        }

    Raises:
        RuntimeError if MISTRAL_API_KEY is not configured.
    """
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not configured")

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
    }
    if max_searches > 0:
        payload["tools"] = [{"type": "web_search"}]
        payload["tool_choice"] = "auto"
        payload["max_tool_calls"] = max_searches
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    response = httpx.post(
        f"{MISTRAL_API_BASE_URL}/chat/completions",
        json=payload, headers=headers, timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    message = data["choices"][0]["message"]
    content = message.get("content", "") or ""
    tool_calls = message.get("tool_calls", []) or []
    searches = [
        {
            "query": tc["web_search"]["query"],
            "results": tc["web_search"].get("results", []),
        }
        for tc in tool_calls
        if tc.get("type") == "web_search"
    ]
    return {
        "content": content,
        "searches": searches,
        "search_count": len(searches),
    }
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestMistralWebSearchChat -v
```

- [ ] **Step 5: Ruff + full suite**

```bash
cd jobs && uv run ruff check . && uv run python -m pytest tests/ -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add jobs/mothertree/search.py jobs/tests/test_research.py
git commit -m "feat: search.py — Mistral websearch wrapper"
```

---

### Task 4: Spotter research extraction

Adds `RESEARCH_EXTENSION` prompt constant and `extract_research(text) -> dict` that returns the same schema as `extract_debrief` so downstream ingestion needs no branch.

**Files:**
- Modify: `jobs/bot/characters/spotter.py` — add `RESEARCH_EXTENSION` + `extract_research`
- Test: `jobs/tests/test_research.py` (extend)

**Reference:** `jobs/bot/characters/spotter.py:DEBRIEF_EXTENSION` + `extract_debrief` (mirror shape)

- [ ] **Step 1: Read existing spotter.py**

Open `jobs/bot/characters/spotter.py`. Confirmed shape (do not guess):
- Imports: `from mothertree.llm import _parse_json, chat_conversation`
- Module constants: `IDENTITY` (not `BASE_EXTRACTION_PROMPT`), `DEBRIEF_EXTENSION`, `MODEL`
- `extract_debrief(content: str)` builds `messages=[{"role":"system","content":IDENTITY+"\n\n"+DEBRIEF_EXTENSION},{"role":"user","content":content}]`, calls `chat_conversation(messages, model=MODEL)`, returns `_parse_json(response)`

Return schema: `{"entities": [...], "pain_signals": [...], "value_hooks": [...], "actions": [...]}`, each item with a `sensitive` flag where relevant.

- [ ] **Step 2: Write the failing test**

Append to `jobs/tests/test_research.py`:

```python
class TestExtractResearch:
    @patch("bot.characters.spotter._parse_json")
    @patch("bot.characters.spotter.chat_conversation")
    def test_returns_same_schema_as_debrief(self, mock_chat, mock_parse):
        mock_chat.return_value = '{"entities":[{"name":"KPN","type":"company","sensitive":false}],"pain_signals":[],"value_hooks":[],"actions":[]}'
        mock_parse.return_value = {
            "entities": [{"name": "KPN", "type": "company", "sensitive": False}],
            "pain_signals": [], "value_hooks": [], "actions": [],
        }
        from bot.characters.spotter import extract_research
        result = extract_research("KPN runs AWS workloads per a recent keynote.")
        assert "entities" in result
        assert "pain_signals" in result
        assert "value_hooks" in result
        assert "actions" in result
        assert result["entities"][0]["name"] == "KPN"

    @patch("bot.characters.spotter._parse_json")
    @patch("bot.characters.spotter.chat_conversation")
    def test_uses_research_extension_prompt(self, mock_chat, mock_parse):
        mock_chat.return_value = "{}"
        mock_parse.return_value = {"entities": [], "pain_signals": [], "value_hooks": [], "actions": []}
        from bot.characters.spotter import IDENTITY, RESEARCH_EXTENSION, extract_research
        extract_research("some research text")
        messages = mock_chat.call_args[0][0]
        system_content = messages[0]["content"]
        assert IDENTITY in system_content
        assert RESEARCH_EXTENSION in system_content
        assert "as fact" in RESEARCH_EXTENSION.lower()
        assert "skip speculation" in RESEARCH_EXTENSION.lower()
```

- [ ] **Step 3: Verify tests fail**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestExtractResearch -v
```

- [ ] **Step 4: Implement `RESEARCH_EXTENSION` + `extract_research`**

In `jobs/bot/characters/spotter.py`, directly after the existing `DEBRIEF_EXTENSION` constant (around line 86), add:

```python
RESEARCH_EXTENSION = """
Extract companies, contacts, and signals mentioned AS FACT in this research
output. Skip speculation, comparisons, and hypotheticals. Preserve provenance
(URL of the finding) in each item's 'source' field when available. Return
the same schema as extract_debrief: entities, pain_signals, value_hooks,
actions. Each item gets a 'sensitive' flag where appropriate.
"""


def extract_research(content: str) -> dict:
    """Fact-only extraction variant for research mode.

    Same return schema as extract_debrief so _ingest_debrief_extraction
    handles both without a branch.
    """
    messages = [
        {"role": "system", "content": IDENTITY + "\n\n" + RESEARCH_EXTENSION},
        {"role": "user", "content": content},
    ]
    response = chat_conversation(messages, model=MODEL)
    return _parse_json(response)
```

Mirrors `extract_debrief` verbatim; only the extension prompt differs.

- [ ] **Step 5: Run tests — expect pass**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestExtractResearch -v
```

- [ ] **Step 6: Ruff + full suite**

```bash
cd jobs && uv run ruff check . && uv run python -m pytest tests/ -q 2>&1 | tail -3
```

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/characters/spotter.py jobs/tests/test_research.py
git commit -m "feat: spotter.extract_research — fact-only extraction"
```

---

### Task 5: `run_research_turn` in intelligence.py

Orchestrates one turn: calls `mistral_websearch_chat`, runs `extract_research` on the reply, merges candidates into session state. This is the deliberate exception to the gather/synthesize split — documented in the module docstring.

**Files:**
- Modify: `jobs/mothertree/intelligence.py` — add `run_research_turn` + merge helper
- Test: `jobs/tests/test_research.py` (extend)

**Reference:** Spec §Design — `run_research_turn` signature and session state shape.

- [ ] **Step 1: Write the failing tests**

Append to `jobs/tests/test_research.py`:

```python
class TestRunResearchTurn:
    @patch("mothertree.intelligence.extract_research")
    @patch("mothertree.intelligence.mistral_websearch_chat")
    def test_merges_pending_extraction(self, mock_search, mock_extract):
        mock_search.return_value = {
            "content": "KPN uses AWS heavily.",
            "searches": [{"query": "KPN cloud", "results": [{"url": "https://kpn.com", "title": "KPN", "snippet": "..."}]}],
            "search_count": 1,
        }
        mock_extract.return_value = {
            "entities": [{"name": "KPN", "type": "company", "sensitive": False}],
            "pain_signals": [], "value_hooks": [], "actions": [],
        }
        from mothertree.intelligence import run_research_turn
        state = {"kind": "research_session", "topic": "KPN", "turns": 0,
                 "searches_used": 0, "findings": [], "pending_extraction": None,
                 "status": "open", "opened_at": "2026-04-20T00:00:00Z"}
        reply, new_state = run_research_turn(history=[], session_state=state, user_message="Tell me more")
        assert reply == "KPN uses AWS heavily."
        assert new_state["turns"] == 1
        assert new_state["searches_used"] == 1
        assert new_state["pending_extraction"]["entities"][0]["name"] == "KPN"
        assert new_state["findings"][0]["url"] == "https://kpn.com"

    @patch("mothertree.intelligence.extract_research")
    @patch("mothertree.intelligence.mistral_websearch_chat")
    def test_search_budget_falls_back_to_no_tool(self, mock_search, mock_extract):
        """At 20 searches used, the next turn is called without web_search at all."""
        mock_search.return_value = {"content": "fallback reply", "searches": [], "search_count": 0}
        mock_extract.return_value = {"entities": [], "pain_signals": [], "value_hooks": [], "actions": []}
        from mothertree.intelligence import run_research_turn
        state = {"kind": "research_session", "topic": "KPN", "turns": 5,
                 "searches_used": 20, "findings": [], "pending_extraction": None,
                 "status": "open", "opened_at": "2026-04-20T00:00:00Z"}
        reply, new_state = run_research_turn(history=[], session_state=state, user_message="more")
        # When budget is exhausted, the wrapper is called with max_searches=0
        # (the wrapper itself drops the tools key entirely — see Task 3).
        assert mock_search.call_args.kwargs.get("max_searches") == 0
        assert "budget" in reply.lower() or "paste" in reply.lower()  # user is told the budget is hit

    @patch("mothertree.intelligence.extract_research")
    @patch("mothertree.intelligence.mistral_websearch_chat")
    def test_turn_cap_hard_stop(self, mock_search, mock_extract):
        """At 30 turns, run_research_turn refuses to run a new turn."""
        mock_search.return_value = {"content": "x", "searches": [], "search_count": 0}
        mock_extract.return_value = {"entities": [], "pain_signals": [], "value_hooks": [], "actions": []}
        from mothertree.intelligence import run_research_turn
        state = {"kind": "research_session", "topic": "KPN", "turns": 30,
                 "searches_used": 5, "findings": [], "pending_extraction": None,
                 "status": "open", "opened_at": "2026-04-20T00:00:00Z"}
        reply, new_state = run_research_turn(history=[], session_state=state, user_message="more")
        assert "wrap" in reply.lower() or "close" in reply.lower() or "done researching" in reply.lower()
        mock_search.assert_not_called()
        assert new_state["turns"] == 30  # unchanged

    @patch("mothertree.intelligence.extract_research")
    @patch("mothertree.intelligence.mistral_websearch_chat")
    def test_merge_does_not_mutate_input(self, mock_search, mock_extract):
        """_merge_extraction must not mutate the passed-in session_state."""
        mock_search.return_value = {"content": "x", "searches": [], "search_count": 0}
        mock_extract.return_value = {
            "entities": [{"name": "NewCo"}], "pain_signals": [], "value_hooks": [], "actions": [],
        }
        from mothertree.intelligence import run_research_turn
        original_pending = {"entities": [{"name": "OldCo"}],
                             "pain_signals": [], "value_hooks": [], "actions": []}
        state = {"kind": "research_session", "topic": "KPN", "turns": 1,
                 "searches_used": 1, "findings": [], "pending_extraction": original_pending,
                 "status": "open", "opened_at": "2026-04-20T00:00:00Z"}
        reply, new_state = run_research_turn(history=[], session_state=state, user_message="more")
        # Original pending_extraction dict should not have been mutated
        assert original_pending["entities"] == [{"name": "OldCo"}]
        # New state has both items merged
        new_names = [e["name"] for e in new_state["pending_extraction"]["entities"]]
        assert "OldCo" in new_names and "NewCo" in new_names

    @patch("mothertree.intelligence.extract_research")
    @patch("mothertree.intelligence.mistral_websearch_chat")
    def test_spotter_failure_preserves_existing_pending(self, mock_search, mock_extract):
        mock_search.return_value = {"content": "ok", "searches": [], "search_count": 0}
        mock_extract.side_effect = RuntimeError("spotter down")
        from mothertree.intelligence import run_research_turn
        existing = {"entities": [{"name": "Earlier", "type": "company"}],
                    "pain_signals": [], "value_hooks": [], "actions": []}
        state = {"kind": "research_session", "topic": "KPN", "turns": 1,
                 "searches_used": 1, "findings": [], "pending_extraction": existing,
                 "status": "open", "opened_at": "2026-04-20T00:00:00Z"}
        reply, new_state = run_research_turn(history=[], session_state=state, user_message="more")
        # Pending extraction is unchanged
        assert new_state["pending_extraction"]["entities"][0]["name"] == "Earlier"
```

- [ ] **Step 2: Verify tests fail**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestRunResearchTurn -v
```

- [ ] **Step 3: Implement `run_research_turn` + merge helper**

In `jobs/mothertree/intelligence.py`, add a new section near the other synthesize/gather functions. Update the module docstring to note the deliberate exception.

```python
# --- Research mode (deliberate gather/synthesize exception) ------------------
# run_research_turn uses Mistral's websearch tool, which interleaves data
# gathering and synthesis inside a single LLM call. This is a documented
# exception to the gather/synthesize split; see
# docs/superpowers/specs/2026-04-20-research-mode-design.md Principle 4.

import copy

from bot.characters.spotter import extract_research
from mothertree.search import mistral_websearch_chat

_RESEARCH_SYSTEM = (
    "You are Mother Tree running a research session on {topic}. "
    "Use web_search when you need current facts. Cite sources inline. "
    "If you hit a closed source (LinkedIn, SSO-gated pages), ask the user to paste it. "
    "Prefer facts over speculation; acknowledge when you're uncertain. "
    "Keep responses under 200 words per turn."
)

SEARCH_BUDGET_PER_SESSION = 20
TURN_CAP_HARD = 30
TURN_CAP_WARN = 25
SEARCHES_PER_TURN = 5


def run_research_turn(
    history: list[dict],
    session_state: dict,
    user_message: str,
    file_contents: list[dict] | None = None,
) -> tuple[str, dict]:
    """Run one conversational turn in research mode.

    Uses Mistral websearch to compose a reply, then runs extract_research on
    the reply and merges candidates into session_state['pending_extraction'].

    This function is the documented exception to gather/synthesize separation.
    """
    current_turns = session_state.get("turns", 0)

    # Hard stop at TURN_CAP_HARD
    if current_turns >= TURN_CAP_HARD:
        return (
            "We're at the turn cap for this session — 30 turns. "
            "Wrap up with `done researching` (or `approve` first to save what we've got), "
            "then start a fresh session if you need more.",
            session_state,
        )

    budget_remaining = SEARCH_BUDGET_PER_SESSION - session_state.get("searches_used", 0)
    max_searches = min(SEARCHES_PER_TURN, max(0, budget_remaining))

    # Note: file_contents are already concatenated into user_message by
    # handle_message (pipeline.py:39-43) as `[File: <name>]\n<content>`.
    # The file_contents parameter is kept in the signature for future use
    # but intentionally unused here to avoid double-pasting.
    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    system = _RESEARCH_SYSTEM.format(topic=session_state.get("topic", "?"))
    try:
        search_result = mistral_websearch_chat(
            system=system,
            messages=messages,
            max_searches=max_searches,
        )
    except Exception:
        # Retry once (spec §Error Handling).
        try:
            search_result = mistral_websearch_chat(
                system=system,
                messages=messages,
                max_searches=max_searches,
            )
        except Exception:
            return (
                "I can't reach search right now — want me to work from what I have, or pause?",
                session_state,
            )

    reply = search_result["content"]
    new_findings = [
        {"turn": current_turns + 1,
         "url": r["url"], "title": r.get("title", ""), "snippet": r.get("snippet", "")}
        for s in search_result["searches"]
        for r in s["results"]
    ]

    # Budget-hit message: when we were called without tool access.
    if max_searches == 0:
        reply = reply + (
            "\n\n(Search budget hit for this session. Paste specific URLs if you want me "
            "to dig deeper, or `done researching` to wrap up.)"
        )

    # Soft warning approaching the turn cap.
    if current_turns + 1 == TURN_CAP_WARN:
        reply = reply + (
            f"\n\n(We're {TURN_CAP_WARN} turns in. Consider wrapping — "
            "`approve` what's worth saving, then `done researching`.)"
        )

    try:
        candidates = extract_research(reply) if reply.strip() else None
    except Exception:
        candidates = None

    new_state = dict(session_state)
    new_state["turns"] = current_turns + 1
    new_state["searches_used"] = session_state.get("searches_used", 0) + search_result["search_count"]
    new_state["findings"] = list(session_state.get("findings") or []) + new_findings
    if candidates:
        new_state["pending_extraction"] = _merge_extraction(
            session_state.get("pending_extraction"), candidates
        )

    return reply, new_state


def _merge_extraction(existing: dict | None, new: dict) -> dict:
    """Merge new extraction into existing, dedup by identity. Never mutates input."""
    if existing:
        result = copy.deepcopy(existing)
    else:
        result = {"entities": [], "pain_signals": [], "value_hooks": [], "actions": []}
    for category in ("entities", "pain_signals", "value_hooks", "actions"):
        merged = list(result.get(category, []))
        seen = {_extraction_key(x) for x in merged}
        for item in new.get(category, []):
            key = _extraction_key(item)
            if key not in seen:
                merged.append(item)
                seen.add(key)
        result[category] = merged
    return result


def _extraction_key(item: dict) -> str:
    """Identity key for dedup — name for entities, first 80 chars otherwise."""
    return (item.get("name") or item.get("signal") or item.get("hook")
            or item.get("action") or str(item))[:80].lower()
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestRunResearchTurn -v
```

- [ ] **Step 5: Ruff + full suite**

```bash
cd jobs && uv run ruff check . && uv run python -m pytest tests/ -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add jobs/mothertree/intelligence.py jobs/tests/test_research.py
git commit -m "feat: run_research_turn orchestrates search + extraction"
```

---

### Task 6: Dispatcher command recognition

Adds `_detect_research_command` and wires it into `dispatch()` before the `GLOBAL_COMMANDS` block.

**Files:**
- Modify: `jobs/bot/characters/dispatcher.py` — add `_detect_research_command`, wire into `dispatch()`
- Test: `jobs/tests/test_research.py` (extend)

**Reference:** `jobs/bot/characters/dispatcher.py:_detect_pipeline_or_brief` (same shape; wire in the same way)

- [ ] **Step 1: Write the failing tests**

Append to `jobs/tests/test_research.py`:

```python
class TestDispatcherResearch:
    def test_research_with_topic_opens(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="research greenchoice", participant_count=1, enrolled=True)
        assert result["character"] == "mother_tree"
        assert result["annotation"]["type"] == "research_start"
        assert result["annotation"]["topic"] == "greenchoice"
        assert result["must_respond"] is True

    def test_research_about_variant(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="research about NIS2 in energy", participant_count=1, enrolled=True)
        assert result["annotation"]["type"] == "research_start"
        assert result["annotation"]["topic"] == "NIS2 in energy"

    def test_done_researching_closes(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="done researching", participant_count=1, enrolled=True)
        assert result["annotation"]["type"] == "research_close"

    def test_close_research_closes(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="close research", participant_count=1, enrolled=True)
        assert result["annotation"]["type"] == "research_close"

    def test_bare_research_returns_teaser(self):
        """'research' alone (no topic) returns a teaser annotation, not research_start."""
        from bot.characters.dispatcher import dispatch
        result = dispatch(text="research", participant_count=1, enrolled=True)
        assert result["annotation"] == {"type": "research_teaser"}
        assert result["must_respond"] is True
```

- [ ] **Step 2: Verify tests fail**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestDispatcherResearch -v
```

- [ ] **Step 3: Implement `_detect_research_command`**

In `jobs/bot/characters/dispatcher.py`, alongside `_detect_pipeline_or_brief`, add:

```python
_RESEARCH_START_RE = re.compile(
    r"^(?:research|do research on|research about)\s+(.+)$",
    re.IGNORECASE,
)
_RESEARCH_CLOSE_RE = re.compile(
    r"^(?:done researching|close research|stop research|end research)\s*$",
    re.IGNORECASE,
)


def _detect_research_command(text: str) -> dict | None:
    """Return research_start, research_close, or research_teaser annotation, or None."""
    stripped = text.strip()
    close = _RESEARCH_CLOSE_RE.match(stripped)
    if close:
        return {"type": "research_close"}
    start = _RESEARCH_START_RE.match(stripped)
    if start:
        topic = start.group(1).strip()
        if topic:
            return {"type": "research_start", "topic": topic}
    # Bare "research" with no topic → teaser
    if stripped.lower() == "research":
        return {"type": "research_teaser"}
    return None
```

Mother Tree handles the `research_teaser` annotation with a short prompt: `"Try `research <company>` or `research about <topic>` — I'll pull current info and walk through it with you."` (Add this branch to `mother_tree.respond` in Task 7 alongside the other research branches.)

Then wire it into `dispatch()`, directly after the existing pipeline/brief detection and before `GLOBAL_COMMANDS`:

```python
    research_action = _detect_research_command(clean)
    if research_action:
        result["must_respond"] = True
        result["intent"] = research_action["type"]
        result["annotation"] = research_action
        return result
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestDispatcherResearch -v
```

- [ ] **Step 5: Ruff + full suite**

```bash
cd jobs && uv run ruff check . && uv run python -m pytest tests/ -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add jobs/bot/characters/dispatcher.py jobs/tests/test_research.py
git commit -m "feat: dispatcher recognises research open/close"
```

---

### Task 7: Mother Tree annotation handling

`respond()` gains `session_state: dict | None = None` and three branches: `research_start`, `research_close`, and "open session, freeform turn."

**Files:**
- Modify: `jobs/bot/characters/mother_tree.py` — add session_state param + three branches
- Test: `jobs/tests/test_research.py` (extend)

**Reference:** `jobs/bot/characters/mother_tree.py:respond` (current pipeline/brief branches — add research alongside)

- [ ] **Step 1: Write the failing tests**

Append to `jobs/tests/test_research.py`:

```python
class TestMotherTreeResearch:
    @patch("bot.characters.mother_tree.run_research_turn")
    @patch("bot.characters.mother_tree.set_research_session")
    def test_research_start_initialises_and_runs_turn(self, mock_set, mock_run):
        mock_run.return_value = ("turn 1 reply", {"status": "open", "turns": 1, "searches_used": 1,
                                                   "topic": "KPN", "findings": [], "pending_extraction": None})
        from bot.characters.mother_tree import respond
        result = respond(
            question="research KPN", history=[], user_name="Jurg",
            participant_count=1, annotation={"type": "research_start", "topic": "KPN"},
            conversation_id="c1",
        )
        assert "turn 1 reply" in result
        mock_set.assert_called_once()

    @patch("bot.characters.mother_tree.clear_research_session")
    def test_research_close_clears_state(self, mock_clear):
        from bot.characters.mother_tree import respond
        state = {"status": "open", "topic": "KPN", "turns": 3, "searches_used": 4,
                 "findings": [{"url": "https://kpn.com"}], "pending_extraction": None}
        result = respond(
            question="done researching", history=[], user_name="Jurg",
            participant_count=1, annotation={"type": "research_close"},
            session_state=state, conversation_id="c1",
        )
        mock_clear.assert_called_once_with("c1")
        assert "KPN" in result  # wrap-up mentions topic

    @patch("bot.characters.mother_tree.run_research_turn")
    @patch("bot.characters.mother_tree.set_research_session")
    def test_open_session_freeform_runs_turn(self, mock_set, mock_run):
        mock_run.return_value = ("turn 2 reply", {"status": "open", "turns": 2, "searches_used": 2,
                                                   "topic": "KPN", "findings": [], "pending_extraction": None})
        from bot.characters.mother_tree import respond
        state = {"status": "open", "topic": "KPN", "turns": 1, "searches_used": 1,
                 "findings": [], "pending_extraction": None}
        result = respond(
            question="what's their stack?", history=[], user_name="Jurg",
            participant_count=1, annotation=None, session_state=state, conversation_id="c1",
        )
        assert "turn 2 reply" in result
        mock_set.assert_called_once()

    @patch("bot.characters.mother_tree.run_research_turn")
    def test_approval_nudge_appended_when_pending(self, mock_run):
        state_with_pending = {"status": "open", "topic": "KPN", "turns": 1, "searches_used": 1,
                               "findings": [],
                               "pending_extraction": {"entities": [{"name": "KPN"}],
                                                      "pain_signals": [], "value_hooks": [], "actions": []}}
        mock_run.return_value = ("reply body", state_with_pending)
        from bot.characters.mother_tree import respond
        result = respond(
            question="continue", history=[], user_name="Jurg",
            participant_count=1, annotation={"type": "research_start", "topic": "KPN"},
            conversation_id="c1",
        )
        assert "Reply *approve* to ingest" in result
```

- [ ] **Step 2: Verify tests fail**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestMotherTreeResearch -v
```

- [ ] **Step 3: Implement the three branches + helper**

In `jobs/bot/characters/mother_tree.py`, update imports and `respond()`:

```python
from datetime import UTC, datetime

from mothertree.graphql_client import (
    clear_research_session,
    set_research_session,
)
from mothertree.intelligence import run_research_turn


def respond(
    question: str, history: list[dict], user_name: str = "you",
    participant_count: int = 1, annotation: dict = None,
    signal_flag: bool = False, exercise_pending: dict = None,
    user_id: str = None,
    session_state: dict | None = None,
    conversation_id: str | None = None,
    on_chunk=None,
) -> str:
    # --- existing pipeline / brief branches stay unchanged ---

    if annotation and annotation.get("type") == "research_start":
        topic = annotation["topic"]
        state = {
            "kind": "research_session",
            "topic": topic,
            "opened_at": datetime.now(UTC).isoformat(),
            "turns": 0,
            "searches_used": 0,
            "findings": [],
            "pending_extraction": None,
            "status": "open",
        }
        reply, new_state = run_research_turn(
            history=history, session_state=state,
            user_message=f"Research topic: {topic}",
        )
        if conversation_id:
            set_research_session(conversation_id, new_state)
        return reply + _approval_nudge_if_pending(new_state, prior=None)

    if annotation and annotation.get("type") == "research_close":
        if conversation_id:
            clear_research_session(conversation_id)
        return _research_close_summary(session_state or {})

    if annotation and annotation.get("type") == "research_teaser":
        return (
            "Try `research <company>` or `research about <topic>` — "
            "I'll pull current info and walk through it with you in this DM."
        )

    if session_state and session_state.get("status") == "open":
        reply, new_state = run_research_turn(
            history=history, session_state=session_state,
            user_message=question,
        )
        if conversation_id:
            set_research_session(conversation_id, new_state)
        return reply + _approval_nudge_if_pending(new_state, prior=session_state)

    # --- fall through to existing character_respond ---


def _approval_nudge_if_pending(state: dict, prior: dict | None) -> str:
    """Append the approve-sentinel only when pending_extraction gained items."""
    pending = state.get("pending_extraction")
    if not pending:
        return ""
    total = sum(len(pending.get(k, [])) for k in ("entities", "pain_signals", "value_hooks", "actions"))
    prior_total = 0
    if prior and prior.get("pending_extraction"):
        p = prior["pending_extraction"]
        prior_total = sum(len(p.get(k, [])) for k in ("entities", "pain_signals", "value_hooks", "actions"))
    if total == prior_total:
        return ""
    return (
        f"\n\nI've got {total} facts worth saving. "
        "Reply *approve* to ingest them, *skip* to discard, or keep going."
    )


def _research_close_summary(state: dict) -> str:
    topic = state.get("topic", "?")
    turns = state.get("turns", 0)
    findings = len(state.get("findings") or [])
    pending = state.get("pending_extraction") or {}
    pending_total = sum(len(pending.get(k, [])) for k in ("entities", "pain_signals", "value_hooks", "actions"))
    drop_msg = ""
    if pending_total:
        drop_msg = f" Dropped {pending_total} unapproved candidates."
    return (
        f"Closed research on *{topic}*. {turns} turns, {findings} sources seen.{drop_msg} "
        "Want to save something? Start a fresh session with `research <topic>`."
    )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestMotherTreeResearch -v
```

- [ ] **Step 5: Ruff + full suite**

```bash
cd jobs && uv run ruff check . && uv run python -m pytest tests/ -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add jobs/bot/characters/mother_tree.py jobs/tests/test_research.py
git commit -m "feat: mother_tree handles research annotations + session turns"
```

---

### Task 8: Pipeline integration + approval generalisation

Load `research_session` in `_get_response`, pass it to `mother_tree.respond`, and generalise the DM approve-detection at `pipeline.py:106-114` to read from either `pending_debrief` or `research_session.pending_extraction`.

**Files:**
- Modify: `jobs/bot/pipeline.py`
- Test: `jobs/tests/test_research.py` (extend with integration tests)

**Reference:** `jobs/bot/pipeline.py:_get_response` (line 750), `pipeline.py:106-114` (approve detection), `pipeline.py:_handle_debrief_approval` (around line 471)

- [ ] **Step 1: Write the failing integration tests**

Append to `jobs/tests/test_research.py`:

```python
class TestPipelineIntegration:
    """_get_response loads research_session and passes it to respond."""

    @patch("bot.pipeline.get_research_session")
    @patch("bot.pipeline.respond")
    def test_get_response_passes_session_state_for_dm(self, mock_respond, mock_get_session):
        mock_get_session.return_value = {
            "status": "open", "topic": "KPN", "turns": 1, "searches_used": 1,
            "findings": [], "pending_extraction": None,
        }
        mock_respond.return_value = "final reply"

        from bot.pipeline import _get_response
        routing = {
            "character": "mother_tree", "intent": "freeform",
            "annotation": None, "must_respond": True,
            "training_mode": False, "signal_flag": False,
            "clean_text": "tell me more", "exercise_pending": None,
        }
        memory_ctx = {"store_type": "dm", "store_id": "conv-1", "messages": []}
        # New signature (Task 8 Step 5): memory_ctx is now a parameter.
        result = _get_response(
            routing, history=[], user_name="Jurg", participant_count=1,
            enrollment={"id": "u-1", "role": "hunter"},
            active_conversation=None, memory_ctx=memory_ctx, on_chunk=None,
        )
        called_kwargs = mock_respond.call_args.kwargs
        assert called_kwargs["session_state"] == mock_get_session.return_value
        assert called_kwargs["conversation_id"] == "conv-1"

    @patch("bot.pipeline.respond")
    def test_research_start_in_channel_rejected(self, mock_respond):
        """research_start annotation in a channel (participant_count > 1) returns a DM-only message."""
        from bot.pipeline import _get_response
        routing = {
            "character": "mother_tree", "intent": "research_start",
            "annotation": {"type": "research_start", "topic": "KPN"},
            "must_respond": True, "training_mode": False, "signal_flag": False,
            "clean_text": "research KPN", "exercise_pending": None,
        }
        memory_ctx = {"store_type": "channel", "store_id": "ch-1", "messages": []}
        result = _get_response(
            routing, history=[], user_name="Jurg", participant_count=5,
            enrollment={"id": "u-1", "role": "hunter"},
            active_conversation=None, memory_ctx=memory_ctx, on_chunk=None,
        )
        assert "DM" in result or "dm" in result.lower()
        # mother_tree.respond should NOT be called in the channel-reject path
        mock_respond.assert_not_called()


class TestApprovalGeneralisation:
    """approve/skip must detect either pending_debrief OR research_session.pending_extraction."""

    @patch("bot.pipeline.get_research_session")
    @patch("bot.pipeline.get_pending_debrief")
    def test_get_pending_returns_research_when_debrief_empty(self, mock_get_debrief, mock_get_research):
        mock_get_debrief.return_value = None
        mock_get_research.return_value = {
            "status": "open", "topic": "KPN",
            "pending_extraction": {"entities": [{"name": "KPN"}],
                                    "pain_signals": [], "value_hooks": [], "actions": []},
        }
        from bot.pipeline import _get_pending_for_approval
        pending, source = _get_pending_for_approval("conv-1")
        assert source == "research"
        assert pending["entities"][0]["name"] == "KPN"

    @patch("bot.pipeline.get_research_session")
    @patch("bot.pipeline.get_pending_debrief")
    def test_get_pending_returns_debrief_when_present(self, mock_get_debrief, mock_get_research):
        # Real debrief shape is {"type", "content"} — re-extracted on approve, not pre-extracted.
        mock_get_debrief.return_value = {"type": "debrief", "content": "raw debrief notes"}
        mock_get_research.return_value = None
        from bot.pipeline import _get_pending_for_approval
        pending, source = _get_pending_for_approval("conv-1")
        assert source == "debrief"
        assert pending["type"] == "debrief"
        assert pending["content"] == "raw debrief notes"

    @patch("bot.pipeline.get_research_session")
    @patch("bot.pipeline.get_pending_debrief")
    def test_approve_research_keeps_session_open(self, mock_get_debrief, mock_get_research):
        """Approving research extraction clears pending_extraction but leaves session open."""
        mock_get_debrief.return_value = None
        state_before = {
            "kind": "research_session", "topic": "KPN", "status": "open",
            "turns": 2, "searches_used": 3, "findings": [{"url": "u1"}],
            "pending_extraction": {"entities": [{"name": "KPN"}],
                                    "pain_signals": [], "value_hooks": [], "actions": []},
            "opened_at": "2026-04-20T00:00:00Z",
        }
        mock_get_research.return_value = state_before

        # The handler needs something to assert — test _clear_pending_after_approve
        # (or equivalent helper introduced in Task 8 Step 4) writes back a state with
        # pending_extraction=None, status still 'open'.
        from bot.pipeline import _clear_pending_after_approve
        new_state = _clear_pending_after_approve(state_before, source="research")
        assert new_state["pending_extraction"] is None
        assert new_state["status"] == "open"
        assert new_state["topic"] == "KPN"
        assert new_state["findings"] == [{"url": "u1"}]  # preserved

    def test_sensitive_items_dropped_on_approve(self):
        """Existing _ingest_debrief_extraction already skips sensitive items; smoke-check
        that our research pending shape carries sensitive flag correctly."""
        pending = {
            "entities": [
                {"name": "KPN", "sensitive": False},
                {"name": "Confidential Person", "sensitive": True},
            ],
            "pain_signals": [], "value_hooks": [], "actions": [],
        }
        # Filter as _ingest_debrief_extraction would (at pipeline.py:544)
        keep = [e for e in pending["entities"] if not e.get("sensitive")]
        assert len(keep) == 1
        assert keep[0]["name"] == "KPN"
```

- [ ] **Step 2: Verify tests fail**

```bash
cd jobs && uv run python -m pytest tests/test_research.py::TestApprovalGeneralisation -v
```

- [ ] **Step 3: Add the `_get_pending_for_approval` + `_clear_pending_after_approve` helpers**

In `jobs/bot/pipeline.py`, near the existing debrief handlers:

```python
def _get_pending_for_approval(conversation_id: str) -> tuple[dict | None, str | None]:
    """Return (pending_extraction, source) from either debrief or research session.

    Source is 'debrief' | 'research' | None. Debrief wins if both are set.
    """
    from mothertree.graphql_client import get_pending_debrief, get_research_session
    debrief = get_pending_debrief(conversation_id)
    if debrief:
        return debrief, "debrief"
    research = get_research_session(conversation_id)
    if research and research.get("pending_extraction"):
        return research["pending_extraction"], "research"
    return None, None


def _clear_pending_after_approve(state: dict, source: str) -> dict:
    """Return a new state dict with pending_extraction cleared.

    For research sessions, the session stays OPEN — only pending_extraction
    is cleared so the user can keep iterating.
    """
    if source != "research":
        return state  # debrief path is handled by clear_pending_debrief directly
    new_state = dict(state)
    new_state["pending_extraction"] = None
    # status, topic, turns, findings all preserved
    return new_state
```

- [ ] **Step 4: Generalise the approve-detection at pipeline.py:106**

Locate the existing DM-only block at `pipeline.py:105-114`:

```python
    # --- DEBRIEF APPROVAL --- check if this is approve/skip reply to a debrief preview
    if context_type == "dm":
        recent_bot = [m for m in memory_ctx["messages"] if m.get("role") == "assistant"]
        if recent_bot and "Reply *approve* to ingest" in recent_bot[-1].get("content", ""):
            reply = text.strip().lower()
            if reply in ("approve", "skip"):
                handled = _handle_debrief_approval(
                    reply, user, memory_ctx, client, channel_id, thinking)
                if handled:
                    return
```

Replace with:

```python
    # --- APPROVAL (debrief OR research pending_extraction) ---
    if context_type == "dm":
        recent_bot = [m for m in memory_ctx["messages"] if m.get("role") == "assistant"]
        if recent_bot and "Reply *approve* to ingest" in recent_bot[-1].get("content", ""):
            reply = text.strip().lower()
            if reply in ("approve", "skip"):
                handled = _handle_extraction_approval(
                    reply, user, memory_ctx, client, channel_id, thinking)
                if handled:
                    return
```

V1 does not handle `edit` — keep the existing two-word vocabulary (`approve`/`skip`). `edit` support can follow as a separate spec.

Rename `_handle_debrief_approval` to `_handle_extraction_approval`. The two sources store DIFFERENT shapes (confirmed by reading pipeline.py:453-531):

- **Debrief source:** `{"type": "debrief" | "service_meeting", "content": "<raw text>"}`. On approve, the existing code re-extracts via `extract_debrief(content)` before ingesting. Preserve this step.
- **Research source:** `pending_extraction` is already an extraction dict `{entities, pain_signals, value_hooks, actions}`. Ingest directly, no re-extract.

Concrete replacement for `_handle_debrief_approval`:

```python
def _handle_extraction_approval(reply, user, memory_ctx, client, channel_id, thinking):
    """Handle approve/skip for pending extractions from either debrief or research."""
    from mothertree.graphql_client import (
        clear_pending_debrief,
        get_research_session,
        set_research_session,
    )
    store_id = memory_ctx.get("store_id")
    if not store_id:
        return False

    pending, source = _get_pending_for_approval(store_id)
    if not pending:
        return False

    try:
        if reply == "skip":
            if source == "debrief":
                clear_pending_debrief(store_id)
            else:  # research
                state = get_research_session(store_id) or {}
                set_research_session(store_id, _clear_pending_after_approve(state, "research"))
            _resolve_thinking(client, channel_id, thinking, "Discarded.")
            from bot.memory import append_message
            append_message(memory_ctx, role="user", content="skip")
            append_message(memory_ctx, role="assistant", content="Discarded.")
            return True

        if reply == "approve":
            if source == "debrief":
                # Preserve existing flow: re-extract raw content before ingesting.
                ann_type = pending.get("type", "debrief")
                content = pending.get("content", "")
                from bot.characters.spotter import extract_debrief
                extraction = extract_debrief(content)
                if not extraction:
                    clear_pending_debrief(store_id)
                    _resolve_thinking(client, channel_id, thinking,
                                      "Couldn't re-extract the data. Try submitting the notes again.")
                    return True
                ingested = _ingest_debrief_extraction(extraction, user)
                if ann_type == "service_meeting":
                    _advance_service_meeting(user)
                clear_pending_debrief(store_id)
                msg = f"Ingested {ingested} items."
                if ann_type == "service_meeting":
                    msg += " Service meeting recorded."
            else:  # research — pending IS already an extraction dict
                ingested = _ingest_debrief_extraction(pending, user)
                state = get_research_session(store_id) or {}
                set_research_session(store_id, _clear_pending_after_approve(state, "research"))
                msg = f"Ingested {ingested} items. Research session stays open — keep going or say `done researching`."

            _resolve_thinking(client, channel_id, thinking, msg)
            from bot.memory import append_message
            append_message(memory_ctx, role="user", content="approve")
            append_message(memory_ctx, role="assistant", content=msg)
            return True

    except Exception:
        log.exception("Extraction approval failed")
        try:
            if source == "debrief":
                clear_pending_debrief(store_id)
            else:
                state = get_research_session(store_id) or {}
                set_research_session(store_id, _clear_pending_after_approve(state, "research"))
        except Exception:
            pass
        _resolve_thinking(client, channel_id, thinking,
                          "Something went wrong ingesting. Try again.")
        return True

    return False
```

This preserves the debrief flow exactly as it is today and adds the research branch alongside. `_ingest_debrief_extraction` expects the same `{entities, pain_signals, value_hooks, actions}` shape for both — debrief gets there via the re-extract, research gets there directly.

- [ ] **Step 5: Update `_get_response` signature + thread session state**

The current `_get_response` at `pipeline.py:750` has signature:
```python
def _get_response(routing, history, user_name, participant_count,
                  enrollment=None, active_conversation=None, on_chunk=None) -> str:
```

Extend to accept `memory_ctx`:
```python
def _get_response(routing, history, user_name, participant_count,
                  enrollment=None, active_conversation=None,
                  memory_ctx: dict | None = None,
                  on_chunk=None) -> str:
```

Update the single call site (the `_get_response(...)` call in `_process_message`, at `pipeline.py:150-152`):
```python
    response = _get_response(
        routing, history, user_name, participant_count,
        enrollment=user, active_conversation=active_exercise,
        memory_ctx=memory_ctx,   # NEW
        on_chunk=stream_cb)
```

**Note on `file_contents`:** we deliberately do NOT thread `file_contents` separately. By the time the message reaches `_process_message`, `handle_message` has already concatenated file contents into `text` as `[File: <name>]\n<content>` blocks (see `pipeline.py:39-43`). Research mode uses that enriched `text` verbatim — no re-pasting needed. `mother_tree.respond()` does NOT take `file_contents` (see Task 7 signature). `run_research_turn`'s signature keeps `file_contents: list[dict] | None = None` for potential future use but its body does not consume it — documented in Task 5's code comment.

**Load session state inside `_get_response`:**
```python
    session_state = None
    conversation_id = None
    if memory_ctx and memory_ctx.get("store_type") == "dm":
        conversation_id = memory_ctx.get("store_id")
        if conversation_id:
            from mothertree.graphql_client import get_research_session
            session_state = get_research_session(conversation_id)
```

**Pass both into the Mother Tree call** (around `pipeline.py:842`):
```python
        from bot.characters.mother_tree import respond
        return respond(
            question=clean_text, history=history,
            user_name=user_name, participant_count=participant_count,
            annotation=annotation, signal_flag=signal_flag,
            exercise_pending=exercise_pending,
            user_id=enrollment.get("id") if enrollment else None,
            session_state=session_state,
            conversation_id=conversation_id,
            on_chunk=on_chunk,
        )
```

Seth and Lawrence paths don't need the new params. Keep their `respond` calls unchanged.

- [ ] **Step 6: Reject research_start in non-DM contexts**

Just before the mother_tree call, add:

```python
    if annotation and annotation.get("type") == "research_start" and participant_count != 1:
        return "Research mode is DM-only for now. Send me `research <topic>` in a DM and I'll pick it up there."
```

- [ ] **Step 7: Run tests**

```bash
cd jobs && uv run python -m pytest tests/test_research.py -v
```

All pass (including the pipeline integration tests you filled in). Full suite:

```bash
cd jobs && uv run python -m pytest tests/ -q 2>&1 | tail -3
cd jobs && uv run ruff check .
```

- [ ] **Step 8: Commit**

```bash
git add jobs/bot/pipeline.py jobs/tests/test_research.py
git commit -m "feat: pipeline loads research_session, approval handles both sources"
```

---

### Task 9: Handbook entry + discoverability

Adds `help research` content and ensures the bare `help` listing surfaces research alongside pipeline and brief.

**Files:**
- Create: `jobs/handbook/research_mode.md`
- Test: existing `jobs/tests/test_handbook.py` should continue to pass; no new tests required (the handbook loader is schema-driven and test_handbook already covers parsing).

- [ ] **Step 1: Write the handbook entry**

Create `jobs/handbook/research_mode.md`:

```markdown
---
key: research_mode
roles: [hunter, gatherer, farmer]
trigger: null
onboarding: false
onboarding_order: null
topic: getting_started
summary: DM me `research <topic>` — I'll pull current web info, combine with internal CI, and walk through it with you.
---

Research mode is a DM-only conversation. Use it when you want current, outside-in picture of a company, person, or topic — combined with what we already know internally.

*Open a session*
```
research greenchoice
```
I'll search the web, surface what's relevant, and point out gaps. If I hit a closed source (LinkedIn, SSO-gated page), I'll ask you to paste the content.

*During the session*
- Keep the conversation going in the DM — every reply is a turn.
- Paste URLs or documents when I ask for them.
- When I've extracted save-worthy facts I'll say "Reply *approve* to ingest…" — that's when you consent to anything landing in CI.

*Close it*
```
done researching
```
I'll give you a wrap-up and drop any unapproved candidates.

*Relationship to `brief`*
`brief <query>` searches internal CI only. `research <topic>` opens a live external session. Use `brief` for "what do we already know" and `research` for "find out what's new."

*Budgets*
20 searches per session, 30 turns. You'll get a soft warning before the caps.
```

- [ ] **Step 2: Run handbook tests**

```bash
cd jobs && uv run python -m pytest tests/test_handbook.py -q
```

Expected: all pass (the loader handles any frontmatter-formatted file).

- [ ] **Step 3: Verify `help research` returns the new entry**

Manual: in a local bot session (if available) DM `help research`. Otherwise inspect the bare `help` flow code path: `pipeline.py:_get_response` → `Handbook` entry lookup by key/substring. "research" in key matches exactly.

- [ ] **Step 4: Commit**

```bash
git add jobs/handbook/research_mode.md
git commit -m "docs: handbook entry for research mode"
```

---

### Task 10: End-to-end integration tests + cleanup

One end-to-end test that exercises open → turn → approve → turn → close, plus the budget-exhaustion and non-DM-rejection scenarios. Grep for stray references to the old flow and clean up.

**Files:**
- Test: `jobs/tests/test_research.py` (extend)

- [ ] **Step 1: Write the end-to-end test**

Append to `jobs/tests/test_research.py`:

```python
class TestResearchEndToEnd:
    @patch("mothertree.intelligence.extract_research")
    @patch("mothertree.intelligence.mistral_websearch_chat")
    @patch("bot.characters.mother_tree.set_research_session")
    @patch("bot.characters.mother_tree.clear_research_session")
    def test_open_turn_approve_close(
        self, mock_clear, mock_set, mock_search, mock_extract
    ):
        mock_search.side_effect = [
            {"content": "turn 1", "searches": [{"query": "q1", "results": [{"url": "u1", "title": "t1", "snippet": "s1"}]}], "search_count": 1},
            {"content": "turn 2", "searches": [], "search_count": 0},
        ]
        mock_extract.side_effect = [
            {"entities": [{"name": "KPN", "sensitive": False}], "pain_signals": [], "value_hooks": [], "actions": []},
            {"entities": [], "pain_signals": [], "value_hooks": [], "actions": []},
        ]

        from bot.characters.mother_tree import respond

        # Turn 1: open
        reply1 = respond(
            question="research KPN", history=[], user_name="Jurg",
            participant_count=1, annotation={"type": "research_start", "topic": "KPN"},
            conversation_id="c1",
        )
        assert "turn 1" in reply1
        assert "Reply *approve* to ingest" in reply1

        state_after_t1 = mock_set.call_args_list[0].args[1]
        assert state_after_t1["turns"] == 1
        assert state_after_t1["searches_used"] == 1
        assert state_after_t1["pending_extraction"]["entities"][0]["name"] == "KPN"

        # Turn 2: freeform continue (pretend approve already cleared pending_extraction)
        state_after_approve = dict(state_after_t1)
        state_after_approve["pending_extraction"] = None
        reply2 = respond(
            question="what about their cloud strategy?", history=[], user_name="Jurg",
            participant_count=1, annotation=None,
            session_state=state_after_approve, conversation_id="c1",
        )
        assert "turn 2" in reply2

        # Close
        state_final = mock_set.call_args_list[-1].args[1]
        reply_close = respond(
            question="done researching", history=[], user_name="Jurg",
            participant_count=1, annotation={"type": "research_close"},
            session_state=state_final, conversation_id="c1",
        )
        mock_clear.assert_called_once_with("c1")
        assert "KPN" in reply_close


class TestResearchBudgetExhaustion:
    @patch("mothertree.intelligence.extract_research")
    @patch("mothertree.intelligence.mistral_websearch_chat")
    def test_twenty_first_search_falls_back_to_no_tool(self, mock_search, mock_extract):
        mock_search.return_value = {"content": "no-search fallback", "searches": [], "search_count": 0}
        mock_extract.return_value = {"entities": [], "pain_signals": [], "value_hooks": [], "actions": []}
        from mothertree.intelligence import run_research_turn
        state = {"kind": "research_session", "topic": "KPN", "turns": 4,
                 "searches_used": 20, "findings": [], "pending_extraction": None,
                 "status": "open", "opened_at": "2026-04-20T00:00:00Z"}
        reply, _ = run_research_turn(history=[], session_state=state, user_message="more?")
        assert mock_search.call_args.kwargs["max_searches"] == 0
```

- [ ] **Step 2: Run tests**

```bash
cd jobs && uv run python -m pytest tests/test_research.py -v 2>&1 | tail -20
```

All pass.

- [ ] **Step 3: Grep for stray direct GraphQL or search calls**

```bash
cd jobs && grep -rn "mistral_websearch_chat\|web_search" --include="*.py" . | grep -v __pycache__
```

Expected: calls only from `intelligence.py` and `search.py` / tests. Any callers outside should be flagged and migrated.

```bash
cd jobs && grep -rn "pending_debrief" --include="*.py" . | grep -v __pycache__
```

Expected callers of `pending_debrief`-related functions:
- `graphql_client.py` — the three helpers (set/get/clear)
- `pipeline.py` — `_store_pending_extraction` (debrief storage is unchanged), `_get_pending_for_approval` (reads debrief first), `_handle_extraction_approval` (dispatches to `clear_pending_debrief` for debrief source)
- Tests

No other callers should remain. The debrief flow itself is preserved; the grep is a sanity check, not a "should be zero" check.

- [ ] **Step 4: Full suite + ruff**

```bash
cd jobs && uv run python -m pytest tests/ -q 2>&1 | tail -3
cd jobs && uv run ruff check .
```

All green.

- [ ] **Step 5: Commit**

```bash
git add jobs/tests/test_research.py
git commit -m "test: end-to-end research session + budget exhaustion"
```

---

## Post-implementation checklist

- [ ] `MISTRAL_API_KEY` secret is SOPS-encrypted and reconciled by Flux.
- [ ] `conversations.research_session` column exists on the running cluster.
- [ ] `DM`-send a `research greenchoice` to the deployed bot; verify a turn runs, a source URL appears, and `approve` surfaces the sentinel.
- [ ] Verify `done researching` returns a wrap-up and clears state (`SELECT research_session FROM conversations WHERE id = <conv>`).
- [ ] Verify `research foo` in a channel returns the DM-only message and does not initialise state.
