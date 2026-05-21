# Organization Profile — Automatic Identity Extraction

## Problem

The foundation extraction prompt has no knowledge of who the organization is. When it processes a case study about replacing Qualtrics at a university, it extracts "Researchers" as a persona and "Researchers don't miss Qualtrics" as a change statement — because the prompt cannot distinguish between company-level positioning and case-study-level content.

The result: foundation tables fill with noise from client engagements, and the distinction between foundation (what we say) and narrative (stories we tell) breaks down.

## Solution

Add an organization profile that the ingestion pipeline builds automatically from the content. The profile acts as a lens for foundation and narrative extraction — it tells the LLM "this is who we are" so it can filter what belongs at the company level vs. what belongs in narratives.

The profile bootstraps from the first content it sees and refines over time as new content flows through. No manual input required.

## The Four-Pass Pipeline

Ingestion becomes four passes, each building on the previous:

```
Pass 1: PROFILE SCAN
  Input:  raw content (all documents)
  Output: organization profile (bootstrap or update)
  Purpose: learn who the organization is from its own content

Pass 2: FOUNDATION EXTRACTION
  Input:  raw content + organization profile
  Output: change, worldview, personas, competitors
  Purpose: extract company-level positioning, filtered by profile

Pass 3: PROFILE RESCAN
  Input:  raw content + foundation data
  Output: organization profile (refined)
  Purpose: sharpen the profile using foundation data as confirmation,
           drop elements that leaked in from case studies

Pass 4: QUALIFIED RE-EXTRACTION
  Input:  raw content + refined profile
  Output: foundation (re-extracted) + narrative (new)
  Purpose: final extraction with maximum context
```

Each pass uses the database as the handoff. Pass 1 writes the profile, pass 2 reads it and writes foundation, pass 3 reads foundation and rewrites the profile, pass 4 reads the refined profile and rewrites foundation + writes narrative.

## Organization Profile Schema

A new `organization` table. One row per profile element — not a single JSON blob — so elements can be tracked independently.

| Column | Type | Purpose |
|--------|------|---------|
| id | uuid | PK, auto-generated |
| element_type | text | `identity`, `change`, `audience`, `competitor_category` |
| content | text | The extracted element |
| confidence | float | 0.0–1.0, increases when multiple documents confirm |
| source_count | int | How many documents contributed to this element |
| created_at | timestamptz | First seen |
| updated_at | timestamptz | Last confirmed or modified |

**Element types:**

- `identity` — who the organization is, what they do. Usually 1–3 rows. The elevator pitch.
- `change` — the core transformation offered. Profile-level, not the detailed foundation records. What does the client become?
- `audience` — who the organization sells to. Role-level ("CTO", "Engineering Director"), not individual persona profiles.
- `competitor_category` — categories of alternatives ("Managed Kubernetes Providers"), not specific company names.

The profile is compact by design. It is not a second copy of the foundation tables — it is the lens that tells extraction what to look for. The difference between "this is about us" and "this is a story we tell about a client."

## Profile Scan Prompt (Pass 1)

```
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
```

## Profile Rescan Prompt (Pass 3)

Same structure as pass 1, but with foundation data injected:

```
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

Return a JSON array. Same format: {"type": "...", "content": "...", "confidence": 0.0-1.0}
```

## Profile Merging

When multiple documents produce profile elements, they merge:

- **Matching elements** (same type, semantically similar content): confidence increases, source_count increments, content updated if the new version is more specific.
- **New elements**: inserted with the extracted confidence and source_count = 1.
- **Contradicting elements**: the one with higher confidence and source_count wins. Low-confidence single-source elements are naturally displaced over time.

Semantic similarity for merging: use pgvector embeddings (already in the stack) to compare profile elements. Embed each element's content, match against existing elements by cosine similarity (threshold ~0.85). This avoids O(documents x elements) LLM calls — embedding is a single cheap call per element, and the comparison is a vector query against a small table.

## How the Profile Feeds into Extraction

Before calling the foundation or narrative extraction prompt, fetch the profile and inject it as a context prefix:

```
ORGANIZATION PROFILE:
- Identity: [top identity elements by confidence]
- Change: [top change elements]
- Audience: [top audience elements]
- Competes with: [top competitor_category elements]

Given this profile, analyze the document for foundational commercial positioning
that applies to THIS organization — not to clients, case studies, or third parties
described in the document.
```

Implemented as a `_fetch_organization_profile()` function, analogous to the existing `_fetch_foundation_context()`.

## CLI Behavior

No new CLI commands. The existing `ingest foundation` command runs all four passes automatically.

**Full ingestion** (`--force`):
```
mothertree ingest foundation repo <path> --force

  Pass 1/4: Building organization profile...
  Pass 2/4: Foundation extraction (with profile)...
  Pass 3/4: Refining organization profile...
  Pass 4/4: Qualified re-extraction (foundation + narrative)...
```

With `--force`, the organization profile is rebuilt from scratch (all rows deleted before pass 1). This is consistent with how foundation and narrative handle `--force`.

**Four-pass orchestration** is a shared function called by all foundation variants (file, dir, repo, url, sitemap). Each variant resolves its content sources, then hands the list to the shared four-pass function.

**Incremental ingestion** (new documents):
Profile already exists. Pass 1 runs on new documents only and adjusts the profile. Passes 2–4 run on new documents with the full profile. Existing records from previous runs are untouched.

**Narrative-only ingestion** (`ingest narrative`):
Skips passes 1–3 (profile and foundation must exist). Runs narrative extraction with the current profile as context. If no profile exists, exits with a message to run foundation first.

## What Changes

**New:**
- `organization` table in PostgreSQL, tracked in Hasura
- Profile scan prompt and rescan prompt in `ingestion/extract.py`
- `_fetch_organization_profile()` function in `ingestion/extract.py`
- Profile merging logic in `ingestion/ingest.py`
- Four-pass orchestration in `ingestion/ingest.py`

**Modified:**
- `FOUNDATION_EXTRACTION` prompt — profile injected as context prefix
- `NARRATIVE_EXTRACTION_TEMPLATE` — profile injected as context prefix
- `cmd_foundation_repo` (and file/dir/url/sitemap variants) — four passes
- `cmd_narrative_repo` (and variants) — requires profile, injects into prompt

**Unchanged:**
- Validation pipeline (schema validation, multi-model scoring, triage, arbitration)
- Source tracking and skip-unchanged logic
- Quality control thresholds
- Foundation and narrative table schemas
- Bot pipeline and character ensemble
- Memory system, Slack integration
