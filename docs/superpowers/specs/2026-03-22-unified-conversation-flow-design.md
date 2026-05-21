# Unified Conversation Flow

## What this is

A redesign that makes Mother Tree conversational everywhere — DMs, channels, threads. One pipeline handles all contexts. The only variable is participant count: a DM is a channel with one participant.

This supersedes the channel-specific signal capture flow in `bot.py` and generalizes the DM pipeline from the [DM flow redesign](2026-03-21-dm-flow-redesign.md).

## The problem

1. DMs are conversational (new pipeline). Channels use a separate codepath: intent classification → signal capture or one-shot answer.
2. A question in #signals gets routed to trainer consensus and generates an exercise instead of answering the question.
3. Mother Tree ignores all channels except #signals. It should be a participant wherever it's invited.
4. Signal capture and conversation are separate actions — they should be one.
5. Commands, training delivery, and persona switches break the conversational illusion. They produce mechanical responses in a different voice.
6. Confirmations (CI save, signal capture) use rigid yes/no detection in what should be a natural conversation.

## Design principles

- **One pipeline.** Every message enters the same flow regardless of context.
- **DM is a channel with one participant.** No DM-specific codepath.
- **Everything flows through the conversation engine.** Commands, training, personas, URLs — the detect phase handles the action, the conversation engine handles the response. Nothing bypasses the engine.
- **Conversation is the enrichment.** Mother Tree responds naturally. Structured data (entities, actions, qualification) is extracted from the conversation afterward.
- **Two memory layers.** Short-term (recent messages) and long-term (central intelligence).
- **Triage before conversation.** A cheap LLM call decides whether to respond and whether to capture a signal — but only for messages without a clear pattern match.
- **Never silent in a DM.** Triage can return "silent" in group channels. Never when there's one participant.
- **Everything persists to memory.** Commands, exercises, persona conversations — all part of the same conversation history.
- **Training is private.** Training commands, exercise answers, and exercise delivery only fire in DMs (participant count 1). In channels, words like "next", "go", and "A" are normal conversation.

## Message pipeline

Two phases: detect (fast, deterministic) and converse (LLM). Detect identifies what's happening and executes side effects. The conversation engine always produces the response.

```
Message received (any context)
    │
    ├─ Skip bot's own messages, empty messages
    │
    ├─ Sanitize: escape [ACTION:*] patterns in user input
    │
    ╔══ DETECT (fast, no LLM) ══════════════════════════════════════╗
    ║                                                               ║
    ║  @mention or /mothertree?  → strip prefix, set must_respond   ║
    ║  Command keyword?          → execute side effect, annotate    ║
    ║  Persona pattern?          → set persona                      ║
    ║  DM-only patterns:                                            ║
    ║    Training command?       → execute side effect, annotate    ║
    ║    Exercise answer?        → score answer, annotate result    ║
    ║  URL in message?           → fetch content (parallel), annot. ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    │
    ├─ Pattern matched or must_respond?
    │   → skip triage, go straight to conversation engine
    │
    └─ No pattern matched?
        → triage (cheap LLM)
            ├─ respond → conversation engine
            ├─ respond + capture → conversation engine (signal flag set)
            └─ silent → persist to memory only (never in DM)
    │
    ╔══ CONVERSE (LLM) ════════════════════════════════════════════╗
    ║                                                              ║
    ║  1. Build context: system prompt + CI + short-term memory    ║
    ║     + detect annotations                                     ║
    ║  2. Select model (see Model Selection below)                 ║
    ║  3. Call LLM                                                 ║
    ║  4. Extract action markers, content markers                  ║
    ║  5. Fix Slack formatting                                     ║
    ║  6. Persist exchange to memory                               ║
    ║  7. Send response                                            ║
    ║  8. Background: signal extraction if flagged                 ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
```

### Detect phase scoping

Training commands and exercise answers are **DM-only** (participant count 1):

| Pattern | Scope | Reason |
|---------|-------|--------|
| `next`, `go`, `practice` | DM only | Training is private. "next" in a channel is normal conversation. |
| `A`, `B`, `C` (bare letter) | DM only | Exercise answers are private. "A" in a channel is normal conversation. |
| `enroll`, `status`, `stats`, `help`, `progress` | All contexts | Commands are unambiguous. |
| `ask seth/lawrence/trainer` | All contexts | Persona invocation is explicit. |
| URL detection | All contexts | URLs are fetched everywhere. |

