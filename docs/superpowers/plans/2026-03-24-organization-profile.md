# Organization Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic organization profile extraction that bootstraps from content and refines over time, then use it as a lens for four-pass foundation + narrative ingestion.

**Architecture:** New `organization` table stores profile elements (identity, change, audience, competitor_category). Ingestion becomes four passes: profile scan → foundation extraction → profile rescan → qualified re-extraction. The profile is injected into extraction prompts as context.

**Tech Stack:** Python 3.11, PostgreSQL 17 + pgvector (via Hasura), Scaleway AI (Mistral Small 3.2 for extraction, bge-multilingual-gemma2 for embeddings)

**Spec:** `docs/superpowers/specs/2026-03-24-organization-profile-design.md`

---

## File Structure

```
deploy/database/schema.sql              — add organization table + embedding + trigger
jobs/mothertree/hasura.py               — add organization CRUD operations
jobs/mothertree/llm.py                  — add embed() function
jobs/ingestion/extract.py               — add profile prompts, profile-aware extraction
jobs/ingestion/profile.py               — NEW: profile scan, merge, fetch logic
jobs/ingestion/ingest.py                — four-pass orchestration
jobs/tests/test_profile.py              — NEW: tests for profile scan, merge, orchestration
```

---

### Task 1: Create the organization table

**Files:**
- Modify: `deploy/database/schema.sql`
- Modify: `jobs/mothertree/hasura.py`

- [ ] **Step 1: Add the organization table to schema.sql**

Add after the `-- === FOUNDATION LAYER ===` section header (before the `change` table):

```sql
-- === ORGANIZATION PROFILE ===
-- Automatically extracted identity of the organization using Mother Tree.
-- Acts as a lens for foundation and narrative extraction.

CREATE TABLE organization (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    element_type TEXT NOT NULL CHECK (element_type IN ('identity', 'change', 'audience', 'competitor_category')),
    content TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    source_count INTEGER DEFAULT 1,
    embedding vector(3584),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_organization_type ON organization(element_type);
CREATE TRIGGER organization_updated_at BEFORE UPDATE ON organization FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

- [ ] **Step 2: Apply the migration to the live database via Hasura**

```bash
export HASURA_URL="https://mothertree.aknostic.com/v1/graphql"
export HASURA_ADMIN_SECRET="<from kubectl>"

# Run SQL via Hasura admin API
curl -X POST "https://mothertree.aknostic.com/v2/query" \
  -H "Content-Type: application/json" \
  -H "x-hasura-admin-secret: $HASURA_ADMIN_SECRET" \
  -d '{
    "type": "run_sql",
    "args": {
      "sql": "CREATE TABLE IF NOT EXISTS organization (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), element_type TEXT NOT NULL CHECK (element_type IN ('"'"'identity'"'"', '"'"'change'"'"', '"'"'audience'"'"', '"'"'competitor_category'"'"')), content TEXT NOT NULL, confidence REAL DEFAULT 0.5, source_count INTEGER DEFAULT 1, embedding vector(3584), created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now()); CREATE INDEX IF NOT EXISTS idx_organization_type ON organization(element_type); CREATE TRIGGER organization_updated_at BEFORE UPDATE ON organization FOR EACH ROW EXECUTE FUNCTION update_updated_at();"
    }
  }'
```

Then track the table in Hasura:

```bash
curl -X POST "https://mothertree.aknostic.com/v1/metadata" \
  -H "Content-Type: application/json" \
  -H "x-hasura-admin-secret: $HASURA_ADMIN_SECRET" \
  -d '{
    "type": "pg_track_table",
    "args": {
      "source": "default",
      "table": "organization"
    }
  }'
```

- [ ] **Step 3: Add Hasura CRUD operations for organization**

Add to `jobs/mothertree/hasura.py`:

```python
# --- Organization profile ---

def get_organization_profile() -> list[dict]:
    """Fetch all organization profile elements, ordered by type and confidence."""
    result = graphql("""
    query {
        organization(order_by: [{element_type: asc}, {confidence: desc}]) {
            id element_type content confidence source_count
        }
    }
    """)
    return result["organization"]


def upsert_organization_element(element: dict) -> str:
    """Insert or update an organization profile element."""
    result = graphql("""
    mutation($object: organization_insert_input!) {
        insert_organization_one(
            object: $object,
            on_conflict: {
                constraint: organization_pkey,
                update_columns: [content, confidence, source_count, embedding, updated_at]
            }
        ) { id }
    }
    """, {"object": {k: v for k, v in element.items() if v is not None}})
    return result["insert_organization_one"]["id"]


