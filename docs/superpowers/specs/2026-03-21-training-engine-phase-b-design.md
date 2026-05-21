# Training Engine Phase B — Stage 0 Instruction

## What this is

The first working training loop: enrollment → exercise delivery → response scoring → feedback → progression. Covers Stage 0 (instruction) only, but built to extend to Stages 1-4.

Amends the training engine design spec (2026-03-19):
1. Stage 4 gets confidence capture + direct feedback against the central intelligence, not just reflection.
2. Training is pull + push — CronJob nudges daily, trainees control their own pace, practice on demand.
3. `practice` added as exercise type (not in original spec).
4. `question_index` added to responses table (tracks per-question scoring within an exercise).
5. `exercise_id` and `current_question` added to conversations table (tracks DM flow state).
6. Delivery CronJob runs as independent CLI job (`jobs train deliver`) rather than calling the bot's HTTP API. Simpler, consistent with existing CronJob pattern, uses `SLACK_BOT_TOKEN` directly.
7. Streak stored on enrollment table (original spec put it on `refresher_schedule`, which Phase B doesn't build).

## Prerequisites

- Enrollment exists and works (`/mothertree enroll`)
- Foundation tables populated (change, worldview, personas, competitors)
- Bot deployed as Deployment, handles slash commands and channel messages
- DM handler exists but only acknowledges — needs to be built out

## What we're building

Five components:

### 1. Exercise generator with stage dispatch

A function that takes a user's stage and chapter (or a practice topic) and returns a structured exercise.

Stage dispatch:
- Stage 0: implemented (this phase)
- Stage 1-4: raises NotImplementedError

For Stage 0, the generator:
- Reads the user's current chapter from enrollment
- Queries the relevant foundation tables for that chapter
- Calls Mistral Small 3.2 (Scaleway) to generate instruction text + 3 multiple-choice questions
- Returns structured JSONB

Chapter-to-table mapping:

| Chapter | Name | Primary tables | What to teach |
|---------|------|---------------|---------------|
| 0 | The Promise | `change` | What change we offer and why it matters |
| 1 | The Worldview | `worldview`, `personas` | What the audience believes and feels |
| 2 | The Audience | `personas` | Specific people, roles, how they decide |
| 3 | The Difference | `competitors` | How we compare, what makes us unique |
| 4 | The Services | `change` (service-related) | Assess, Build, Operate — what each delivers |

Generation prompt pattern:

```
You are generating training material for chapter {chapter}: {chapter_name}.

PURPOSE OF THIS CHAPTER:
{what the trainee should understand after completing it}

SOURCE DATA:
{actual rows from the relevant CI tables}

GENERATE:
1. Instruction text (300-500 words). Teach this material as a practitioner
   would explain it to a new colleague. Direct, concrete, no jargon overload.
   Use the actual data — real change statements, real worldview beliefs, real
   persona details. This isn't theory, it's what we actually say.

2. Three multiple-choice questions that test understanding, not memorization.
   Each question presents a realistic situation where the trainee applies what
   they just learned. Include:
   - The question (a scenario, not "which of the following...")
   - Three options (one correct, two plausible but wrong)
   - The correct answer
   - Why the correct answer is stronger than the alternatives (one sentence)
   - A redirect — a thinking prompt the trainee can carry into real
     conversations (one sentence)
```

Generation model: Mistral Small 3.2 on Scaleway. Stage 0 runs entirely on European open-source infrastructure.

### 2. Stage 0 scoring

Deterministic. The LLM generates the correct answer at exercise creation time. Scoring checks if the trainee picked right.

No multi-model pipeline needed. That's built when Stage 1 requires it.

Wrong-answer feedback has three beats:
1. The correct answer
2. Why it's stronger — what makes it the right lens
3. A redirect — a thinking prompt they can reuse

Example:
```
Not quite — it's A.

"Every renewal is a negotiation you didn't prepare for" is stronger because
it names what's actually at stake. Rising costs is a symptom — the worldview
targets the power dynamic underneath.

Try this: when someone says something is "just a formality," ask yourself
what they're not preparing for.
```

### 3. Delivery CronJob

Runs weekday mornings (8:00 AM CET). Stage-agnostic from day one.

Flow:
1. Query enrollment for active users
2. For each user with no pending exercise (no conversation in `waiting_response` state):
   - Read current_stage and current_chapter
   - Call exercise generator
   - Store exercise in exercises table
   - Create conversation record (state: `waiting_response`, current_question: -1)
   - Send DM with instruction text + "Reply 'go' when ready for the questions"

If exercise generation fails (malformed LLM response, timeout, fewer than 3 questions), log the error and skip the user. The next CronJob run will retry.

CronJob manifest follows the existing pattern in `deploy/cronjobs/`. Calls `jobs train deliver` via CLI. Uses `SLACK_BOT_TOKEN` directly (available in the CronJob template environment).

### 4. Bot DM response handler

Currently the DM handler acknowledges but doesn't process. Build it out:

Flow:
1. Receive DM message
2. Look up active conversation for this user (state = `waiting_response`)
3. If no active conversation:
   - Check for commands: "next", "practice", "practice [topic]"
   - "next" → cancel any stale conversations, generate next chapter exercise, deliver it
   - "practice [topic]" → generate practice exercise for that topic (no progression). Topic matched case-insensitively against chapter names: "promise", "worldview", "audience", "difference", "services". Unrecognized topics get: "I don't have a chapter called that. Try: promise, worldview, audience, difference, or services."
   - "practice" → generate practice exercise for current chapter
   - Anything else → friendly nudge ("No active exercise. Say 'next' to continue training, or 'practice' to drill a topic.")
4. If active conversation exists:
   - Parse which question they're on (tracked in conversation messages JSONB)
   - If "go" and instruction was just sent → send first question
   - If answer to current question → score it, send feedback, advance to next question or complete chapter
5. After all 3 questions answered (one response row per question in the responses table):
   - If chapter complete → update enrollment (advance current_chapter)
   - If all 5 chapters complete → advance current_stage to 1
   - Update streak
   - Send completion message with options: "next" or "practice [topic]"

### 5. Progression

- Complete a chapter's 3 questions → advance `current_chapter`
- Complete all 5 chapters (0-4) → advance `current_stage` from 0 to 1
- Stage 1 shows "coming soon" until we build it
- Streak: stored on `enrollment` table (`streak INTEGER`, `last_activity TIMESTAMPTZ`). Incremented daily when any training activity happens (not per-exercise — multiple exercises in one day still count as one streak day). Broken by a calendar day of inactivity (CET timezone, matching the CronJob). Visible to the individual only.

## Exercise content structure

Stored as JSONB in the exercises table:

```json
{
  "stage": 0,
  "chapter": 2,
  "chapter_name": "The Worldview",
  "type": "instruction",
  "instruction": "300-500 words of teaching text from CI data...",
  "questions": [
    {
      "question": "A CTO tells you: 'We're fine with AWS, renewal is just a formality.' Which worldview belief does this conflict with?",
      "options": {
        "A": "Every SaaS renewal is a sovereignty negotiation you didn't prepare for",
        "B": "Cloud costs always increase year over year",
        "C": "CTOs don't understand procurement"
      },
      "correct": "A",
      "why": "It names what's actually at stake — the power dynamic, not the cost.",
      "redirect": "When someone says something is 'just a formality,' ask yourself what they're not preparing for."
    }
  ],
  "source_tables": ["worldview", "personas"]
}
```

Practice exercises (no progression):

```json
{
  "stage": 0,
  "chapter": 2,
  "chapter_name": "The Worldview",
  "type": "practice",
  "questions": [{ "..." }],
  "source_tables": ["worldview", "personas"]
}
```

No instruction text for practice — they've already read it. Fresh questions only.

## Slack interaction flow

### Morning push (CronJob)

```
Bot DM:
━━━━━━━━━━━━━━━━━━━━━━
Chapter 3 of 5: The Audience
━━━━━━━━━━━━━━━━━━━━━━

[Instruction text — 300-500 words]

Ready for the questions? Reply "go" when you've read this.
```

### Questions (one at a time)

```
Bot:
Question 1 of 3

A CTO tells you: "We're fine with AWS, renewal is just
a formality." Which worldview belief does this conflict with?

A) Every SaaS renewal is a sovereignty negotiation you didn't prepare for
B) Cloud costs always increase year over year
C) CTOs don't understand procurement
```

### Correct answer

```
Bot:
✓ Right.

The CTO is treating renewal as routine. The worldview says it's a
negotiation — one where the power dynamic is already set before the
conversation starts.

Question 2 of 3
[next question]
```

### Wrong answer

```
Bot:
Not quite — it's A.

"Every renewal is a negotiation you didn't prepare for" is stronger
because it names what's actually at stake. Rising costs is a symptom —
the worldview targets the power dynamic underneath.

Try this: when someone says something is "just a formality,"
ask yourself what they're not preparing for.

Question 2 of 3
[next question]
```

### Chapter complete

```
Bot:
━━━━━━━━━━━━━━━━━━━━━━
Chapter 3 complete — 3/3 ✓
Streak: 4 days
━━━━━━━━━━━━━━━━━━━━━━

Tomorrow: Chapter 4 — The Difference

Want to keep going? Say "next" for chapter 4,
or "practice audience" to do more on this one.
```

### Self-service

```
User: next
→ Bot serves next chapter immediately

User: practice worldview
→ Bot generates fresh questions on The Worldview (no progression)

User: practice
→ Bot generates fresh questions on current chapter
```

### Display numbering

Chapters are 0-indexed internally but 1-indexed for users. Internal chapter 0 displays as "Chapter 1 of 5: The Promise."

### Practice flow

Practice exercises have no instruction text. The bot delivers the first question immediately — conversation starts with `current_question: 0`, no "go" prompt.

### "next" after final chapter

When the user completes chapter 4 (The Services) and says "next", Stage 1 is not yet implemented. The bot responds: "You've completed Stage 0. Stage 1 — the marketing framework — is coming soon. In the meantime, say 'practice [topic]' to keep sharpening."

### Pace

- Default: one chapter per morning (CronJob nudge)
- Pull: trainee requests more anytime, no limit
- New recruits can burn through all 5 chapters in a day

## Database changes

Tables from the original design spec that need to be added to `schema.sql` and deployed:

```sql
CREATE TABLE exercises (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES enrollment(id),
    stage INTEGER NOT NULL,
    chapter INTEGER,
    exercise_type TEXT NOT NULL CHECK (exercise_type IN
        ('instruction', 'multiple_choice', 'practice', 'open', 'scenario', 'prep')),
    content JSONB NOT NULL,
    source_tables TEXT[],
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exercise_id UUID REFERENCES exercises(id),
    user_id UUID REFERENCES enrollment(id),
    response TEXT NOT NULL,
    question_index INTEGER NOT NULL,
    correct BOOLEAN,
    scores JSONB,
    confidence REAL,
    feedback TEXT,
    responded_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES enrollment(id),
    exercise_id UUID REFERENCES exercises(id),
    stage INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state IN
        ('active', 'waiting_response', 'complete')),
    current_question INTEGER DEFAULT -1,
    messages JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

Note: `current_question` is -1 when instruction text has been sent but questions haven't started (waiting for "go"). 0-2 during questions. After question 2 is scored, set `current_question` to 3 and `state` to `complete`.

The `enrollment` table exists in production but is missing from `schema.sql` — add it for completeness. Phase B adds two columns: `streak INTEGER DEFAULT 0` and `last_activity TIMESTAMPTZ`.

The `refresher_schedule` table from the original spec is not needed yet.

## Files to create or modify

### New files

- `jobs/training/engine.py` — exercise generator with stage dispatch, chapter-to-table mapping, generation prompts
- `jobs/training/score.py` — scoring with stage dispatch (Stage 0: deterministic MC)
- `jobs/training/deliver.py` — delivery logic (query enrollment, generate, send DM)
- `deploy/cronjobs/training-deliver.yaml` — weekday 8 AM CronJob

### Modified files

- `jobs/bot/bot.py` — expand `handle_dm()` from acknowledgement to full response handling
- `jobs/mothertree/hasura.py` — add queries for exercises, responses, conversations
- `jobs/cli.py` — add `train deliver` command
- `deploy/database/schema.sql` — add exercises, responses, conversations tables; add enrollment table

## What we're not building yet

- Multi-model scoring pipeline (Stage 1-2 need it, Stage 0 doesn't)
- Conversational scoring via Haiku (Stage 3-4)
- Refresher scheduling (needs completed stages to draw from)
- Stage 4 confidence capture (needs contacts, interactions, calendar)
- Calendar integration (separate project)
- Framework balance tracking (needs data across stages)
- Progress reporting (useful but not essential for first loop)

All of these have extension points in the architecture: stage dispatch in generator and scorer, practice mechanic as seed for refreshers, conversation state for multi-turn.

## Relationship to existing spec

This is Phase B of the training engine design (2026-03-19). It implements the first end-to-end training loop and amends the original spec:

1. **Stage 4 scoring** — confidence capture + direct feedback against the central intelligence, not just reflection. The multi-model pipeline evaluates whether the hunter engaged with contact history, drew on relevant insights, and reflected awareness of method positioning. Feedback tells them what they missed and what to draw on next time.

2. **Training pace** — pull + push. CronJob nudges daily, trainee controls pace via "next" and "practice [topic]" commands. No artificial gates on learning speed.