In channels, `next`/`go`/`practice`/`A`/`B`/`C` are not matched by detect and flow through to triage as normal conversation.

### Detect annotations

The detect phase produces context that the conversation engine uses to craft its response. The detect phase never responds directly to the user.

| Pattern | Side effect | Annotation |
|---------|-------------|------------|
| `enroll hunter` | Create enrollment record | `{"type": "enrolled", "role": "hunter", "name": "Jurg"}` |
| `status` | Fetch enrollment data | `{"type": "status", "role": "hunter", "stage": 0, "chapter": 2, "streak": 3}` |
| `stats` | Fetch CI counts | `{"type": "stats", "data": {"insights": 42, "signals": 15, ...}}` |
| `help` | None | `{"type": "help"}` |
| `progress` | Fetch team data | `{"type": "progress", "enrollments": [...]}` |
| `next` (DM) | Deliver next chapter | `{"type": "training_delivered", "chapter": "worldview", "content": "..."}` |
| `next` (DM, citizen) | Generate inspiration | `{"type": "citizen_inspiration", "content": "..."}` |
| `go` (DM) | Start exercise | `{"type": "exercise_started", "question": "...", "options": [...]}` |
| `go` (DM, no pending) | None | `{"type": "error", "message": "no pending instruction"}` |
| `practice` (DM) | Deliver practice | `{"type": "practice_delivered", "topic": "...", "content": "..."}` |
| `practice` (DM, bad topic) | None | `{"type": "error", "message": "unknown topic"}` |
| `A`/`B`/`C` (DM, active ex.) | Score answer | `{"type": "answer_scored", "correct": true, "feedback": "...", "progress": {...}}` |
| `A`/`B`/`C` (DM, no exercise) | None | No annotation — falls through to conversation |
| `ask seth ...` | None | Sets persona to "seth" |
| `ask lawrence ...` | None | Sets persona to "lawrence" |
| `ask trainer ...` | None | Sets persona to "trainer" (triggers trainer consensus) |
| URL detected | Fetch + parse content | `{"type": "url_content", "url": "...", "content": "..."}` |
| URL fetch failed | None | `{"type": "url_failed", "url": "...", "reason": "unreachable"}` |

The conversation engine's system prompt includes instructions for each annotation type. For example, when it receives an `enrolled` annotation, it knows to welcome the user warmly. When it receives `answer_scored`, it wraps the feedback conversationally.

**Active exercise nudge:** When a DM user has an active exercise but sends a non-answer message, the detect phase annotates `{"type": "exercise_pending", "question_num": 2, "total": 5}`. The conversation engine responds to the user's message normally, then includes a natural nudge: "By the way, question 2 is still waiting whenever you're ready."

**Citizen inspiration:** When a citizen says `next`, `go`, or `practice`, the detect phase generates inspiration instead of training. Uses `ask_with_history()` with a prompt that varies between change statements, worldview insights, real stories, and reflective questions. The annotation type is `citizen_inspiration`.

### How this changes command responses

Before: `status` → `*Jurg* — hunter\nStage 0, Chapter 2\nActive: yes`

After: `status` → detect fetches the data → conversation engine: "You're in Stage 0, Chapter 2 — the worldview. Three-day streak going. Want to keep going?"

Before: `next` → formatted exercise block drops into chat

After: `next` → detect delivers the chapter → conversation engine wraps it: "Here's the next piece. This one's about how your audience already sees the world..." followed by the content, then a natural transition to the exercise.

### How this changes persona handling

The active persona persists in conversation history. When the user says `ask seth ...`, the conversation engine switches to Seth's voice. If the user follows up naturally ("what would Lawrence think?"), the conversation engine sees the persona context in history and can switch without an explicit `ask lawrence` prefix.

**Trainer consensus:** `ask trainer ...` invokes the trainer consensus flow — a multi-step LLM process (Seth perspective, Lawrence perspective, synthesis). This stays as-is: the detect phase sets persona to "trainer", and `ask_with_history` routes to `_trainer_consensus()` which produces the synthesized response. The conversation engine wraps the result. The three-call LLM flow is preserved because it produces meaningfully better training content than a single call.

