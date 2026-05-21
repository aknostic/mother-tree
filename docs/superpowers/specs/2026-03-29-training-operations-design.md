# Training Operations — State Machine, Proficiency, and Delivery

## Problem

Six out of seven training commands are broken. The pipeline creates annotations but never executes the corresponding database operations. Enrollment doesn't persist. Exercises generate but never deliver. Answers score but never advance. The CronJob bypasses the pipeline entirely. There is no proficiency tracking, no decay, no refreshers.

The root cause: no layer owns training state transitions. The Dispatcher does pattern matching AND side effects. The pipeline does response generation AND sometimes delivery. deliver.py does exercise generation AND Slack posting. Responsibilities are scattered.

## Solution

One module — `training/operations.py` — owns all training state transitions and database writes. The Dispatcher only matches patterns and produces annotations. The pipeline delegates training logic to operations.py. The CronJob calls the same operations module.

## Separation of Concerns

**Dispatcher** — pattern matching only. Recognizes commands, reads enrollment state, produces routing decision with annotation. No database writes, no LLM calls, no Slack messages.

**Training Engine** (`engine.py`) — generates content. Given role, stage, chapter, produces exercises. Called by operations.py.

**Training Operations** (`operations.py`) — the state machine. Handles all transitions, all database writes, all content assembly. Called by both the pipeline and the CronJob.

**Pipeline** — orchestration. Receives routing decision, calls operations.py for training commands, handles response delivery.

```
User message → Dispatcher → annotation
                              │
Pipeline receives annotation → operations.py handles state transition
                              │
                              ├→ generates exercise (via engine.py)
                              ├→ writes to database
                              └→ returns formatted response
                              │
Pipeline delivers response → Slack
```

## The Training State Machine

Each training interaction is a conversation with a state:

```
IDLE → INSTRUCTION → EXERCISING → COMPLETE → IDLE (next chapter)
```

**IDLE** — no active conversation. "next" starts the next chapter.

**INSTRUCTION** — chapter instruction delivered, waiting for "go". User reads the material.

**EXERCISING** — questions asked one at a time. `current_question` tracks progress (0, 1, 2).

**COMPLETE** — all questions answered. "I'll have the next chapter ready tomorrow. Or reply *next* if you want to continue."

### State Transitions

| From | Trigger | To | Operations action |
|------|---------|------|-------------------|
| (none) | "enroll hunter" | IDLE | `enroll()` — INSERT enrollment |
| IDLE | "next" | INSTRUCTION | `deliver_chapter()` — generate exercise, INSERT exercise + conversation, return instruction |
| INSTRUCTION | "go" | EXERCISING | `start_exercises()` — UPDATE conversation (state=exercising, current_question=0), return first question |
| EXERCISING | answer | EXERCISING | `score_answer()` — INSERT response, UPDATE conversation (current_question+1), return feedback + next question |
| EXERCISING | last answer | COMPLETE | `complete_chapter()` — INSERT response, UPDATE conversation (state=complete), UPDATE training_progress, return summary |
| COMPLETE | "next" or CronJob | INSTRUCTION | `advance_and_deliver()` — UPDATE enrollment (chapter+1 or stage+1), then same as deliver_chapter() |
| COMPLETE (last chapter, last stage) | — | REFRESHER | `complete_program()` — acknowledge, enter refresher mode |
| REFRESHER | CronJob decay check | EXERCISING | `deliver_refresher()` — generate practice for decayed chapter, same exercise flow |

Every transition is a database write. The operations module owns all transitions.

## Command Map

| User says | Dispatcher annotation | Operations function | DB operations |
|-----------|----------------------|---------------------|---------------|
| "enroll hunter" | `{type: "enroll", role: "hunter"}` | `enroll(slack_user_id, name, role)` | INSERT enrollment |
| "next" (idle) | `{type: "training_next", role, stage, chapter}` | `deliver_chapter(enrollment, stage, chapter)` | INSERT exercise, INSERT conversation |
| "next" (not enrolled) | `{type: "training_next", enrolled: false}` | None — Mother Tree suggests enrollment | None |
| "go" | `{type: "exercise_go", conversation_id}` | `start_exercises(conversation_id)` | UPDATE conversation |
| "A"/"B"/"C" | `{type: "answer", answer, conversation_id}` | `score_answer(conversation_id, answer)` | INSERT response, UPDATE conversation |
| "practice [topic]" | `{type: "practice", role, topic}` | `deliver_practice(enrollment, topic)` | INSERT exercise, INSERT conversation |
| "status" | `{type: "status", ...enrollment data}` | None — factual annotation, character presents | READ only |
| "progress" | `{type: "progress", role}` | `get_progress(enrollment_id)` | READ enrollment + training_progress |
| CronJob daily | (programmatic) | `daily_check(enrollment)` | READ + conditional writes |

