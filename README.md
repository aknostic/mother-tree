# Mother Tree

> *"A forest is much more than what you see." — Suzanne Simard*

Mother Tree is a commercial intelligence platform for consultative sales teams — methodology, training engine, and always-on intelligence layer in a single deployable system.

## What is Mother Tree

Mother Tree combines a sales methodology (the Mycorrhizal Method) with a pipeline of scheduled jobs that turns that methodology into daily practice. The framework is content-agnostic: Mother Tree defines the structure — what an insight looks like, how training progresses, what the sales choreography is. Your content sources (marketing site, git repository, case studies) provide the substance. Change the content sources, change what the platform knows.

See [docs/methodology.md](docs/methodology.md) for the Mycorrhizal Method in full.

## Who is it for

Consultative sales teams running multi-quarter deals who want an always-on intelligence layer. The platform is built around four roles: **hunters** (commercial choreography), **gatherers** (signal and story capture from delivery), **farmers** (platform infrastructure), and **citizens** (inspired colleagues, not full participants). It works best for relationship-driven, expertise-based businesses — consultancies, advisory firms, specialized services — with small deal volume and long sales cycles, where the challenge is choreography, not volume.

## Quick start

```bash
# Start the full stack (Postgres, PostGraphile, bot, jobs)
docker compose up
```

```bash
# First ingest — extract foundation layer from your marketing site
uv run python -m cli ingest foundation url https://your-marketing-site.example/sitemap.xml

# Dedup + synthesize the organization profile
uv run python -m cli ingest consolidate

# Enroll your first hunter
uv run python -m cli train enroll hunter@example.com "Hunter Name" hunter

# Full CLI reference
uv run python -m cli --help
```

The Slack bot starts in CLI-only mode if no Slack credentials are provided — you can run ingestion, training enrollment, and briefings entirely from the command line without a Slack workspace.

## Architecture

Mother Tree runs as two coordinated layers.

### Always-on layer

PostgreSQL 17 + pgvector + PostGraphile provide the data backbone. Kubernetes CronJobs handle ingestion (foundation and narrative extraction from your content sources), daily training delivery, weekly pipeline review, monthly LLM-synthesized retrospective, calendar prep and debrief, and signal capture from Slack conversations. Vector embeddings (BGE Multilingual Gemma2) on all intelligence tables drive context fetching, training source selection, and semantic search.

### Interactive layer

A Slack bot participates as a conversational member in any channel — capturing signals, delivering training via DM, responding to questions via `@mention`. Operators interact via CLI. A Claude Code skill also queries the platform via GraphQL, using the same data layer as the bot.

See [docs/methodology.md](docs/methodology.md) for how the methodology maps to the platform and [docs/inspirations.md](docs/inspirations.md) for the practitioner credits.

## Personas — Saga and Lena

Saga is a positioning strategist; Lena is a consultative diagnostician. They co-train hunters and respond to queries in their own voices. In Slack, reach them via `@mention` in any channel or `ask saga` / `ask lena` in a DM. They share the same underlying intelligence but bring distinct perspectives — Saga grounds training in positioning and differentiation, Lena in conversation structure and stakeholder diagnosis.

See [docs/inspirations.md](docs/inspirations.md) for the real practitioners whose work informs these archetypes.

## Models

Mother Tree's model selection policy favors European open-source LLMs. Extraction, classification, scoring, and embeddings run on Scaleway: Qwen 3.5 397B for deep extraction, Mistral Small 3.2 for classification, Devstral 2 123B / Llama 3.3 70B / Gemma 3 27B as independent scoring judges, and BGE Multilingual Gemma2 for embeddings. Anthropic Claude is used for certain interactive and synthesis steps. All model choices are configurable per environment variable — see [`jobs/mothertree/config.py`](jobs/mothertree/config.py).

See [docs/model-selection-policy.md](docs/model-selection-policy.md) for the full policy and selection rationale.

## Production deployment

[`deploy/`](deploy/) contains Kubernetes manifests targeting CloudNativePG (Postgres operator), PostGraphile, and Scaleway Inference. Any Kubernetes cluster running Postgres 17 with pgvector works — the manifests are a starting point, not a turnkey deployment. Example CronJob manifests in [`deploy/cronjobs.example/`](deploy/cronjobs.example/) show how to wire ingestion jobs to your content sources. Mother Tree ships with no customer content, ingestion sources, or organizational configuration — you fork and adapt for your environment.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