**Persona in channels:** In group channels, Mother Tree introduces persona perspectives in third person ("From Seth's perspective..." or "Lawrence would say...") rather than fully embodying the voice. In DMs, full embodiment is natural.

The conversation engine's system prompt includes:

```
PERSONA AWARENESS:
You can draw on Seth Godin or Lawrence Miller perspectives when asked.
The user may invoke them explicitly ("ask seth ...") or naturally
("what would Lawrence say?", "give me Seth's take"). When a persona
is active in the conversation, maintain it until the user switches or
returns to general conversation. You are still Mother Tree — the
personas are perspectives you can offer, not separate people.
In group channels, present persona perspectives in third person.
In DMs, you can fully embody the voice.
```

### How this changes confirmations

No more deterministic yes/no detection. Pending states (CI save offers, low-confidence signal capture) become part of the conversation context. The conversation engine handles nuanced responses naturally.

Before:
- Mother Tree: "Want me to save this to the CI?"
- User: "Yeah, and she also mentioned Kubernetes" → deterministic matcher fails → flag cleared silently

After:
- Mother Tree: "Want me to save this to the CI?"
- User: "Yeah, and she also mentioned Kubernetes" → conversation engine understands this as confirmation + elaboration → responds conversationally → background extraction captures both

The conversation engine's response includes action markers when it decides to execute something:

```
When you decide to save content to the central intelligence (because the
user confirmed, or because you offered and they agreed), include
[ACTION:ci_save] in your response. When you decide a signal should be
captured, include [ACTION:capture_signal]. These markers are stripped
before sending to the user and trigger background processing.
```

### How this changes URL handling in channels

URLs no longer get special treatment in the detect phase based on context. The detect phase fetches the content and annotates it. Multiple URLs are fetched in parallel (capped at 3 per message). The conversation engine decides how to respond based on context:

- In a DM: "Got it. Want me to save this to the central intelligence?"
- In a channel where someone shared a link as part of discussion: participates in the discussion using the content, doesn't presume to save it
- In a channel where someone shared intelligence with a link: responds conversationally, offers to capture the signal (which includes saving to CI)

The conversation engine makes this judgment because it has the short-term memory — it knows whether the link is part of an intelligence share or a casual discussion.

## Triage

A cheap, fast LLM call. Runs only when the detect phase found no pattern match and must_respond is not set. Decides whether Mother Tree should respond and whether there's signal potential.

**Input:**
- Message text
- Participant count (1 = DM, >1 = channel)
- Last ~5 messages for minimal context

**Output:**
```json
{
  "respond": true,
  "signal": { "capture": true, "confidence": 0.85 },
  "reason": "sharing prospect intelligence"
}
```

**Rules in the triage prompt:**
- Participant count 1 → `respond` is always true
- Respond when: direct question, request for help, Mother Tree has something useful to add
- Stay silent when: people talking to each other, small talk, reactions
- Signal capture: intelligence about a prospect, client, market, competitor, or event

**Signal confidence thresholds:**
- High (≥0.8): conversation engine captures alongside its response
- Low (<0.8): conversation engine asks naturally in its response

**Model:** Extraction model (Mistral Small 3.2 on Scaleway).

**Triage runs in parallel with `fetch_context()`.** They have no dependency — triage decides whether to respond while CI context is fetched for the conversation engine. Saves 0.5-1.5s on channel messages.

## Memory model

Two layers.

### Short-term memory

Recent messages in the LLM context window. Everything persists — commands, exercises, persona conversations, URLs. All part of one conversation stream.

| Context | Scope | Window |
|---------|-------|--------|
| DM | Per user | Configurable, default ~200 messages |
| Channel top-level | Per channel | Configurable, default ~200 top-level messages (excludes thread replies) |
| Thread | Per thread | Configurable, default ~100 messages (oldest summarized when exceeded) |

**Configurable window:** The message window is tied to the generation model's context size. Default: `min(200, context_window_tokens // 200)`. If the generation model changes (e.g., from 131K to 32K context), the window auto-adjusts.

