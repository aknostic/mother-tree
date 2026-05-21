# Organization Profile Synthesis + Weaver Persona Recognition

## Problem

Two gaps found during email-identity deployment:

1. **Organization profile is empty.** The `organization` table has 0 records. The bot can't ground responses in who Aknostic is. The foundation data (135 changes, 156 worldviews, 32 personas, 108 competitors) already contains everything needed — Seth just hasn't been asked to synthesize it. `consolidate_profile()` exists in `ingestion/profile.py` but is only callable from the CLI (`mothertree ingest consolidate`), never as part of the foundation ingest flow.

2. **Weaver creates contacts for fictional personas.** The Spotter extracts persona names (Maria Santos, Joost van der Berg) from channel conversations and the Weaver creates contact records for them. These are personas from the CI extraction, not real people. The Weaver's `get_existing_graph()` query does not include the `personas` table, so it has no way to distinguish personas from real contacts.

## Decision

### Organization profile: synthesize during foundation ingest

`ORGANIZATION_NAME` env var hints to Seth who "we" are. Profile consolidation runs only in the `consolidate` CLI command — after `consolidate_foundation()` completes. Per-document `extract_profile()` calls during ingest accumulate raw elements; the consolidation pass synthesizes them into 3–5 elements per type (identity, change, audience, competitor_category).

This matches the existing pattern: per-document extraction during ingest, Seth consolidation as a separate pass afterward. No auto-consolidation after each file — that would be wasteful and noisy before the full corpus is ingested.

### Weaver: add personas to graph context

Add a `allPersonasList` query to `get_existing_graph()`. Include persona names, roles, and short profiles in `_format_graph_summary()` under a "Known personas (fictional — do not create contacts)" section. The Weaver LLM already decides NEW/MATCHED/UNCERTAIN — with personas in context, it will match "Maria Santos" to the persona instead of creating a contact.

## Changes

### 1. Config

In `jobs/mothertree/config.py`, add:

```python
ORGANIZATION_NAME = os.environ.get("ORGANIZATION_NAME", "")
```

Not sensitive — use a plain env var in deployment manifests, not a secret.

### 2. Foundation ingest: wire profile consolidation

In `jobs/ingestion/ingest.py`, the `consolidate` CLI command (line 645) currently calls only `consolidate_foundation()`. After that call, add profile consolidation:

```python
# Consolidate organization profile
from mothertree.graphql_client import delete_all_organization, get_organization_profile
from ingestion.profile import consolidate_profile, merge_elements
elements = get_organization_profile()  # returns list[dict] from GraphQL
if elements:
    consolidated = consolidate_profile(elements)
    if consolidated:
        delete_all_organization()
        merge_elements(consolidated)
        print(f"Profile: {len(consolidated)} consolidated elements")
```

**Important:** Use `get_organization_profile()` from `mothertree/graphql_client.py` (returns `list[dict]`), NOT `fetch_organization_profile()` from `ingestion/profile.py` (returns formatted `str` for prompt injection). `consolidate_profile()` expects `list[dict]`.

Profile consolidation runs only via the `consolidate` CLI command, not after each individual file ingest. Per-document `extract_profile()` calls accumulate raw elements during ingest; the consolidation pass runs afterward as a separate step (same pattern as `consolidate_foundation()`).

### 3. Inject ORGANIZATION_NAME into profile prompts

In `jobs/ingestion/profile.py`:

**`extract_profile()` (line 102):** The extraction prompt doesn't mention who the organization is. Add `ORGANIZATION_NAME` as context:

```python
from mothertree.config import ORGANIZATION_NAME

org_hint = f"The organization is {ORGANIZATION_NAME}. " if ORGANIZATION_NAME else ""
# Inject into the system prompt, e.g.:
# f"{org_hint}Extract organization profile elements from this document..."
```

