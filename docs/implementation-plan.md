# Mother Tree — Implementation Plan

## Current status (2026-04-01)

| Phase | Status | Notes |
|-------|--------|-------|
| Prerequisites | DONE | Namespace, Flux, Inference, S3, DNS — all provisioned |
| 1. Foundation | DONE | PostgreSQL 17 + pgvector 0.8.2 (migrated from pgvecto.rs), PostGraphile GraphQL (migrated from Hasura), 11 tables, TLS, S3 backups, vector embeddings on all CI tables |
| 2. Content ingestion | DONE | Dual-lens (foundation: Saga, narrative: Lena), three sources, context-aware extraction (Qwen 3.5), multi-model scoring, pre-insert dedup, skip-unchanged. 303 foundation records, narrative extraction running. |
| 3. Slack bot | DONE | Unified pipeline, character ensemble (Mother Tree, Saga, Lena, Spotter, Weaver), signal capture, training via DM |
| 4. Calendar | DONE | iCal feed sync, prep 2 days before meetings, debrief prompt 3 days after |
| 5. Training engine | DONE | Role-specific curriculum (hunter/gatherer/farmer/citizen), exercise generation with answer randomization, proficiency decay + refreshers, progress tracking, streak + nudges, citizen inspiration flow (4 stages, 2x/week), vector-driven source selection. CronJob deployed. |
| 6. Rhythm | MOSTLY DONE | Stale relationship checks (weekdays 08:00), weekly pipeline review (Mondays 08:00), monthly retrospective (1st of month 09:00, LLM-synthesized). Signal scanner not started. |
| 7. Claude Code skill | DONE | `/mothertree` skill using shared `ask` module (`mothertree/ask.py`) |
| — Character ensemble | DONE | Mother Tree (Librarian), [Saga](inspirations.md), [Lena](inspirations.md), Dispatcher, Spotter (signal extraction), Weaver (relationship graph) |
| — Organization profile | DONE | Wired into ingestion pipeline + context, vector-based dedup (85% similarity merge) |
| — Vector embeddings | DONE | All CI tables (insights, change, worldview, personas, competitors, signals, organization) with BGE Multilingual Gemma2, semantic search via pgvector cosine distance |

---

## Prerequisites (groupware team)

Requested and confirmed. Groupware will provision:

- [x] Namespace `mother-tree` with namespace-scoped ServiceAccount + kubeconfig
- [x] Flux GitRepository + Kustomization syncing `deploy/` from `git@gitlab.aknostic.com:aknostic/mother-tree.git`
- [x] Scaleway Generative APIs key (pay-per-token, multiple models)
- [x] S3 bucket `groupware-mother-tree-backups` (endpoint: `s3.fr-par.scw.cloud`)
- [x] DNS: `mothertree.aknostic.com` pointing at cluster gateway with TLS

SOPS age public key received: `age1ny5rpz82l25pxw3esxrv6e2g5wy3j09uwgmwu6ygh6q9k6jajp3srl0ru5`
CNPG is cluster-wide — our Cluster resource in `deploy/` will be picked up automatically.

**Our action items:**
- [x] Generate deploy key for GitLab repo (read-only)
- [x] Add deploy key to GitLab repo, share with groupware
- [x] SOPS-encrypt secret files with real credentials
- [x] Uncomment secrets in `deploy/kustomization.yaml`
- [x] Apply `schema.sql` to the database
- [x] Verify PostGraphile picks up the schema and generates GraphQL API

## Phase 1: Foundation — Database and API

**Goal:** PostgreSQL running, PostGraphile serving GraphQL, schema deployed. Anyone can query Mother Tree.

**Complete.** All infrastructure running:
- [x] CNPG PostgreSQL 17 + pgvector 0.8.2 deployed via Flux (migrated from deprecated pgvecto.rs)
- [x] 11 tables with PostGraphile GraphQL API live at `https://mothertree.aknostic.com`
- [x] SOPS-encrypted secrets (S3 backup, GraphQL admin, Scaleway AI)
- [x] TLS + security headers via groupware-managed HTTPRoute
- [x] Namespace managed by groupware (labels, route, TLS); we deploy workloads only

**Lessons learned:**
- Namespace manifest should not be in our deploy/ — groupware owns it (labels, HTTPRoute, TLS)
- pgvector 0.8.2 extension for vector similarity search (migrated from pgvecto.rs on 2026-04-01 — pgvecto.rs is deprecated and incompatible with CNPG pgvector image)
- CNPG v0.23.0 does not support `.spec.postgresql.extensions` — use `shared_preload_libraries` + `postInitTemplateSQL`

## Phase 2: Content Ingestion — Three Sources to Database

**Goal:** Content from three sources is continuously extracted, structured, and loaded into PostgreSQL. New content automatically becomes training material.

