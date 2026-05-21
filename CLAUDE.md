# Mother Tree — Claude Code Context

## What this project is

A commercial intelligence platform for consultative sales teams. Combines a sales methodology (the Mycorrhizal Method) with an always-on intelligence layer. Content-agnostic — teams bring their own marketing content, personas, and case studies.

## Key decisions

- **"Freedom to operate" not "sovereignty"** — sovereignty is hyperscaler-co-opted and sounds activistic. Use freedom/independence language everywhere except when referencing specific regulatory frameworks.
- **Content-agnostic** — Mother Tree defines the structure (methodology, insight schema, training mechanics). External content sources (e.g., a marketing repository) provide the substance. Don't bake organization-specific content into the framework.
- **Two-layer architecture** — always-on layer (PostgreSQL + PostGraphile + CronJobs + Scaleway Inference) and interactive layer (Slack bot as conversational participant + Claude Code skill via GraphQL). No agent framework — scheduled workflows that call an LLM when needed.
- **V1 features: hunter training + discipline** — narrative development, daily refreshers, conversation prep/debrief, daily/weekly/monthly rhythm, reminders.
- **PostGraphile for GraphQL** — auto-generated, typed API on PostgreSQL + pgvector.
- **Model selection policy** — no OpenAI, open source first, European second. See `docs/model-selection-policy.md`.
- **Personas:** Seth Godin (marketing strategy), Lawrence Miller (consultative selling). **Trainer consensus:** both Seth and Lawrence assess together.
- **Slack bot** — conversational participant in all channels. Unified pipeline: detect → triage → converse → extract. Commands via DM or @mention, no slash commands.
- **Slack bot interaction:** DM for training (next, go, practice, A/B/C) and commands (enroll, status, help, pending). Admin commands in DM only (make admin, remove admin, enroll X as Y). @mention in channels for questions and personas (ask seth/lawrence/trainer). Signal capture from any conversation, background extraction. Thread memory with reminders. Channel memory for context.
- **Contacts enrichment** — personal details, team members, enriched from signals and conversations.
- **Vector embeddings everywhere** — all CI tables (insights, change, worldview, personas, competitors, signals, organization) have BGE Multilingual Gemma2 embeddings. Semantic search via pgvector cosine distance (`<->`) drives context fetching, training source selection, briefings, signal dedup, and org profile merging (85% similarity).
- **Rhythm engine** — Pulse scanner (`jobs/pulse/`) runs every 5 minutes: due reminders, stale threads/contacts, pipeline nudges, expired enrollment requests. Discipline (`jobs/discipline/`): weekly pipeline review (Mondays 08:00), monthly retrospective (1st of month 09:00, LLM-synthesized), calendar sync (prep 2 days before, debrief 3 days after). CLI: `mothertree rhythm {weekly|monthly|calendar|pulse}`.
- **Calendar integration** — iCal feed sync, prep delivered 2 days before meetings, debrief prompt 3 days after.

## Ingestion pipeline

Content flows through a staged pipeline. Each stage must complete before the next starts.

**Sources:** aknostic.com sitemap, marketing git repo, Clouds of Europe sitemap.

**Pipeline order:** foundation (weekly) → narrative (daily) → training consumes both.

### Foundation extraction (Seth lens)
Classifies documents and extracts positioning data: change statements, worldview beliefs, personas, competitor responses. Uses `extract_deep()` (Qwen 3.5) for extraction, Mistral Small 3.2 for classification. Context-aware — fetches existing records and injects them into the prompt to avoid duplicates. Pre-insert dedup check as final safety net. Foundation runs skip multi-model scoring (`lens="foundation"`).

