# Intelligence Consolidation + Pipeline & Brief Commands

## Problem

CI data access is scattered across bot characters, CLI commands, discipline cronjobs, and the ask module. Each has its own inline GraphQL queries, context assembly, and formatting. This creates drift — bugs fixed in one path don't get fixed in the other, and new CI tables require changes in multiple places.

The immediate trigger: users want on-demand pipeline review and CI briefing via Slack DM, but the logic for both lives in places the bot can't reach (weekly_review.py, ask.py CLI path).

## Architectural Principles

These apply to this spec and to all future Mother Tree development.

### 1. Single path to CI data

Every query against CI tables (changes, worldviews, personas, competitors, insights, contacts, signals, interactions, opportunities, organization) goes through `intelligence.py`. No direct GraphQL calls from bot characters, discipline jobs, or CLI commands. `graphql_client.py` provides the raw query functions; `intelligence.py` composes them into meaningful data bundles.

### 2. Gather and synthesize are separate

Data gathering returns plain dicts. LLM synthesis takes plain dicts and returns text. Never mix data fetching with LLM calls in the same function. This lets us test gathering without LLM costs, swap models for synthesis, and reuse the same data in multiple presentations.

### 3. Thin callers

CLI commands, bot handlers, and cronjobs are thin — they resolve the user's intent, call gather + synthesize, and deliver the result. Business logic lives in `intelligence.py`, not in the caller.

### 4. One function, many callers

If the weekly review and the bot `pipeline` command need the same data, they call the same function with the same parameters. Don't duplicate "almost the same" queries. Add parameters to the shared function if scoping differs.

### 5. GraphQL queries are parameterized

All GraphQL queries use `$variables`, never f-string interpolation. This is a security rule (OWASP injection) and a correctness rule (special characters in user input).

## Design

### New file: `jobs/mothertree/intelligence.py`

#### Data Gathering

```python
def gather_pipeline(user_id: str | None = None, days: int = 7,
                    counts_only: bool = False) -> dict:
    """Gather pipeline state — opportunities, signals, interactions, contacts, training.

    Args:
        user_id: Scope to this user's owned items. None = global.
        days: Lookback window for signals and interactions.
        counts_only: If True, return totalCount per table instead of full lists.
                     Used by monthly retro which synthesizes from aggregates.

    Returns:
        {
            "opportunities": [...],   # with company, contact, stage, next_action
            "signals": [...],         # recent, deduped by source (or count if counts_only)
            "interactions": [...],    # recent, grouped by contact (or count if counts_only)
            "contacts": [...],        # warm/hot, with last_contact (or count if counts_only)
            "training": [...],        # enrollment progress per user
            "scope": "global" | "personal" | "other",
            "target_name": str | None,  # name of scoped user if applicable
        }
    """

def gather_brief(query: str) -> dict:
    """Cross-table semantic + text search.

    Args:
        query: Free-text search term.

    Returns:
        {
            "query": str,
            "contacts": [...],        # name/role/company matches
            "companies": [...],       # name/industry matches
            "signals": [...],         # content matches
            "interactions": [...],    # summary matches
            "changes": [...],         # semantic matches
            "worldviews": [...],      # semantic matches
            "competitors": [...],     # semantic matches
            "insights": [...],        # semantic + text matches
            "proof_points": [...],    # semantic matches
        }
    """

def gather_context(query: str | None = None, top_n: int = 5) -> dict:
    """CI context for character conversation prompts.

    Args:
        query: Optional — if set, includes semantic search results.
        top_n: Max records per table.

    Returns:
        {
            "changes": [...],
            "worldviews": [...],
            "personas": [...],
            "competitors": [...],
            "contacts": [...],
            "signals": [...],
            "proof_points": [...],
            "organization": [...],    # org profile elements
            "semantic_results": [...] | None,  # only if query set
        }
    """

def gather_meeting_context(event: dict) -> dict:
    """CI context for a calendar event — meeting prep and debrief.

    Looks up each attendee by name in contacts, then runs semantic search
    on insights, changes, and proof_points using meeting title + attendee context.

    Args:
        event: {"title": str, "attendees": [str], "date": str, ...}

    Returns:
        {
            "event": {...},
            "attendee_contacts": [...],  # matched contacts per attendee
            "insights": [...],           # semantic matches for meeting context
            "changes": [...],
            "proof_points": [...],
        }
    """

def gather_training_state(user_id: str) -> dict:
    """Training progress for a single user.

    Returns:
        {
            "user": {...},
            "progress": [...],        # per-area scores
            "current_stage": int,
            "current_chapter": int,
            "streak": int,
            "curriculum_position": str,  # human-readable
        }
    """

def gather_account(company_name: str | None = None,
                   company_id: str | None = None) -> dict:
    """Account details — company + contacts + opportunities + plan.

    Returns:
        {
            "company": {...},
            "contacts": [...],
            "opportunities": [...],
            "interactions": [...],
            "account_plan": {...} | None,
        }
    """

def resolve_user(name_or_email: str) -> dict | None:
    """Fuzzy-match a user by name or email.

    Builds on find_user_by_name() in graphql_client.py for the name path,
    userByEmail() for the email path. Adds case-insensitive partial matching.
    Returns None if no match.
    Raises AmbiguousUserError(matches=[...]) if multiple matches — caller
    should present options and ask for clarification.
    """
```

