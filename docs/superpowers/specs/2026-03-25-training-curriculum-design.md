# Training Curriculum — Role-Specific Paths With Character Trainers

## Problem

Training uses a single chapter sequence (Stage 0, Chapters 0-4) for all roles, delivered through a generic prompt. Hunters, gatherers, farmers, and citizens all get the same content about positioning, worldview, audience, differentiation, and services. But their jobs are different — a gatherer needs to recognize signals, not articulate positioning. A farmer needs to empathize with hunters, not learn sales technique.

The training voice comes from `_trainer_consensus` in `ask.py` — a generic synthesis that doesn't use the character modules. The result: markdown formatting, generic tone, no character voice.

## Solution

Four role-specific training paths, each with its own stages, chapters, and trainers. Trainers are the character modules (Seth, Lawrence, Mother Tree). Each chapter specifies which trainer leads. The training engine reads the curriculum for the enrolled role and routes to the right character.

## The Four Paths

### Hunter — the full choreography

The hunter learns everything: positioning (Seth), then sales method (Lawrence), then integration (both).

| Stage | Name | Trainer | Exercise type |
|-------|------|---------|--------------|
| 0 | The Foundation | Seth | Multiple choice |
| 1 | The Framework | Seth | Scenario |
| 2 | The Conversation | Lawrence | Scenario |
| 3 | The Dance | Both | Open response |
| 4 | Prep Sessions | Both | Real-world |

**Stage 0 chapters:**

| Ch | Name | CI Tables | Seth teaches |
|----|------|-----------|-------------|
| 0 | The Promise | change | What transformation do we offer? Not what we do — what the customer becomes. |
| 1 | The Worldview | worldview | What does our audience already believe? These beliefs make them ready. |
| 2 | The Audience | personas | Who specifically? Not everyone. Specific people with specific concerns. |
| 3 | The Difference | competitors | What's the status quo they leave behind? How are we different? |
| 4 | The Services | change | Assess, Build, Operate — the journey from dependent to independent. |

### Gatherer — signal recognition + handoff

The gatherer learns to recognize opportunities and have lightweight consultative follow-ups before handing off to Mother Tree.

| Stage | Name | Trainer | Exercise type |
|-------|------|---------|--------------|
| 0 | The Change | Seth | Multiple choice |
| 1 | Signal Recognition | Lawrence | Scenario |
| 2 | The Conversation | Lawrence | Scenario |
| 3 | The Handoff | Mother Tree | Simulation |
| 4 | Stories | Seth | Open response |

**Stage 0 chapters:**

| Ch | Name | CI Tables | Seth teaches |
|----|------|-----------|-------------|
| 0 | Who We Are | change | Brief: the transformation we offer. Enough to recognize it. |
| 1 | Who It's For | personas | The buyers. So you know who matters when you're in a delivery meeting. |

**Stage 1 chapters:**

| Ch | Name | CI Tables | Lawrence teaches |
|----|------|-----------|-----------------|
| 0 | What's a Signal | insights, worldview | When someone mentions cost pressure, lock-in, or compliance — that's a signal. |
| 1 | Listening for Pain | worldview | The pain is rarely stated directly. Here's what to listen for. |
| 2 | Context Matters | personas | A CTO complaining about costs means something different than a developer. |

**Stage 2 chapters:**

| Ch | Name | Lawrence teaches |
|----|------|-----------------|
| 0 | The Follow-Up | "Tell me more about that" — how to ask without selling. |
| 1 | Knowing Your Limits | When to listen, when to ask, when to stop and hand off. |

**Stage 3 chapters:**

| Ch | Name | Mother Tree teaches |
|----|------|---------------------|
| 0 | Sharing a Signal | How to tell Mother Tree what you noticed — natural conversation, not a form. |
| 1 | Building Together | Mother Tree asks follow-up questions to structure the signal. The gatherer learns what makes a complete signal. |
| 2 | Looping In | When and how to bring a hunter into the conversation. |

**Stage 4 chapters:**

| Ch | Name | Seth teaches |
|----|------|-------------|
| 0 | Delivery as Soil | Your delivery work creates awareness. How client success becomes the next story. |
| 1 | The Narrative | How to frame what you did as evidence for the change we offer. |

### Farmer — platform + team empathy

The farmer maintains the platform. To do it well, they need to understand what hunters and gatherers go through.

| Stage | Name | Trainer | Exercise type |
|-------|------|---------|--------------|
| 0 | The Change | Seth | Multiple choice |
| 1 | The Hunter's World | Lawrence | Awareness + simulation |
| 2 | The Gatherer's World | Lawrence | Awareness + simulation |
| 3 | The Platform | Mother Tree | Scenario |
| 4 | Quality | Mother Tree | Practical |

**Stage 0 chapters:**

| Ch | Name | CI Tables | Seth teaches |
|----|------|-----------|-------------|
| 0 | Who We Are | change | Brief: what the organization does. |
| 1 | Who It's For | personas | The people the platform ultimately serves. |

**Stage 1 chapters:**

