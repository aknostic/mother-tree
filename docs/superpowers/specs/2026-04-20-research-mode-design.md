# Research Mode — Conversational Company/Topic Research

## Problem

Users ask Mother Tree questions like "research greenchoice" expecting her to pull current public information — recent news, tech stack signals, competitive posture — and combine it with internal CI. Today she can only work from internal CI; when asked to research, she acknowledges the gap ("I don't have live browsing") and compensates by synthesising what she already knows. That compensation is often useful but leaves a real hole: the team has no way to get a current outside-in picture of a target without doing it manually and pasting URLs.

Filling this hole cleanly requires three things the bot doesn't have today: live web search, a conversational mode where Mother Tree can ask the user to supply material she can't reach (LinkedIn PDFs, SSO-gated pages), and an explicit consent step before any of the findings become persistent CI.

## Architectural Principles

These extend the principles from `docs/superpowers/specs/2026-04-16-intelligence-consolidation-design.md`. Same rules apply here.

### 1. V1 is DM-only

Research sessions run in a 1:1 DM between a user and Mother Tree. This choice lets us reuse the existing `conversations.pending_debrief` pattern (DM-gated approval flow at `pipeline.py:106`) and sidesteps the complications of channel/thread state routing. Future work can extend to threads, but that requires generalising the approval path — out of scope for V1.

### 2. Explicit open/close

`research <topic>` opens a session; `done researching` closes it. Mother Tree's mode is always observable from the DM state. `research` without a topic and `done researching` with no open session both no-op gracefully.

### 3. Mistral websearch is the only new external dependency

Mistral's built-in `websearch` tool (on `api.mistral.ai`) fits the existing stack (Mistral Small 3.2 is already in use for classification) and the "European second" model policy. No Brave/Tavily/Serper; no scrapers; no LinkedIn API (LinkedIn is closed to non-humans by design — the user supplies that material).

**Infrastructure note:** this is a separate endpoint from the Scaleway-hosted Mistral we use today. Scaleway's OpenAI-compatible proxy (`api.scaleway.ai/v1`) does not expose Mistral's agent/tools APIs. `search.py` calls `api.mistral.ai` directly with a dedicated `MISTRAL_API_KEY` env var, which ships as a new SOPS-encrypted secret.

### 4. Tool-use blurs gather/synthesize — accept it with a named exception

Consolidation split data gathering from LLM synthesis. Mistral's websearch tool interleaves the two in a single call (the LLM decides when to search and composes with results in the same round-trip). Forcing the split would mean replaying the tool-use loop manually outside the model — more code, worse prompts, and no real separation because search queries are derived from the model's reasoning anyway. `run_research_turn` is a deliberate exception, documented in the module docstring. The rule still holds everywhere else; future features should only repeat this pattern when the same tool-use constraint applies.

### 5. Nothing writes to CI without explicit consent

Research findings surface as `pending_extraction` candidates with provenance. The user approves (`approve`), edits (`edit 3,5`), or skips (`skip`) before anything lands in CI tables. Uses **the existing debrief approval flow** verbatim — the preview shape, the `Reply *approve* to ingest` sentinel string, and `_ingest_debrief_extraction` downstream. Sensitive items marked by Spotter get dropped by default on `approve`.

### 6. Session state lives in the `conversations` table

A new column `conversations.research_session JSONB` holds session state — parallel to the existing `conversations.pending_debrief`. Helper functions `set_research_session`, `get_research_session`, `clear_research_session` live alongside their pending_debrief siblings in `graphql_client.py`. `research_session` is a new column; no collision risk.

## Design

### New file: `jobs/mothertree/search.py`

Thin wrapper around Mistral's `api.mistral.ai/v1/chat/completions` endpoint with `tools=[{"type": "web_search"}]`. Single function:

```python
def mistral_websearch_chat(system: str, messages: list[dict],
                            max_searches: int = 5) -> dict:
    """Call Mistral with the web_search tool enabled.

    Returns:
        {
            "content": str,                 # assistant's final reply text
            "searches": [                    # searches performed this call
                {"query": str,
                 "results": [{"url", "title", "snippet"}]}
            ],
            "search_count": int,
        }
    """
```

