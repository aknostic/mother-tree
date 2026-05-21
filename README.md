# Mother Tree

> *"A forest is much more than what you see." — Suzanne Simard*

Mother Tree is a commercial intelligence platform for consultative sales teams. It combines a sales methodology (the Mycorrhizal Method) with an always-on intelligence layer that turns methodology into daily practice.

Designed for relationship-driven, expertise-based businesses with small deal volume and long sales cycles — consultancies, advisory firms, specialized services — where the sales challenge is not volume but choreography: connecting warmth, expertise, and reputation into pipeline.

## How it works

**Bring your own content.** Mother Tree defines the structure — what an insight looks like, how training works, what the sales choreography is. Your marketing repository, case studies, personas, and competitive positioning provide the substance. Change the content source, change the training.

**Two layers:**
- **Always-on** (Kubernetes) — scheduled jobs extract content, deliver training, check for stale relationships, generate pipeline reviews. Calls European LLMs (Scaleway: Qwen 3.5, Mistral Small 3.2, Devstral 2, Llama 3.3, Gemma 3). Anthropic (Haiku/Sonnet) only for triage and arbitration — core pipeline runs without it.
- **Interactive** — Slack bot as conversational participant (DMs and channels) + Claude Code skill queries via GraphQL. Character ensemble: Mother Tree (Librarian), Seth (marketing), Lawrence (sales), with invisible Spotter and Weaver for background intelligence.

**V1 features:**
- Content ingestion: dual-lens pipeline (foundation via Seth, narrative via Lawrence), context-aware extraction, multi-model scoring, vector embeddings on insert
- Training engine: role-specific curriculum (hunter/gatherer/farmer/citizen), proficiency tracking with decay, refreshers, streaks, answer randomization, repetition avoidance
- Citizen inspiration: 4-stage flow with 2x/week nudges, designed to inspire belief
- Signal capture: background entity/action extraction from any Slack conversation via Spotter + Weaver, vector-based similar signal detection
- Semantic search: pgvector cosine distance across all CI tables, cross-table briefings via CLI
- Calendar integration: iCal feed sync, meeting prep 2 days before, debrief prompt 3 days after
- Rhythm engine: stale relationship checks (daily), weekly pipeline review, monthly LLM-synthesized retrospective
- Coming: signal scanner (RSS/news/job boards)

## Repository structure

```
mother-tree/
├── methodology/          # The Mycorrhizal Method (content-agnostic)
│   ├── principles.md     # Five core beliefs
│   ├── roles.md          # Hunters, gatherers, farmers
│   ├── choreography.md   # Soil → Signal → Reframe → Diagnosis → Proposal → Sustain
│   └── qualification.md  # Walk-away signals and the mutual respect gate
│
├── insights/             # Insight category schemas (content loaded from external sources)
│   ├── README.md         # How the insight library works
│   ├── lock-in-freedom.md
│   ├── regulatory-pressure.md
│   ├── capability-vs-dependency.md
│   ├── cost-reality.md
│   ├── developer-experience.md
│   └── resilience-reliability.md
│
├── assessments/
│   └── templates/        # Assessment frameworks (adapt to your domain)
│       ├── lock-in-audit.md
│       └── independence-assessment.md
│
├── patterns/             # Cross-engagement intelligence (accumulated over time)
│
├── briefings/            # Role-specific onboarding decks
│   ├── hunter-briefing-deck.md
│   ├── gatherer-briefing-deck.md
│   └── farmer-briefing-deck.md
│
├── docs/
│   ├── content-pipeline.md   # How external content sources feed into Mother Tree
│   ├── slack-bot-commands.md  # How Mother Tree works in Slack
│   └── superpowers/specs/
│       └── 2026-03-17-mycorrhizal-method-design.md
│
├── jobs/                      # Python code — all runtime workloads
│   ├── mothertree/            # Shared package (config, hasura, llm, ask)
│   ├── ingestion/             # Content ingestion pipeline
│   ├── bot/                   # Slack bot + unified conversation engine
│   │   └── characters/        # Character ensemble (mother_tree, seth, lawrence, dispatcher, spotter, weaver)
│   ├── training/              # Training engine (curriculum, operations, delivery, exercises)
│   ├── reminders/             # Thread reminders
│   ├── cli.py                 # CLI entry point
│   ├── Dockerfile.bot         # Slack bot container
│   └── Dockerfile.jobs        # CronJob container
│
├── deploy/                    # Kubernetes manifests (Flux CD)
└── .gitlab-ci.yml             # CI: kaniko builds for bot + jobs images
```

