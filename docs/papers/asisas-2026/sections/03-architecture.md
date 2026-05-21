# 3 Architecture

Mother Tree's architecture puts the database before the agents. Every persona, prompt, training piece, and briefing reads from one PostgreSQL database, produces text, and writes back. The schedule decides what happens next; the agents are the things that get called when it does.

This differs from a frontier model with persistent vector memory: a model with memory has private state it owns; our substrate has no owner and is read-write by many scheduled processes. Any agent can be swapped without losing memory; the memory cannot be swapped without losing every agent at once.

Two layers wrap the database (Fig. 1). The always-on layer is a set of scheduled jobs that ingest content, extract structured intelligence, score it, generate training material, and notice when a salesperson is overdue for a check-in. The interactive layer is a Slack bot speaking to the database through the GraphQL API; an operator-facing CLI (`mothertree`) calls the same API. Both layers call `jobs/mothertree/intelligence.py`, so there is exactly one path to commercial-intelligence data.

![Fig. 1: Two-layer architecture wrapped around the intelligence substrate. Always-on cronjobs and interactive surfaces both call `intelligence.py`; the inference plane is split between a large European open-weight core (Scaleway) and a small Anthropic boundary.](figures/fig1-architecture.pdf){width=40%}

## 3.1 The intelligence substrate

PostgreSQL 17 with `pgvector` 0.8.2 (CloudNativePG) is the source of truth. PostGraphile exposes the schema as a typed GraphQL API at `mothertree.aknostic.com/graphql`; the schema is the API. Authorisation is described in §3.5.

Six **commercial-intelligence (CI) tables** carry the substantive data: `change` (the change statements the organisation makes about the world), `worldview` (the beliefs and pains its audience already holds), `personas` (the people in those audiences), `competitors` (alternative responses to the same change), `insights` (consultative reframes, evidence, triggers, stakeholder lenses), and `signals` (observations gathered from delivery work or any channel conversation). User-facing tables (`users`, `admins`, `channel_links`, `training_progress`, `enrollment_requests`, `signal_threads`, `contacts`, `companies`) sit around them. Email is the canonical identity; Slack accounts attach to users via `channel_links`, calendar URLs sit on `users` directly.

Every CI table carries a `vector(3584)` embedding produced by **BGE Multilingual Gemma2** on Scaleway (BGE is the BAAI General Embedding family; the Gemma2 variant is multilingual and produces 3,584-dimensional vectors). Cosine distance (the `<->` operator) drives the semantic operations on those tables: training-source selection, briefing assembly, signal deduplication, foundation-record dedup before insertion, and organisation-profile element merging at an 85% similarity threshold. Vector search is the primary read pattern for CI data, alongside ID and email lookups for the user-facing tables.

## 3.2 The always-on layer

The always-on layer is a set of declarative cronjobs in `deploy/cronjobs/`, each invoking a subcommand of `jobs/cli.py`. **Foundation ingestion** (weekly) classifies marketing-surface documents and extracts change, worldview, personas, and competitor records context-aware: each document gets existing records as prompt context to suppress duplicates, with a cosine-similarity check before insertion. **Narrative ingestion** (daily) extracts consultative reframes, evidence, triggers, and stakeholder lenses anchored in those foundation records. **Discipline** runs the weekly review (Mondays 07:00 UTC), monthly retrospective (1st of the month, 08:00 UTC), calendar sync (once daily on weekdays; the same run emits prep two business days before each meeting and debrief three days after), and an account-review poll (weekly cron, quarterly effect — each account is processed only when its QBR cycle is due). **Pulse** scans every five minutes for due reminders, stale threads, stale contacts, pipeline nudges, and expired enrollment requests. **Training delivery** (daily) generates the next training piece for each enrolled user according to role, stage, and chapter. **Embed-backfill** generates BGE embeddings for any record that lacks one.

Each job is a self-contained Python entry point with no state outside the database. There is no message queue and no workflow engine: the cron schedule plus PostgreSQL is the orchestrator.

Narrative ingestion additionally triggers **multi-judge scoring**. Three Scaleway judges (Devstral 2 123B, Llama 3.3 70B, Gemma 3 27B) independently score each candidate insight on a 0–1 scale. The decision is by quorum, not by mean: `min(scores) ≥ 0.7` auto-accepts (all three agree on accept); `max(scores) ≤ 0.4` auto-drops (all three agree on reject); `spread ≥ 0.3` escalates to a Claude Haiku 4.5 triage call which may defer to Claude Sonnet 4.6 for arbitration. Anthropic models also handle the deep extraction itself; §5 describes that decision and its boundary.

## 3.3 The interactive layer

The user-facing surface is the Slack bot; operators reach the same data through the `mothertree` CLI.

**The Slack bot** (`jobs/bot/`) listens in every channel it is invited to. The pipeline is the same for every message: buffer the message, detect whether it is a DM, a mention, or ambient channel chatter, triage it (question, signal, training response, admin command, or noise), and route to a conversation handler if it is conversational, or to a background extractor if it might carry a signal. One codepath for DM and channel. We don't use slash commands.