def insert_organization_element(element: dict) -> str:
    """Insert a new organization profile element."""
    result = graphql("""
    mutation($object: organization_insert_input!) {
        insert_organization_one(object: $object) { id }
    }
    """, {"object": {k: v for k, v in element.items() if v is not None}})
    return result["insert_organization_one"]["id"]


def delete_all_organization() -> int:
    """Delete all organization profile elements (for --force rebuild)."""
    result = graphql("""
    mutation {
        delete_organization(where: {}) { affected_rows }
    }
    """)
    return result["delete_organization"]["affected_rows"]


def update_organization_element(element_id: str, updates: dict) -> None:
    """Update an existing organization profile element."""
    graphql("""
    mutation($id: uuid!, $updates: organization_set_input!) {
        update_organization_by_pk(pk_columns: {id: $id}, _set: $updates) { id }
    }
    """, {"id": element_id, "updates": updates})
```

- [ ] **Step 4: Commit**

```bash
git add deploy/database/schema.sql jobs/mothertree/hasura.py
git commit -m "Add organization table and Hasura CRUD operations"
```

---

### Task 2: Add embedding function to llm.py

**Files:**
- Modify: `jobs/mothertree/llm.py`
- Test: `jobs/tests/test_profile.py`

- [ ] **Step 1: Write the test**

```python
# jobs/tests/test_profile.py
"""Tests for organization profile extraction and merging."""
from unittest.mock import patch, MagicMock


class TestEmbedding:
    """Embedding function for profile similarity matching."""

    @patch("mothertree.llm.scaleway")
    def test_embed_returns_vector(self, mock_scw):
        from mothertree.llm import embed
        mock_scw.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 3584)]
        )
        result = embed("test text")
        assert len(result) == 3584
        assert result[0] == 0.1

    @patch("mothertree.llm.scaleway")
    def test_embed_uses_embedding_model(self, mock_scw):
        from mothertree.llm import embed
        from mothertree.config import EMBEDDING_MODEL
        mock_scw.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 3584)]
        )
        embed("test text")
        call_kwargs = mock_scw.embeddings.create.call_args
        assert call_kwargs[1]["model"] == EMBEDDING_MODEL or call_kwargs.kwargs["model"] == EMBEDDING_MODEL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_profile.py::TestEmbedding -v`
Expected: FAIL — `embed` not found

- [ ] **Step 3: Add embed function to llm.py**

Add to `jobs/mothertree/llm.py`:

```python
def embed(text: str) -> list[float]:
    """Generate an embedding vector for text using the embedding model."""
    from mothertree.config import EMBEDDING_MODEL
    response = scaleway.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0].embedding
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jobs && python -m pytest tests/test_profile.py::TestEmbedding -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/mothertree/llm.py jobs/tests/test_profile.py
git commit -m "Add embed() function for profile similarity matching"
```

---

### Task 3: Create profile.py — scan, merge, and fetch

**Files:**
- Create: `jobs/ingestion/profile.py`
- Modify: `jobs/tests/test_profile.py`

This is the core of the feature. Profile scan extracts organization identity from documents, merge logic combines elements using embedding similarity, and fetch formats the profile for prompt injection.

- [ ] **Step 1: Write tests for profile scan, merge, and fetch**

Add to `jobs/tests/test_profile.py`:

```python
class TestProfileScan:
    """Profile scan extracts organization identity from documents."""

    @patch("ingestion.profile.extract_structured")
    def test_scan_document_returns_elements(self, mock_extract):
        from ingestion.profile import scan_document
        mock_extract.return_value = [
            {"type": "identity", "content": "Cloud-native consultancy", "confidence": 0.9},
            {"type": "audience", "content": "CTO / VP Engineering", "confidence": 0.8},
        ]
        result = scan_document("Some document content")
        assert len(result) == 2
        assert result[0]["type"] == "identity"

    @patch("ingestion.profile.extract_structured")
    def test_scan_document_empty_for_irrelevant_content(self, mock_extract):
        from ingestion.profile import scan_document
        mock_extract.return_value = []
        result = scan_document("A random meeting agenda")
        assert result == []

    @patch("ingestion.profile.extract_structured")
    def test_scan_document_filters_invalid_types(self, mock_extract):
        from ingestion.profile import scan_document
        mock_extract.return_value = [
            {"type": "identity", "content": "Cloud consultancy", "confidence": 0.9},
            {"type": "unknown_type", "content": "Should be dropped", "confidence": 0.5},
        ]
        result = scan_document("Some content")
        assert len(result) == 1


