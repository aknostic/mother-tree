# Small Wins Plan A: Infrastructure + Pulse Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up infrastructure and fix Pulse scanner gaps — CI context in nudges, stage-aware thresholds, interaction ownership, contact dedup, verbosity, and Hasura cleanup.

**Architecture:** Six independent changes touching the Pulse scanner, extraction pipeline, character base, and deploy manifests. Each task commits independently. No new user-facing flows.

**Tech Stack:** Python, PostGraphile GraphQL, pgvector semantic search, Kubernetes manifests.

**Spec:** `docs/superpowers/specs/2026-04-11-small-wins-batch.md` (sections 2-6, 9)

---

## File Structure

### Modified Files

| File | Responsibility |
|------|---------------|
| `jobs/pulse/scanner.py` | CI context fetching, stage-aware thresholds |
| `jobs/bot/extraction.py:231-266` | interactions.slack_user_id passthrough, contact fuzzy matching |
| `jobs/bot/pipeline.py:567+` | Pass slack_user_id to _background_extract |
| `jobs/mothertree/graphql_client.py` | Interaction mutation update, fuzzy contact search |
| `jobs/bot/characters/base.py:42-55` | Verbosity rule replacement |

### Removed Files

| File | Reason |
|------|--------|
| `deploy/hasura/deployment.yaml` | Old Hasura deployment, replaced by PostGraphile |
| `deploy/hasura/service.yaml` | Old Hasura service |

---

## Task 1: PostGraphile Cleanup

**Files:**
- Remove: `deploy/hasura/deployment.yaml`
- Remove: `deploy/hasura/service.yaml`

- [ ] **Step 1: Verify admin-secret.yaml is still referenced**

Run: `grep -r "hasura-admin-secret" deploy/ --include="*.yaml" | head -10`
Expected: Multiple references to the secret name in PostGraphile, bot, and CronJob manifests. This confirms we must keep `admin-secret.yaml`.

- [ ] **Step 2: Remove old files**

```bash
git rm deploy/hasura/deployment.yaml deploy/hasura/service.yaml
```

- [ ] **Step 3: Verify no references to removed files**

Run: `grep -r "hasura/deployment\|hasura/service" deploy/ --include="*.yaml"`
Expected: No matches (these files are standalone, not referenced by kustomization).

- [ ] **Step 4: Commit**

```bash
git commit -m "cleanup: remove old Hasura deployment and service manifests"
```

---

## Task 2: Response Verbosity Reduction

**Files:**
- Modify: `jobs/bot/characters/base.py:42-55`
- Test: `jobs/tests/test_characters.py`

- [ ] **Step 1: Read current SLACK_FORMATTING_RULES**

Read `jobs/bot/characters/base.py` lines 42-55 to find the exact 2500-character rule text.

- [ ] **Step 2: Write failing test**

Add to `jobs/tests/test_characters.py`:

```python
class TestVerbosityRules:
    def test_verbosity_rule_present(self):
        from bot.characters.base import SLACK_FORMATTING_RULES
        assert "150 words" in SLACK_FORMATTING_RULES
        assert "2500 characters" not in SLACK_FORMATTING_RULES

    def test_training_exempt(self):
        from bot.characters.base import SLACK_FORMATTING_RULES
        assert "training" in SLACK_FORMATTING_RULES.lower()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_characters.py::TestVerbosityRules -v`
Expected: FAIL

- [ ] **Step 4: Replace the character limit rule**

In `base.py`, find the line containing "2500 characters" (around line 51) and replace with:

```python
"Keep responses under 150 words unless the user asks for detail or you "
"are delivering training or factual content (status, stats, progress). "
"Prefer one clear paragraph over multiple sections. No bullet lists "
"unless comparing options."
```

