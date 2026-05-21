# Intelligence Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate all CI data access into `intelligence.py` and add on-demand pipeline/brief commands to bot and CLI.

**Architecture:** New `intelligence.py` module provides gather (data) and synthesize (LLM narrative) functions. All callers — bot characters, CLI commands, discipline cronjobs — become thin wrappers. Pipeline and brief are new bot commands routing through Mother Tree with annotations.

**Tech Stack:** Python 3.12, PostGraphile GraphQL, Scaleway/Anthropic LLM, Slack WebClient, pytest

**Spec:** `docs/superpowers/specs/2026-04-16-intelligence-consolidation-design.md`

---

### Task 1: Create intelligence.py with gather_context()

The first and most impactful migration — `gather_context()` replaces `ask.py:fetch_context()` which is called by every character response.

**Files:**
- Create: `jobs/mothertree/intelligence.py`
- Test: `jobs/tests/test_intelligence.py`

**Reference:** `jobs/mothertree/ask.py:54-109` (current fetch_context), `jobs/mothertree/graphql_client.py:843` (get_organization_profile)

- [ ] **Step 1: Write the failing test for gather_context**

```python
# jobs/tests/test_intelligence.py
import pytest
from unittest.mock import patch


@patch("mothertree.intelligence.graphql")
class TestGatherContext:
    def test_returns_all_ci_tables(self, mock_gql):
        mock_gql.return_value = {
            "allChangesList": [{"id": "c1", "statement": "change1"}],
            "allWorldviewsList": [{"id": "w1", "belief": "belief1"}],
            "allPersonasList": [{"id": "p1", "name": "persona1"}],
            "allCompetitorsList": [{"id": "co1", "type": "comp1"}],
            "allContactsList": [{"id": "ct1", "name": "contact1"}],
            "allSignalsList": [{"id": "s1", "content": "signal1"}],
            "allProofPointsList": [{"id": "pp1", "outcome": "proof1"}],
            "allOrganizationsList": [{"id": "o1", "elementType": "identity", "content": "org1"}],
        }

        from mothertree.intelligence import gather_context
        result = gather_context()

        assert "changes" in result
        assert "worldviews" in result
        assert "personas" in result
        assert "competitors" in result
        assert "contacts" in result
        assert "signals" in result
        assert "proof_points" in result
        assert "organization" in result
        assert result["semantic_results"] is None

    def test_with_query_includes_semantic_results(self, mock_gql):
        mock_gql.return_value = {
            "allChangesList": [], "allWorldviewsList": [],
            "allPersonasList": [], "allCompetitorsList": [],
            "allContactsList": [], "allSignalsList": [],
            "allProofPointsList": [], "allOrganizationsList": [],
        }

        with patch("mothertree.intelligence.search_similar") as mock_search:
            mock_search.return_value = [{"id": "r1", "content": "match"}]
            from mothertree.intelligence import gather_context
            result = gather_context(query="sovereignty")
            assert result["semantic_results"] is not None
            assert mock_search.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && uv run python -m pytest tests/test_intelligence.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement gather_context**

Create `jobs/mothertree/intelligence.py`. Port logic from `ask.py:fetch_context()` (lines 54-109). Include all tables: changes, worldviews, personas, competitors, contacts, signals, proof_points, organization. Add optional semantic search when query is provided.

Reference `ask.py:54-109` for the current GraphQL queries and field selections. Add `proof_points` (via `allProofPointsList`) and `organization` (via `get_organization_profile()` at graphql_client.py:843) which are missing from the current fetch_context.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jobs && uv run python -m pytest tests/test_intelligence.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/mothertree/intelligence.py jobs/tests/test_intelligence.py
git commit -m "feat: intelligence.py with gather_context — single path to CI context"
```

---

### Task 2: Migrate character responses to gather_context

Replace `fetch_context()` import in `base.py` with `gather_context()` from intelligence.py. This is the atomic step — fetch_context usage and its replacement must happen together.

**Files:**
- Modify: `jobs/bot/characters/base.py:91-122`
- Modify: `jobs/mothertree/ask.py` (remove fetch_context)
- Test: `jobs/tests/test_characters.py` (existing tests must still pass)

- [ ] **Step 1: Update base.py to import from intelligence**

In `base.py`, replace:
```python
from mothertree.ask import fetch_context
```
with:
```python
from mothertree.intelligence import gather_context
```

Update `character_respond()` to call `gather_context(query=question)` instead of `fetch_context(question)`. The return shape must match what `build_system_prompt` in `ask.py` expects — check `ask.py:571` for how context is injected into prompts. Adapt the return dict keys if needed (the format_context helper in ask.py may need the same key names).