**Three content sources:**

1. **Marketing repo** (`gitlab.aknostic.com/aknostic/marketing`) — structured strategy docs: personas, positioning, case studies, competitive intel, sales narratives. Changes slowly. Structured extraction into typed tables.

2. **Clouds of Europe** (`clouds-of-europe.eu/sitemap.xml`) — published articles on sovereignty, regulation, cloud independence. Changes frequently. Each new article is a potential reframe or training exercise.

3. **Aknostic blog** (`aknostic.com/sitemap.xml`) — thought leadership, technical content, client stories. Same pattern as CoE.

**Completed:**
- [x] Content ingestion CLI (`jobs/cli.py`) with five input modes (file, dir, repo, url, sitemap)
- [x] Dual-lens extraction: foundation (Saga) and narrative (Lena)
- [x] Deep extraction with Qwen 3.5, classification with Mistral Small 3.2
- [x] Context-aware foundation extraction: injects existing records to avoid duplicates
- [x] Pre-insert dedup check as deterministic safety net
- [x] Multi-model scoring for narrative (Devstral 2 123B, Llama 3.3 70B, Gemma 3 27B)
- [x] Triage (Haiku 4.5) and arbitration (Sonnet 4.6) for disagreements
- [x] Skip-unchanged detection (content hash in ingestion_log)
- [x] Foundation CronJobs deployed (site + marketing, weekly)
- [x] Narrative CronJobs deployed (site + marketing + CoE, daily)
- [x] LLM-driven consolidation command for manual dedup
- [x] Dump/restore for testing pipeline stages independently
- [x] Foundation data: 303 records (92 changes, 116 worldviews, 28 personas, 67 competitors)
- [x] Vector embeddings on all CI tables (BGE Multilingual Gemma2), generated on insert
- [x] Semantic search via pgvector cosine distance wired into fetch_context, training, briefings, signals
- [x] Cross-table briefing function + CLI command (`mothertree brief <query>`)
- [x] Confidence scores in extraction prompts (LLM scores 0.0-1.0)
- [x] Organization profile wired into ingestion pipeline + context

**Deliverable:** All three content sources queryable via GraphQL. New articles automatically become training material within hours of publication.

**Dependencies:** Phase 1 complete. Marketing repo access. Public website access (sitemap).

## Phase 3: Slack Bot — Conversational Participant

**Goal:** Mother Tree is a conversational participant everywhere — DMs, channels, threads. One pipeline handles all contexts.

**Architecture:** Two-phase pipeline — detect (fast pattern matching producing annotations) feeds into a conversation engine (LLM). Triage decides when to respond in channels. Background signal extraction runs after responses. Three memory stores (DM, channel, thread) with the same interface.