class TestProfileRescan:
    """Profile rescan refines profile using foundation data."""

    @patch("ingestion.profile.extract_structured")
    def test_rescan_includes_foundation_context(self, mock_extract):
        from ingestion.profile import rescan_document
        mock_extract.return_value = [
            {"type": "identity", "content": "Refined identity", "confidence": 0.95},
        ]
        rescan_document(
            content="Some content",
            foundation_context="Change: We help organizations...",
            current_profile="Identity: Cloud consultancy",
        )
        call_args = mock_extract.call_args
        prompt = call_args[0][1]  # second arg is the instruction
        assert "foundation" in prompt.lower()


class TestProfileMerge:
    """Profile merge combines elements using embedding similarity."""

    @patch("ingestion.profile.embed")
    @patch("ingestion.profile.get_organization_profile")
    @patch("ingestion.profile.insert_organization_element")
    def test_merge_inserts_new_element(self, mock_insert, mock_get, mock_embed):
        from ingestion.profile import merge_element
        mock_get.return_value = []  # empty profile
        mock_embed.return_value = [0.1] * 3584
        mock_insert.return_value = "new-id"
        merge_element({"type": "identity", "content": "Cloud consultancy", "confidence": 0.9})
        mock_insert.assert_called_once()

    @patch("ingestion.profile.embed")
    @patch("ingestion.profile.get_organization_profile")
    @patch("ingestion.profile.update_organization_element")
    def test_merge_updates_matching_element(self, mock_update, mock_get, mock_embed):
        from ingestion.profile import merge_element
        mock_get.return_value = [
            {"id": "existing-id", "element_type": "identity", "content": "Cloud consultancy", "confidence": 0.7, "source_count": 2},
        ]
        # Return identical embeddings (cosine similarity = 1.0)
        mock_embed.return_value = [0.1] * 3584
        merge_element({"type": "identity", "content": "Cloud-native consultancy", "confidence": 0.9})
        mock_update.assert_called_once()
        update_args = mock_update.call_args
        assert update_args[0][0] == "existing-id"


class TestProfileFetch:
    """Fetch formats profile for prompt injection."""

    @patch("ingestion.profile.get_organization_profile")
    def test_fetch_formats_by_type(self, mock_get):
        from ingestion.profile import fetch_organization_profile
        mock_get.return_value = [
            {"id": "1", "element_type": "identity", "content": "Cloud consultancy", "confidence": 0.9, "source_count": 5},
            {"id": "2", "element_type": "change", "content": "From lock-in to freedom", "confidence": 0.85, "source_count": 3},
            {"id": "3", "element_type": "audience", "content": "CTO / VP Engineering", "confidence": 0.8, "source_count": 4},
        ]
        result = fetch_organization_profile()
        assert "Identity:" in result
        assert "Cloud consultancy" in result
        assert "Change:" in result
        assert "Audience:" in result

    @patch("ingestion.profile.get_organization_profile")
    def test_fetch_empty_profile(self, mock_get):
        from ingestion.profile import fetch_organization_profile
        mock_get.return_value = []
        result = fetch_organization_profile()
        assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_profile.py -v`
Expected: FAIL — `ingestion.profile` not found

- [ ] **Step 3: Create profile.py**

```python
# jobs/ingestion/profile.py
"""Organization profile — automatic identity extraction and merging.

Scans content to build a profile of who the organization is.
Used as a lens for foundation and narrative extraction.
"""
import logging

from mothertree.llm import extract as extract_structured, embed
from mothertree.hasura import (
    get_organization_profile,
    insert_organization_element,
    update_organization_element,
)

log = logging.getLogger(__name__)

VALID_ELEMENT_TYPES = {"identity", "change", "audience", "competitor_category"}