**Git (this repo):** methodology, insight schemas, assessment templates, patterns, briefings — the framework.

**PostgreSQL (PostGraphile GraphQL):** contacts, signals, interactions, insights (loaded from content sources), training state — the live data.

**External content source (e.g., marketing repo):** buyer personas, case studies, reframes, competitive positioning — your specific commercial knowledge.

## Platform stack

| Component | Purpose |
|-----------|---------|
| PostgreSQL 17 + pgvector 0.8.2 | Central data store with vector embeddings on all CI tables (cosine distance search) |
| CloudNativePG | PostgreSQL lifecycle on Kubernetes |
| PostGraphile | Auto-generated GraphQL API |
| Kubernetes CronJobs | Scheduled intelligence (signal scanning, training delivery, pipeline reviews) |
| Scaleway Generative APIs | Open-weight LLMs: Qwen 3.5 397B (generation/deep extraction), Mistral Small 3.2 (classification), Devstral 2 123B / Llama 3.3 70B / Gemma 3 27B (scoring), BGE Multilingual Gemma2 (embeddings) |
| Anthropic (Haiku/Sonnet) | Triage coordination and arbitration for flagged content |
| Slack bot | Conversational participant in all channels, training via DM, signal capture from conversation, thread memory, reminders |
| Claude Code skill | Interactive queries using shared `ask` module — same personas as Slack bot |

## Start here

| You are a... | Read this |
|--------------|-----------|
| Hunter | [Hunter briefing](briefings/hunter-briefing-deck.md), then [choreography](methodology/choreography.md) |
| Gatherer | [Gatherer briefing](briefings/gatherer-briefing-deck.md) |
| Farmer | [Farmer briefing](briefings/farmer-briefing-deck.md) |
| Everyone | [Principles](methodology/principles.md) |
| Integrating content | [Content pipeline](docs/content-pipeline.md) |
| Slack bot | [How Mother Tree works](docs/slack-bot-commands.md) |

## Status (2026-04-01)

Methodology defined. Architecture running. [Implementation plan](docs/implementation-plan.md) tracks all phases.

**Phase 1 — Foundation: DONE.** PostgreSQL 17 + pgvector 0.8.2 (migrated from pgvecto.rs), PostGraphile GraphQL (migrated from Hasura), 11 tables, TLS, S3 backups, vector embeddings on all CI tables.

**Phase 2 — Content ingestion: DONE.** Dual-lens extraction (foundation via Seth, narrative via Lawrence), context-aware with Qwen 3.5, multi-model scoring, pre-insert dedup, vector embeddings generated on insert, confidence scores in extraction prompts. 303 foundation records, narrative extraction active.

**Phase 3 — Slack bot: DONE.** Character ensemble (Mother Tree, Seth, Lawrence, Spotter, Weaver, Dispatcher). Unified pipeline. Signal capture from any conversation. Training via DM.

**Phase 4 — Calendar: DONE.** iCal feed sync, meeting prep 2 days before, debrief prompt 3 days after.

**Phase 5 — Training engine: DONE.** Role-specific curriculum (hunter/gatherer/farmer/citizen), exercise generation with answer randomization, proficiency decay + refreshers, streaks, citizen inspiration flow (4 stages, 2x/week), vector-driven source selection, repetition avoidance. CronJob deployed.

**Phase 6 — Discipline: MOSTLY DONE.** Stale relationship checks (weekdays 08:00), weekly pipeline review (Mondays 08:00), monthly retrospective (1st of month 09:00, LLM-synthesized). Signal scanner not started.

**Phase 7 — Claude Code skill: DONE.** `/mothertree` skill using shared `ask` module.