**Completed:**
- [x] Unified pipeline: detect → triage → converse → extract
- [x] Character ensemble: Mother Tree (Librarian), Saga (positioning), Lena (consultative diagnosis), Dispatcher (routing)
- [x] Spotter: extracts entities, signals, actions, sales stage from conversations
- [x] Weaver: resolves entities into relationship graph (contacts, companies, deduplication)
- [x] Participates in all channels (not just #signals)
- [x] Commands via DM or @mention (no slash commands)
- [x] Training delivery in DMs (next, go, practice, exercise scoring)
- [x] Personas (ask saga/lena/trainer) in all contexts
- [x] Background signal extraction from any conversation
- [x] Channel memory and thread memory with configurable windows
- [x] Per-channel message serialization
- [x] Lazy persistence buffer for silent channel messages
- [x] Legacy signal_threads compatibility (fallback lookup)
- [x] Thread reminders for both legacy and new tables
- [x] Action markers ([ACTION:ci_save], [ACTION:capture_signal]) for background processing
- [x] Model selection: extraction model for simple commands, generation model for conversation
- [x] URL following (up to 3 per message)

**Deliverable:** Mother Tree participates naturally in all channels. Signal capture happens through conversation, not a separate action.

**Dependencies:** Phase 1 complete. Slack workspace admin access.

## Phase 4: Calendar Integration

**Goal:** Mother Tree knows about upcoming and past meetings. Hunters get prep before and debrief prompts after.

**Completed:**
- [x] iCal feed sync (no OAuth needed — works with any calendar that exports iCal)
- [x] Meeting prep delivered 2 days before (contact context, relevant insights, suggested reframes via Slack DM)
- [x] Debrief prompt delivered 3 days after meetings without debrief
- [x] Attendee matching against known contacts in database
- [x] Deploy as CronJob

**Deliverable:** Hunter gets meeting prep DM before a call. Gets debrief prompt after.

**Dependencies:** Phase 1, Phase 3 (Slack bot for DM delivery).

## Phase 5: Training Engine

**Goal:** Role-specific progressive training via Slack DM — from foundational concepts through scenario practice.

**Architecture:** Role-specific curriculum (`jobs/training/curriculum.py`) with stages and chapters. Each chapter specifies a trainer (Saga, Lena, or Mother Tree) and which CI tables provide source data. Exercise generation via Qwen 3.5. Proficiency tracking with time-based decay.

**Completed:**
- [x] Role-specific curriculum: Hunter (5 stages), Gatherer (5 stages), Farmer (3 stages)
- [x] Exercise generation from CI data (Qwen 3.5), grounded in curriculum chapter context
- [x] Exercise scoring with multi-question support (A/B/C answers)
- [x] Proficiency tracking per chapter with time-based decay
- [x] Refresher delivery when proficiency drops below threshold
- [x] Daily check logic: advance (new chapter), refresh (decayed), or nudge (idle 7+ days)
- [x] Progress display with completion count, streak, decay info
- [x] Streak tracking (consecutive training days)
- [x] Practice mode: drill specific topics on demand (`practice [topic]`)
- [x] Enrollment via DM (`enroll hunter/gatherer/farmer/citizen`) or CLI
- [x] Stage advancement and program completion logic
- [x] CronJob deployed (`deploy/training-deliver/`)
- [x] Citizen inspiration flow (4 stages, 5 interactions each, 2x/week nudges Tue/Thu, stage 3 is gatherer conversation)
- [x] Vector-driven source data selection (chapter purpose drives semantic search)
- [x] Answer randomization (shuffle A/B/C after LLM generation)
- [x] Repetition avoidance (recent topics injected as "ALREADY DISCUSSED")
- [ ] First real enrollment (Pim)

**Deliverable:** Daily training via Slack DM that adapts to each role, tracks proficiency, and refreshes decaying knowledge.

**Dependencies:** Phase 2 (content in database — stage 0 works with foundation only, stage 1+ needs narrative), Phase 3 (Slack bot).

## Phase 6: Rhythm Engine

**Goal:** Hunters have a daily/weekly/monthly rhythm enforced by the system.

**Completed:**
- [x] Stale relationship check (weekdays 08:00) — hot contacts: 7-day threshold, warm contacts: 14-day threshold, reminder to responsible hunter via Slack
- [x] Weekly pipeline review (Mondays 08:00) — pipeline state summary, stale items, upcoming follow-ups, delivered to hunters via Slack
- [x] Monthly retrospective (1st of month 09:00) — LLM-synthesized pipeline health, insight usage patterns, training progress per hunter

**Remaining:**
- [ ] Signal scanner job (RSS feeds, job boards, news feeds → classify → notify)

**Deliverable:** Daily/weekly/monthly rhythm running. Hunters get reminders, reviews, and retrospectives automatically. Signal scanner still to come.

**Dependencies:** Phase 1, Phase 2, Phase 3.

## Phase 7: Claude Code Skill

**Goal:** Hunters can query Mother Tree from Claude Code.

**Tasks:**
- [ ] Build Claude Code skill (`/mothertree`):
  - `briefing "Company X"` — pulls contact, company, interactions, relevant insights from PostGraphile GraphQL
  - `pipeline` — current pipeline summary
  - `signal "message"` — creates a signal record
  - `prep "Contact Name"` — meeting prep with reframe suggestions
  - `debrief` — guided debrief that writes to interactions
- [ ] Skill authenticates against PostGraphile (API key or JWT)
- [ ] Test with real data: hunter runs `/mothertree briefing "Company X"`, gets useful output

**Deliverable:** Working `/mothertree` skill in Claude Code.

**Dependencies:** Phase 1, Phase 2 (content in database for prep/briefing to be useful).

## Phase summary

| Phase | What | Depends on | Team |
|-------|------|------------|------|
| Prerequisites | Namespace, Flux, Inference, S3 | — | Groupware |
| 1. Foundation | PostgreSQL + PostGraphile + schema | Prerequisites | Farmer |
| 2. Content ingestion | Marketing repo → database | Phase 1 | Farmer + Hunter (validation) |
| 3. Slack bot | Signal capture + DM delivery | Phase 1 | Farmer |
| 4. Calendar | Meeting prep + debrief | Phase 1, 3 | Farmer |
| 5. Training | Daily refreshers + narrative dev | Phase 2, 3 | Farmer + Hunter (testing) |
| 6. Rhythm | Signals, reminders, reviews | Phase 1, 2, 3 | Farmer |
| 7. Claude Code skill | Interactive queries | Phase 1, 2 | Hunter |

Phases 3-6 can largely run in parallel once Phase 1 is done. Phase 2 should start early since Phases 5 and 6 need content in the database.

**Pim's involvement:** Test from Phase 3 onward. He gets the Slack DMs, tries the training, gives feedback on what works. Don't ask for structured feedback — watch what he uses and what he ignores.