## Proficiency and Decay

Each chapter has a proficiency score (0.0–1.0) per user. Stored in `training_progress`.

### Score Calculation

- **Stage 0 (multiple choice):** percentage correct (e.g., 2/3 = 0.67)
- **Stages 1+ (open response):** trainer character evaluates (LLM-as-judge, 0.0–1.0)

### Decay Formula

```
proficiency = initial_score × (0.5 ^ (days_since_last_activity / half_life))
```

Half-life per stage type:
- Stage 0 (foundation knowledge): 30 days
- Stage 1-2 (conversation/offering skills): 14 days
- Stage 3-4 (applied skills): 21 days

### Hunter Certified

All chapters above minimum proficiency threshold (0.6). When any chapter drops below, Mother Tree triggers a refresher.

### Refresher Flow

1. CronJob detects decayed chapter (proficiency < 0.6)
2. Calls `deliver_refresher(enrollment, chapter)` via operations.py
3. Generates 2-3 practice questions for that chapter
4. User answers through normal exercise flow
5. Score updates proficiency, resets decay clock

## Exercise Generation with Character Voice

The exercise generation prompt includes the trainer's identity:

- Seth-trained chapters: Seth's voice for instruction text + questions
- Lawrence-trained chapters: Lawrence's voice
- Mother Tree-trained chapters: Mother Tree's voice

Generation uses Qwen 3.5 (same model as character responses). Slack formatting rules included in the prompt.

## CronJob Integration

The daily CronJob (`training-deliver`) calls operations.py, not deliver.py directly.

**Daily check per enrollment:**

1. Active conversation exists? → skip (mid-chapter)
2. Last conversation complete > 24h ago? → `deliver_chapter()` for next chapter
3. Any chapter proficiency < 0.6? → `deliver_refresher()` for lowest proficiency chapter
4. No activity in 7+ days? → nudge message
5. Update streak: activity yesterday → increment, else reset to 0

## Dispatcher Changes

Strip all side effects from the Dispatcher. Remove:
- `deliver_next()` — moves to operations.py
- `score_exercise_answer()` — moves to operations.py
- `generate_citizen_inspiration()` — moves to operations.py

The Dispatcher keeps:
- Pattern matching for all training commands
- Enrollment state lookup (read-only)
- Active conversation lookup (read-only)
- Annotation production

## Pipeline Changes

`_training_response()` in pipeline.py becomes a thin dispatcher to operations.py:

```python
def _training_response(annotation, enrollment, active_conversation, user_name):
    ann_type = annotation["type"]

    if ann_type == "enroll":
        return operations.enroll(...)
    elif ann_type == "training_next":
        return operations.deliver_chapter(...)
    elif ann_type == "exercise_go":
        return operations.start_exercises(...)
    elif ann_type == "answer":
        return operations.score_answer(...)
    elif ann_type == "practice":
        return operations.deliver_practice(...)
    elif ann_type == "progress":
        return operations.get_progress(...)
```

Each operations function returns a formatted string ready for Slack delivery.

## Test Coverage

All in `jobs/tests/test_operations.py`:

**Unit tests (mocked DB):**
- Enrollment creates record
- Chapter delivery generates exercise and creates conversation
- "go" transitions to exercising state
- Answer advances question
- Last answer completes chapter
- Chapter completion advances enrollment
- Stage completion advances stage
- Program completion enters refresher
- Proficiency decay calculation (pure function)
- Refresher resets decay clock
- CronJob selects correct enrollments
- Invalid state transitions handled gracefully
- Exercise generation uses trainer voice in prompt

**Integration tests (gated, `RUN_LLM_TESTS=1`):**
- Full chapter flow: enroll → next → go → A → B → C → verify progress
- Proficiency decay → refresher → recovery

## What Changes

**New:**
- `jobs/training/operations.py` — state machine, all training logic
- `jobs/tests/test_operations.py` — comprehensive test coverage

**Major rewrites:**
- `jobs/bot/pipeline.py` — training delegation to operations.py
- `jobs/bot/characters/dispatcher.py` — stripped of side effects
- `jobs/training/engine.py` — character-voiced exercise generation

**Modified:**
- `jobs/mothertree/hasura.py` — ensure all training DB functions work
- `jobs/training/score.py` — add LLM-based scoring for open responses
- CronJob entry point — calls operations.py

**Removed/replaced:**
- `jobs/training/deliver.py` — replaced by operations.py
- Dispatcher's `deliver_next()`, `score_exercise_answer()`, `generate_citizen_inspiration()`

**Unchanged:**
- `jobs/training/curriculum.py` — data, not logic
- Character modules — respond to prompts
- Ingestion pipeline, memory system