The persona ensemble has two flavours. **Conversational personas** live under `jobs/bot/characters/`. They are Seth (positioning), Lawrence (consultative selling), Mother Tree (the default integrative voice), and a Trainer dispatcher that invokes Seth and Lawrence and reconciles their answers. Each gathers persona-relevant data from `intelligence.py` and calls Qwen 3.5 397B on Scaleway. **Operational personas** run inside the pipeline: a Spotter (Haiku) decides whether a message carries a signal, a Weaver (Sonnet) turns captured signals into structured records, an Archivist writes them, and a Pulse character works out whose turn it is. Each has a prompt, an assigned model, and one responsibility, and runs only when called.

**The `mothertree` CLI** (`jobs/cli.py`) is the operator surface. Commands such as `mothertree ask`, `mothertree brief`, `mothertree pipeline`, and the admin set (`train enroll`, `admin add`, `rhythm weekly`) call the same GraphQL API and the same intelligence module the bot uses.

## 3.4 Deployment posture

Mother Tree runs in one Kubernetes namespace (`mother-tree`) on a Scaleway-hosted cluster operated by Aknostic's groupware team. **Flux CD** reconciles from `deploy/` with image automation; GitLab CI builds two container images (`Dockerfile.bot`, `Dockerfile.jobs`) with kaniko; secrets are SOPS-encrypted.

The data layer is **CloudNativePG** with continuous backups to `s3.fr-par.scw.cloud`. The GraphQL layer is a small Node service running PostGraphile behind an Envoy gateway. Inference goes to Scaleway's Generative APIs at `api.scaleway.ai`, hosted in Paris. Every byte of customer data, every model call, every backup, and every audit log lives within European jurisdiction. The Anthropic surface (triage, arbitration, the Spotter, the Weaver, and the bot's premium conversational tier) is the only call that leaves. Section 5 describes how small that surface is.

There is no agent framework in the dependency graph and no autonomous-agent loop. We are careful with the word "multi-agent": we mean it in the choreographed sense. The system has nine named personas, composed by an external orchestrator (cron, the bot pipeline, the persona dispatcher). Eight have their own prompt and model assignment (Seth, Lawrence, Mother Tree, Spotter, Weaver, Archivist, Pulse, Dispatcher); the Trainer is a router that invokes Seth and Lawrence and reconciles their answers into one response. Dispatcher itself does most of its routing through deterministic pattern matching, with an LLM triage call only for ambiguous messages. If the conference's threshold for "multi-agent" is "agents with goals", we do not clear it; if the threshold is "many addressable LLM-backed components composed by a fixed orchestrator", we are squarely in scope.

Mother Tree itself is developed using Claude Code, Anthropic's CLI development environment. Frontier tooling assists the engineering upstream; it is not part of the deployed runtime.

## 3.5 Security and trust

**Authorisation** is currently shared-secret: the PostGraphile endpoint is gated by a single `x-hasura-admin-secret` header check in an Express middleware; user-level authz is enforced one layer up by restricting which Kubernetes workloads carry the secret. We do not use PostgreSQL row-level security. Admin actions inside the bot are gated by an `admins` table with `granted_by` and `granted_at` columns, seeded from the `ADMIN_EMAIL` environment variable on startup — a permissions check inside the bot, not an authorisation boundary against the GraphQL surface.

**Auditability** is partial. Every LLM call has a named entry point (`extract`, `extract_deep`, `score`, `triage`, `arbitrate`, `character_respond`) with a model assignment either hardcoded or set from config. The `ingestion_log` table records per-source content hashes and record counts per run, so an extraction can be traced to the source document and the run that produced it; prompt context and raw judge scores are not persisted, only the median (stored as `confidence`). The substrate can be dumped and restored via `mothertree dump` / `mothertree restore`, both operator-run rather than automatic — a gap to be closed.

**Trust in extracted records** is enforced at the data layer by the multi-judge quorum described in §3.2. The failure mode the panel guards against is single-model bias; the failure mode it does not guard against is judge collusion, all three agreeing on a plausible-but-wrong record. The current implementation marks such records as `flagged=True` in the `insights` table and leaves them there. A reviewer-facing queue with sampling of auto-accepted records is future work (§8.3).

**Consent** is enforced at enrollment, not at the message level. Hunters and gatherers are admin-enrolled (`enroll <email> as <role>`); citizens are auto-created on first contact for the lighter inspiration path; any user can be removed. Passive channel ingestion is workspace-scoped: the workspace owner consents on behalf of the workspace when installing the app. Per-message consent UI is intentionally absent because the appropriate consent boundary for a tool aimed at a deploying organisation (not at end-customers) is workspace installation plus role enrollment.

**Hardening posture.** Containers run as non-root, secrets are SOPS age-encrypted (private key in 1Password, decryptable by Flux), backups go to Scaleway Object Storage in the cluster's Paris region. The named gaps are SSRF protection on external URL fetches and lack of adversarial-input testing against the bot.
