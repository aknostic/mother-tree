# Training Engine — Design Spec

## What this is

A Slack-based training system that teaches the Aknostic methodology through progressive exercises generated from the central intelligence. Everyone on the team can enroll. Training adapts to role, stage, and individual progress.

The training follows the same structure as the methodology itself: start with the marketing framework (what to say, to whom), then the sales method (how to say it, when), then practice the dance between them.

## How training maps to the frameworks

The methodology has two layers — the marketing framework (Seth Godin's structure) and the sales method (Mycorrhizal Method). Training teaches both, but more importantly teaches how they feed each other:

```
    TRAINING PROGRESSION

    Stage 0                Stage 1                 Stage 2
    ───────────────        ────────────────        ──────────────────────
    WHAT WE SAY            WHY WE SAY IT           HOW WE SAY IT

    The Promise            The Change ──────────►  Soil
    The Worldview          The Worldview ────────►  Signal → Reframe
    The Audience           The Story ───────────►  Diagnosis → Proposal
    The Difference         The Audience ─────────►  Sustain
    The Services
                           MARKETING FRAMEWORK      SALES METHOD
                           (Seth Godin)             (Mycorrhizal Method)

         │                        │                        │
         │                        │                        │
         ▼                        ▼                        ▼

    Stage 3                                        Stage 4
    ──────────────────────────────────────         ──────────────────
    THE DANCE                                      LIVE SITUATIONS

    The scaffolding dissolves.                      Prep sessions
    Respond to the person.                          Meeting prep
    The system finds the framework                  Debrief
    in what you said naturally.                     Conference prep
    Feedback connects instinct
    to methodology — after the fact.

    "Here's a person with a situation. Go."
```

The training draws from two data layers in the central intelligence, each fed by the content pipeline's two extraction lenses:

```
    FOUNDATION TABLES                NARRATIVE TABLES
    (positioning — changes slowly)   (evidence — grows continuously)
    ┌─────────────────────────┐     ┌─────────────────────────┐
    │ change     — statements │     │ insights    — reframes  │
    │ worldview  — beliefs    │     │ case_studies — proof     │
    │ personas   — audience   │     │                         │
    │ competitors — landscape │     │                         │
    └────────────┬────────────┘     └────────────┬────────────┘
                 │                               │
                 └───────────┬───────────────────┘
                             │
                             ▼
                 ┌───────────────────────┐
                 │   TRAINING ENGINE     │
                 │                       │
                 │  Generates exercises  │
                 │  from live data —     │
                 │  new content at any   │
                 │  layer automatically  │
                 │  becomes new training │
                 └───────────────────────┘
```

When narrative ingestion runs on schedule, new insights flow into the training engine automatically. A new Clouds of Europe article becomes a reframe exercise within hours of publication. Foundation refreshes after positioning changes propagate new change statements and personas into Stage 0 instruction.

## Enrollment and roles

| Role | Stages | Refreshers | Prep sessions | Scored |
|------|--------|------------|---------------|--------|
| Hunter | 0-4 | Daily (high frequency) | Own situations (meetings, presentations, conferences) | Required, must score high |
| Gatherer | 0-3 | Regular | Can practice hunter/gatherer scenarios on request | Required |
| Farmer | 0-3 | Regular | Can practice any role's perspective on chosen topics | Required |
| Citizen | 0-1 (encouraged) | Occasional if enrolled | No | Only if requested |

Everyone can send signals. Enrollment is required for hunters, gatherers, and farmers. Encouraged for citizens.

## Training stages

### Stage 0: Instruction

Multiple chapters of core knowledge. Each chapter is instruction text followed by questions to anchor understanding. Generated entirely from **foundation** data — what we say, not yet why or how.

Chapters:
1. **The Promise** — what change we offer, why it matters. Source: `change` table.
2. **The Worldview** — who we're talking to, what they believe, what they feel. Source: `worldview` + `personas` tables.
3. **The Audience** — the specific people, their roles, how they decide. Source: `personas` table.
4. **The Difference** — how we compare to alternatives, what makes us unique. Source: `competitors` table.
5. **The Services** — Assess, Build, Operate — what each phase delivers. Source: `change` table (service-related statements).

Each chapter: instruction (generated from database), 3 multiple-choice questions, then proceed to next chapter.

This stage answers: *"What do we actually say?"*

### Stage 1: Marketing framework (Seth Godin)

Teaches the framework itself — the *why* behind what was learned in Stage 0. How the change, worldview, story, and audience connect. Why stories exist before conversations. How signals indicate readiness. What makes an audience "smallest viable."

This is the first stage that draws from **both** foundation and narrative data. The trainee sees how foundation positioning (change statements, worldview beliefs) connects to narrative evidence (insights, case studies).

Exercises test understanding of framework concepts:
- "A prospect read our Clouds of Europe article on lock-in risk. Which element of Seth's framework did that article serve — the change, the worldview, or the story?"
- "Here's a case study excerpt: *'Consumentenbond reduced platform costs by 40% while gaining full control of their deployment pipeline.'* Is this a change statement or a story? What's the difference?"
- "Which worldview belief does this insight speak to: *'Every SaaS renewal is a sovereignty negotiation you didn't prepare for.'*"
- "A marketing page says we offer 'Kubernetes-based internal developer platforms.' Is this the change? If not, what's the change underneath it?"

Source: `change`, `worldview`, `insights`, `case_studies`, framework documentation.

This stage answers: *"Why do we say what we say?"*

### Stage 2: Sales framework (Mycorrhizal Method)

Teaches the choreography — Soil through Sustain. Qualification framework. Roles. Assessment as first product. The six steps of the method and how each maps to a framework element.

```
    METHOD STEP      WHAT IT IS                        FRAMEWORK CONNECTION
    ───────────      ──────────                        ────────────────────
    Soil             Stories in the landscape           Story → builds worldview
    Signal           Visible readiness                  Audience → emits signals
    Reframe          Change in their context            Change → articulated for one
    Diagnosis        Quantified assessment              Worldview → shapes the proof
    Proposal         Offer to guide the change          Change → packaged as service
    Sustain          Client tells the story             Story → feeds back to Soil
```

Exercises test application of the method, drawing from **narrative** insights for realistic scenarios:
- "A gatherer from a client mentions their sister company is struggling with cloud costs. What method stage is this? What do you do next?"
- "A prospect wants to negotiate the assessment price down by 50%. What qualification signal is this? Walk or talk?"
- "You're in the Reframe step. A CISO at a financial services company is across the table. Which insight categories from the central intelligence are most relevant? Pick two and explain why."
- "A prospect says: 'We already looked at this, our team decided AWS is fine.' Which worldview belief is *not* present? Is this someone in your smallest viable audience?"

Source: methodology files + `insights` + `personas` + `competitors`.

This stage answers: *"How do we say it, and when?"*

### Stage 3: The dance

Stages 0-2 taught the vocabulary and the structure — consciously, analytically, by name. Stage 3 is where the scaffolding dissolves.

The trainee no longer labels framework elements or identifies method steps. They just respond to a person in a situation. The system evaluates whether the framework is present in their response — without the trainee having to name it.

This is the difference between knowing grammar and speaking a language. Between knowing music theory and playing by ear. The framework should become invisible. A hunter in a conversation shouldn't be thinking "I'm now in the Reframe step, activating the Change element." They should just... talk to the person across the table. Connect. Listen. Respond with something that matters.

**The principle: teach the framework consciously, then train until it's unconscious. The exercises provoke natural responses. The feedback reveals the framework underneath.**

```
    STAGES 0-2                              STAGE 3-4
    ─────────────────────                   ─────────────────────────────

    "Which element is this?"                "Go."

    Analytical. Naming.                     Instinctive. Conversational.
    The trainee labels.                     The trainee responds.
    Right/wrong answers.                    The system finds the framework
                                            in what they said naturally.

    Learning the vocabulary.                Speaking the language.
```

#### How exercises work

The system presents a human situation. No framework labels. No "identify the step." Just a person with a problem and a conversation to have.

Examples:

- "You're at a conference coffee break. The person next to you mentions they just got a bill from AWS that made their CFO call an emergency meeting. They laugh about it, but they're not really laughing. What do you say?"

- "A prospect you've been talking to for months sends you a message: 'We decided to go with Datadog after all. It's just easier.' How do you respond?"

- "You're having dinner with a long-term client. They mention their CTO is leaving, and the new one is 'very cloud-first, very Azure.' They seem worried. What do you talk about over dessert?"

- "A gatherer tells you that during a delivery standup, a client engineer said: 'I wish we could just run this ourselves instead of waiting for vendor tickets.' Nobody else noticed. What do you do with this?"

- "You just published an article about NIS2 compliance. Two days later, a CIO you've been nurturing shares it on LinkedIn with a comment about their own compliance headaches. What happens next?"

- "A prospect says: 'We tried self-hosted GitLab once and it was a nightmare.' They're looking at you to see if you flinch."

No "walk me through the steps." No "which framework element." Just: respond as you would respond.

#### How scoring works

The system doesn't grade the response against a rubric of framework elements. It reads the response as a whole and looks for:

- **Presence** — did they actually engage with the person, or retreat into a pitch?
- **Listening** — does the response reflect what was said, or does it redirect to a script?
- **Instinct** — did they naturally reframe, or did they describe features?
- **Curiosity** — did they ask something, or just tell?
- **Warmth** — would this make someone want to keep talking?

The framework is present when someone naturally listens to a pain (worldview), offers a perspective shift (reframe), and creates a reason to continue the relationship (next step) — without ever naming any of those things.

#### How feedback works

The feedback is where the framework surfaces — *after* the trainee has responded naturally. The system connects what they did instinctively to the methodology they learned:

- "You picked up on the CFO emergency meeting as the real signal — that's exactly the kind of readiness signal the worldview describes. And your instinct to ask about their team's reaction rather than jumping to a solution? That's what keeps the conversation going."

- "Notice what you did there — you didn't defend self-hosted GitLab. You asked what went wrong. That's the difference between selling a solution and understanding a worldview. The prospect told you they believe 'self-hosted = pain.' That's real. You can work with that belief instead of against it."

- "You went straight to reassuring the client about the CTO change. That's natural, but you might be leaving something on the table. What did the client actually say? They're *worried*. That worry is a signal. What if you just sat with it for a moment instead of solving it?"

The feedback is conversational, not clinical. It speaks the trainee's language, not the framework's. It makes the trainee realize they already have the instincts — the training just sharpens them.

#### What this stage is really about

Most people who end up in consultative sales are there because they're good with people. They listen. They care. They want to help. The worst thing traditional sales training does is make them self-conscious about that — turning natural relationship builders into people who are running a checklist in their head while someone is talking to them.

Stage 3 does the opposite. It says: trust your instincts. Respond to the person. The methodology is there to catch you when your instincts aren't enough — not to replace them.

The framework dance — Story creates Soil, Audience emits Signals, Change becomes the Reframe, Worldview shapes the Diagnosis, Sustain produces a new Story — should be something a hunter *recognizes in hindsight*, not something they execute step by step.

"Oh, that's what happened — the article created soil, they signaled readiness, and I reframed without even thinking about it." That's mastery. That's what Stage 3 trains for.

Source: `insights` + `case_studies` + `personas` + `competitors` + `change` + `worldview`.

This stage answers: *"Can I be myself and still be effective?"*

### Stage 4: Prep sessions (hunters only, farmers on request)

Tailored to specific upcoming situations. Not a framework exercise — a genuine conversation about what's coming up and how to approach it with confidence.

The system provides context from the central intelligence and previous interactions, then asks open, human questions:

- Pre-meeting: "You're seeing Maria Santos tomorrow. She runs platform engineering at Company X — you've met twice before. Last time she was frustrated about NIS2 timelines and her team's dependency on AWS support tickets. What's on your mind going into this meeting? What do you want to understand better about her situation?"

- Pre-presentation: "You're speaking at KubeCon next week. The room will be mostly engineers, some engineering leaders. What's the one thing you want people to feel when they leave? Not remember — feel."

- Pre-conference: "Three people from your pipeline are at the cloud summit tomorrow. For each one — what's the relationship right now? What would a good conversation look like? Not a pitch. A conversation."

- Post-meeting debrief: "How did it go with Maria? What surprised you? What did you learn about her situation that you didn't know before? Is there something you wish you'd said differently?"

The prep doesn't tell the hunter what to do. It helps them think through the situation in their own way, with the central intelligence providing context they might not have top of mind. The debrief helps them notice what happened — what worked, what they missed, what they'd do differently — so the next conversation is better.

```
    PREP SESSION FLOW

    Central intelligence                        Hunter's own thinking
    ─────────────────────                       ────────────────────
    Contact history                             "What do I want to
    Company context            ──► Prompt ──►    understand about
    Previous interactions                        this person?"
    Relevant insights
    Worldview signals                           "How am I feeling
                                                 about this meeting?"

                                                        │
                                                        ▼
                                                  The meeting
                                                        │
                                                        ▼

                               ◄── Debrief ◄──  "What surprised me?
                                                  What did I learn?
    Update interactions                           What would I do
    Capture new signals                           differently?"
    Note follow-ups
```

Source: `contacts` + `companies` + `interactions` + `insights` + `change` + `worldview` + calendar integration.

This stage answers: *"Am I ready for this specific person, in this specific moment?"*

## Refresher mode (Duolingo)

After completing their training scope, everyone receives refreshers. A refresher is a single exercise drawn from any completed stage, weighted by:

1. **Weak spots** — areas where the trainee scored low
2. **Staleness** — topics not practiced recently
3. **New content** — fresh insights from recent narrative ingestion (new CoE article = new exercise)
4. **Framework balance** — if someone's strong on foundation but weak on the dance, weight toward Stage 3

Frequency scales with advancement:

| Progress | Refresher frequency |
|----------|-------------------|
| Completed Stage 0-1 | Weekly |
| Completed Stage 2 | 2-3x per week |
| Completed Stage 3 | Daily |
| Stage 4 active | Daily + pre-event prep |

Refreshers pull from both foundation and narrative tables. For trainees who've completed Stage 3, refreshers are conversational — not framework quizzes. When the narrative pipeline ingests a new article overnight, the next morning's refresher might be: "A new article went up on Clouds of Europe yesterday about NIS2 enforcement timelines. Imagine a prospect mentions this over coffee. What do you say?" The system evaluates naturalness, not labeling. For trainees still in Stages 0-2, refreshers stay structured — multiple choice, framework identification, method application.

Streaks tracked. Missing a refresher breaks the streak. Streak length visible to the individual (not a leaderboard — not surveillance).

## Scoring

Responses are scored against the central intelligence using the same multi-model pipeline as content extraction:

```
Trainee's response
    │
    ▼
Three Scaleway models evaluate independently:
  Devstral 2 123B  ──┐
  Llama 3.3 70B    ──┼── "Does this response demonstrate understanding
  Gemma 3 27B      ──┘    of our change, worldview, and evidence?"
    │
    ▼
Median confidence score (0.0 - 1.0)
    │
    ├── ≥ 0.7 — correct, advance
    ├── 0.4 - 0.7 — partial, provide targeted feedback
    └── < 0.4 — incorrect, explain why and retry
```

### Scoring by stage

| Stage | What's evaluated | Scoring style |
|-------|-----------------|---------------|
| 0 (Instruction) | Factual recall — change statements, worldview, personas, competitors | Strict. Multiple choice. Right or wrong. |
| 1 (Marketing framework) | Framework understanding — can the trainee identify which element applies? | Structured. Clear correct answer, but reasoning matters. |
| 2 (Sales method) | Method application — right step, right response, right qualification judgment | Structured. Some subjectivity in approach, but method steps are definite. |
| 3 (The dance) | Presence, listening, instinct, curiosity, warmth — is the framework there without being named? | Conversational. No rubric. The feedback reveals the framework in what they did naturally. |
| 4 (Prep sessions) | Depth of thinking — did they engage with the person's situation or retreat to abstractions? | No failing. Reflective. The debrief is the learning, not the score. |

Stages 0-2 have right answers. Stages 3-4 don't. The shift is deliberate: the early stages build confidence through structure, the later stages build confidence through freedom. A hunter who can only perform in a structured exercise isn't ready. A hunter who responds naturally to a person and the framework shows up in their response — that's the goal.

For Stage 3-4, Haiku 4.5 evaluates conversational responses since multi-turn context and emotional nuance matter more than factual accuracy.

For citizens with scoring requested, same pipeline applies.

## Slack bot architecture

### Persistent service

The Slack bot runs as a Deployment (always-on), not a CronJob. It manages:

- **Inbound messages** — signal capture from anyone, training responses from enrolled users
- **Outbound messages** — training exercises, refreshers, feedback, signal notifications
- **Conversation state** — multi-turn interactions for Stage 3-4

### Message types

| Message | Direction | Trigger |
|---------|-----------|---------|
| Training exercise | Bot -> User (DM) | Scheduled (CronJob triggers bot) |
| Response | User -> Bot (DM) | User replies to exercise |
| Feedback | Bot -> User (DM) | After scoring the response |
| Refresher | Bot -> User (DM) | Scheduled based on refresher_schedule |
| Signal | User -> Channel | Anyone posts in #signals channel |
| Signal notification | Bot -> Hunter (DM) | After signal is captured and enriched |
| Prep prompt | Bot -> Hunter (DM) | Calendar-driven (before meetings) |
| Debrief prompt | Bot -> Hunter (DM) | Calendar-driven (after meetings) |

### Conversation state

Stored in PostgreSQL:

```
conversations
  id, user_id, stage, chapter, exercise_id,
  state (active | waiting_response | complete),
  messages (JSONB array of the conversation),
  created_at, updated_at
```

For Stage 0-2 (structured exercises), state is simple: exercise sent -> waiting -> response received -> scored -> feedback sent -> complete.

For Stage 3-4 (conversational), state includes the full message history. The bot uses this context for multi-turn interaction. The LLM generates the next prompt based on the conversation so far, drawing from the central intelligence to challenge and extend.

### Scheduled triggers

CronJobs still trigger the timing, but they call the bot's API rather than sending Slack messages directly:

```
CronJob (8 AM weekdays)
    │
    └── POST to bot: /trigger/daily-training
            │
            Bot queries: who needs an exercise today?
            For each user:
              ├── Check enrollment, stage, last exercise
              ├── Query foundation + narrative tables for fresh content
              ├── Generate exercise from database + LLM
              └── Send DM
```

### Content freshness in exercises

The training engine benefits from the content pipeline's two-lens model and different cadences:

```
    Foundation pipeline                    Narrative pipeline
    (runs after positioning changes)       (runs on recurring schedule)
              │                                     │
              ▼                                     ▼
    Stage 0 chapters refresh               New insights appear
    Stage 1 framework examples update      New case studies arrive
    Personas get richer                            │
              │                                     │
              └──────────────┬──────────────────────┘
                             │
                             ▼
                    Training engine picks up
                    changes automatically:

                    • Stage 0: new chapter content
                    • Stage 1: new framework examples
                    • Stage 2: new method scenarios
                    • Stage 3: new dance exercises
                    • Refreshers: "new content" weight increases
```

No manual exercise authoring needed. The pipeline feeds the intelligence, the intelligence feeds the training.

## Database additions

```sql
-- Enrollment
CREATE TABLE enrollment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slack_user_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('hunter', 'gatherer', 'farmer', 'citizen')),
    current_stage INTEGER DEFAULT 0,
    current_chapter INTEGER DEFAULT 0,
    enrolled_at TIMESTAMPTZ DEFAULT now(),
    active BOOLEAN DEFAULT true
);

-- Exercise history
CREATE TABLE exercises (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES enrollment(id),
    stage INTEGER NOT NULL,
    chapter INTEGER,
    exercise_type TEXT NOT NULL,  -- 'instruction', 'multiple_choice', 'open', 'scenario', 'prep'
    content JSONB NOT NULL,       -- the exercise as sent
    source_tables TEXT[],         -- which CI tables contributed to this exercise
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Responses and scores
CREATE TABLE responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exercise_id UUID REFERENCES exercises(id),
    user_id UUID REFERENCES enrollment(id),
    response TEXT NOT NULL,
    scores JSONB,                  -- per-model scores
    confidence REAL,               -- median
    feedback TEXT,                 -- generated feedback
    responded_at TIMESTAMPTZ DEFAULT now()
);

-- Conversation state for multi-turn
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES enrollment(id),
    stage INTEGER NOT NULL,
    state TEXT DEFAULT 'active' CHECK (state IN ('active', 'waiting_response', 'complete')),
    messages JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Refresher schedule
CREATE TABLE refresher_schedule (
    user_id UUID REFERENCES enrollment(id) PRIMARY KEY,
    frequency TEXT DEFAULT 'weekly' CHECK (frequency IN ('daily', '3x_week', '2x_week', 'weekly', 'biweekly')),
    next_refresher TIMESTAMPTZ,
    streak INTEGER DEFAULT 0,
    last_refresher TIMESTAMPTZ
);
```

## Implementation phases

### Phase A: Bot infrastructure + signal capture

- Deploy Slack bot as Deployment in mother-tree namespace
- Slash command: `/mothertree enroll [role]`
- Signal capture from #signals channel
- Basic DM capability (bot can send and receive DMs)

### Phase B: Stage 0 instruction

- Generate instruction chapters from **foundation** data (change, worldview, personas, competitors)
- Multiple-choice questions after each chapter
- Score responses against central intelligence
- Track progress in enrollment (stage, chapter)
- **Prerequisite:** foundation pipeline has been run on marketing repo and/or aknostic.com

### Phase C: Stage 1-2 structured exercises

- Marketing framework exercises (Stage 1) — draws from **both** foundation and narrative
- Sales framework exercises (Stage 2) — draws from methodology + narrative insights
- Refresher scheduling after stage completion
- Streak tracking
- **Prerequisite:** narrative pipeline has been run on at least one source (CoE, aknostic blog, or marketing repo)

### Phase D: Stage 3 — the dance

- Multi-turn conversation state
- Scenario generation from **all** central intelligence tables — but presented as human situations, not framework exercises
- Conversational scoring — presence, listening, instinct, curiosity, warmth (Haiku evaluation for multi-turn context and emotional nuance)
- Feedback that reveals the framework in the trainee's natural response, after the fact
- No framework labeling in exercises — the scaffolding is invisible
- **Prerequisite:** both foundation and narrative tables well-populated

### Phase E: Stage 4 prep sessions + calendar

- Google Calendar integration
- Pre-meeting prep generation (drawing from contacts, companies, interactions, insights)
- Post-meeting debrief prompts
- Prep session exercises for hunters
- **Prerequisite:** conversation layer populated (contacts, companies, interactions)

### Phase F: Polish

- Per-topic practice mode for farmers
- Citizen opt-in scoring
- New content -> new exercises pipeline (automatic, based on narrative ingestion schedule)
- Progress reporting (individual, not comparative)
- Framework balance tracking — ensure trainees aren't strong on theory but weak on the dance