PROFILE_SCAN_PROMPT = """
You are building a profile of the organization that AUTHORED this document —
not the organizations described IN the document.

Many documents describe client engagements, case studies, or prospect situations.
The author is the consultancy/vendor/service provider. The subjects are their clients.

Extract what you can learn about the AUTHOR:

1. IDENTITY: What does this organization do? What is their core business?
   Only extract if the document reveals this directly or indirectly.

2. CHANGE: What transformation do they offer their clients?
   Not features — the change in the client's situation.

3. AUDIENCE: Who do they sell to? Job titles, roles, industries.
   These are the BUYERS, not the end-users of a client's product.

4. COMPETITOR_CATEGORY: What categories of alternatives do they position against?
   Categories, not company names.

Return a JSON array. Each object: {"type": "...", "content": "...", "confidence": 0.0-1.0}
Confidence reflects how directly the document states this vs. how much you inferred.
If a document reveals nothing about the author, return [].
"""

PROFILE_RESCAN_PROMPT = """
You are refining the profile of the organization that authored these documents.

Here is what foundation extraction found — the positioning data we extracted:
{foundation_context}

And here is the current profile:
{current_profile}

Rescan this document. For each profile element you extract:
- If it confirms an existing profile element, return it with higher confidence.
- If it contradicts the foundation data (e.g., a persona that doesn't match the
  buyer roles found in foundation), return it with lower confidence or omit it.
- If it reveals something new that the foundation data supports, add it.

Return a JSON array. Each object: {"type": "...", "content": "...", "confidence": 0.0-1.0}
If a document reveals nothing about the author, return [].
"""


def scan_document(content: str) -> list[dict]:
    """Extract organization profile elements from a document (pass 1)."""
    try:
        elements = extract_structured(content, PROFILE_SCAN_PROMPT)
    except Exception as e:
        log.warning(f"Profile scan failed: {e}")
        return []
    return [e for e in elements if e.get("type") in VALID_ELEMENT_TYPES]


def rescan_document(content: str, foundation_context: str, current_profile: str) -> list[dict]:
    """Rescan a document with foundation data for profile refinement (pass 3)."""
    prompt = PROFILE_RESCAN_PROMPT.format(
        foundation_context=foundation_context,
        current_profile=current_profile,
    )
    try:
        elements = extract_structured(content, prompt)
    except Exception as e:
        log.warning(f"Profile rescan failed: {e}")
        return []
    return [e for e in elements if e.get("type") in VALID_ELEMENT_TYPES]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


SIMILARITY_THRESHOLD = 0.85


def merge_element(element: dict) -> None:
    """Merge a profile element into the organization table.

    If a semantically similar element of the same type exists, update it
    (bump confidence and source_count). Otherwise, insert a new element.
    """
    element_type = element["type"]
    content = element["content"]
    confidence = element.get("confidence", 0.5)

    # Embed the new element
    new_embedding = embed(content)

    # Check existing elements of the same type
    existing = get_organization_profile()
    same_type = [e for e in existing if e["element_type"] == element_type]

    best_match = None
    best_similarity = 0.0

    for existing_elem in same_type:
        # Embed existing element for comparison
        existing_embedding = embed(existing_elem["content"])
        similarity = _cosine_similarity(new_embedding, existing_embedding)
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = existing_elem

    if best_match and best_similarity >= SIMILARITY_THRESHOLD:
        # Update existing: bump confidence and source_count
        new_confidence = min(1.0, max(best_match["confidence"], confidence))
        new_source_count = best_match["source_count"] + 1
        # Use the higher-confidence content
        new_content = content if confidence > best_match["confidence"] else best_match["content"]
        update_organization_element(best_match["id"], {
            "content": new_content,
            "confidence": new_confidence,
            "source_count": new_source_count,
            "embedding": new_embedding,
        })
    else:
        # Insert new element
        insert_organization_element({
            "element_type": element_type,
            "content": content,
            "confidence": confidence,
            "source_count": 1,
            "embedding": new_embedding,
        })


def merge_elements(elements: list[dict]) -> dict:
    """Merge a batch of profile elements. Returns stats."""
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    for element in elements:
        if not element.get("content"):
            stats["skipped"] += 1
            continue
        try:
            merge_element(element)
            stats["inserted"] += 1  # simplification — merge handles insert vs update
        except Exception as e:
            log.warning(f"Profile merge failed for {element.get('type')}: {e}")
            stats["skipped"] += 1
    return stats


