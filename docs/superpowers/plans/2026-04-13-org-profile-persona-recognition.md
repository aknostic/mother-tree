# Organization Profile + Persona Recognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synthesize the organization profile during foundation ingest and prevent the Weaver from creating contact records for fictional personas.

**Architecture:** Two independent changes. (1) Wire the existing `consolidate_profile()` function into the `consolidate` CLI command after `consolidate_foundation()`, injecting `ORGANIZATION_NAME` into prompts. (2) Add personas to the Weaver's graph context so the LLM can distinguish personas from real people.

**Tech Stack:** Python, PostgreSQL, PostGraphile GraphQL, Scaleway Generative APIs.

**Spec:** `docs/superpowers/specs/2026-04-13-org-profile-and-persona-recognition.md`

---

## File Structure

### Modified Files

| File | Change |
|------|--------|
| `jobs/mothertree/config.py` | Add `ORGANIZATION_NAME` env var |
| `jobs/ingestion/ingest.py` | Wire profile consolidation into `consolidate` CLI command |
| `jobs/ingestion/profile.py` | Inject `ORGANIZATION_NAME` into extraction and consolidation prompts |
| `jobs/bot/characters/weaver.py` | Add personas to graph context, use `ORGANIZATION_NAME` in team context |
| `deploy/slack-bot/deployment.yaml` | Add `ORGANIZATION_NAME` env var |
| `deploy/cronjobs/foundation-ingest-marketing.yaml` | Add `ORGANIZATION_NAME` env var |
| `deploy/cronjobs/foundation-ingest-site.yaml` | Add `ORGANIZATION_NAME` env var |

### New Files

| File | Responsibility |
|------|---------------|
| `jobs/tests/test_weaver.py` | Tests for Weaver persona recognition in graph context |

### Modified Test Files

| File | Change |
|------|--------|
| `jobs/tests/test_profile.py` | Add consolidate CLI flow test |

---

## Task 1: Config + Deployment Manifests

**Files:**
- Modify: `jobs/mothertree/config.py`
- Modify: `deploy/slack-bot/deployment.yaml`
- Modify: `deploy/cronjobs/foundation-ingest-marketing.yaml`
- Modify: `deploy/cronjobs/foundation-ingest-site.yaml`

- [ ] **Step 1: Add ORGANIZATION_NAME to config**

In `jobs/mothertree/config.py`, after the `ADMIN_EMAIL` line (line 35), add:

```python
ORGANIZATION_NAME = os.environ.get("ORGANIZATION_NAME", "")
```

- [ ] **Step 2: Add env var to slack-bot deployment**

In `deploy/slack-bot/deployment.yaml`, in the `env:` section (after the `ADMIN_EMAIL` block), add:

```yaml
            - name: ORGANIZATION_NAME
              value: "Aknostic"
```

- [ ] **Step 3: Add env var to foundation ingest cronjobs**

In `deploy/cronjobs/foundation-ingest-site.yaml`, in the `env:` section (after the last env var, before `resources:`), add:

```yaml
                - name: ORGANIZATION_NAME
                  value: "Aknostic"
```

Same in `deploy/cronjobs/foundation-ingest-marketing.yaml`.

- [ ] **Step 4: Commit**

```bash
git add jobs/mothertree/config.py deploy/slack-bot/deployment.yaml deploy/cronjobs/foundation-ingest-marketing.yaml deploy/cronjobs/foundation-ingest-site.yaml
git commit -m "config: add ORGANIZATION_NAME env var"
```

---

## Task 2: Inject ORGANIZATION_NAME into Profile Prompts

**Files:**
- Modify: `jobs/ingestion/profile.py`

- [ ] **Step 1: Update EXTRACT_PROFILE_PROMPT**

In `jobs/ingestion/profile.py`, find `EXTRACT_PROFILE_PROMPT` (line 49). The prompt starts with:

```
You are analyzing a document to build an organization profile.
```

Modify `extract_profile()` (line 102) to inject the org name into the prompt before calling `extract_structured`:

```python
def extract_profile(content: str) -> list[dict]:
    """Extract organization profile elements from a document."""
    from mothertree.config import ORGANIZATION_NAME
    prompt = EXTRACT_PROFILE_PROMPT
    if ORGANIZATION_NAME:
        prompt = f"The organization you are profiling is {ORGANIZATION_NAME}.\n\n{prompt}"
    try:
        elements = extract_structured(content, prompt)
    except Exception as e:
        log.warning(f"Profile extraction failed: {e}")
        return []
    if not isinstance(elements, list):
        return []
    result = []
    for e in elements:
        if not isinstance(e, dict) or "type" not in e:
            continue
        e["type"] = e["type"].lower()
        if e["type"] in VALID_ELEMENT_TYPES and e.get("content"):
            result.append(e)
    return result
```

- [ ] **Step 2: Update CONSOLIDATE_PROMPT**