No retries inside the function; caller handles retry policy. No state. No extraction — that's Spotter's job. Reads `MISTRAL_API_KEY` from `mothertree.config`.

### New function in `jobs/mothertree/intelligence.py`

```python
def run_research_turn(history: list[dict],
                      session_state: dict,
                      user_message: str,
                      file_contents: list[dict] | None = None
                     ) -> tuple[str, dict]:
    """Run one conversational turn in research mode.

    Uses Mistral websearch (via search.py) to compose a reply, then runs
    Spotter (extract_research) to surface save candidates. Merges candidates
    into session_state['pending_extraction'] with provenance.

    Returns:
        (reply_text, updated_session_state)
    """
```

Principle 4 exception documented in the module docstring.

### Session state

Stored on `conversations.research_session` JSONB:

```python
{
  "kind": "research_session",
  "topic": "greenchoice",
  "opened_at": "2026-04-20T06:20:00Z",
  "turns": int,
  "searches_used": int,
  "findings": [
    {"turn": int, "url": str, "title": str, "snippet": str}
  ],
  "pending_extraction": {        # same shape as debrief — no extra keys
    "entities": [...],
    "pain_signals": [...],
    "value_hooks": [...],
    "actions": [...]
  } | None,
  "status": "open" | "closed"
}
```

The `pending_extraction` schema matches `extract_debrief` exactly so `_ingest_debrief_extraction` handles both without a branch.

### Session lifecycle

| Event | Dispatcher | Mother Tree / pipeline | State change |
|---|---|---|---|
| `research <topic>` | `{"type": "research_start", "topic": "<topic>"}` | Initialises session via `set_research_session`, runs turn 1 | `turns=1`, state persisted |
| Freeform DM, open session | No annotation; dispatcher unaware | `_get_response` reads `get_research_session(conv_id)`, passes into `respond(..., session_state=...)` | `turns++`, `searches_used += n`, `pending_extraction` merged |
| `approve` in open session | Existing approve detection at `pipeline.py:108` | `_handle_debrief_approval` reads `pending_debrief` OR `research_session.pending_extraction` — generalised to handle both | `pending_extraction = None`, Spotter+Weaver write |
| `edit 3,5` / `skip` | Existing handlers | Same generalisation | Trim or clear |
| `done researching` / `close research` | `{"type": "research_close"}` | Wrap-up reply, `clear_research_session` | State deleted |
| `research <new>` inside open session | `{"type": "research_start", "topic": "<new>"}` | Confirms switch; on confirm clears old, opens new | Old dropped, new opened |

**Approval-path generalisation:** `pipeline.py:106-114` today only reads the DM conversation's `pending_debrief`. We extend the sentinel check to also look at `research_session.pending_extraction` (both live on the same `conversations` row). `_handle_debrief_approval` grows to pull from whichever is set and ingest via the same `_ingest_debrief_extraction`. Remains DM-only.

### Dispatcher changes

`jobs/bot/characters/dispatcher.py` gets one helper:

```python
def _detect_research_command(text: str) -> dict | None:
    """Return {'type': 'research_start', 'topic': ...} or
    {'type': 'research_close'} or None."""
```

Matches:
- `research <topic>` / `do research on <topic>` / `research about <topic>` → `research_start`
- `done researching` / `close research` / `stop research` / `end research` → `research_close`

Wired into `dispatch()` alongside the existing pipeline/brief patterns, BEFORE the `GLOBAL_COMMANDS` block. Not added to `GLOBAL_COMMANDS` (research always pairs with a topic or close verb).

### Mother Tree changes

`respond()` gains an optional parameter:

```python
def respond(..., session_state: dict | None = None, ...) -> str:
```

`pipeline.py:_get_response` loads `get_research_session(conversation_id)` when the message is a DM, and passes it in. Inside `respond()`:

```python
if annotation and annotation.get("type") == "research_start":
    state = _init_research_session(annotation["topic"])
    reply, state = run_research_turn(history, state, user_message=annotation["topic"], file_contents=...)
    set_research_session(conv_id, state)
    return reply + _approval_nudge_if_pending(state)

if annotation and annotation.get("type") == "research_close":
    state = session_state or {}
    clear_research_session(conv_id)
    return _research_close_summary(state)

if session_state and session_state.get("status") == "open":
    reply, state = run_research_turn(history, session_state, user_message=question, file_contents=...)
    set_research_session(conv_id, state)
    return reply + _approval_nudge_if_pending(state)

# else: existing flow
```

The `_approval_nudge_if_pending` helper appends the `Reply *approve* to ingest` sentinel (the exact string pipeline.py:108 matches on) when `pending_extraction` has new items since last turn. No change to that sentinel — existing detection keeps working.

### Spotter changes

New function in `jobs/bot/characters/spotter.py`:

```python
RESEARCH_EXTENSION = """
Extract companies, contacts, and signals mentioned AS FACT in this research
output. Skip speculation, comparisons, and hypotheticals. Preserve provenance
(URL of the finding). Return the same schema as extract_debrief: entities,
pain_signals, value_hooks, actions. Each item gets a `sensitive` flag.
"""

def extract_research(text: str) -> dict:
    """Fact-only extraction variant for research mode. Same return schema as
    extract_debrief so _ingest_debrief_extraction handles both."""
```

Parallel to the existing `DEBRIEF_EXTENSION` + `extract_debrief`. Module-level constant, not a handbook file — consistent with existing extraction prompts in `spotter.py`.

### Budgets

| Cap | Value | Rationale |
|---|---|---|
| `max_searches` per turn | 5 | Matches typical defaults in tool-use configs; tight enough to bound per-turn cost |
| `searches_used` per session | 20 | ~4 turns of heavy searching before degrading; empirically enough for a single company investigation |
| `turns` per session | 30 | Fits within `THREAD_MAX_MESSAGES` (100) with headroom for interleaved user messages |

Soft warning at 25 turns; hard stop at 30. Beyond search cap: Mistral called without tool; reply asks user for specific URLs.

### Files changed

- **New:** `jobs/mothertree/search.py` — Mistral websearch wrapper
- **New:** `jobs/tests/test_research.py` — unit + integration coverage
- **New:** `jobs/handbook/research_mode.md` — so `help research` works
- **New:** SOPS secret for `MISTRAL_API_KEY` under `deploy/` (sibling to existing secrets)
- **New:** migration `deploy/database/migrations/NNN-research-session.sql` adding `conversations.research_session JSONB`
- **Modify:** `jobs/mothertree/intelligence.py` — add `run_research_turn`
- **Modify:** `jobs/mothertree/graphql_client.py` — add `set/get/clear_research_session`
- **Modify:** `jobs/mothertree/config.py` — add `MISTRAL_API_KEY`, `MISTRAL_API_BASE_URL`
- **Modify:** `jobs/bot/characters/dispatcher.py` — add `_detect_research_command`
- **Modify:** `jobs/bot/characters/mother_tree.py` — handle research_start / research_close / open-session freeform
- **Modify:** `jobs/bot/characters/spotter.py` — add `RESEARCH_EXTENSION` + `extract_research`
- **Modify:** `jobs/bot/pipeline.py` — load research_session in `_get_response`; generalise `pipeline.py:106-114` approve-detection and `_handle_debrief_approval` to pull from either column
- **Modify:** deployment manifests under `deploy/` — wire `MISTRAL_API_KEY` secret into jobs/slack-bot deployments

### Relationship to `brief`

`brief <q>` searches internal CI only. `research <t>` opens a live external session. The handbook entry for `research_mode.md` states the split explicitly. No technical overlap; no shared code path.

## Error Handling

