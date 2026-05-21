# DM Flow Redesign — Conversational by Default

## What this is

A redesign of the Mother Tree DM experience. Currently, DMs are command-routed: the bot pattern-matches keywords and rejects everything else. This redesign makes DMs conversational by default — Mother Tree answers from the central intelligence, maintains conversation history, and handles training exercises as a lightweight overlay.

## The problem

1. Follow-up questions fail. "Can you give me links to those talks?" gets routed to the training handler because it doesn't match a command keyword.
2. Mother Tree fabricates URLs and references when it doesn't know something, instead of saying so.
3. No conversation memory — each message is stateless.
4. Commands and conversation are tangled in the same parsing logic.

## Design principles

- **Conversation is the default.** Everything that isn't a command or an exercise answer goes to the central intelligence.
- **Commands are explicit keywords.** A small set of unambiguous words: `enroll`, `status`, `stats`, `help` (global), plus `next`, `go`, `practice` (training-context only — require enrollment). Plus `/mothertree ...` always works.
- **Personas work in DMs.** `ask seth ...`, `ask lawrence ...`, `ask trainer ...` are detected as a pattern before the LLM call and route to the persona with conversation history. No `/mothertree` prefix needed.
- **Mother Tree doesn't fabricate.** If it doesn't know something, it says so and asks the user for a link.
- **Mother Tree doesn't fetch on its own.** External references are user-initiated. Mother Tree asks, the user provides.
- **History persists.** One DM conversation per user, maintained across sessions.

## Message pipeline

Every DM goes through these steps in order:

```
DM received
    │
    ├─ Global command? (enroll/status/stats/help, or /mothertree ...)
    │   → Execute command. Done.
    │
    ├─ Training command? (next/go/practice) + user is enrolled?
    │   → Execute training command. Done.
    │   (Unenrolled user typing "next" falls through to conversation.)
    │
    ├─ Persona invocation? ("ask seth ...", "ask lawrence ...", "ask trainer ...")
    │   → Route to persona with conversation history + no-hallucination rules.
    │   → Done.
    │
    ├─ Active exercise + answer? (A/B/C)
    │   → Score, feedback, progress. Done.
    │
    ├─ Active exercise + not an answer?
    │   → Answer from CI with conversation history.
    │   → "By the way, you still have a question waiting — reply A, B, or C when ready."
    │   → Done.
    │
    ├─ Pending CI save? (user replied after "Want me to save this to the CI?")
    │   → Detect "yes"/"no"/"y"/"n" deterministically.
    │   → If yes: run content pipeline. If no: acknowledge.
    │   → Clear pending flag. Continue conversation.
    │
    ├─ URL in message?
    │   → Fetch + parse content. If fetch fails: "I couldn't reach that URL —
    │     it might be behind a login or unavailable."
    │   → Add to conversation context.
    │   → Set pending_ci_save flag.
    │   → "Got it. Want me to save this to the central intelligence too?"
    │   → Continue conversation grounded in that content.
    │
    └─ Everything else
        → Route to central intelligence with full DM conversation history.
        → Never fabricate URLs or references.
        → If asked about something unknown, ask for a link.
```

No modes. No prefixes needed for conversation. Commands are exact keywords that can't be confused with natural language during exercises.

## Conversation history

One persistent DM conversation record per user, stored in the `conversations` table:

```
stage: -1 (freeform DM, not a training stage)
state: "active" (always active, never completes)
messages: JSONB array of the full DM history
exercise_id: NULL (not tied to an exercise)
pending_ci_save: tracked in conversation messages as a flag (see URL handling)
```

The freeform DM conversation is keyed by `slack_user_id`, not by `enrollment.id`. This allows unenrolled users to have conversations — enrollment is only required for training commands (`next`, `go`, `practice`). The `user_id` foreign key in the conversations table is nullable for stage -1 records; a `slack_user_id TEXT` column is added for DM conversation lookup.

Each message entry uses `content` (matching LLM API convention):
```json
{"role": "user", "content": "...", "ts": "2026-03-21T20:00:00Z"}
{"role": "assistant", "content": "...", "ts": "2026-03-21T20:00:01Z"}
{"role": "system", "content": "Content from https://...: [parsed text]", "ts": "..."}
```

When calling the LLM, the conversation history is passed as the messages array. Follow-ups work naturally.

A user can have both:
- One freeform DM conversation (persistent, stage -1)
- Zero or one active training exercise (stage 0-4, waiting_response)

Both coexist. The pipeline decides which one handles each message.

**Important:** `cancel_stale_conversations` must exclude stage -1 records. The freeform DM conversation is never cancelled.

No compaction or reset for now — build that later when histories get long. Practical limit: Mistral Small 3.2 has a 128K context window. Implement compaction when messages exceed 200 entries.

### LLM model for freeform DM

Freeform DM conversations use the generation model (`GENERATION_MODEL` — currently Qwen 3 235B on Scaleway) via a new `chat_conversation()` function in `llm.py`: multi-turn messages, temperature 0.7, max_tokens 2000. This differs from `llm.chat()` (extraction model, 300 tokens, 0.3 temp) which is for quick signal thread replies.