#### Synthesis

```python
def synthesize_pipeline(data: dict, scope: str = "global",
                        model: str = None,
                        on_chunk: callable = None) -> str:
    """Generate narrative pipeline review.

    scope:
        "global" — Monday-review style (Moved / Stalled / Attention / Blockers)
        "personal" — coaching tone (Your deals / What needs attention / Suggested actions)
        "other" — third-person (Pim's deals / Where Pim might need support)

    on_chunk: Optional streaming callback for bot responses. If set, chunks
              are streamed as they arrive and the full text is still returned.
    """

def synthesize_brief(data: dict, query: str,
                     model: str = None,
                     on_chunk: callable = None) -> str:
    """Generate narrative briefing from search results.

    on_chunk: Optional streaming callback for bot responses.
    """

def synthesize_weekly(data: dict, model: str = None) -> str:
    """Monday morning briefing format. <300 words, Slack formatting.
    No streaming — cronjob delivers complete message."""

def synthesize_monthly(data: dict, model: str = None) -> str:
    """Monthly retrospective format. Expects counts_only=True pipeline data.
    No streaming — cronjob delivers complete message."""
```

### Bot Routing

#### detect.py

Add to `GLOBAL_COMMANDS`: `"pipeline"`, `"brief"`.

#### dispatcher.py

Pattern matching before LLM triage:

```
"the pipeline" / "pipeline" (bare)     → {"type": "pipeline", "scope": "global"}
"my pipeline"                          → {"type": "pipeline", "scope": "personal"}
"pim's pipeline" / "pipeline pim"      → {"type": "pipeline", "scope": "other", "target": "pim"}
"brief <query>"                        → {"type": "brief", "query": "<query>"}
```

These go to Mother Tree with the annotation.

#### mother_tree.py

Handle pipeline/brief annotations in `respond()`:

```python
if annotation and annotation.get("type") == "pipeline":
    data = gather_pipeline(user_id, days=7)
    return synthesize_pipeline(data, scope)

if annotation and annotation.get("type") == "brief":
    data = gather_brief(annotation["query"])
    return synthesize_brief(data, annotation["query"])
```

### CLI

#### Existing: `mothertree brief <query>`

Rewire to: `gather_brief(query)` → `synthesize_brief(data, query)` → print.

#### New: `mothertree pipeline [name|email]`

- `mothertree pipeline` → global
- `mothertree pipeline pim` → scoped to Pim
- `mothertree pipeline jurg@aknostic.com` → scoped by email

### Discipline Cronjobs

#### weekly_review.py

Replace `gather_pipeline_state()` + `generate_weekly_briefing()` with:

```python
data = gather_pipeline()
text = synthesize_weekly(data)
```