Modify `consolidate_profile()` (line 267) to inject the org name:

```python
def consolidate_profile(elements: list[dict]) -> list[dict]:
    """Consolidate profile elements — deduplicate and synthesize."""
    from mothertree.config import ORGANIZATION_NAME
    if not elements:
        return []

    # Group by type
    by_type = {}
    for e in elements:
        t = e.get("type") or e.get("element_type", "")
        content = e.get("content", "")
        if t and content:
            by_type.setdefault(t, []).append(content)

    parts = []
    for t in ("identity", "change", "audience", "competitor_category"):
        items = by_type.get(t, [])
        if items:
            parts.append(f"\n{t.upper()} ({len(items)} elements):")
            for i, item in enumerate(items, 1):
                parts.append(f"  {i}. {item}")

    if not parts:
        return []

    elements_text = "\n".join(parts)
    prompt = CONSOLIDATE_PROMPT.format(elements_by_type=elements_text)
    if ORGANIZATION_NAME:
        prompt = f"The organization is {ORGANIZATION_NAME}.\n\n{prompt}"
```

(Rest of the function stays the same.)

- [ ] **Step 3: Run existing profile tests**

Run: `cd jobs && python -m pytest tests/test_profile.py -v --tb=short`
Expected: PASS (existing tests still work — ORGANIZATION_NAME defaults to empty string)

- [ ] **Step 4: Commit**

```bash
git add jobs/ingestion/profile.py
git commit -m "feat: inject ORGANIZATION_NAME into profile extraction and consolidation prompts"
```

---

## Task 3: Wire Profile Consolidation into CLI

**Files:**
- Modify: `jobs/ingestion/ingest.py`
- Modify: `jobs/tests/test_profile.py`

- [ ] **Step 1: Write failing test for consolidation CLI flow**

In `jobs/tests/test_profile.py`, add:

```python
class TestConsolidateCLIFlow:
    """Test that the consolidate command runs profile consolidation after foundation."""

    @patch("ingestion.profile.extract_structured")
    @patch("mothertree.graphql_client.graphql")
    def test_consolidate_profile_called_with_org_elements(self, mock_gql, mock_extract):
        """get_organization_profile → consolidate_profile → merge_elements."""
        # Mock: get_organization_profile returns raw elements
        mock_gql.return_value = {"allOrganizationsList": [
            {"id": "1", "element_type": "identity", "content": "We build IDPs", "confidence": 0.8, "source_count": 1},
            {"id": "2", "element_type": "identity", "content": "We build and operate IDPs", "confidence": 0.7, "source_count": 1},
        ]}
        # Mock: LLM consolidation returns merged result
        mock_extract.return_value = [
            {"type": "identity", "content": "We build and operate IDPs on open source", "confidence": 0.9},
        ]
        from ingestion.ingest import consolidate_organization_profile
        result = consolidate_organization_profile()
        assert result["consolidated"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_profile.py::TestConsolidateCLIFlow -v`
Expected: FAIL — `ImportError: cannot import name 'consolidate_organization_profile'`

- [ ] **Step 3: Add consolidate_organization_profile function to ingest.py**

In `jobs/ingestion/ingest.py`, after `consolidate_foundation()` (around line 380), add:

```python
def consolidate_organization_profile() -> dict:
    """Consolidate organization profile elements after foundation consolidation.

    Fetches all raw profile elements, runs Seth's consolidation,
    replaces stale entries with consolidated ones.
    """
    from mothertree.graphql_client import delete_all_organization, get_organization_profile
    from ingestion.profile import consolidate_profile, merge_elements

    stats = {"consolidated": 0, "skipped": False}
    elements = get_organization_profile()
    if not elements:
        print("  No profile elements to consolidate")
        stats["skipped"] = True
        return stats

    # Convert from GraphQL camelCase to consolidate_profile's expected format
    normalized = [{"type": e.get("element_type", ""), "content": e.get("content", "")} for e in elements]
    consolidated = consolidate_profile(normalized)
    if consolidated:
        delete_all_organization()
        merge_stats = merge_elements(consolidated)
        stats["consolidated"] = merge_stats.get("inserted", 0)
        print(f"  Profile: {stats['consolidated']} consolidated elements")
    return stats
```

- [ ] **Step 4: Wire into consolidate CLI command**

In the `consolidate` CLI command handler (line 645), after `consolidate_foundation()`:

```python
    if cmd == "consolidate":
        print("Seth consolidation pass...", flush=True)
        cons = consolidate_foundation()
        print(f"Consolidation: {cons}", flush=True)
        print("Organization profile consolidation...", flush=True)
        from ingestion.ingest import consolidate_organization_profile
        profile_stats = consolidate_organization_profile()
        print(f"Profile: {profile_stats}", flush=True)
        return
```

- [ ] **Step 5: Run tests**