CI context (foundation + narrative data) is fetched via `fetch_context()` from `ask.py` and prepended as a system message, same as the current `ask()` flow. Every freeform DM call includes both CI context and conversation history.

## LLM system instruction

For freeform DM conversation, the LLM receives:

```
You are Mother Tree, the central intelligence for a consultative sales team.
You answer from what you know — the foundation (change, worldview, personas,
competitors) and narrative (insights, case studies) in the central intelligence.

RULES:
- Never fabricate URLs, links, schedules, or external references.
- If the user asks about something you don't have (an event schedule, a
  specific article, a competitor's pricing page), say so and ask them to
  share a link if they'd like you to work with it.
- When the user shares a URL, you will receive its content. Ask if they
  want to save it to the central intelligence.
- You have the conversation history. Use it. Don't ask for context that
  was already given.
```

When the user explicitly invokes a persona (`ask seth ...`), the persona's system prompt takes over — but with the no-hallucination rules appended.

## URL handling

When Mother Tree detects a URL in a DM message:

1. **Fetch and parse** — reuse the existing URL fetching from `enrich.py` (skips LinkedIn, extracts text content). If the fetch fails, respond: "I couldn't reach that URL — it might be behind a login or unavailable." Continue the conversation without the content.
2. **Add to conversation context** — the parsed content is appended to the conversation messages:
   ```json
   {"role": "system", "content": "Content from https://...: [parsed text]", "ts": "..."}
   ```
3. **Ask about CI** — "Got it. Want me to save this to the central intelligence too?" Set a `pending_ci_save` flag in the conversation messages:
   ```json
   {"role": "system", "content": "pending_ci_save", "url": "https://...", "ts": "..."}
   ```
4. **Detect response deterministically** — the next message is checked for "yes"/"y"/"no"/"n" (case-insensitive) before anything else in the pipeline. If matched, handle the CI save and clear the flag. If not matched (user moved on to a different topic), clear the flag silently and process the message normally.
5. **If yes** — run through the content pipeline (extraction → scoring → insert). Respond: "Saved to the central intelligence."
6. **If no** — content lives only in the conversation context. Respond: "OK, keeping it in our conversation only."

The conversation continues grounded in the fetched content either way.

Mother Tree does not fetch external content on its own initiative. If it doesn't have what the user asks about, it says so and asks the user to share a link. The user decides what to feed it.

## Command handling

Commands are recognized by exact keyword match, case-insensitive. Two categories:

**Global commands** (work for everyone):

| Keyword | Action |
|---------|--------|
| `enroll <role>` | Enroll in training |
| `status` | Show enrollment status |
| `progress` | Team overview |
| `stats` | CI database counts |
| `help` | Show available commands |

**Training commands** (require enrollment, otherwise fall through to conversation):

| Keyword | Action |
|---------|--------|
| `next` | Advance to next training chapter |
| `go` | Start exercise questions |
| `practice [topic]` | Practice exercises |

**Persona invocation** (detected as pattern, not exact keyword):

| Pattern | Action |
|---------|--------|
| `ask seth ...` | Route to Seth Godin persona with conversation history |
| `ask lawrence ...` | Route to Lawrence Miller persona with conversation history |
| `ask trainer ...` | Route to trainer consensus with conversation history |
| `ask onboarding` | Route to onboarding instruction |

`/mothertree <command>` also works in DMs — the prefix is stripped and routed the same way.

Commands and persona patterns are processed before any LLM call. They are fast, deterministic, and unambiguous.

## Training exercise overlay

When a training exercise is active (conversation with state `waiting_response`):

- **A, B, or C** → score the answer, send feedback, progress as before
- **Anything else** → answer from CI with conversation history, then nudge: "By the way, you still have a question waiting — reply A, B, or C when ready."

The exercise is paused, not a cage. The user can ask questions, explore, and come back to the exercise when ready.

## What changes from current implementation

**Remove:**
- Command-prefix routing in `handle_dm` (the `subcmd == "ask"`, etc. block)
- The "No active exercise" dead-end message for unrecognized input
- Stateless `ask` calls for DM conversations

**Keep:**
- Slash command handler (`/mothertree`) — unchanged, works in channels and DMs
- Bare keyword detection for commands
- Training exercise flow (deliver, score, progress)
- Signal capture in channels

**Add:**
- Freeform DM conversation record (stage -1, persistent per user)
- Conversation-aware LLM calls (pass history as context)
- Mid-exercise question handling (answer from CI, nudge back)
- URL detection, fetch, ingest into conversation, optional CI save
- No-hallucination system instruction on all DM LLM calls

## Files affected

- `jobs/bot/bot.py` — rewrite `handle_dm` pipeline
- `jobs/bot/training_dm.py` — add URL detection, update `parse_dm_command` for conversation fallthrough
- `jobs/mothertree/hasura.py` — add `get_or_create_dm_conversation`, `append_dm_message`
- `jobs/mothertree/ask.py` — add conversation-aware variant that accepts message history
- `jobs/mothertree/llm.py` — add `chat_conversation()` for multi-turn DM with generation model
- `deploy/database/schema.sql` — add `slack_user_id` column to conversations for DM lookup without enrollment