Remove the old "under 2500 characters" rule entirely.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd jobs && python -m pytest tests/test_characters.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add jobs/bot/characters/base.py jobs/tests/test_characters.py
git commit -m "feat: replace 2500-char limit with 150-word verbosity rule"
```

---

## Task 3: Pulse — CI Context in Nudges

**Files:**
- Modify: `jobs/pulse/scanner.py:124-240`
- Test: `jobs/tests/test_pulse_scanner.py`

- [ ] **Step 1: Write failing test**

Add to `jobs/tests/test_pulse_scanner.py`:

```python
class TestCIContextFetching:
    @patch("pulse.scanner.search_similar")
    def test_fetch_ci_context_returns_formatted_results(self, mock_search):
        mock_search.return_value = [
            {"reframe": "Cloud sovereignty is about freedom to operate, not isolation."},
            {"belief": "CTOs fear vendor lock-in more than migration cost."},
        ]
        from pulse.scanner import _fetch_ci_context
        result = _fetch_ci_context("STACKIT sovereignty")
        assert "sovereignty" in result.lower() or "freedom" in result.lower()
        mock_search.assert_called()

    @patch("pulse.scanner.search_similar")
    def test_fetch_ci_context_empty_when_no_results(self, mock_search):
        mock_search.return_value = []
        from pulse.scanner import _fetch_ci_context
        result = _fetch_ci_context("unknown topic")
        assert result == ""

    @patch("pulse.scanner._fetch_ci_context")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.get_stale_contacts_for_pulse")
    @patch("pulse.scanner.mark_contact_pulse_nudged")
    def test_stale_contact_nudge_includes_ci_context(self, mock_mark, mock_get, mock_nudge, mock_ci):
        from datetime import UTC, datetime, timedelta
        old_contact = (datetime.now(UTC) - timedelta(days=16)).isoformat()
        mock_get.return_value = [{
            "id": "uuid-1", "name": "Sarah", "role": "CTO",
            "temperature": "hot", "lastContact": old_contact,
            "ownerSlackId": "U_JURG", "pulseNudgedAt": None,
            "companyByCompanyId": {"name": "STACKIT"},
        }]
        mock_ci.return_value = "Sovereignty concerns align with reframe."
        mock_nudge.return_value = "Sarah at STACKIT — worth checking in."

        from unittest.mock import MagicMock
        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_contacts
        scan_stale_contacts(mock_slack)

        # Verify ci_context was passed to generate_nudge
        mock_nudge.assert_called_once()
        call_kwargs = mock_nudge.call_args
        assert "ci_context" in call_kwargs.kwargs or len(call_kwargs.args) > 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_pulse_scanner.py::TestCIContextFetching -v`
Expected: FAIL — `ImportError: cannot import name '_fetch_ci_context'`

- [ ] **Step 3: Write implementation**

Add to `jobs/pulse/scanner.py`, after the imports:

```python
from mothertree.graphql_client import search_similar
```

Add the helper function before `scan_due_reminders()`:

```python
def _fetch_ci_context(query: str) -> str:
    """Fetch relevant CI nuggets via semantic search for nudge context."""
    if not query:
        return ""
    results = []
    for table in ("insights", "worldview"):
        try:
            hits = search_similar(table, query, limit=2)
            results.extend(hits)
        except Exception:
            log.warning("CI context search failed for table %s", table)
    if not results:
        return ""
    parts = []
    for r in results[:3]:
        text = r.get("reframe") or r.get("belief") or r.get("statement") or ""
        if text:
            parts.append(text)
    return " | ".join(parts)
```

- [ ] **Step 4: Wire into scan_stale_contacts**

In `scan_stale_contacts()`, before the `generate_nudge()` call, add:

```python
        ci_query = f"{contact['name']} {company_name}".strip()
        ci_context = _fetch_ci_context(ci_query)
```

Update the `generate_nudge()` call to pass `ci_context=ci_context`.

- [ ] **Step 5: Wire into scan_stale_threads**

In `scan_stale_threads()`, before the `generate_nudge()` call, add:

```python
        ci_context = _fetch_ci_context(f"thread {thread['threadTs']}")
```

Update the `generate_nudge()` call to pass `ci_context=ci_context`.

- [ ] **Step 6: Wire into scan_pipeline**

In `scan_pipeline()`, update the existing `generate_nudge()` call to enhance context:

```python
        ci_query = f"{opp.get('title', '')} {company_name}".strip()
        ci_context = _fetch_ci_context(ci_query)
        notes_context = opp.get("notes", "")
        full_context = f"{notes_context}\n{ci_context}".strip() if ci_context else notes_context