Run: `cd jobs && python -m pytest tests/test_profile.py -v --tb=short`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add jobs/ingestion/ingest.py jobs/tests/test_profile.py
git commit -m "feat: wire organization profile consolidation into consolidate CLI command"
```

---

## Task 4: Weaver Persona Recognition

**Files:**
- Modify: `jobs/bot/characters/weaver.py`
- Create: `jobs/tests/test_weaver.py`

- [ ] **Step 1: Write failing tests**

Create `jobs/tests/test_weaver.py`:

```python
"""Tests for Weaver entity resolution — persona recognition."""
from unittest.mock import patch


class TestGetExistingGraph:
    @patch("bot.characters.weaver.graphql")
    def test_includes_personas(self, mock_gql):
        mock_gql.return_value = {
            "allContactsList": [],
            "allCompaniesList": [],
            "allSignalsList": [],
            "allPersonasList": [
                {"id": "p1", "name": "Maria Santos", "role": "Enterprise Platform Director", "profile": "Runs platform across multi-country orgs."}
            ],
        }
        from bot.characters.weaver import get_existing_graph
        graph = get_existing_graph()
        assert "personas" in graph
        assert len(graph["personas"]) == 1
        assert graph["personas"][0]["name"] == "Maria Santos"

    @patch("bot.characters.weaver.graphql")
    def test_error_fallback_includes_personas_key(self, mock_gql):
        mock_gql.side_effect = Exception("GraphQL down")
        from bot.characters.weaver import get_existing_graph
        graph = get_existing_graph()
        assert "personas" in graph
        assert graph["personas"] == []


class TestFormatGraphSummary:
    def test_personas_section_in_output(self):
        from bot.characters.weaver import _format_graph_summary
        graph = {
            "contacts": [],
            "companies": [],
            "signals": [],
            "personas": [
                {"name": "Maria Santos", "role": "Enterprise Platform Director", "profile": "Runs platform across multi-country orgs."},
                {"name": "Joost van der Berg", "role": "Technical Evaluator", "profile": "Founding Engineer/Tech Lead."},
            ],
        }
        result = _format_graph_summary(graph)
        assert "Known personas" in result
        assert "fictional" in result.lower() or "NOT real contacts" in result
        assert "Maria Santos" in result
        assert "Joost van der Berg" in result

    def test_no_personas_section_when_empty(self):
        from bot.characters.weaver import _format_graph_summary
        graph = {"contacts": [], "companies": [], "signals": [], "personas": []}
        result = _format_graph_summary(graph)
        assert "personas" not in result.lower()


class TestTeamContext:
    @patch("bot.characters.weaver.graphql")
    def test_uses_organization_name_config(self, mock_gql):
        mock_gql.side_effect = [
            {"allUsersList": []},
            {"allOrganizationsList": []},
        ]
        with patch("bot.characters.weaver.ORGANIZATION_NAME", "Aknostic"):
            from bot.characters.weaver import _get_team_context
            result = _get_team_context()
            assert "Aknostic" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_weaver.py -v`
Expected: FAIL — `personas` key not in graph, no `ORGANIZATION_NAME` import

- [ ] **Step 3: Update get_existing_graph()**

In `jobs/bot/characters/weaver.py`, update `get_existing_graph()` (line 78):

Add `allPersonasList` to the GraphQL query:

```python
  allPersonasList(first: 50) {
    id name role profile
  }
```

Add to the return dict:

```python
    "personas": result.get("allPersonasList", []),
```

Update the error fallback (line 98) to include `"personas": []`:

```python
    return {"contacts": [], "companies": [], "signals": [], "personas": []}
```

- [ ] **Step 4: Update _format_graph_summary()**

In `_format_graph_summary()` (line 181), after the companies section, add:

```python
    personas = graph.get("personas", [])
    if personas:
        lines.append("Known personas (fictional — NOT real contacts, do NOT create contacts for these):")
        for p in personas:
            profile_snippet = (p.get("profile") or "")[:80]
            desc = f"  {p.get('name', '?')} — {p.get('role', '?')}"
            if profile_snippet:
                desc += f" ({profile_snippet})"
            lines.append(desc)
```

- [ ] **Step 5: Update _get_team_context()**

In `_get_team_context()` (line 153), replace the hardcoded company name:

```python
def _get_team_context() -> str:
    """Build team context for the Weaver — who we are, so it never flags us as unknown."""
    from mothertree.config import ORGANIZATION_NAME
    org_name = ORGANIZATION_NAME or "our organization"
    parts = [f"Our company: {org_name}"]
```

- [ ] **Step 6: Run tests**

Run: `cd jobs && python -m pytest tests/test_weaver.py -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `cd jobs && python -m pytest --tb=short -q`
Expected: ALL PASS (510+ tests)

- [ ] **Step 8: Run ruff**

Run: `cd jobs && ruff check .`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add jobs/bot/characters/weaver.py jobs/tests/test_weaver.py
git commit -m "feat: Weaver persona recognition — add personas to graph context, use ORGANIZATION_NAME"
```