**Thread memory cap:** When a thread exceeds ~100 messages, the oldest half is summarized into a single system message and the originals are removed. The summary preserves who said what, key decisions, and open questions.

**URL content in stored memory:** URL content annotations are capped at ~1,000 chars (250 tokens) when persisted to memory. The full content (up to 3,000 chars) is only in the annotation at conversation time, not in historical context.

When Mother Tree is in a thread, it sees the thread's history. It can reference channel-level memory for broader context.

When triage returns "silent," the user's message still persists to channel memory. Mother Tree remembers what was said even when it doesn't respond.

### Long-term memory

The central intelligence. Foundation (change, worldview, personas, competitors) and narrative (insights, case studies). Fetched via `fetch_context()` and included as system context in every LLM call.

**Caching:** `fetch_context()` results are cached with a 60-120 second TTL. CI data doesn't change mid-conversation.

For specific references: Mother Tree checks short-term memory first. If it finds something relevant in the CI that wasn't in the recent conversation, it confirms before using it.

### Storage

- **DM conversations:** existing `conversations` table (stage -1 records), keyed by `slack_user_id`
- **Channel memory:** new `channel_memory` table — `channel_id`, `messages` (JSONB), capped at ~200
- **Thread memory:** new `thread_memory` table — `thread_ts`, `channel_id`, `messages` (JSONB), capped at ~100 with summarization

### What the LLM sees

1. System prompt (persona or default + no-hallucination rules + CI context + detect annotations)
2. Short-term memory for the current scope
3. The new message

## Conversation engine

One function handles all of Mother Tree's responses. Same code for DM, channel, and thread. Same code for commands, training, personas, and freeform conversation.

**Input:**
- Message text
- Memory context (short-term memory for this scope)
- Detect annotations (command data, persona, exercise result, URL content — or empty)
- Signal flag from triage
- Participant count
- User name

**Steps:**
1. Fetch CI context via `fetch_context()` (cached, parallel with triage when applicable)
2. Build LLM messages: system prompt + CI + detect annotations + short-term memory + new message
3. Select model (see model selection)
4. Call LLM
5. Extract action markers (`[ACTION:ci_save]`, `[ACTION:capture_signal]`) and content markers (`[CONTENT:training]`) from response
6. Fix Slack formatting
7. Persist the full exchange to the appropriate memory store (including detect annotations as system messages)
8. Send response to user
9. Execute actions: CI save, signal capture, entity extraction — all background, non-blocking

### Model selection

Not every response needs the full generation model. The conversation engine selects the model based on annotation type:

| Annotation type | Model | Reason |
|----------------|-------|--------|
| `status`, `stats`, `help`, `progress` | Extraction model (fast, 0.5-1.5s) | Short conversational wrapper around structured data |
| `enrolled` | Extraction model | Welcome message is formulaic |
| `answer_scored` | Extraction model | Feedback wrapper is short |
| `exercise_started` | Extraction model | Question introduction is short |
| `training_delivered`, `citizen_inspiration` | Extraction model | Conversational intro is short; bulk content is injected via `[CONTENT:training]` |
| `error` | Extraction model | Error responses are short |
| Freeform conversation | Generation model (2-5s) | Needs full context understanding |
| Persona conversation | Generation model | Needs persona embodiment |
| Signal flag set | Generation model | Needs nuanced response + action judgment |
| URL content | Generation model | Needs to interpret and discuss content |

This keeps commands responsive (~1-2s total) while reserving the full model for conversations that need it.

### System prompt

`DM_SYSTEM_PROMPT` + `SELF_KNOWLEDGE` + `NO_HALLUCINATION_RULES`, extended with:

```
CONTEXT AWARENESS:
You may receive annotations from the system — command results, exercise
scores, URL content, enrollment data. Weave these into your response
naturally. You are a person sharing information, not a system displaying
output. A status check gets a warm update, not a formatted table. An
exercise gets an introduction, not a card drop.

When in a group channel, you are a participant in the conversation.
Speak when you have something useful to add. Use first names.
If multiple people are talking, track who said what.

SIGNAL THREAD BEHAVIOR:
When you are in a thread about a signal someone shared:
- Build on what was said. Don't repeat. Don't re-summarize from scratch.
- If someone answers a question, acknowledge briefly and ask the next
  one if needed.
- When different people contribute, connect their pieces.
- When the signal is complete, close actively and suggest a follow-up
  moment: "No further questions. I'll check back after KubeCon."
  Never say "if you need further assistance" — you are a participant,
  not a helpdesk.
- If someone mentions a date or timeframe, note it. If no timing is
  mentioned, suggest a default: "I'll check back in a week. Too soon?"
- Be brief, warm, Dutch-direct. No corporate filler.

PERSONA AWARENESS:
You can draw on Seth Godin or Lawrence Miller perspectives when asked.
The user may invoke them explicitly ("ask seth ...") or naturally
("what would Lawrence say?", "give me Seth's take"). When a persona
is active in the conversation, maintain it until the user switches or
returns to general conversation. You are still Mother Tree — the
personas are perspectives you can offer, not separate people.
In group channels, present persona perspectives in third person.
In DMs, you can fully embody the voice.

ACTIONS:
When you decide to save content to the central intelligence, include
[ACTION:ci_save] in your response. When you decide a signal should be
captured, include [ACTION:capture_signal]. These markers are stripped
before the user sees your response and trigger background processing.
You decide when these actions are appropriate based on the conversation —
explicit confirmation, natural agreement, or clear intent.

EXERCISE AWARENESS:
If the system tells you the user has a pending exercise question, handle
their current message normally, then add a natural nudge at the end:
"By the way, question 2 is still waiting whenever you're ready."
Don't nag. One mention per conversation turn is enough.
```

**Thread behavior:** First response to a top-level channel message goes in-channel. Follow-ups go in a thread.

## Signal extraction (background)

Runs after the conversation response is sent, triggered by triage's signal flag or an `[ACTION:capture_signal]` marker. Non-blocking.

Three things are extracted from the conversation exchange:

### 1. Entities → existing tables

- People → `contacts` (name, role, company, temperature)
- Companies → `companies`
- Events → `events` + `event_participants`

Uses existing `process_entities()`.

### 2. Actions → existing fields

- Next steps and commitments → `interactions` record (type: "slack", summary, next_action, next_action_date)
- If linked to an opportunity → `opportunities.next_action` + `next_action_date`

### 3. Qualification → existing `opportunities.stage`

Maps to the Mycorrhizal Method stages: soil → signal → reframe → diagnosis → proposal → converted.

- Known company/contact with existing opportunity: update stage if the conversation suggests progression
- New opportunity: create at the appropriate stage
- Signal record: `signals.status` tracks its own lifecycle (new → reviewed → acted_on → archived)

No new entity or action tables. The conversation feeds the existing schema.

## Preserved behaviors

These existing behaviors are preserved in the new design:

### Welcome DM on channel join

The `member_joined_channel` event handler stays. When someone joins a channel with Mother Tree and has no prior DM conversation, Mother Tree sends a welcome DM. This is outside the unified pipeline — it's an event-triggered one-time action, not a conversation response. The welcome text and enrollment prompt are unchanged.

### Stale conversation cancellation

`cancel_stale_conversations()` is called in the detect phase before training delivery (`next`, `practice`). It cancels incomplete exercises from prior sessions, same as today.

### Streak tracking

`calculate_streak()` and `update_streak()` are called in the detect phase after exercise completion. The streak count appears in the `answer_scored` annotation and the `status` annotation.

### "Thinking..." ephemeral

For slash commands (`/mothertree ask ...`), the bot sends an ephemeral "Thinking..." message before the pipeline runs. This stays — slash commands go through the pipeline but the ephemeral gives immediate feedback while the LLM responds.

## What changes in the codebase

### Modified