**`consolidate_profile()` (line 267):** Same treatment — inject `ORGANIZATION_NAME` into `CONSOLIDATE_PROMPT` so Seth knows whose profile he's synthesizing:

```python
org_hint = f"for {ORGANIZATION_NAME} " if ORGANIZATION_NAME else ""
# e.g.: f"You are Seth Godin consolidating the organization profile {org_hint}..."
```

### 4. Weaver: add personas to graph context

In `jobs/bot/characters/weaver.py`:

**`get_existing_graph()` (line 78):** Add personas query and include in return dict:

```python
result = graphql("""
query {
  allContactsList(first: 100, orderBy: CREATED_AT_DESC) {
    id fullName role companyId
  }
  allCompaniesList(first: 100, orderBy: CREATED_AT_DESC) {
    id name industry
  }
  allSignalsList(first: 50, orderBy: CREATED_AT_DESC) {
    id source content type status
  }
  allPersonasList(first: 50) {
    id name role profile
  }
}
""")
return {
    "contacts": result.get("allContactsList", []),
    "companies": result.get("allCompaniesList", []),
    "signals": result.get("allSignalsList", []),
    "personas": result.get("allPersonasList", []),
}
```

**Error fallback (line 98):** Update to include `"personas": []` for consistency:

```python
return {"contacts": [], "companies": [], "signals": [], "personas": []}
```

**`_format_graph_summary()` (line 181):** Add personas section. Include `profile` field (truncated) to help the LLM disambiguate name collisions:

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

**`_get_team_context()` (line 155):** Replace the hardcoded "Our company: Aknostic" with the config var:

```python
from mothertree.config import ORGANIZATION_NAME
org_name = ORGANIZATION_NAME or "our organization"
parts = [f"Our company: {org_name}"]
```

No changes to the `resolve()` function or `IDENTITY` system prompt. The LLM already has instructions to match against existing data — adding personas to the graph context is sufficient.

### 5. Deployment manifests

Add `ORGANIZATION_NAME` env var to:
- `deploy/slack-bot/deployment.yaml`
- `deploy/cronjobs/foundation-ingest-marketing.yaml`
- `deploy/cronjobs/foundation-ingest-site.yaml`

As a plain value (not secretKeyRef):

```yaml
- name: ORGANIZATION_NAME
  value: "Aknostic"
```

## Testing

- Profile consolidation: existing tests in `test_profile.py` cover `consolidate_profile()`. Add a test that verifies the CLI `consolidate` path calls `get_organization_profile()` → `consolidate_profile()` → `merge_elements()` in sequence.
- Weaver persona recognition: add tests in a new `tests/test_weaver.py`:
  - `get_existing_graph()` returns `personas` key
  - `_format_graph_summary()` includes personas section with "fictional" label
  - Error fallback includes `"personas": []`
- Integration: verify the Weaver resolves a persona name (e.g., "Maria Santos") as not-NEW when personas are in graph context.

## File Inventory

| File | Change |
|------|--------|
| `jobs/mothertree/config.py` | Add `ORGANIZATION_NAME` |
| `jobs/ingestion/ingest.py` | Wire `consolidate_profile` after `consolidate_foundation` in consolidate CLI command |
| `jobs/ingestion/profile.py` | Inject `ORGANIZATION_NAME` into extraction and consolidation prompts |
| `jobs/bot/characters/weaver.py` | Add personas to `get_existing_graph()`, `_format_graph_summary()`, `_get_team_context()`; fix error fallback |
| `deploy/slack-bot/deployment.yaml` | Add `ORGANIZATION_NAME` env var |
| `deploy/cronjobs/foundation-ingest-marketing.yaml` | Add `ORGANIZATION_NAME` env var |
| `deploy/cronjobs/foundation-ingest-site.yaml` | Add `ORGANIZATION_NAME` env var |
| `jobs/tests/test_profile.py` | Add consolidate CLI flow test |
| `jobs/tests/test_weaver.py` | New: persona recognition tests |