Sequential: site first (builds context), then marketing (sees site's output). Organization profile elements extracted per document, consolidated after all documents are processed.

### Organization profile synthesis
Each foundation document also extracts organization profile elements (identity, change, audience, competitor_category) via `extract_profile()`. After all documents in a run, `consolidate_foundation()` deduplicates the foundation tables and `consolidate_organization_profile()` synthesizes profile elements into 3-5 per type. `ORGANIZATION_NAME` env var hints to Seth who the organization is.

### Narrative extraction (Lawrence lens)
Extracts sales conversation material — reframes, evidence, stakeholder lenses, triggers. Grounded in foundation data (fetches top changes, worldviews, personas as context). Uses `extract_deep()` (Qwen 3.5). Narrative runs go through full multi-model scoring.

### Multi-model scoring (narrative only)
Three independent judges score each insight: Devstral 2 123B, Llama 3.3 70B, Gemma 3 27B (all Scaleway). If judges agree → auto-accept (≥0.7) or auto-reject (≤0.4). If judges disagree (spread >0.3) → Haiku 4.5 triages → Sonnet 4.6 arbitrates. Core extraction pipeline runs without Anthropic; only triage/arbitration uses it.

### Models
- **Deep extraction** (foundation + narrative): Qwen 3.5 397B (Scaleway)
- **Classification + simple extraction**: Mistral Small 3.2 24B (Scaleway)
- **Scoring judges**: Devstral 2 123B, Llama 3.3 70B, Gemma 3 27B (Scaleway)
- **Triage**: Haiku 4.5 (Anthropic)
- **Arbitration**: Sonnet 4.6 (Anthropic)
- **Embeddings**: BGE Multilingual Gemma2 (Scaleway)
- **Bot conversations + training generation**: Qwen 3.5 397B (Scaleway)

### CLI commands
`jobs/cli.py` — entry point for all jobs. Run via `uv run python -m cli` or as container entrypoint.

- `mothertree ingest foundation {sitemap,repo,file,dir,url} <source>` — foundation extraction
- `mothertree ingest narrative {sitemap,repo,file,dir,url} <source>` — narrative extraction
- `mothertree ingest consolidate` — LLM-driven dedup + organization profile synthesis
- `mothertree ingest truncate [table ...]` — clear CI tables (all if none specified)
- `mothertree dump <path>` — dump all CI tables to JSON
- `mothertree restore <path>` — restore from dump
- `mothertree train enroll <email> <name> <role>` — enroll a user
- `mothertree train status <email>` — show enrollment status
- `mothertree admin add|remove|list` — manage admins
- `mothertree brief <query>` — cross-table semantic briefing (vector search across all CI tables)

### Test data dumps
`test-data/` contains snapshots for testing pipeline stages independently:
- `post-foundation-extraction.json` — old Mistral Small run (944 records, heavy duplicates)
- `post-foundation-context-aware.json` — Qwen 3.5 context-aware run (303 records, zero duplicates)
- `post-opus-consolidated.json` — Opus extraction + Seth/Lawrence consolidation (42 changes, 121 worldviews, 9 personas, 17 competitors, 977 insights)

## Training curriculum

Role-specific, multi-stage curriculum in `jobs/training/curriculum.py`. Each chapter specifies a trainer (Seth, Lawrence, or Mother Tree) and which CI tables provide source data.

**Hunter path:** The Foundation (change, worldview, personas) → The Offering (change, insights) → The Conversation (personas, competitors, insights) → In the Field (insights, worldview, personas, competitors)

**Gatherer path:** Signal Recognition → Signal Sharing → Delivery as Intelligence

**Farmer path:** Quality & Standards

Foundation data (stage 0) works without insights. Stage 1+ requires narrative extraction to populate the insights table.

**Citizen path:** Inspiration flow — 4 stages, 5 interactions each, 2x/week nudges (Tue/Thu). Stage 3 is a gatherer conversation. Lighter touch than formal training — designed to inspire belief, not drill knowledge.

## Identity system

Email is the canonical identity. Slack is a linked channel via `channel_links` table.

- **First contact:** Slack message → `channel_links` lookup → if not found: Slack API `users_info` → email → `users` table lookup → if not found: auto-create as citizen → create channel_link. Module: `jobs/mothertree/identity.py`.
- **Admin system:** `admins` table with audit trail. Root admin seeded from `ADMIN_EMAIL` env var on bot startup. Admins can: `make admin <email>`, `remove admin <email>`, `enroll <email> as <role>`, `pending`.
- **Tables:** `users` (replaces old `enrollment`), `admins`, `channel_links`. All `slack_user_id` references replaced with `user_id UUID` foreign keys. Reverse lookup via `get_slack_user_id(user_id)` for DM sending.

## Roles (generic)

- **Hunters** — full commercial choreography, the ones who sell
- **Gatherers** — signals and stories from delivery work
- **Farmers** — platform infrastructure and maintenance

## Architecture

Runs in `mother-tree` namespace on groupware team's K8s cluster, deployed via Flux CD from `deploy/` directory. CI via GitLab CI with kaniko (`.gitlab-ci.yml`). Two container images: `slack-bot` (Dockerfile.bot) and `jobs` (Dockerfile.jobs).

Shared Python package: `jobs/mothertree/` (config, graphql_client, llm, intelligence, ask). Job packages: `jobs/ingestion/`, `jobs/bot/`, `jobs/training/`, `jobs/reminders/`, `jobs/discipline/`. CLI entry point: `jobs/cli.py`.

### Code principles

- **Single path to CI data** — every query against CI tables goes through `intelligence.py`. No direct GraphQL calls from bot characters, discipline jobs, or CLI commands. `graphql_client.py` provides raw query functions; `intelligence.py` composes them into meaningful data bundles.
- **Gather and synthesize are separate** — data gathering returns plain dicts, LLM synthesis takes plain dicts and returns text. Never mix data fetching with LLM calls in the same function.
- **Thin callers** — CLI commands, bot handlers, and cronjobs resolve the user's intent, call gather + synthesize, and deliver the result. Business logic lives in `intelligence.py`, not in the caller.
- **One function, many callers** — if the weekly review and the bot `pipeline` command need the same data, they call the same function. Don't duplicate "almost the same" queries. Add parameters to the shared function if scoping differs.

PostgreSQL 17 + pgvector (CloudNativePG) → PostGraphile (GraphQL at `mothertree.aknostic.com`) → CronJobs + Slack bot → Scaleway Generative APIs (multiple models, see pipeline section). Claude Code skill as interactive interface.

Kubeconfig: `kubeconfig-mother-tree.yaml` (gitignored, namespace-scoped)
PostGraphile GraphQL: `https://mothertree.aknostic.com/graphql`
GraphQL admin secret: in SOPS-encrypted `deploy/hasura/admin-secret.yaml`
Scaleway AI: `https://api.scaleway.ai/v1` (model config in `jobs/mothertree/config.py`)
SOPS age public key: `age1ny5rpz82l25pxw3esxrv6e2g5wy3j09uwgmwu6ygh6q9k6jajp3srl0ru5` (safe to share — encrypts only). Private key is in `sops-age` secret in `flux-system` on the cluster.
S3 bucket: `groupware-mother-tree-backups` at `s3.fr-par.scw.cloud`
Namespace managed by groupware — we only deploy workloads, no namespace manifest
pgvector 0.8.2 extension for vector similarity search, standard `vector(3584)` type, cosine distance operator (`<->`)
Vector embeddings on all CI tables (insights, change, worldview, personas, competitors, signals, organization) via BGE Multilingual Gemma2

## Security

- **GraphQL queries** — ALWAYS use parameterized variables (`$var: Type!`), NEVER interpolate values with f-strings. Even for internal IDs. No exceptions.
- **SOPS age key** — the private key is NOT in this repo. Public recipient key is in `.sops.yaml`. Private key is in 1Password (groupware vault). To encrypt: `sops encrypt --age <public-key> --encrypted-regex '^(data|stringData)$' --in-place <file>`.
- **Secrets** — all Kubernetes secrets are SOPS-encrypted in `deploy/`. Never commit plaintext secrets. Never log secret values.
- **Containers** — run as non-root (TODO: add USER directive to Dockerfiles). Resource limits on all deployments.
- **Admin commands** — gated by `is_admin()` check against the `admins` table. Root admin seeded from `ADMIN_EMAIL` env var on bot startup.
- **Slack input** — all user text goes through `sanitize_user_input()` before processing. GraphQL queries use parameterized variables.
- **External URLs** — fetched with timeout, size limits, and redirect following budget. No SSRF protection yet (TODO).

## Writing style

Direct, concise, practitioner-friendly. No jargon overload. Keep the framework generic — organization-specific content belongs in content sources, not in Mother Tree itself.