#### monthly_retro.py

Replace inline data gathering with:

```python
data = gather_pipeline(days=30, counts_only=True)
text = synthesize_monthly(data)
```

#### qbr_review.py

Replace inline account gathering with `gather_account()`.

### Character Context

#### base.py

Replace inline CI context fetching in `character_respond()`:

```python
# Before (in each character or base):
context = fetch_context(question)

# After:
from mothertree.intelligence import gather_context
context = gather_context(query=question)
```

`ask.py:fetch_context()` is deleted. The PERSONAS dict and `build_prompt()` helper stay in `ask.py` (or move to `intelligence.py` if cleaner).

## Migration Plan

### What moves

| Source | Function | Destination |
|--------|----------|-------------|
| `ask.py` | `fetch_context()` | `intelligence.py:gather_context()` |
| `ask.py` | `briefing()` | `intelligence.py:gather_brief()` + `synthesize_brief()` |
| `weekly_review.py` | `gather_pipeline_state()` | `intelligence.py:gather_pipeline()` |
| `weekly_review.py` | `generate_weekly_briefing()` | `intelligence.py:synthesize_weekly()` |
| `monthly_retro.py` | inline data gathering | `intelligence.py:gather_pipeline(days=30)` |
| `qbr_review.py` | inline account gathering | `intelligence.py:gather_account()` |
| `calendar_sync.py` | `get_ci_context_for_event()` | `intelligence.py:gather_meeting_context()` |

### What stays

- `graphql_client.py` — raw queries, used only by `intelligence.py`
- `llm.py` — LLM wrappers, used by synthesis functions and extraction
- `config.py` — env vars and model config
- Character modules — identity, goals, rules, thin `respond()` wrapper
- `ask.py` — PERSONAS dict, `build_prompt()`, character-specific prompt assembly

### What's new

- `intelligence.py` — all CI data access and synthesis
- Bot: `pipeline` and `brief` commands
- CLI: `mothertree pipeline` command

## Files Changed

- **New:** `jobs/mothertree/intelligence.py`
- **Simplify:** `jobs/mothertree/ask.py` (remove `fetch_context`, `briefing`)
- **Simplify:** `jobs/discipline/weekly_review.py` (thin caller)
- **Simplify:** `jobs/discipline/monthly_retro.py` (thin caller)
- **Simplify:** `jobs/discipline/qbr_review.py` (thin caller)
- **Simplify:** `jobs/discipline/calendar_sync.py` (thin caller)
- **Simplify:** `jobs/bot/characters/base.py` (context from `intelligence.py`)
- **Modify:** `jobs/bot/characters/mother_tree.py` (handle pipeline/brief)
- **Modify:** `jobs/bot/characters/dispatcher.py` (routing patterns)
- **Modify:** `jobs/bot/detect.py` (add commands)
- **Modify:** `jobs/cli.py` (add pipeline, rewire brief)

## Known Issues to Fix During Implementation

- **GLOBAL_COMMANDS duplication** — both `detect.py` and `dispatcher.py` define their own copy. Consolidate into a single source (detect.py) imported by dispatcher.py.

## Migration Ordering

Implementation is incremental, file-by-file. One constraint:

1. Create `intelligence.py` with all `gather_*` functions first (can coexist with old code)
2. Migrate callers one at a time — each caller switches to intelligence.py imports
3. **Atomic step:** `ask.py:fetch_context()` deletion and `base.py` migration must happen together (base.py imports from ask.py)
4. Add bot routing (detect.py + dispatcher.py + mother_tree.py) last — depends on intelligence.py being complete
5. Delete dead code from ask.py, weekly_review.py, etc. after all callers migrated

## Testing

- Unit tests for all `gather_*` functions (mock GraphQL)
- Unit tests for `resolve_user` fuzzy matching
- Unit tests for dispatcher routing (pipeline/brief patterns)
- Integration test: CLI brief produces output
- Integration test: CLI pipeline produces output
- Existing character tests still pass (context source changed but format unchanged)
