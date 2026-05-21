"""Organization profile — automatic identity extraction and merging.

Three isolated units:
1. classify_document — what kind of document is this? (foundation/narrative/mixed/irrelevant)
2. extract_profile — what can we learn about the author? (identity/change/audience/competitors)
3. merge_element — store a profile element, deduplicating against existing ones

Each unit is independently testable with its own prompt, model, and interface.
"""
import logging

from mothertree.config import EXTRACTION_MODEL
from mothertree.graphql_client import (
    get_organization_profile,
    insert_organization_element,
    update_organization_element,
)
from mothertree.llm import extract as extract_structured

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unit 1: Classify a document
# ---------------------------------------------------------------------------

VALID_DOCUMENT_TYPES = {"foundation", "narrative", "mixed", "irrelevant"}

CLASSIFY_PROMPT = """Classify this document. Is it:
- "foundation": about the organization's own positioning, strategy, offerings, audience, competitive landscape, OR audience research (buyer profiles, persona research, prospect profiles used to understand the target market)
- "narrative": a case study, client engagement story, or article with real-world examples and evidence that a seller could use in conversation
- "mixed": contains both positioning and case study material
- "irrelevant": templates, internal plans, meeting notes, or other non-content documents

Return ONLY a JSON object: {"document_type": "foundation|narrative|mixed|irrelevant"}"""


def classify_document(content: str) -> str:
    """Classify a document as foundation, narrative, mixed, or irrelevant.

    Returns one of: "foundation", "narrative", "mixed", "irrelevant".
    Returns "unknown" only if the LLM call fails.
    """
    try:
        result = extract_structured(content, CLASSIFY_PROMPT, model=EXTRACTION_MODEL)
        doc_type = result.get("document_type", "unknown").lower()
        return doc_type if doc_type in VALID_DOCUMENT_TYPES else "unknown"
    except Exception as e:
        log.warning(f"Document classification failed: {e}")
        return "unknown"


# ---------------------------------------------------------------------------
# Unit 2: Extract profile elements from a document
# ---------------------------------------------------------------------------

VALID_ELEMENT_TYPES = {"identity", "change", "audience", "competitor_category"}

EXTRACT_PROFILE_PROMPT = """You are building a profile of the organization that AUTHORED this document —
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

RESCAN_PROFILE_PROMPT = """You are refining the profile of the organization that authored these documents.

Here is what foundation extraction found — the positioning data we extracted:
{foundation_context}

And here is the current profile:
{current_profile}

Rescan this document. For each profile element you extract:
- If it confirms an existing profile element, return it with higher confidence.
- If it contradicts the foundation data (e.g., a persona that doesn't match the
  buyer roles found in foundation), return it with lower confidence or omit it.
- If it reveals something new that the foundation data supports, add it.

Return a JSON array. Each object: {{"type": "...", "content": "...", "confidence": 0.0-1.0}}
If a document reveals nothing about the author, return [].
"""


def extract_profile(content: str) -> list[dict]:
    """Extract organization profile elements from a document.

    Returns a list of dicts with keys: type, content, confidence.
    Only returns elements with valid types.
    """
    from mothertree.config import ORGANIZATION_NAME
    prompt = EXTRACT_PROFILE_PROMPT
    if ORGANIZATION_NAME:
        prompt = f"The organization you are profiling is {ORGANIZATION_NAME}.\n\n{prompt}"
    try:
        elements = extract_structured(content, prompt, model=EXTRACTION_MODEL)
    except Exception as e:
        log.warning(f"Profile extraction failed: {e}")
        return []
    if not isinstance(elements, list):
        return []
    # Normalize and filter
    result = []
    for e in elements:
        if not isinstance(e, dict) or "type" not in e:
            continue
        e["type"] = e["type"].lower()
        if e["type"] in VALID_ELEMENT_TYPES and e.get("content"):
            result.append(e)
    return result


def rescan_profile(content: str, foundation_context: str, current_profile: str) -> list[dict]:
    """Re-extract profile elements with foundation data for refinement (pass 3).

    Same interface as extract_profile but uses a prompt that includes
    foundation data and the current profile for cross-referencing.
    """
    prompt = RESCAN_PROFILE_PROMPT.format(
        foundation_context=foundation_context,
        current_profile=current_profile,
    )
    try:
        elements = extract_structured(content, prompt, model=EXTRACTION_MODEL)
    except Exception as e:
        log.warning(f"Profile rescan failed: {e}")
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


# ---------------------------------------------------------------------------
# Unit 3: Merge a profile element into the database
# ---------------------------------------------------------------------------

def merge_element(element: dict) -> str:
    """Merge a profile element into the organization table.

    Checks for exact match first, then semantic similarity (>0.85).
    If either matches, bumps confidence and source_count on the existing record.
    Otherwise inserts a new element.

    Returns "updated" or "inserted".
    """
    element_type = element["type"]
    content = element["content"]
    confidence = element.get("confidence", 0.5)

    existing = get_organization_profile()
    same_type = [e for e in existing if e["element_type"] == element_type]

    # Exact content match — update confidence and source_count
    for existing_elem in same_type:
        if existing_elem["content"] == content:
            update_organization_element(existing_elem["id"], {
                "confidence": min(1.0, max(existing_elem["confidence"], confidence)),
                "source_count": existing_elem["source_count"] + 1,
            })
            return "updated"

    # Semantic similarity match — merge near-duplicates
    try:
        from mothertree.graphql_client import search_similar
        similar = search_similar("organization", content, limit=1, threshold=0.85)
        if similar:
            match = similar[0]
            match_id = match["id"]
            # Only merge if same element type
            if match.get("element_type") == element_type:
                # Keep the higher-confidence version's content
                existing_conf = float(match.get("confidence", 0.5))
                if confidence > existing_conf:
                    update_organization_element(match_id, {
                        "content": content,
                        "confidence": confidence,
                        "source_count": int(match.get("source_count", 1)) + 1,
                    })
                else:
                    update_organization_element(match_id, {
                        "confidence": max(existing_conf, confidence),
                        "source_count": int(match.get("source_count", 1)) + 1,
                    })
                return "updated"
    except Exception:
        pass  # Embeddings not available — fall through to insert

    # Cap at 5 per type — if at limit, only insert if higher confidence than the weakest
    MAX_PER_TYPE = 5
    if len(same_type) >= MAX_PER_TYPE:
        weakest = min(same_type, key=lambda e: e.get("confidence", 0))
        if confidence > weakest.get("confidence", 0):
            from mothertree.graphql_client import graphql
            graphql("""