```

Pass `ci_context=full_context` to `generate_nudge()`.

- [ ] **Step 7: Run tests**

Run: `cd jobs && python -m pytest tests/test_pulse_scanner.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add jobs/pulse/scanner.py jobs/tests/test_pulse_scanner.py
git commit -m "feat: Pulse nudges include CI context via semantic search"
```

---

## Task 4: Pulse — Stage-Aware Stale Thread Thresholds

**Files:**
- Modify: `jobs/pulse/scanner.py:124-144`
- Modify: `jobs/mothertree/graphql_client.py`
- Test: `jobs/tests/test_pulse_scanner.py`

- [ ] **Step 1: Write failing test**

Add to `jobs/tests/test_pulse_scanner.py`:

```python
class TestStageAwareThresholds:
    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.mark_thread_pulse_nudged")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner._get_thread_stage")
    @patch("pulse.scanner.get_stale_threads")
    def test_skips_soil_thread_under_60_days(self, mock_get, mock_stage, mock_nudge, mock_mark, mock_ci):
        from datetime import UTC, datetime, timedelta
        mock_get.return_value = [{
            "id": 5, "threadTs": "soil.123", "channelId": "C1",
            "ownerSlackId": "U1", "updatedAt": (datetime.now(UTC) - timedelta(days=20)).isoformat(),
            "pulseNudgedAt": None,
        }]
        mock_stage.return_value = "soil"  # 60-day threshold

        from unittest.mock import MagicMock
        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)

        mock_nudge.assert_not_called()  # 20 days < 60 day soil threshold

    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.mark_thread_pulse_nudged")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner._get_thread_stage")
    @patch("pulse.scanner.get_stale_threads")
    def test_nudges_diagnosis_thread_over_14_days(self, mock_get, mock_stage, mock_nudge, mock_mark, mock_ci):
        from datetime import UTC, datetime, timedelta
        mock_get.return_value = [{
            "id": 6, "threadTs": "diag.456", "channelId": "C1",
            "ownerSlackId": "U1", "updatedAt": (datetime.now(UTC) - timedelta(days=16)).isoformat(),
            "pulseNudgedAt": None,
        }]
        mock_stage.return_value = "diagnosis"  # 14-day threshold
        mock_nudge.return_value = "Check in on diagnosis."

        from unittest.mock import MagicMock
        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)

        mock_nudge.assert_called_once()

    @patch("pulse.scanner._fetch_ci_context", return_value="")
    @patch("pulse.scanner.mark_thread_pulse_nudged")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner._get_thread_stage")
    @patch("pulse.scanner.get_stale_threads")
    def test_default_14_days_when_no_opportunity(self, mock_get, mock_stage, mock_nudge, mock_mark, mock_ci):
        from datetime import UTC, datetime, timedelta
        mock_get.return_value = [{
            "id": 7, "threadTs": "no_opp.789", "channelId": "C1",
            "ownerSlackId": "U1", "updatedAt": (datetime.now(UTC) - timedelta(days=16)).isoformat(),
            "pulseNudgedAt": None,
        }]
        mock_stage.return_value = None  # No opportunity linked
        mock_nudge.return_value = "Thread went quiet."

        from unittest.mock import MagicMock
        mock_slack = MagicMock()
        from pulse.scanner import scan_stale_threads
        scan_stale_threads(mock_slack)

        mock_nudge.assert_called_once()  # 16 days > 14 day default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_pulse_scanner.py::TestStageAwareThresholds -v`
Expected: FAIL — `cannot import name '_get_thread_stage'`

- [ ] **Step 3: Add stage lookup helper**

Add to `jobs/pulse/scanner.py`:

```python
def _get_thread_stage(thread: dict) -> str | None:
    """Look up the pipeline stage for a thread via its owner's opportunities."""
    owner = thread.get("ownerSlackId")
    if not owner:
        return None
    try:
        result = graphql("""
        query($owner: String!) {
            allOpportunitiesList(
                filter: {ownerSlackId: {equalTo: $owner}},
                orderBy: UPDATED_AT_DESC,
                first: 1
            ) { stage }
        }
        """, {"owner": owner})
        opps = result.get("allOpportunitiesList", [])
        return opps[0]["stage"] if opps else None
    except Exception:
        log.warning("Stage lookup failed for thread %s", thread.get("threadTs"))
        return None
```

