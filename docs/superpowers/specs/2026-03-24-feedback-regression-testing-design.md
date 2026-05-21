# Feedback-Driven Regression Testing

## Problem

The test suite tests plumbing (code flows correctly) but not quality (outputs are acceptable). When prompts change, characters evolve, or models update, there is no way to detect whether Mother Tree's responses got better or worse. The only signal is manual observation in Slack.

## Solution

A feedback loop that captures human quality judgments on real interactions, building a labeled test corpus over time. Two test modes use this corpus: fast structural checks (CI-safe) and deep LLM-judged quality comparison (pre-deploy).

## The Feedback Scale

- **1 bad** — response was wrong, unhelpful, or harmful
- **2 ok** — response was acceptable but not great
- **3 good** — response was genuinely helpful
- **4 leave me alone** — Mother Tree should not have spoken up

## Feedback Collection

After substantive interactions, Mother Tree appends a feedback prompt:

```
[... normal response ...]

_How was that? 1 bad · 2 ok · 3 good · 4 leave me alone (feel free to say why)_
```

The user replies with a number, optionally followed by an explanation: `2 felt too generic` or just `3`.

### Eligible Interactions

| Interaction type | When to ask |
|---|---|
| signal_capture | After Mother Tree closes a signal thread |
| meeting_prep | After the prep is delivered |
| meeting_debrief | After the debrief summary |
| training_chapter | After all questions in a chapter are completed |
| training_refresher | After the refresher session |
| persona_question | After a substantive Seth/Lawrence answer |

NOT eligible: status, help, enroll, individual training questions, casual channel conversation, reminders.

### Collection Flow

1. Pipeline detects eligible interaction type after a character responds.
2. Pipeline appends feedback prompt to the response.
3. Pipeline sets a `feedback_pending` flag in conversation memory.
4. When user replies with 1-4 (detected by Dispatcher), route to feedback handler.
5. Feedback handler: extracts score + explanation, looks back for the rated interaction, stores everything in the `feedback` table, clears the flag, acknowledges briefly ("Got it, thanks.").
6. If user ignores the prompt and says something else, the flag clears silently. No nagging.

## Feedback Table

```sql
CREATE TABLE feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_type TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score IN (1, 2, 3, 4)),
    explanation TEXT,
    user_input TEXT NOT NULL,
    bot_output TEXT NOT NULL,
    context JSONB,
    user_slack_id TEXT NOT NULL,
    channel_id TEXT,
    thread_ts TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

The `context` JSONB stores whatever is needed to replay the interaction: annotation, persona, signal data, thread history, participant count, profile context.

`user_input` and `bot_output` are the raw messages. `context` is everything the pipeline needed to produce the output.

## Fast Mode — Structural Regression

CLI command: `mothertree test regression`

Replays each feedback record through the pipeline (no Slack, no actual messages). Checks structural properties:

| Interaction type | Checks |
|---|---|
| signal_capture | Same entities extracted? Triage = respond + signal? No hallucinated entities? |
| meeting_prep | Response references contact/company from context? References CI data? |
| persona_question | Correct persona activated? Response length in range? |
| training_chapter | Exercise generated for correct stage/chapter? |
| All types | No hallucinated URLs? Slack formatting correct? No leaked markers? |

**Score 4 records:** assert Dispatcher returns `character: "silent"`. If it doesn't, triage regressed.

**Pass/fail:** structural properties match. Output doesn't need to be identical — just the same shape and key properties.

Gated behind `RUN_REGRESSION_TESTS=1`. No LLM calls for judging (only for generating the new output). Fast enough for CI.

## Deep Mode — LLM-Judged Quality

CLI command: `mothertree test regression --deep`

Same replay as fast mode, plus an LLM judge compares the new output against the stored baseline:

```
The original interaction was rated {score}/4 by the team.
{explanation if provided}

ORIGINAL OUTPUT (rated {score}):
{stored_bot_output}

NEW OUTPUT:
{new_bot_output}

Is the new output at least as good as the original?
Score 0.0-1.0.
Consider: tone, accuracy, helpfulness, relevance.
{The team specifically noted: {explanation} — if provided}
```

Uses the existing `assess_confidence` pattern (2 scoring models, median score).

**Regression detection:**
- Original rated 3, judge scores new output below 0.6 → regression, flag it
- Original rated 1, judge scores new output above 0.7 → improvement, track it
- Score 4 records skip LLM judge, use fast-mode triage assertion only

**Cost:** ~2 LLM calls per feedback record. A corpus of 50 interactions = ~100 calls, under a minute.

## What Changes

**New:**
- `feedback` table in PostgreSQL + tracked in Hasura
- Feedback detection pattern in Dispatcher (1-4 at start of message when feedback pending)
- Feedback handler (stores context, clears flag)
- Feedback prompt injection in pipeline (after eligible interactions)
- `feedback_pending` flag in conversation memory
- `mothertree test regression` CLI command (fast + deep modes)
- `jobs/bot/feedback.py` — feedback handler module
- `jobs/tests/test_feedback.py` — tests for collection and regression runner

**Modified:**
- `jobs/bot/pipeline.py` — append feedback prompt after eligible interactions
- `jobs/bot/characters/dispatcher.py` — detect feedback replies
- `jobs/cli.py` — add `test` command
- `jobs/mothertree/hasura.py` — feedback CRUD
- `deploy/database/schema.sql` — feedback table

**Unchanged:**
- Character modules (no knowledge of feedback)
- Extraction pipeline
- Validation pipeline
- Training engine
- Memory system