- **`bot.py` `handle_message`** — responds in any channel Mother Tree is invited to, not just #signals. Routes everything through the unified pipeline. Per-channel message serialization (see Concurrency).
- **`dm_pipeline.py`** — restructured into detect + triage + converse phases. Detect replaces the old classify_dm with annotations instead of early exits. Training/exercise patterns scoped to DM only. All contexts (DM, channel, thread) enter the same pipeline.
- **`dm_conversation.py` → `conversation.py`** — `handle_conversation()` takes detect annotations and memory context. Handles all response types (commands, training, freeform) through one LLM call. Parses action markers from response. Selects model based on annotation type.
- **`ask.py`** — `ask_with_history()` accepts annotations and memory context. System prompt extended with context awareness, signal thread behavior, persona awareness, exercise awareness, and action markers. `_trainer_consensus()` stays as-is for the "ask trainer" flow.
- **`hasura.py`** — new functions for channel/thread memory (get, append, cap). Thread reply lookup checks `thread_memory` first, falls back to `signal_threads` for legacy threads.
- **`reminders/thread_reminders.py`** — queries both `signal_threads` (legacy) and `thread_memory` (new) for threads due a reminder. Posts reminder via Slack, updates the corresponding table.

### Removed

- **`enrich.py`** `enrich_signal()`, `format_enrichment()`, `continue_signal_conversation()` — replaced by the conversation engine. `fetch_url_context()` and `extract_urls()` stay.
- **`intent.py`** — replaced by the triage function.
- **`bot.py`** signal-specific intent classification + enrichment flow in `handle_message`.
- **Deterministic yes/no detection** for CI save and signal confirmation — replaced by conversation engine judgment.
- **Direct command response formatting** — commands no longer format and send their own responses. They return data; the conversation engine responds.

### Added

- **Detect phase** — fast pattern matching that produces annotations instead of responses. Training/exercise patterns scoped to DM only.
- **Triage function** — cheap LLM call, returns respond/signal/silent.
- **Action marker parsing** — strips `[ACTION:*]` markers from LLM response, triggers background processing. Sanitizes user input to prevent injection.
- **Content marker parsing** — strips `[CONTENT:training]` markers and injects full training content.
- **Background signal extraction** — entities, actions, qualification from conversation exchanges. Feeds existing tables.
- **`channel_memory` table** — `channel_id`, `messages` (JSONB), capped at ~200.
- **`thread_memory` table** — `thread_ts`, `channel_id`, `messages` (JSONB), capped at ~100 with summarization, plus `remind_after` and `remind_context` for reminders.
- **Per-channel message queue** — serializes message processing per channel.
- **`fetch_context()` cache** — 60-120 second TTL.

### Unchanged

- Slash command handler (`/mothertree`) — still strips prefix and routes into the pipeline
- Training side effects (deliver, score, progress) — still executed in detect phase
- Persona definitions in `ask.py`
- Trainer consensus flow (`_trainer_consensus()`)
- CI fetch (`fetch_context()`) — now cached
- URL fetching (`fetch_url_context()`, `extract_urls()`)
- Welcome DM on channel join (`member_joined_channel`)
- Stale conversation cancellation
- Streak tracking
- CronJob-initiated training delivery (daily refresher) — delivers directly via Slack, not through the conversation pipeline

## Database changes