| Failure | Response |
|---|---|
| Mistral 5xx / timeout | Retry once. Second failure: "Can't reach search right now — want to work from what I have, or pause?" Session stays open. |
| `websearch` returns empty | Mistral usually replies anyway; if genuinely empty, MT asks for a specific URL. |
| Spotter extraction crashes | Log + skip this turn's extraction. Reply delivered without "I noticed X" line. |
| Search budget hit (20/session) | Mistral called without tool; reply tells user to paste URLs or close. |
| Turn cap approached (25/30) | Reply nudges toward wrap-up. Hard stop at 30 refuses new turns. |
| File upload | Passed to `run_research_turn` via existing `file_contents` plumbing (already present in `bot/pipeline.py`). PDF text extraction via Slack's `file.text` field when available; otherwise user pastes excerpts. |
| Pasted URL | Existing `extract_urls` + `fetch_and_follow` runs; content flows into next turn. |
| `approve` with empty pending | "Nothing to save yet — I haven't extracted any concrete facts. Keep going or `done researching`?" |
| `done researching` with no session | No-op: "No research session active." |
| `research <new>` inside open session | Confirm switch; on confirm, clear + open new. |
| Thread memory write fails | Turn reply still delivered; reply ends with `⚠️ Couldn't save session state — your next message may be treated as a new topic. Paste the URL again if it matters.` No retry logic. |
| `MISTRAL_API_KEY` missing at startup | Startup log warning. `research_start` returns "Research mode is not configured — ask a farmer to set MISTRAL_API_KEY." |

## Testing

**Unit** (mocked Mistral + Spotter + GraphQL):
- `search.mistral_websearch_chat` — request shape (tools param, headers, auth) + response parsing
- `run_research_turn` — state transitions (pending merge, searches_used increment, turn cap, search cap)
- Dispatcher patterns — open/close variants, `research` without topic no-op
- Mother Tree annotation routing — research_start initialises state, open-session freeform delegates, close clears state
- `extract_research` returns same-schema dict as `extract_debrief` (sentinel test)

**Integration** (module boundaries mocked):
- Full session: open → turn → approve → turn → close. Assert final `_ingest_debrief_extraction` called with expected payload.
- Budget exhaustion: simulate 20 searches; assert turn 21 falls back to non-search mode.
- File upload mid-session flows into `run_research_turn` with `file_contents` populated.
- Research in channel (non-DM) — `research_start` replies "DMs only for now" without initialising state.

**Explicitly not testing:**
- Mistral's actual search quality
- Spotter extraction quality (covered by Spotter's existing tests)
- Real HTTP calls

**New fixture:** `fake_research_session(topic, turns=0, pending=None)` for state setup.

**Target:** ~15 new tests total.

## Discoverability

- `help` (bare command) lists "research" alongside pipeline and brief in the grouped-by-topic output, via the new `research_mode.md` handbook entry (topic: `getting_started`).
- `help research` returns the research_mode entry directly.
- First-time cue: when a hunter/gatherer types something that looks like "research" intent (`research`, `tell me about`, `what do we know about`) but no topic is supplied, MT replies with a one-liner teaser: "Try `research <company>` — I'll pull current info and walk through it with you."

## Out of scope

- LinkedIn API integration (user supplies PDFs via Slack file upload or paste).
- Site-specific scrapers (no `/careers` sniffer, no Google News RSS).
- Autonomous multi-turn agent loop — Mistral tool-use handles search iteration within a turn; we do not loop without user input.
- Persisting research sessions as a first-class CI record for later recall — session state dies when cleared. A `research_sessions` history table could follow later.
- Channel / thread research sessions — V1 is DM-only. Generalising the approval flow to threads is deferred.
- CLI `mothertree research <topic>` — deferred. The interactive flow is Slack-only for now.
- PDF binary extraction — V1 relies on Slack's `file.text` field and pasted excerpts. A `pdfminer.six` integration can follow if users can't get clean paste.
- Citizen role access — research is available to hunter/gatherer/farmer only, gated by the existing `enrolled` check.
