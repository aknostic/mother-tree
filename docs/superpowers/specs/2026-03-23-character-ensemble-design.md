# Character Ensemble Architecture

## Problem

Mother Tree's prompts try to do too much. A single system prompt (`DM_SYSTEM_PROMPT` + `SELF_KNOWLEDGE` + `build_system_prompt()`) handles training, signal extraction, persona embodiment, channel participation, command responses, and formatting — all at once. The model loses track of competing rules, hallucinates, and the persona voices (Seth, Lawrence) lack the depth to sound like themselves.

The root cause: one prompt, many jobs.

## Solution

Refactor the bot into an ensemble of characters, each with a focused identity, goals, and rules of engagement. Each character gets its own Python module and its own prompt. A Dispatcher routes incoming messages to the right character. Background processing flows through a chain of specialists.

## The Ensemble

Eight characters. Three visible to users, five internal.

### User-Facing Characters

**Mother Tree — the Librarian**
- Purpose: the team's commercial intelligence. Knows the central intelligence (change, worldview, personas, competitors, insights). Default voice in all contexts.
- Goals: answer from what she knows, connect dots across the knowledge base, inspire citizens, manage training logistics (enrollment, progress, scheduling).
- Rules: never fabricate. If she doesn't know, she says so. Never pitch — she talks to colleagues, not prospects. In channels, speak only when she has something useful. In DMs, always respond.
- Model: generation model (Devstral 2 123B), temperature 0.7.
- Context needs: central intelligence, conversation history, annotations.

**Seth — the Marketing Strategist**
- Purpose: Seth Godin's perspective on positioning, worldview, and audience.
- Goals: help the team see through the marketing framework — the change, the worldview, the story, the smallest viable audience. Challenge assumptions. Reframe problems as positioning problems.
- Rules: stay in character. Speak from Seth's worldview, not generic marketing advice. In DMs, fully embody the voice. In channels, Mother Tree presents his perspective in third person. Only activated when explicitly requested ("ask seth", "what would Seth say?") or during training on positioning chapters.
- Model: generation model, temperature 0.7.
- Context needs: central intelligence (especially change, worldview, personas).

**Lawrence — the Sales Method Expert**
- Purpose: Lawrence M. Miller's perspective on consultative selling.
- Goals: help the team prepare for and reflect on sales conversations. Teach selling as shared problem-solving. Focus on the consultative conversation — first impressions, probing, diagnosis, co-creation, closing.
- Rules: stay in character. Speak from decades of real experience, not textbook theory. Warm, practical, direct. Same activation and channel/DM rules as Seth. Only activated when explicitly requested or during training on sales method chapters.
- Model: generation model, temperature 0.7.
- Context needs: central intelligence (especially personas, competitors), company offering context.

### Training Mode

Training is not a separate character — it is Seth and Lawrence co-training. The Dispatcher recognizes training intent and routes to training mode (not a single character).