def fetch_organization_profile() -> str:
    """Fetch the organization profile formatted for prompt injection.

    Returns a formatted string like:
    ORGANIZATION PROFILE:
    - Identity: Cloud-native consultancy...
    - Change: From lock-in to freedom to operate...
    - Audience: CTO / VP Engineering, Engineering Director...
    - Competes with: Managed Kubernetes Providers, Kubernetes Consultancies...
    """
    elements = get_organization_profile()
    if not elements:
        return ""

    by_type = {}
    for e in elements:
        t = e["element_type"]
        by_type.setdefault(t, []).append(e["content"])

    TYPE_LABELS = {
        "identity": "Identity",
        "change": "Change",
        "audience": "Audience",
        "competitor_category": "Competes with",
    }

    parts = []
    for element_type in ("identity", "change", "audience", "competitor_category"):
        items = by_type.get(element_type, [])
        if items:
            label = TYPE_LABELS[element_type]
            parts.append(f"- {label}: {'; '.join(items)}")

    if not parts:
        return ""

    return "ORGANIZATION PROFILE:\n" + "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jobs && python -m pytest tests/test_profile.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/ingestion/profile.py jobs/tests/test_profile.py
git commit -m "Add profile scan, merge, and fetch logic"
```

---

### Task 4: Modify extraction prompts to accept profile context

**Files:**
- Modify: `jobs/ingestion/extract.py`
- Modify: `jobs/tests/test_profile.py`

- [ ] **Step 1: Write tests for profile-aware extraction**

Add to `jobs/tests/test_profile.py`:

```python
class TestProfileAwareExtraction:
    """Extraction prompts receive the organization profile as context."""

    @patch("ingestion.extract.extract_structured")
    def test_foundation_extraction_includes_profile(self, mock_extract):
        from ingestion.extract import extract_foundation
        mock_extract.return_value = [{"type": "change", "statement": "test", "context": "test"}]
        extract_foundation("Some content", profile_context="ORGANIZATION PROFILE:\n- Identity: Cloud consultancy")
        call_args = mock_extract.call_args
        instruction = call_args[0][1]
        assert "ORGANIZATION PROFILE" in instruction
        assert "Cloud consultancy" in instruction

    @patch("ingestion.extract.extract_structured")
    def test_foundation_extraction_works_without_profile(self, mock_extract):
        from ingestion.extract import extract_foundation
        mock_extract.return_value = []
        extract_foundation("Some content")
        # Should not raise

    @patch("ingestion.extract._fetch_foundation_context")
    @patch("ingestion.extract.extract_structured")
    def test_narrative_extraction_includes_profile(self, mock_extract, mock_foundation):
        from ingestion.extract import extract_narrative
        mock_foundation.return_value = "Change: test"
        mock_extract.return_value = []
        extract_narrative("Some content", profile_context="ORGANIZATION PROFILE:\n- Identity: Cloud consultancy")
        call_args = mock_extract.call_args
        instruction = call_args[0][1]
        assert "ORGANIZATION PROFILE" in instruction
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_profile.py::TestProfileAwareExtraction -v`
Expected: FAIL — `extract_foundation` doesn't accept `profile_context`

- [ ] **Step 3: Modify extract.py**

Update `FOUNDATION_EXTRACTION` prompt to include a profile prefix placeholder:

```python
FOUNDATION_EXTRACTION = """
{profile_section}
Analyze this document for foundational commercial positioning that applies to
the organization described in the profile above. If no profile is provided,
extract positioning for the document's author.

Do NOT extract positioning that belongs to clients, case studies, or third parties
described in the document. Only extract what applies to the authoring organization.

Extract four types of content:

1. CHANGE STATEMENTS: The core transformation this organization offers. Not features or services —
   the change in the customer's situation. What does the customer become? Use the company's
   own words where possible.

   Return as: {{"type": "change", "statement": "...", "context": "why this matters"}}

2. WORLDVIEW RECORDS: The beliefs the target audience already holds — what makes them ready
   for the change. For each audience type or persona mentioned:

   Return as: {{"type": "worldview", "persona_name": "...", "belief": "what they believe",
   "pain": "what they feel", "readiness_signal": "how you'd recognize someone ready for change"}}

3. PERSONAS: Detailed buyer profiles with decision-making context.

   Return as: {{"type": "persona", "name": "...", "role": "...", "profile": "goals and challenges",
   "communication": "how they engage", "decision_criteria": [...], "objections": [{{"objection": "...", "response": "..."}}],
   "how_to_reach": "channels that work"}}

4. COMPETITORS: How to differentiate against alternatives.

   Return as: {{"type": "competitor", "competitor_type": "category not company name",
   "positioning": "how to differentiate", "when_mentioned": "context", "response": "what to say"}}

Return a JSON array mixing all types. Each object MUST have a "type" field.
If the document contains none of a type, simply don't include any objects of that type.
If a document is purely about a client engagement with no company-level positioning, return [].
"""
```

Update `NARRATIVE_EXTRACTION_TEMPLATE` to include profile:

```python
NARRATIVE_EXTRACTION_TEMPLATE = """
{profile_section}

You have access to our foundational positioning below. Use it to extract insights
that connect directly to our change statements, worldview beliefs, and personas.

OUR FOUNDATION:
{foundation_context}

---

Now analyze this content for commercial insights — perspective shifts that a consultative seller
could use in conversation with a prospect.

An insight is NOT a summary of the article. It IS a reframe: a specific statement that makes
a prospect see their own situation differently. It should be directly usable in a sales conversation.

Ground your insights in our foundation:
- Connect reframes to specific change statements or worldview beliefs where possible
- Frame stakeholder lenses using our persona roles and their known concerns
- Identify triggers that match our personas' readiness signals

For each insight, return:
- category: one of "lock-in-freedom", "regulatory-pressure", "capability-vs-dependency",
  "cost-reality", "developer-experience", "resilience-reliability"
- reframe: the one-sentence perspective shift (direct, punchy, conversational)
- evidence: the specific data or argument from the content that supports this reframe
- stakeholder_lens: array of {{{{role, framing}}}} for relevant stakeholders (use our persona roles)
- trigger: what would make this insight timely for a prospect (connect to readiness signals)
- next_step: where this naturally leads

Return a JSON array. Only extract genuine insights — not summaries, not truisms.
If the content contains no usable commercial insights, return [].
"""
```

Update the functions:

```python
def extract_foundation(content: str, profile_context: str = "") -> list[dict]:
    """Extract change, worldview, personas, and competitors from foundation content."""
    profile_section = profile_context if profile_context else "No organization profile available yet. Extract positioning for the document's author."
    prompt = FOUNDATION_EXTRACTION.format(profile_section=profile_section)
    return extract_structured(content, prompt)