- [ ] **Step 2: Run existing character tests**

Run: `cd jobs && uv run python -m pytest tests/test_characters.py -v`
Expected: PASS — all existing tests still work

- [ ] **Step 3: Remove fetch_context from ask.py**

Delete `fetch_context()` function (lines 54-109) and its cache from `ask.py`. Keep PERSONAS dict, `build_system_prompt()`, `ask_with_history()`, and all persona/prompt logic.

- [ ] **Step 4: Run full test suite**

Run: `cd jobs && uv run python -m pytest tests/ -x -q`
Expected: All pass. If any test imports `fetch_context` from ask, fix the import.

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/characters/base.py jobs/mothertree/ask.py
git commit -m "refactor: character context now via intelligence.gather_context"
```

---

### Task 3: Add gather_pipeline and synthesize_pipeline

Port `weekly_review.py:gather_pipeline_state()` into intelligence.py as `gather_pipeline()`. Add user_id scoping and counts_only mode. Add `synthesize_pipeline()` with scope-dependent system prompts.

**Files:**
- Modify: `jobs/mothertree/intelligence.py`
- Test: `jobs/tests/test_intelligence.py`

**Reference:** `jobs/discipline/weekly_review.py:18-134` (current gather + synthesis)

- [ ] **Step 1: Write failing tests for gather_pipeline**

```python
@patch("mothertree.intelligence.graphql")
class TestGatherPipeline:
    def test_global_returns_all_opportunities(self, mock_gql):
        mock_gql.return_value = {
            "allOpportunitiesList": [{"id": "o1", "stage": "signal", "title": "Deal A"}],
            "allSignalsList": [], "allInteractionsList": [],
            "allContactsList": [], "allUsersList": [],
        }
        from mothertree.intelligence import gather_pipeline
        result = gather_pipeline()
        assert len(result["opportunities"]) == 1
        assert result["scope"] == "global"

    def test_scoped_filters_by_user(self, mock_gql):
        mock_gql.return_value = {
            "allOpportunitiesList": [
                {"id": "o1", "ownerUserId": "u1", "stage": "signal"},
                {"id": "o2", "ownerUserId": "u2", "stage": "reframe"},
            ],
            "allSignalsList": [], "allInteractionsList": [],
            "allContactsList": [], "allUsersList": [],
        }
        from mothertree.intelligence import gather_pipeline
        result = gather_pipeline(user_id="u1")
        assert all(o["ownerUserId"] == "u1" for o in result["opportunities"])

    def test_counts_only_returns_counts(self, mock_gql):
        mock_gql.return_value = {
            "allOpportunities": {"totalCount": 5},
            "recentSignals": {"totalCount": 12},
            "recentInteractions": {"totalCount": 8},
            "warmHotContacts": {"totalCount": 3},
            "allUsersList": [],
        }
        from mothertree.intelligence import gather_pipeline
        result = gather_pipeline(counts_only=True)
        assert isinstance(result["signals"], int) or "count" in str(type(result["signals"]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && uv run python -m pytest tests/test_intelligence.py::TestGatherPipeline -v`
Expected: FAIL — gather_pipeline not found

- [ ] **Step 3: Implement gather_pipeline**

Port from `weekly_review.py:gather_pipeline_state()` (lines 18-134). Add:
- `user_id` parameter — filter opportunities/contacts/interactions by `ownerUserId`
- `days` parameter — lookback window for signals/interactions (default 7)
- `counts_only` parameter — return totalCount integers instead of full lists (for monthly retro)
- `scope` and `target_name` in return dict

- [ ] **Step 4: Write failing test for synthesize_pipeline**

```python
@patch("mothertree.intelligence.generate")
class TestSynthesizePipeline:
    def test_global_uses_monday_review_style(self, mock_gen):
        mock_gen.return_value = "Pipeline review text"
        from mothertree.intelligence import synthesize_pipeline
        data = {"opportunities": [], "signals": [], "interactions": [],
                "contacts": [], "training": [], "scope": "global", "target_name": None}
        result = synthesize_pipeline(data, scope="global")
        assert result == "Pipeline review text"
        prompt = mock_gen.call_args[0][0]  # system prompt
        assert "Monday" in prompt or "briefing" in prompt.lower()

    def test_personal_uses_coaching_tone(self, mock_gen):
        mock_gen.return_value = "Your pipeline"
        from mothertree.intelligence import synthesize_pipeline
        data = {"opportunities": [], "signals": [], "interactions": [],
                "contacts": [], "training": [], "scope": "personal", "target_name": "Jurg"}
        result = synthesize_pipeline(data, scope="personal")
        prompt = mock_gen.call_args[0][0]
        assert "your" in prompt.lower() or "coaching" in prompt.lower()
```

- [ ] **Step 5: Implement synthesize_pipeline**

Port system prompt from `weekly_review.py:generate_weekly_briefing()` (lines 136-193). Create three prompt variants for scope: global, personal, other. Use `generate()` from llm.py. Support `on_chunk` callback for streaming.

- [ ] **Step 6: Run all intelligence tests**

Run: `cd jobs && uv run python -m pytest tests/test_intelligence.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add jobs/mothertree/intelligence.py jobs/tests/test_intelligence.py
git commit -m "feat: gather_pipeline + synthesize_pipeline with user scoping"
```

---

### Task 4: Add gather_brief and synthesize_brief

Port `ask.py:briefing()` into intelligence.py. Add proof_points to semantic search.

**Files:**
- Modify: `jobs/mothertree/intelligence.py`
- Test: `jobs/tests/test_intelligence.py`

**Reference:** `jobs/mothertree/ask.py:212-300` (current briefing)

- [ ] **Step 1: Write failing test for gather_brief**

```python
@patch("mothertree.intelligence.search_similar")
@patch("mothertree.intelligence.graphql")
class TestGatherBrief:
    def test_returns_all_table_results(self, mock_gql, mock_search):
        mock_gql.return_value = {"allContactsList": [], "allCompaniesList": [],
                                 "allSignalsList": [], "allInteractionsList": []}
        mock_search.return_value = [{"id": "1", "content": "match"}]

        from mothertree.intelligence import gather_brief
        result = gather_brief("KPN")
        assert "contacts" in result
        assert "insights" in result
        assert "proof_points" in result
        assert result["query"] == "KPN"
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement gather_brief**

Port from `ask.py:briefing()` (lines 212-300). Text search on contacts, companies, signals, interactions. Semantic search on changes, worldviews, competitors, insights, proof_points. Deduplicate across text and semantic matches.

- [ ] **Step 4: Write failing test for synthesize_brief**

- [ ] **Step 5: Implement synthesize_brief**

LLM synthesis of brief results into a narrative. System prompt: "You are Mother Tree providing a briefing on {query}. Synthesize what we know across contacts, signals, insights, and competitive context."

- [ ] **Step 6: Run tests, commit**

```bash
git add jobs/mothertree/intelligence.py jobs/tests/test_intelligence.py
git commit -m "feat: gather_brief + synthesize_brief with proof_points"
```

---

### Task 5: Add gather_meeting_context, gather_training_state, gather_account, resolve_user

Remaining gather functions for calendar sync, training, QBR, and user resolution.

**Files:**
- Modify: `jobs/mothertree/intelligence.py`
- Test: `jobs/tests/test_intelligence.py`

**Reference:**
- `calendar_sync.py:137-185` (get_ci_context_for_event)
- `qbr_review.py:24-75` (synthesize_qbr data gathering)
- `graphql_client.py:1462-1530` (get_due_qbrs, get_due_service_meetings)

- [ ] **Step 1: Write failing tests for all four functions**

Test gather_meeting_context: given event with attendees, returns matched contacts + semantic CI results.
Test gather_training_state: given user_id, returns progress/streak/stage.
Test gather_account: given company_name, returns company + contacts + opportunities + plan.
Test resolve_user: given "pim", returns user record. Given ambiguous input, raises AmbiguousUserError.

- [ ] **Step 2: Implement gather_meeting_context**

Port from `calendar_sync.py:get_ci_context_for_event()` (lines 137-185). Per-attendee contact lookup, semantic search on insights/changes/proof_points using meeting title + attendee context.

- [ ] **Step 3: Implement gather_training_state**

Query user record, training_progress by user_id, current stage/chapter from users table. Map to curriculum position name from `training/curriculum.py`.

- [ ] **Step 4: Implement gather_account**

Port data gathering from `qbr_review.py`. Query company by name or id, then contacts, opportunities, interactions, account_plan for that company.

- [ ] **Step 5: Implement resolve_user**

Case-insensitive partial match on users.name and users.email. Use `allUsersList` with filter. If 0 results → return None. If 1 → return user dict. If >1 → raise `AmbiguousUserError(matches=[...])`. Define `AmbiguousUserError` as a simple Exception subclass in intelligence.py.

- [ ] **Step 6: Run all tests, commit**

```bash
git add jobs/mothertree/intelligence.py jobs/tests/test_intelligence.py
git commit -m "feat: gather_meeting_context, training_state, account, resolve_user"
```

---

### Task 6: Add synthesize_weekly and synthesize_monthly

Dedicated synthesis for cronjob outputs.

**Files:**
- Modify: `jobs/mothertree/intelligence.py`
- Test: `jobs/tests/test_intelligence.py`

**Reference:** `weekly_review.py:136-193`, `monthly_retro.py:53-117`

- [ ] **Step 1: Write failing tests**

Test synthesize_weekly: given pipeline data, calls LLM with Monday-review system prompt, returns string <300 words.
Test synthesize_monthly: given counts_only pipeline data, calls LLM with retrospective prompt, returns string.

- [ ] **Step 2: Implement synthesize_weekly**

Port system prompt from `weekly_review.py:generate_weekly_briefing()`. Format pipeline data into the prompt context. Call `generate()`. No streaming — cronjob delivers complete message.

- [ ] **Step 3: Implement synthesize_monthly**

Port from `monthly_retro.py:generate_retro()`. Expects counts in data dict. Format counts into prompt context.

- [ ] **Step 4: Run tests, commit**

```bash
git add jobs/mothertree/intelligence.py jobs/tests/test_intelligence.py
git commit -m "feat: synthesize_weekly + synthesize_monthly"
```

---

### Task 7: Migrate discipline cronjobs to intelligence.py

Make weekly_review, monthly_retro, qbr_review, and calendar_sync thin callers.

**Files:**
- Modify: `jobs/discipline/weekly_review.py`
- Modify: `jobs/discipline/monthly_retro.py`
- Modify: `jobs/discipline/qbr_review.py`
- Modify: `jobs/discipline/calendar_sync.py`
- Test: existing tests in `jobs/tests/test_qbr.py`, `jobs/tests/test_operations.py`

- [ ] **Step 1: Migrate weekly_review.py**

Replace `gather_pipeline_state()` with `gather_pipeline()` from intelligence. Replace `generate_weekly_briefing()` with `synthesize_weekly()`. Delete the old functions. Keep the delivery logic (Slack DM sending).

- [ ] **Step 2: Run existing tests**

Run: `cd jobs && uv run python -m pytest tests/ -x -q`
Expected: PASS. Fix any imports that break.

- [ ] **Step 3: Migrate monthly_retro.py**

Replace inline data gathering with `gather_pipeline(days=30, counts_only=True)`. Replace `generate_retro()` with `synthesize_monthly()`.

- [ ] **Step 4: Migrate qbr_review.py**

Replace inline company data gathering with `gather_account()`. Keep QBR-specific synthesis and delivery logic.

- [ ] **Step 5: Migrate calendar_sync.py**

Replace `get_ci_context_for_event()` with `gather_meeting_context()`. Keep prep/debrief generation and delivery logic.

- [ ] **Step 6: Run full test suite**

Run: `cd jobs && uv run python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add jobs/discipline/
git commit -m "refactor: discipline cronjobs now thin callers to intelligence.py"
```

---

### Task 8: Migrate CLI brief and add pipeline command

Rewire CLI brief to intelligence.py. Add new `mothertree pipeline` command.

**Files:**
- Modify: `jobs/cli.py`
- Modify: `jobs/mothertree/ask.py` (remove briefing function)
- Test: `jobs/tests/test_intelligence.py`

**Reference:** `jobs/cli.py:89-97` (current brief routing)

- [ ] **Step 1: Rewire CLI brief**

In `cli.py`, replace:
```python
from mothertree.ask import briefing
result = briefing(query)
```
with:
```python
from mothertree.intelligence import gather_brief, synthesize_brief
data = gather_brief(query)
result = synthesize_brief(data, query)
```

- [ ] **Step 2: Add CLI pipeline command**

Add to cli.py main():
```python
elif cmd == "pipeline":
    from mothertree.intelligence import gather_pipeline, synthesize_pipeline, resolve_user
    target = args[1] if len(args) > 1 else None
    if target:
        user = resolve_user(target)
        data = gather_pipeline(user_id=user["id"])
        scope = "other"
    else:
        data = gather_pipeline()
        scope = "global"
    print(synthesize_pipeline(data, scope=scope))
```

- [ ] **Step 3: Remove briefing() from ask.py**

Delete the `briefing()` function from ask.py. Keep PERSONAS, build_system_prompt, ask_with_history.

- [ ] **Step 4: Run full test suite**

Run: `cd jobs && uv run python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add jobs/cli.py jobs/mothertree/ask.py
git commit -m "feat: CLI pipeline command + brief rewired to intelligence.py"
```

---

### Task 9: Consolidate GLOBAL_COMMANDS and add bot routing

Fix the GLOBAL_COMMANDS duplication. Add pipeline and brief routing to dispatcher. Add annotation handling to mother_tree.py.

**Files:**
- Modify: `jobs/bot/detect.py:14`
- Modify: `jobs/bot/characters/dispatcher.py:16,184-276`
- Modify: `jobs/bot/characters/mother_tree.py:42-60`
- Test: `jobs/tests/test_characters.py`, `jobs/tests/test_unified.py`

- [ ] **Step 1: Write failing test for pipeline/brief routing**

```python
# In test_characters.py or new test_dispatcher.py
def test_dispatch_pipeline_global():
    routing = dispatch("the pipeline", user_id="u1", ...)
    assert routing["annotation"]["type"] == "pipeline"
    assert routing["annotation"]["scope"] == "global"

def test_dispatch_my_pipeline():
    routing = dispatch("my pipeline", user_id="u1", ...)
    assert routing["annotation"]["type"] == "pipeline"
    assert routing["annotation"]["scope"] == "personal"

def test_dispatch_pipeline_pim():
    routing = dispatch("pim's pipeline", user_id="u1", ...)
    assert routing["annotation"]["type"] == "pipeline"
    assert routing["annotation"]["scope"] == "other"
    assert routing["annotation"]["target"] == "pim"

def test_dispatch_brief():
    routing = dispatch("brief KPN", user_id="u1", ...)
    assert routing["annotation"]["type"] == "brief"
    assert routing["annotation"]["query"] == "KPN"
```

- [ ] **Step 2: Consolidate GLOBAL_COMMANDS**

In `detect.py`, add `"pipeline"` and `"brief"` to GLOBAL_COMMANDS. In `dispatcher.py`, remove the local GLOBAL_COMMANDS copy and import from detect.py instead.

- [ ] **Step 3: Add pipeline/brief pattern matching to dispatcher**

In `dispatch()`, before the LLM triage, add pattern matching:
- `"the pipeline"` or bare `"pipeline"` → pipeline/global annotation
- `"my pipeline"` → pipeline/personal annotation
- `"<name>'s pipeline"` or `"pipeline <name>"` → pipeline/other annotation with target
- `"brief <query>"` → brief annotation with query

Route all to Mother Tree character.

- [ ] **Step 4: Add annotation handling to mother_tree.py**

In `respond()`, before calling `character_respond()`, check annotation type:

```python
if annotation and annotation.get("type") == "pipeline":
    from mothertree.intelligence import gather_pipeline, synthesize_pipeline, resolve_user
    scope = annotation["scope"]
    user_id = None
    if scope == "personal":
        user_id = current_user_id  # from identity resolution
    elif scope == "other":
        target = resolve_user(annotation["target"])
        user_id = target["id"] if target else None
    data = gather_pipeline(user_id=user_id)
    return synthesize_pipeline(data, scope=scope, on_chunk=on_chunk)

if annotation and annotation.get("type") == "brief":
    from mothertree.intelligence import gather_brief, synthesize_brief
    data = gather_brief(annotation["query"])
    return synthesize_brief(data, annotation["query"], on_chunk=on_chunk)
```

- [ ] **Step 5: Run dispatch tests**

Run: `cd jobs && uv run python -m pytest tests/test_characters.py tests/test_unified.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `cd jobs && uv run python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/detect.py jobs/bot/characters/dispatcher.py jobs/bot/characters/mother_tree.py
git commit -m "feat: pipeline + brief bot commands with dispatcher routing"
```

---

### Task 10: Final cleanup and full test pass

Remove dead code, verify no direct GraphQL calls remain in callers, run full suite.

**Files:**
- Verify: all files modified in previous tasks
- Test: full suite

- [ ] **Step 1: Grep for stray GraphQL calls in callers**

```bash
cd jobs && grep -rn "graphql(" discipline/ bot/characters/ --include="*.py" | grep -v "__pycache__" | grep -v "test_"
```

Expected: No results (all GraphQL should go through intelligence.py now). If any remain, migrate them.

Exception: `bot/characters/dispatcher.py` may still call `is_admin()` from graphql_client — that's identity/auth, not CI data, so it's OK.

- [ ] **Step 2: Remove dead imports and functions**

Check ask.py — remove any unused imports or helper functions that only served fetch_context/briefing.
Check weekly_review.py, monthly_retro.py — remove old gather/generate functions if still present.

- [ ] **Step 3: Run full test suite**

Run: `cd jobs && uv run python -m pytest tests/ -v`
Expected: All pass, no warnings about missing imports.

- [ ] **Step 4: Run linter**

Run: `cd jobs && uv run ruff check .`
Expected: Clean.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: remove dead code after intelligence.py consolidation"
```