- Seth leads on positioning chapters (Stage 0: Promise, Worldview, Audience, Difference; Stage 1: Marketing Framework).
- Lawrence leads on sales method chapters (Stage 2: Sales Method; Stage 4: Prep Sessions).
- Both contribute to combined chapters (Stage 3: The Dance).
- Three LLM calls per training response (same pattern as today's `_trainer_consensus`): Seth responds, Lawrence responds, a synthesis call merges them into one voice. The synthesis uses the generation model at temperature 0.7. The voice leans toward the domain owner — the user should recognize "that's Seth's thinking" or "that's Lawrence's approach" without explicit labels.
- Mother Tree handles logistics: enrollment, progress tracking, delivery scheduling, streak calculation. These are deterministic — no LLM needed.

The Dispatcher signals training mode with `training_mode: true` in its output. The pipeline handles this as a special case — it calls Seth and Lawrence's modules directly rather than routing to a single character.

### Internal Characters

**Dispatcher — the Receptionist**
- Purpose: look at every incoming message and route it to the right character.
- Two-tier dispatch:
  1. Pattern matching (deterministic, no LLM): commands (`enroll`, `status`, `help`...), persona triggers (`ask seth`...), training commands (`next`, `go`, `practice`, answer letters), URL detection.
  2. LLM triage (only when patterns don't resolve): "should I respond?" and "who handles this?" Uses a focused routing prompt that knows each character's domain.
- Output: `{character, intent, annotation, must_respond, training_mode}`.
- Model: extraction model (Mistral Small 3.2), temperature 0.1.
- Context needs: message text, context type (DM/channel/thread), participant count, user enrollment state, active exercise state.

**Spotter — Signal Intelligence**
- Purpose: extract commercial signals from conversations. Runs in background after every response.
- Goals: identify entities (people, companies, events), actions (commitments, next steps), and sales stage from conversation content.
- Rules: extract only what's present. Never infer entities that aren't mentioned. Conservative on confidence — flag uncertain extractions rather than guessing. Run the dual-path assessment (independent verification of ci_save and capture_signal decisions).
- Model: extraction model, temperature 0.1.
- Context needs: conversation content, existing entities for deduplication hints.

**Weaver — the Relationship Builder**
- Purpose: maintain the relationship graph. Takes raw extractions from the Spotter and connects the dots.
- Goals: resolve contacts (find or create, deduplicate), link people to companies, track events, manage opportunity stages.
- Rules: prefer matching existing entities over creating duplicates. When uncertain about a match, flag it rather than merge. Maintain referential integrity.
- No LLM needed — this is data processing logic (fuzzy matching, graph operations). If an LLM call becomes necessary for disambiguation, use extraction model at temperature 0.1.
- Context needs: Spotter's raw extractions, existing entity graph from database.

**Archivist — the Knowledge Gate**
- Purpose: decide what enters the central intelligence and ensure quality.
- Goals: process ci_save actions from conversations, run the ingestion pipeline (foundation + narrative extraction), enforce quality control.
- Quality control pipeline (for narrative insights):
  1. Field validation (schema, required fields)
  2. Three-model confidence scoring (Devstral 2 123B, Llama 3.3 70B, Gemma 3 27B)
  3. Auto-accept >= 0.7, auto-reject <= 0.4, flag if spread > 0.3
  4. Haiku triage for flagged items
  5. Sonnet arbitration for genuinely ambiguous cases
- Rules: never lower the quality bar. Rejected content stays rejected. The Archivist protects the integrity of the knowledge base.
- Model: varies by pipeline stage (extraction model for parsing, scoring models for quality, Haiku/Sonnet for triage/arbitration).
- Context needs: content to evaluate, existing foundation data for grounding narrative extraction.

**Reminder — the Nudger**
- Purpose: re-enter stale signal threads with contextual follow-ups.
- Goals: check in naturally, reference what was discussed, ask for updates. Brief, warm, Dutch-direct.
- Rules: never re-summarize the whole thread. Build on what was said. If someone mentioned a date, respect it. If no timing was mentioned, suggest a default.
- Model: generation model, temperature 0.3.
- Context needs: thread history, signal context, reminder reason.

## Pipeline Flow

```
Message arrives
    │
    ▼
Dispatcher ── pattern match (deterministic)
           ── LLM triage if unresolved
    │
    │ routing decision
    ▼
Selected Character (Mother Tree / Seth / Lawrence / silent)
    │ own prompt, own model, own rules
    │
    │ response + actions
    ▼
Spotter ── background, always runs
    │ raw entities, actions, stage
    ▼
Weaver ── resolves and links entities
    │ structured relationships
    ▼
Archivist ── quality gate, writes to CI
```

Training mode variant:
```
Dispatcher recognizes training intent
    │
    ▼
Seth + Lawrence co-respond
    │ domain owner leads, synthesis merges
    ▼
Mother Tree handles logistics
    (enrollment, progress, scheduling — deterministic)
```

## Module Structure

```
jobs/bot/characters/
    __init__.py
    base.py            # shared interface, formatting rules, no-hallucination rules
    mother_tree.py
    seth.py
    lawrence.py
    dispatcher.py
    spotter.py
    weaver.py
    archivist.py
    reminder.py
```

Each module contains:
- `IDENTITY` — who the character is (system prompt preamble)
- `GOALS` — what the character tries to achieve
- `RULES` — what the character must and must never do
- `build_prompt(context)` — assembles the full prompt from identity + goals + rules + context
- `MODEL` and `TEMPERATURE` — defaults from `base.py` (generation model, 0.7), overridden only where needed (Dispatcher: extraction model, 0.1; Spotter: extraction model, 0.1; Reminder: generation model, 0.3)
- `respond(question, history, context)` — entry point, returns response dict

Shared utilities in `base.py`:
- Slack formatting rules and post-processing
- No-hallucination rules (each character includes these)
- Memory windowing
- Action/content marker handling
- Sanitization of user input

## What Changes

| Today | After |
|---|---|
| One mega-prompt in `ask.py` (400+ lines) | Eight focused prompts, each < 100 lines |
| `detect()` + `triage()` as separate pipeline stages | `Dispatcher` as single routing decision |
| Monolithic `extract_signal()` | Spotter → Weaver → Archivist chain |
| Personas as 3-line entries in a dict | Full character modules with rich identity |
| Training as separate flow in `training_dm.py` | Seth + Lawrence co-training mode |
| One `ask_with_history()` assembling franken-prompts | Each character builds its own prompt |

## What Stays the Same

- Per-channel locking for message serialization
- Thinking indicator (reaction in channels, message in DMs/threads)
- Memory persistence (DM, channel, thread stores)
- Hasura GraphQL data layer
- Model selection policy (open source first, no OpenAI)
- Ingestion sources and content fetching
- Exercise scoring (deterministic, no LLM)
- Slack bot initialization and event routing

## Implementation Order

**Phase 1 — Foundation + Channel Conversation (biggest pain point)**
1. Create `characters/` module with `base.py` (shared rules, interface)
2. Build `dispatcher.py` (refactor detect + triage into single routing module)
3. Build `mother_tree.py` (focused identity, extracted from mega-prompt)
4. Wire `pipeline.py` to use Dispatcher → Mother Tree for non-persona, non-training messages
5. Add tests, smoke-test in Slack

**Phase 2 — Persona Voice**
6. Build `seth.py` with rich, standalone identity
7. Build `lawrence.py` with rich, standalone identity
8. Refactor training mode to use Seth + Lawrence co-response
9. Wire Dispatcher to route persona requests to the right module
10. Add LLM-assessed persona quality tests

**Phase 3 — Background Intelligence Chain**
11. Build `spotter.py` (extract from current `extraction.py`)
12. Build `weaver.py` (extract from current `entities.py` + entity processing)
13. Build `archivist.py` (extract from ingestion pipeline + ci_save handling)
14. Wire the Spotter → Weaver → Archivist chain
15. Add tests for each link in the chain

**Phase 4 — Cleanup**
16. Build `reminder.py` (extract from `thread_reminders.py`)
17. Remove old mega-prompt, old triage.py, old monolithic code
18. Add LLM-assessed baseline tests for each character
19. Update documentation

Each phase is independently deployable. Phase 1 alone fixes channel conversation. Phase 2 fixes persona voice. Phases 3–4 improve debuggability and maintainability.