def extract_narrative(content: str, profile_context: str = "") -> list[dict]:
    """Extract insights/reframes from narrative content, grounded in foundation."""
    foundation = _fetch_foundation_context()
    profile_section = profile_context if profile_context else ""
    prompt = NARRATIVE_EXTRACTION_TEMPLATE.format(
        profile_section=profile_section,
        foundation_context=foundation,
    )
    return extract_structured(content, prompt)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jobs && python -m pytest tests/test_profile.py -v`
Expected: all PASS

- [ ] **Step 5: Run existing tests to check no regressions**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: all PASS (existing tests call `extract_foundation("content")` without `profile_context` — the default `""` handles this)

- [ ] **Step 6: Commit**

```bash
git add jobs/ingestion/extract.py jobs/tests/test_profile.py
git commit -m "Add profile context to foundation and narrative extraction prompts"
```

---

### Task 5: Four-pass orchestration in ingest.py

**Files:**
- Modify: `jobs/ingestion/ingest.py`
- Modify: `jobs/tests/test_profile.py`

This is the integration task. The existing `cmd_foundation_repo` (and variants) gets replaced with a four-pass flow.

- [ ] **Step 1: Write tests for the four-pass orchestration**

Add to `jobs/tests/test_profile.py`:

```python
class TestFourPassOrchestration:
    """Four-pass pipeline: profile → foundation → rescan → re-extract."""

    @patch("ingestion.ingest.process_narrative")
    @patch("ingestion.ingest.process_foundation")
    @patch("ingestion.ingest.run_profile_rescan")
    @patch("ingestion.ingest.run_profile_scan")
    def test_four_passes_called_in_order(self, mock_p1, mock_p3, mock_p2, mock_p4):
        from ingestion.ingest import run_four_pass
        mock_p1.return_value = {"identity": 1, "change": 1, "audience": 1, "competitor_category": 0}
        mock_p2.return_value = {"change": 5, "worldview": 3, "personas": 2, "competitors": 2, "rejected": 0}
        mock_p3.return_value = {"identity": 1, "change": 1, "audience": 1, "competitor_category": 0}
        mock_p4.return_value = {"insights": 10, "rejected": 0, "flagged": 0}

        files = [{"path": "test.md", "content": "Test content", "content_hash": "abc123"}]
        run_four_pass(files, force=True)

        assert mock_p1.called
        assert mock_p2.called
        assert mock_p3.called
        assert mock_p4.called

        # Verify order: p1 before p2 before p3 before p4
        assert mock_p1.call_args_list[0] is not None  # was called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_profile.py::TestFourPassOrchestration -v`