```sql
CREATE TABLE channel_memory (
    id SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL UNIQUE,
    channel_name TEXT,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE thread_memory (
    id SERIAL PRIMARY KEY,
    thread_ts TEXT NOT NULL UNIQUE,
    channel_id TEXT NOT NULL,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    remind_after TIMESTAMPTZ,
    remind_context TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Message format (same across all memory stores):
```json
{"role": "user", "name": "Jurg", "content": "...", "ts": "2026-03-22T10:00:00Z"}
{"role": "assistant", "content": "...", "ts": "2026-03-22T10:00:01Z"}
{"role": "system", "content": "...", "annotation": {"type": "status", ...}, "ts": "..."}
```

Detect annotations are stored as system messages in the conversation history. This means the conversation engine sees what happened (commands executed, exercises scored, URLs fetched) as part of the natural flow.

## Reliability

### Action marker reliability

The `[ACTION:ci_save]` and `[ACTION:capture_signal]` markers depend on the LLM including them consistently. Two risks: the LLM forgets a marker (action doesn't fire), or hallucinates one (unwanted action fires).

**Mitigation — dual path:** Action markers are the primary trigger, but the background signal extraction step independently assesses whether a save or capture should happen based on the conversation content. If the conversation clearly contains a confirmed save ("yeah, save that") but the LLM forgot the marker, the background step catches it. If the LLM hallucinated a marker but the conversation doesn't support it, the background step skips the action.

The background step is the safety net. The marker is the fast path. Both must agree for destructive actions (like creating an opportunity or advancing a stage). For low-risk actions (logging a signal, creating an interaction record), the marker alone is sufficient.

**Testing:** Action marker reliability must be tested across models and prompt variations before deployment. Track marker accuracy (precision and recall) during development. If reliability falls below 95%, fall back to the background assessment as the sole trigger.

### Action marker injection

Users could type `[ACTION:ci_save]` literally in a message. If stored in memory as-is, future LLM calls could be influenced by it (mild prompt injection).

**Mitigation:** Sanitize user input before storing in memory. Replace `[ACTION:` with `[action:` (lowercase) in all user messages. The parser only matches uppercase `[ACTION:*]` in LLM output. This preserves readability without matching the parser pattern.

### Training content in annotations

Training content (chapter text, exercise questions with options) can be large — up to several thousand tokens. The detect phase passes this as an annotation into the conversation engine's context.

**Approach:** Pass a summary annotation, not the full content. The detect phase stores the full training content in the memory store as a system message. The annotation sent to the conversation engine contains:

- For `training_delivered`: chapter name, chapter number, a one-line summary, and the first paragraph. The full content is in memory.
- For `exercise_started`: the question text and options. This is short enough to include in full.
- For `answer_scored`: the feedback text and progress data. Also short enough in full.

The conversation engine wraps the annotation conversationally. For training delivery, it introduces the material and the full content follows as a separate message (not LLM-generated). This keeps the LLM call efficient while preserving the conversational wrapper.

**Implementation:** The conversation engine returns a response that may include a `[CONTENT:training]` marker. The pipeline replaces this marker with the full training content before sending to the user. The user sees: conversational introduction → full content → conversational transition. One fluid message, but the bulk of the content isn't generated by the LLM.

### Silent message persistence

When triage returns "silent" in a channel, the user's message persists to channel memory. In a busy channel, this means many writes for messages Mother Tree never responds to.

**Approach — lazy persistence:** Don't write every silent message to the database immediately. Instead:

1. Keep a short in-memory buffer per channel (last ~20 messages). This is process memory, not database.
2. When Mother Tree decides to respond (triage returns respond), flush the buffer to the database along with Mother Tree's response. This ensures the conversation engine has context for its response.
3. If the buffer fills without Mother Tree responding, flush to the database to avoid data loss on process restart.
4. On process startup, backfill the buffer from the Slack API (last ~20 messages per channel) so Mother Tree doesn't lose context after a restart.

**Fallback for backfill failure:** If the Slack API is unavailable at startup (rate limit, network issue), fall back to the last ~20 messages from `channel_memory` in the database. Stale is better than empty.

This reduces database writes dramatically in busy channels while preserving the context Mother Tree needs when it does speak. The ~200 message cap in `channel_memory` applies to what's in the database; the in-memory buffer is the working set.

### Detect side effects and conversation engine failure

The detect phase executes side effects (enroll user, score exercise, advance enrollment) before the conversation engine runs. If the conversation engine then fails (LLM timeout, API error, crash), the side effect has already happened but the user gets no response.

**Approach — fallback responses:**

Every detect annotation type has a static fallback response that fires if the conversation engine fails:

| Annotation type | Fallback response |
|----------------|-------------------|
| `enrolled` | "Welcome to Mother Tree, {name}. Enrolled as {role}." |
| `status` | "Stage {stage}, Chapter {chapter}. Streak: {streak} days." |
| `answer_scored` | "{feedback}" (the raw feedback from scoring) |
| `training_delivered` | The formatted training content (current format) |
| `exercise_started` | The formatted question (current format) |
| No annotation (freeform) | "Sorry, I'm having trouble thinking right now. Try again in a moment." |

These fallback responses are the mechanical, pre-conversation-engine format. They're not ideal — they break the conversational illusion — but they ensure the user always gets a response when a side effect has occurred. The user sees something functional rather than silence after their enrollment went through or their answer was scored.

**Retry safety:** All detect side effects are idempotent. Enrolling an already-enrolled user returns the existing enrollment. Scoring an already-scored answer returns the existing score. If the pipeline retries after a conversation engine failure, the detect phase safely re-runs without duplicate side effects.

### Concurrency

Channel messages are serialized per channel. When two users post in the same channel within milliseconds, the second message waits for the first to complete (through the full detect → triage → converse pipeline). This prevents:

- Race conditions on `channel_memory` writes
- Stale context in concurrent LLM calls (message B sees message A's response)
- Out-of-order responses in Slack

Implementation: a per-channel asyncio lock or queue. DMs are naturally serialized per user. Different channels process in parallel.

### Rate limiting

In busy periods, Mother Tree may be in multiple active channels simultaneously. Each responded message triggers at least one LLM call (triage or conversation engine, sometimes both).

**Scaleway budget:** At 50 messages/minute across 5 channels, with ~50% response rate, that's ~25 triage calls + ~25 conversation engine calls = ~50 LLM calls/minute. Scaleway's standard tier allows ~60 requests/minute per endpoint.

**Mitigations:**
- Triage's "silent" threshold should be conservative in channels. If Mother Tree responds to more than ~30% of channel messages, it's both too chatty and too expensive.
- Triage and `fetch_context()` run in parallel, reducing sequential calls.
- The extraction model handles simple annotations, reducing generation model load.
- If rate limited (429 from Scaleway), fall back to the static fallback response for annotated messages, or stay silent for unannotated ones. Log the rate limit event.

**Slack posting limits:** ~1 message/second/channel. The per-channel serialization naturally throttles this. If the conversation engine responds faster than 1/second (unlikely given LLM latency), add a minimum delay between posts.

## Migration

### Phase 1 — Database preparation (before deploy, non-breaking)

1. Create `channel_memory` table with `updated_at` trigger.
2. Create `thread_memory` table with `updated_at` trigger, including `remind_after` and `remind_context` columns.
3. Track both tables in Hasura. Set permissions for the `mothertree` role.
4. Update `deploy/database/schema.sql` for documentation.

### Phase 2 — Code changes

1. Restructure `dm_pipeline.py` into detect + triage + converse phases.
2. Rename `dm_conversation.py` to `conversation.py`, extend with annotation handling, model selection, and action marker parsing.
3. Rewrite `bot.py` `handle_message` to route all channels through the unified pipeline. Add per-channel serialization.
4. Add `channel_memory` and `thread_memory` CRUD functions to `hasura.py`.
5. Add `signal_threads` fallback lookup in the thread reply path (compatibility shim).
6. Add triage function.
7. Add background signal extraction.
8. Add Slack API backfill on startup for in-memory channel buffers.
9. Update `thread_reminders.py` to query both `signal_threads` and `thread_memory`.
10. Extend `ask_with_history` to accept annotations and build the extended system prompt.
11. Add `fetch_context()` caching.
12. Remove: `intent.py`, `enrich_signal()`, `format_enrichment()`, `continue_signal_conversation()`, deterministic yes/no detection.

### Phase 3 — Deploy

1. Push new image via CI. Flux picks up the tag change.
2. Single switchover — old pod stops, new pod starts.
3. In-flight DM conversations: Slack queues messages during the ~5-30 second gap. DM state is in the database, survives restart.
4. In-flight channel conversations: in-memory buffer is lost. Slack API backfill on startup recovers context.

### Rollback

Rollback to the previous image is clean:
- `conversations` table format is backwards-compatible (extra fields ignored by old code).
- `channel_memory` and `thread_memory` are ignored by old code.
- `signal_threads` table is unchanged.
- Only data loss: new `thread_memory` records and `channel_memory` records created during the new pipeline's lifetime. These represent new functionality the old code never had.

### Legacy signal_threads compatibility

Existing `signal_threads` records stay in the database. The reminder CronJob continues to fire for these threads. When a user replies to a legacy signal thread:

1. The unified pipeline checks `thread_memory` first (no record found).
2. Falls back to `signal_threads` and loads the stored messages.
3. Processes the reply through the conversation engine with that history.
4. Stores the response in a new `thread_memory` record (migrating the thread forward).

After this first reply, the thread lives in `thread_memory` and future replies use the unified pipeline natively. The `signal_threads` record becomes read-only history.

New signal threads (created by the unified pipeline) go into `thread_memory` only. The `signal_threads` table becomes a legacy/read-only table over time.
