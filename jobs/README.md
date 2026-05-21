# Mother Tree — Jobs

Python code for all runtime workloads: ingestion, Slack bot, training, pulse, discipline, and the shared `mothertree` package.

## Package structure

```
jobs/
├── mothertree/          # Shared package — used by all workloads
│   ├── config.py        # Environment variables, model IDs, thresholds
│   ├── graphql_client.py # PostGraphile GraphQL client (queries, mutations)
│   ├── identity.py      # Email-first identity resolution (Slack → user)
│   ├── llm.py           # LLM wrapper (Scaleway + Anthropic)
│   ├── ask.py           # Shared ask logic — personas, context fetching
│   └── handbook.py      # Role-aware feature docs for help + onboarding
│
├── ingestion/           # Content ingestion pipeline
│   ├── ingest.py        # Main entry point (lenses, modes, sources, consolidation)
│   ├── extract.py       # LLM extraction (foundation + narrative)
│   ├── profile.py       # Organization profile extraction + consolidation
│   ├── validate.py      # Field validation, scoring, triage, arbitration
│   └── sources.py       # Source readers (file, dir, repo, url, sitemap)
│
├── bot/                 # Slack bot + unified conversation engine
│   ├── bot.py           # Entry point — routes all messages to pipeline
│   ├── pipeline.py      # Unified pipeline: detect → triage → converse → extract
│   ├── detect.py        # Pattern matching, training commands, annotation production
│   ├── memory.py        # Unified memory interface (DM, channel, thread)
│   ├── extraction.py    # Background signal extraction (Spotter → Weaver → store)
│   ├── buffer.py        # In-memory channel buffer for lazy persistence
│   ├── markers.py       # Action/content marker parsing + user input sanitization
│   ├── enrich.py        # URL fetching utilities (fetch_url_context, extract_urls)
│   └── characters/      # Character modules
│       ├── dispatcher.py # Routes messages to the right character
│       ├── mother_tree.py # Default conversational character
│       ├── saga.py      # Positioning strategy ([Saga](../docs/inspirations.md))
│       ├── lena.py      # Consultative diagnosis ([Lena](../docs/inspirations.md))
│       ├── spotter.py   # Entity/signal extraction from conversations
│       ├── weaver.py    # Entity resolution against relationship graph
│       └── pulse.py     # Nudge generation for Pulse scanner
│
├── training/            # Training engine
│   ├── curriculum.py    # Stage/chapter definitions per role
│   ├── engine.py        # Exercise generation from CI data
│   ├── operations.py    # Enroll, deliver, score, advance state machine
│   ├── deliver.py       # CronJob: daily training delivery
│   └── score.py         # Exercise scoring
│
├── pulse/               # Pulse scanner — background nudges
│   └── scanner.py       # Due reminders, stale threads/contacts, pipeline nudges
│
├── discipline/          # Rhythm engine — periodic reviews
│   ├── weekly_review.py # Monday morning pipeline briefing
│   ├── monthly_retro.py # Monthly retrospective
│   └── calendar_sync.py # iCal feed sync, meeting prep/debrief
│
├── handbook/            # Markdown playbooks (loaded by mothertree/handbook.py)
├── tests/               # pytest test suite (500+ tests)
├── cli.py               # CLI entry point (all commands)
├── requirements.txt     # Python dependencies
├── Dockerfile.bot       # Container image for the Slack bot
└── Dockerfile.jobs      # Container image for CronJobs
```

## CLI usage

```bash
# Content ingestion
mothertree ingest foundation sitemap https://aknostic.com/sitemap.xml
mothertree ingest foundation repo /path/to/marketing
mothertree ingest narrative sitemap https://clouds-of-europe.eu/sitemap.xml
mothertree ingest consolidate                # Dedup + org profile synthesis

# Training
mothertree train enroll user@example.com "Name" hunter
mothertree train status user@example.com
mothertree train deliver                     # CronJob: daily delivery
mothertree train pending                     # List pending enrollment requests

# Admin
mothertree admin add user@example.com
mothertree admin remove user@example.com
mothertree admin list

# Rhythm
mothertree rhythm weekly                     # Monday pipeline briefing
mothertree rhythm monthly                    # Monthly retrospective
mothertree rhythm calendar                   # Calendar sync (prep/debrief)
mothertree pulse scan                        # Pulse scanner (nudges)

# Database
mothertree dump <path>                       # Dump all CI tables to JSON
mothertree restore <path>                    # Restore from dump

# Other
mothertree bot                               # Start Slack bot (Socket Mode)
mothertree brief <query>                     # Cross-table semantic briefing
```

## Running locally

```bash
cd jobs/
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Required environment variables
export HASURA_URL=https://mothertree.aknostic.com/graphql
export HASURA_ADMIN_SECRET=<from SOPS-encrypted deploy/hasura/admin-secret.yaml>
export SCALEWAY_AI_API_KEY=<Scaleway Generative APIs key>
export ADMIN_EMAIL=you@example.com
export ORGANIZATION_NAME=Aknostic

# For the Slack bot
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_APP_TOKEN=xapp-...

# Run tests
python -m pytest tests/ -v

# Run commands
python cli.py ingest foundation sitemap https://aknostic.com/sitemap.xml
python cli.py bot
```

## Deployment

Two container images, built by GitLab CI (`.gitlab-ci.yml`) using kaniko:

| Image | Dockerfile | Contains | Deployed as |
|-------|-----------|----------|-------------|
| `slack-bot` | `Dockerfile.bot` | `mothertree/` + `bot/` + `training/` + `handbook/` | Deployment (always-on) |
| `jobs` | `Dockerfile.jobs` | `mothertree/` + `ingestion/` + `training/` + `pulse/` + `discipline/` + `cli.py` | CronJobs |

Images pushed to `registry.gitlab.aknostic.com/aknostic/mother-tree/`. Flux CD image automation detects new tags, updates deployment manifests, and applies via kustomization from `deploy/`.

CI pipeline: lint (ruff) → security (bandit + TruffleHog) → test (pytest) → build (kaniko) → scan (trivy + SBOM).