Expected: FAIL — `run_four_pass` not found

- [ ] **Step 3: Add the four-pass orchestration function and update CLI commands**

Add to `jobs/ingestion/ingest.py`:

```python
from ingestion.profile import scan_document, rescan_document, merge_elements, fetch_organization_profile
from ingestion.extract import _fetch_foundation_context
from mothertree.hasura import delete_all_organization


def run_profile_scan(files: list[dict], force: bool = False) -> dict:
    """Pass 1: Scan all documents to build/update organization profile."""
    if force:
        deleted = delete_all_organization()
        if deleted:
            print(f"  Cleared {deleted} profile elements")

    stats = {"identity": 0, "change": 0, "audience": 0, "competitor_category": 0}
    for f in files:
        elements = scan_document(f["content"])
        if elements:
            merge_elements(elements)
            for e in elements:
                t = e.get("type", "")
                if t in stats:
                    stats[t] += 1
    return stats


def run_profile_rescan(files: list[dict]) -> dict:
    """Pass 3: Rescan all documents with foundation data to refine profile."""
    foundation_context = _fetch_foundation_context()
    profile_text = fetch_organization_profile()

    # Clear and rebuild profile with refined data
    delete_all_organization()

    stats = {"identity": 0, "change": 0, "audience": 0, "competitor_category": 0}
    for f in files:
        elements = rescan_document(
            content=f["content"],
            foundation_context=foundation_context,
            current_profile=profile_text,
        )
        if elements:
            merge_elements(elements)
            for e in elements:
                t = e.get("type", "")
                if t in stats:
                    stats[t] += 1
    return stats


def run_four_pass(files: list[dict], force: bool = False) -> dict:
    """Run the four-pass ingestion pipeline.

    Pass 1: Profile scan — build organization profile from content
    Pass 2: Foundation extraction — extract positioning with profile context
    Pass 3: Profile rescan — refine profile using foundation data
    Pass 4: Qualified re-extraction — re-extract foundation + narrative with refined profile
    """
    totals = {
        "profile": {},
        "foundation_p2": {},
        "profile_refined": {},
        "foundation_p4": {},
        "narrative": {},
    }

    # Pass 1: Profile scan
    print("\n  Pass 1/4: Building organization profile...")
    totals["profile"] = run_profile_scan(files, force=force)
    profile = fetch_organization_profile()
    print(f"    Profile: {totals['profile']}")

    # Pass 2: Foundation extraction (with profile)
    print("\n  Pass 2/4: Foundation extraction (with profile)...")
    foundation_totals = {"change": 0, "worldview": 0, "personas": 0, "competitors": 0, "rejected": 0}
    for f in files:
        source = source_key("foundation", f["path"])
        stats = process_foundation(f["content"], source, profile_context=profile)
        log_ingestion(source, f["content"], stats)
        for k in foundation_totals:
            foundation_totals[k] += stats.get(k, 0)
    totals["foundation_p2"] = foundation_totals
    print(f"    Foundation: {foundation_totals}")

    # Pass 3: Profile rescan (with foundation data)
    print("\n  Pass 3/4: Refining organization profile...")
    totals["profile_refined"] = run_profile_rescan(files)
    profile = fetch_organization_profile()
    print(f"    Profile refined: {totals['profile_refined']}")

    # Pass 4: Qualified re-extraction (foundation + narrative)
    print("\n  Pass 4/4: Qualified re-extraction...")
    foundation_totals = {"change": 0, "worldview": 0, "personas": 0, "competitors": 0, "rejected": 0}
    narrative_totals = {"insights": 0, "rejected": 0, "flagged": 0}
    for f in files:
        # Re-extract foundation
        f_source = source_key("foundation", f["path"])
        f_stats = process_foundation(f["content"], f_source, profile_context=profile)
        log_ingestion(f_source, f["content"], f_stats)
        for k in foundation_totals:
            foundation_totals[k] += f_stats.get(k, 0)

        # Extract narrative
        n_source = source_key("narrative", f["path"])
        n_stats = process_narrative(f["content"], n_source, profile_context=profile)
        log_ingestion(n_source, f["content"], n_stats)
        for k in narrative_totals:
            narrative_totals[k] += n_stats.get(k, 0)

    totals["foundation_p4"] = foundation_totals
    totals["narrative"] = narrative_totals
    print(f"    Foundation: {foundation_totals}")
    print(f"    Narrative: {narrative_totals}")

    return totals
```

