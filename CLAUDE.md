# Mother Tree

## What this is

Mother Tree is a commercial intelligence platform for consultative sales teams. It combines the Mycorrhizal Method — a sales methodology structured around positioning, narrative, and conversation — with an always-on intelligence layer. The platform is content-agnostic: Mother Tree defines the structure (methodology, insight schema, training mechanics). Your fork provides the substance — your marketing content, customer personas, case studies, and ingestion sources.

See [`docs/methodology.md`](docs/methodology.md) and [`methodology/`](methodology/) for the full method.

## Architecture

Two layers, no agent framework.

**Always-on layer** — PostgreSQL 17 + pgvector + PostGraphile (GraphQL API) + Kubernetes CronJobs. Ingestion pipelines extract and score commercial intelligence from your content sources. Scheduled jobs run the rhythm engine (daily refreshers, weekly reviews, monthly retrospectives, calendar prep/debrief).

**Interactive layer** — Slack bot as conversational participant across all channels. CLI for operators. Both layers share the same CI data via PostGraphile GraphQL.

Vector embeddings (BGE Multilingual Gemma2, `vector(3584)`) on all CI tables drive semantic search, training source selection, signal dedup, and briefings.

## Saga and Lena

Mother Tree trains through two persona coaches.

**Saga** is the positioning strategist. She works from foundation data — change statements, worldview beliefs, market personas, competitor responses. Her lens is: what does the market need to believe, and why is now the moment?

**Lena** is the consultative diagnostician. She works from narrative data — reframes, evidence, stakeholder lenses, conversation triggers. Her lens is: how do you surface the buyer's problem before proposing anything?

In training, Saga and Lena assess together. In briefings and conversation prep, they respond from their respective lenses. The `@mention` bot interaction routes questions to Saga, Lena, or both depending on context.

Practitioner credits — the real people who shaped these archetypes — are in [`docs/inspirations.md`](docs/inspirations.md).

## Getting started locally

```bash
# Start the full stack (PostgreSQL, PostGraphile, Slack bot, job runner)
docker compose up
```

Ingest your first content source (foundation extraction builds the CI base):

```bash
uv run python -m cli ingest foundation url <your-sitemap-url>
```

Then consolidate (dedup + org profile synthesis):

```bash
uv run python -m cli ingest consolidate
```

Enroll a user and start training:

```bash
uv run python -m cli train enroll <email> <name> hunter
```

Talk to the bot in Slack via DM (`next`, `go`, `practice`) or `@mention` in any channel.

Full CLI reference: `uv run python -m cli --help`

## Repo layout

| Path | What lives here |
|---|---|
| `jobs/` | Python package: bot, ingestion, training, reminders, discipline, handbook, shared `mothertree/` core |
| `deploy/` | Kubernetes manifests — the production target; fork and adapt for your cluster |
| `docs/` | Methodology guides, model selection policy, runbook, inspirations, security audit |
| `methodology/` | The Mycorrhizal Method writeups — roles, choreography, principles, qualification |
| `assessments/` | Generic assessment templates (role-neutral) |
| `briefings/` | Role briefing decks for hunters, gatherers, farmers |
| `insights/` | Generic insight categories (lock-in, cost, risk, etc.) |
| `test-data/` | README only — CI data dumps are generated per deployment, not shipped here |
| `patterns/` | Placeholder for emerging conversation patterns |

## Conventions

**GraphQL queries** — always use parameterized variables (`$var: Type!`). Never interpolate values with f-strings. This applies to internal IDs too. No exceptions.

**Single path to CI data** — all queries against CI tables go through `jobs/mothertree/intelligence.py`. No direct GraphQL calls from bot characters, discipline jobs, or CLI commands. `graphql_client.py` provides raw query functions; `intelligence.py` composes them into data bundles.

**Gather and synthesize are separate** — data-gathering functions return plain dicts. LLM synthesis takes plain dicts and returns text. Never mix the two in the same function.

**Prompts live next to their characters** — system prompts and persona definitions are in `jobs/bot/characters/*.py`, not in separate prompt files.

**Tests use the compose-stack DB** — no mocked database. Tests run against a real PostgreSQL instance started by `docker compose`.

**Persona inspirations documented separately** — see [`docs/inspirations.md`](docs/inspirations.md). Do not embed attribution inside character modules.

**License** — Apache 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

## Instance vs. upstream

This repo is the framework. It ships with no ingestion sources, no customer references, no case studies, and no organization-specific content.

Your production deployment is a fork. Real content — your sitemap URLs, marketing repos, `ORGANIZATION_NAME` env var, Slack workspace credentials, Kubernetes secrets — lives in your fork's environment and deployment config, not here.

Keep your fork's production secrets out of version control. The `deploy/` directory uses SOPS-encrypted Kubernetes secrets; see [`docs/runbook.md`](docs/runbook.md) for the encryption workflow.

Contributing back? See [`CONTRIBUTING.md`](CONTRIBUTING.md).