mutation($id: UUID!) {
    deleteOrganizationById(input: {id: $id}) { organization { id } }
}
""", {"id": weakest["id"]})
        else:
            return "skipped"

    insert_organization_element({
        "element_type": element_type,
        "content": content,
        "confidence": confidence,
        "source_count": 1,
    })
    return "inserted"


def merge_elements(elements: list[dict]) -> dict:
    """Merge a batch of profile elements. Returns stats."""
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    for element in elements:
        if not element.get("content"):
            stats["skipped"] += 1
            continue
        try:
            action = merge_element(element)
            stats[action] += 1
        except Exception as e:
            log.warning(f"Profile merge failed for {element.get('type')}: {e}")
            stats["skipped"] += 1
    return stats


# ---------------------------------------------------------------------------
# Unit 4: Consolidate profile — deduplicate and synthesize
# ---------------------------------------------------------------------------

CONSOLIDATE_PROMPT = """You are consolidating an organization profile. You have multiple extracted
elements of each type — many are duplicates or near-duplicates saying the same thing differently.

For each type, consolidate to the 3-5 MOST DISTINCT elements. Merge duplicates into one clear statement.
Drop elements that are vague, redundant, or clearly about a client rather than the organization itself.

Current elements by type:
{elements_by_type}

Return a JSON array of consolidated elements:
{{"type": "identity|change|audience|competitor_category", "content": "...", "confidence": 0.0-1.0}}

Rules:
- Keep only what's distinct. "We build IDPs on open source" and "We build and operate IDPs" → one element.
- Higher confidence for elements confirmed by multiple sources.
- Drop anything that sounds like a client's problem rather than the organization's offering.
- 3-5 elements per type. Fewer is better if the extras are redundant.
"""


def consolidate_profile(elements: list[dict]) -> list[dict]:
    """Consolidate profile elements — deduplicate and synthesize.

    Input: raw list of all extracted elements (may have many duplicates).
    Output: consolidated list with 3-5 distinct elements per type.
    """
    if not elements:
        return []

    # Group by type
    by_type = {}
    for e in elements:
        t = e.get("type") or e.get("element_type", "")
        content = e.get("content", "")
        if t and content:
            by_type.setdefault(t, []).append(content)

    # Format for the prompt
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
    from mothertree.config import ORGANIZATION_NAME
    prompt = CONSOLIDATE_PROMPT.format(elements_by_type=elements_text)
    if ORGANIZATION_NAME:
        prompt = f"The organization is {ORGANIZATION_NAME}.\n\n{prompt}"

    try:
        result = extract_structured("", prompt, model=EXTRACTION_MODEL)
    except Exception as e:
        log.warning(f"Profile consolidation failed: {e}")
        return elements  # return originals if consolidation fails

    if not isinstance(result, list):
        return elements

    # Normalize and filter
    consolidated = []
    for e in result:
        if not isinstance(e, dict) or "type" not in e:
            continue
        e["type"] = e["type"].lower()
        if e["type"] in VALID_ELEMENT_TYPES and e.get("content"):
            consolidated.append(e)

    return consolidated if consolidated else elements


# ---------------------------------------------------------------------------
# Fetch profile for prompt injection
# ---------------------------------------------------------------------------

def fetch_organization_profile() -> str:
    """Fetch the organization profile formatted for prompt injection."""
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