Update `process_foundation` and `process_narrative` to accept `profile_context`:

```python
def process_foundation(content: str, source: str, profile_context: str = ""):
    """Extract and insert foundation records from content."""
    stats = {"change": 0, "worldview": 0, "personas": 0, "competitors": 0, "rejected": 0}

    for table in ("change", "worldview", "personas", "competitors"):
        deleted = delete_by_source(table, source)
        if deleted:
            print(f"  Replaced {deleted} {table}")

    try:
        records = extract_foundation(content, profile_context=profile_context)
    except Exception as e:
        print(f"  Extraction error: {e}")
        return stats

    # ... rest unchanged ...


def process_narrative(content: str, source: str, profile_context: str = ""):
    """Extract, score, and insert narrative insights from content."""
    stats = {"insights": 0, "rejected": 0, "flagged": 0}

    deleted = delete_by_source("insights", source)
    if deleted:
        print(f"  Replaced {deleted} insights")

    try:
        insights = extract_narrative(content, profile_context=profile_context)
    except Exception as e:
        print(f"  Extraction error: {e}")
        return stats

    # ... rest unchanged ...
```

Update `cmd_foundation_repo` to use `run_four_pass`:

```python
def cmd_foundation_repo(path: str, force: bool = False):
    """Ingest all .md files in a git repo — four-pass pipeline."""
    files = read_repo_markdown(path)
    print(f"Ingestion repo: {path} ({len(files)} files)")
    totals = run_four_pass(files, force=force)
    print(f"\nComplete: {totals}")
```

Similarly update `cmd_foundation_dir`, `cmd_foundation_file`, `cmd_foundation_url`, `cmd_foundation_sitemap` to collect their files/content into a list and call `run_four_pass`.

Update `cmd_narrative_repo` (and variants) to inject profile:

```python
def cmd_narrative_repo(path: str, force: bool = False):
    """Ingest all .md files in a git repo as narrative."""
    profile = fetch_organization_profile()
    if not profile:
        print("No organization profile found. Run 'ingest foundation' first.")
        sys.exit(1)
    files = read_repo_markdown(path)
    print(f"Narrative repo: {path} ({len(files)} files)")
    totals = {"insights": 0, "rejected": 0, "flagged": 0, "skipped": 0}
    for f in files:
        source = source_key("narrative", f["path"])
        if not force and should_skip(source, f["content"]):
            totals["skipped"] += 1
            continue
        print(f"  {f['path']}...")
        stats = process_narrative(f["content"], source, profile_context=profile)
        log_ingestion(source, f["content"], stats)
        for k in totals:
            if k != "skipped":
                totals[k] += stats.get(k, 0)
        print(f"    {stats}")
    print(f"\nTotal: {totals}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jobs && python -m pytest tests/test_profile.py -v`
Expected: all PASS

- [ ] **Step 5: Run full test suite**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add jobs/ingestion/ingest.py jobs/tests/test_profile.py
git commit -m "Add four-pass orchestration to ingestion pipeline"
```

---

### Task 6: Manual integration test

Not automated — run against real data and verify results.

- [ ] **Step 1: Truncate database**

```python
# Truncate all CI tables + organization
from mothertree.hasura import graphql
for table in ['organization', 'insights', 'change', 'worldview', 'personas', 'competitors', 'ingestion_log']:
    result = graphql(f'mutation {{ delete_{table}(where: {{}}) {{ affected_rows }} }}')
    print(f"{table}: {result}")
```

- [ ] **Step 2: Run four-pass ingestion**

```bash
export HASURA_URL="https://mothertree.aknostic.com/v1/graphql"
export HASURA_ADMIN_SECRET="<from kubectl>"
export SCALEWAY_AI_API_KEY="<from kubectl>"
cd jobs && python -m cli ingest foundation repo /path/to/marketing --force
```

- [ ] **Step 3: Verify results**

Check that:
- Organization profile contains Aknostic-level identity (not "Researchers", not "Faculty Administrators")
- Foundation tables contain company-level positioning (not case-study-specific change statements)
- Narrative insights reference the organization's actual positioning
- `mothertree stats` shows reasonable counts

- [ ] **Step 4: Smoke test in Slack**

Ask Mother Tree: "can you tell me what you know?" — verify the response describes Aknostic's positioning without Qualtrics-specific content.