| Ch | Name | Lawrence teaches |
|----|------|-----------------|
| 0 | Before the Meeting | What a hunter goes through before a first conversation. The preparation, the anxiety. |
| 1 | In the Room | What happens in a consultative conversation. Why the prep has to be right. |
| 2 | After the Meeting | What a hunter needs from the platform — debrief, signal capture, next steps. |

**Stage 2 chapters:**

| Ch | Name | Lawrence teaches |
|----|------|-----------------|
| 0 | Spotting a Signal | What it feels like to notice something in a delivery meeting and not know what to do. |
| 1 | The Awkward Moment | The gatherer heard something. They're not a salesperson. How does it feel? What do they need? |
| 2 | The Handoff | What the platform should do when a gatherer shares a signal. What good support looks like. |

**Stage 3 chapters:**

| Ch | Name | Mother Tree teaches |
|----|------|---------------------|
| 0 | What Mother Tree Does | How the platform serves hunters and gatherers day-to-day. |
| 1 | What Good Looks Like | When the platform is working well, this is what the team experiences. |

**Stage 4 chapters:**

| Ch | Name | Mother Tree teaches |
|----|------|---------------------|
| 0 | Assessing Quality | How to evaluate what Mother Tree extracts and generates. |
| 1 | Improving the System | How to feed corrections back, tune the pipeline, improve outcomes. |

### Citizen — structured inspiration

Citizens don't get formal training. They get one piece of insight at a time, building belief progressively. No exercises, no scoring — just something to think about.

| Stage | Name | Trainer | Format |
|-------|------|---------|--------|
| 0 | See the Change | Seth | One change statement per session |
| 1 | See the Worldview | Seth | One worldview belief per session |
| 2 | See the Signals | Mother Tree | Reflective questions |
| 3 | Become a Gatherer | Mother Tree | Transition suggestion |

**Stage 0:** Seth shares one change statement, framed as something worth believing. Not a lesson — an idea.

**Stage 1:** Seth shares one worldview belief. "The people we help believe vendor lock-in is a strategic risk. Not everyone believes this — but the ones who do are ready for change."

**Stage 2:** Mother Tree asks reflective questions. "In your work this week, did you hear anyone mention cloud costs?" No right answer — just noticing.

**Stage 3:** Mother Tree tracks whether the citizen has shared signals in channels. If they have: "You've been noticing signals naturally. Want to enroll as a gatherer?"

## How Training Uses Character Modules

The training engine routes to character modules based on the curriculum:

1. User says "next" → Dispatcher detects training command
2. Pipeline looks up enrollment (role, current stage, current chapter)
3. Engine looks up the curriculum: `CURRICULA[role][stage]["chapters"][chapter]`
4. Gets the trainer: `"seth"`, `"lawrence"`, or `"mother_tree"`
5. Calls the trainer's `respond()` with a training-specific prompt and CI data
6. Post-processes through the standard pipeline (markers, Slack formatting, persist)

The `CURRICULA` dict replaces the flat `CHAPTERS` dict in `engine.py`:

```python
CURRICULA = {
    "hunter": {
        0: {
            "name": "The Foundation",
            "chapters": {
                0: {"name": "The Promise", "tables": ["change"], "trainer": "seth"},
                1: {"name": "The Worldview", "tables": ["worldview", "personas"], "trainer": "seth"},
                ...
            }
        },
        ...
    },
    "gatherer": { ... },
    "farmer": { ... },
    "citizen": { ... },
}
```

Exercise generation reads the trainer from the curriculum and calls the right character module. The character's voice shapes the instruction, the questions, and the feedback.

**Citizen delivery** is different: no exercise generation, just a short message from the trainer. The engine checks `role == "citizen"` and calls the trainer's `respond()` with a simple prompt: "Share one [change statement / worldview belief / reflective question] with this person."

## Scoring

**Stage 0 (all roles):** Deterministic multiple choice (A/B/C/D). Same as today.

**Stage 1+ (scenarios and open responses):** The trainer character evaluates the response. Seth judges positioning answers ("did they articulate the change correctly?"), Lawrence judges conversation answers ("would this response build trust in a meeting?"), Mother Tree judges platform answers ("is this assessment accurate?").

The evaluation is a follow-up call to the trainer's `respond()` with the question, the user's answer, and criteria for good/bad.

## What Changes

**New:**
- `CURRICULA` dict with role-specific stages, chapters, and trainers
- Citizen inspiration delivery mode
- Citizen-to-gatherer transition detection
- Trainer routing in exercise generation
- Character-based evaluation for Stage 1+ scoring

**Modified:**
- `training/engine.py` — `CHAPTERS` → `CURRICULA`, `generate_exercise` reads role
- `training/deliver.py` — uses character modules for instruction voice
- `training/score.py` — later stages use trainer character for evaluation
- `bot/characters/dispatcher.py` — passes role context to training mode
- `bot/pipeline.py` — training mode routes to trainer character

**Unchanged:**
- Enrollment system (role, stage, chapter)
- DM command flow (next, go, practice, A/B/C)
- Exercise and response storage
- Streak and progress tracking