- [ ] **Step 4: Update scan_stale_threads to use stage thresholds**

Replace the body of `scan_stale_threads()` to use `_get_thread_stage()`:

After `_recently_nudged` check and owner check, add:

```python
        stage = _get_thread_stage(thread)
        threshold = STAGE_THRESHOLDS.get(stage, 14) if stage else 14
        updated_dt = datetime.fromisoformat(thread["updatedAt"])
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=UTC)
        days_idle = (datetime.now(UTC) - updated_dt).days
        if days_idle < threshold:
            continue
```

- [ ] **Step 5: Run tests**

Run: `cd jobs && python -m pytest tests/test_pulse_scanner.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add jobs/pulse/scanner.py jobs/tests/test_pulse_scanner.py
git commit -m "feat: Pulse stale threads use stage-aware thresholds"
```

---

## Task 5: Pulse — interactions.slack_user_id Passthrough

**Files:**
- Modify: `jobs/bot/extraction.py:231-266`
- Modify: `jobs/bot/pipeline.py:567+`
- Test: `jobs/tests/test_signal_pipeline.py`

- [ ] **Step 1: Read current _process_actions and _background_extract**

Read `jobs/bot/extraction.py` lines 231-270 and `jobs/bot/pipeline.py` lines 567-600 to understand the current signatures and call chain.

- [ ] **Step 2: Write failing test**

Add to `jobs/tests/test_signal_pipeline.py`:

```python
class TestInteractionOwnership:
    @patch("bot.extraction.graphql")
    def test_process_actions_passes_slack_user_id(self, mock_gql):
        mock_gql.return_value = {"createInteraction": {"interaction": {"id": "test-id"}}}
        from bot.extraction import _process_actions
        actions = [{"type": "meeting", "contact": "Sarah", "summary": "Discussed project", "contact_id": "c1"}]
        _process_actions(actions, slack_user_id="U_JURG")
        # Verify the mutation included slackUserId
        call_args = mock_gql.call_args
        assert "slackUserId" in str(call_args) or "U_JURG" in str(call_args)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_signal_pipeline.py::TestInteractionOwnership -v`
Expected: FAIL — `_process_actions() got an unexpected keyword argument 'slack_user_id'`

- [ ] **Step 4: Add slack_user_id to _process_actions**

In `extraction.py`, modify `_process_actions()` to accept `slack_user_id=None` parameter. In the GraphQL mutation that creates interactions, add `slackUserId: $slackUserId` to the input.

- [ ] **Step 5: Thread slack_user_id through _background_extract**

In `pipeline.py`, `_background_extract()` already receives context. Add `slack_user_id` parameter and pass it to `_process_actions()`.

In `_process_message()` where `_background_extract` is called, pass `user_slack_id`.

- [ ] **Step 6: Run tests**

Run: `cd jobs && python -m pytest tests/test_signal_pipeline.py tests/test_pipeline_ux.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/extraction.py jobs/bot/pipeline.py
git commit -m "feat: pass slack_user_id through to interaction records"
```

---

## Task 6: Contact Deduplication

**Files:**
- Modify: `jobs/bot/extraction.py:105+` (in `_apply_resolution`)
- Modify: `jobs/mothertree/graphql_client.py`
- Test: `jobs/tests/test_weaver.py`

- [ ] **Step 1: Write failing test**

Add to `jobs/tests/test_weaver.py`:

```python
class TestContactDedup:
    @patch("mothertree.graphql_client.graphql")
    def test_fuzzy_match_substring_same_company(self, mock_gql):
        mock_gql.return_value = {
            "allContactsList": [
                {"id": "existing-1", "name": "Jurg van Vliet", "companyByCompanyId": {"id": "company-1"}},
            ]
        }
        from mothertree.graphql_client import search_contacts_fuzzy
        result = search_contacts_fuzzy("Jurg", company_id="company-1")
        assert result is not None
        assert result["id"] == "existing-1"

    @patch("mothertree.graphql_client.graphql")
    def test_no_match_short_name_different_company(self, mock_gql):
        mock_gql.return_value = {
            "allContactsList": [
                {"id": "existing-1", "name": "Jan de Vries", "companyByCompanyId": {"id": "company-1"}},
            ]
        }
        from mothertree.graphql_client import search_contacts_fuzzy
        result = search_contacts_fuzzy("Jan", company_id="company-2")
        assert result is None

    @patch("mothertree.graphql_client.graphql")
    def test_no_match_short_name_without_company(self, mock_gql):
        """Short names (< 4 chars) require exact match."""
        mock_gql.return_value = {
            "allContactsList": [
                {"id": "existing-1", "name": "Janet Smith", "companyByCompanyId": {"id": "company-1"}},
            ]
        }
        from mothertree.graphql_client import search_contacts_fuzzy
        result = search_contacts_fuzzy("Jan", company_id="company-1")
        assert result is None  # "Jan" is < 4 chars, not substring match

    @patch("mothertree.graphql_client.graphql")
    def test_exact_match_always_works(self, mock_gql):
        mock_gql.return_value = {
            "allContactsList": [
                {"id": "existing-1", "name": "Jurg van Vliet", "companyByCompanyId": {"id": "company-1"}},
            ]
        }
        from mothertree.graphql_client import search_contacts_fuzzy
        result = search_contacts_fuzzy("Jurg van Vliet", company_id="company-1")
        assert result is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_weaver.py::TestContactDedup -v`
Expected: FAIL — `ImportError: cannot import name 'search_contacts_fuzzy'`

- [ ] **Step 3: Implement search_contacts_fuzzy**

Add to `jobs/mothertree/graphql_client.py`:

```python
import unicodedata

def _normalize_name(name: str) -> str:
    """Normalize name for fuzzy matching: lowercase, strip diacritics."""
    normalized = unicodedata.normalize("NFD", name.lower())
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def search_contacts_fuzzy(name: str, company_id: str = None) -> dict | None:
    """Find an existing contact by fuzzy name match.

    Rules:
    - Exact match (normalized) always matches
    - Substring match requires name >= 4 chars AND same company
    - Returns the best match or None
    """
    normalized = _normalize_name(name)
    # Fetch contacts, optionally filtered by company
    if company_id:
        result = graphql("""
        query($companyId: UUID!) {
            allContactsList(filter: {companyId: {equalTo: $companyId}}) {
                id name companyByCompanyId { id }
            }
        }
        """, {"companyId": company_id})
    else:
        result = graphql("""
        query { allContactsList { id name companyByCompanyId { id } } }
        """)

    contacts = result.get("allContactsList", [])
    for contact in contacts:
        existing_normalized = _normalize_name(contact["name"])
        # Exact match
        if normalized == existing_normalized:
            return contact
        # Substring match: name must be 4+ chars and same company
        if len(normalized) >= 4 and company_id:
            if normalized in existing_normalized or existing_normalized in normalized:
                return contact
    return None
```

- [ ] **Step 4: Wire into _apply_resolution**

In `jobs/bot/extraction.py`, in `_apply_resolution()`, before the call to `find_or_create_contact()` for NEW entities, add a fuzzy check:

```python
from mothertree.graphql_client import search_contacts_fuzzy

# Before creating new contact, check for fuzzy match
fuzzy_match = search_contacts_fuzzy(entity["name"], company_id=entity.get("company_id"))
if fuzzy_match:
    # Use existing contact instead of creating new
    entity["id"] = fuzzy_match["id"]
    entity["resolution"] = "MATCHED"
    continue
```

- [ ] **Step 5: Run tests**

Run: `cd jobs && python -m pytest tests/test_weaver.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `cd jobs && python -m pytest tests/ -q --no-header`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add jobs/mothertree/graphql_client.py jobs/bot/extraction.py jobs/tests/test_weaver.py
git commit -m "feat: fuzzy contact dedup prevents duplicate contacts on name variations"
```
