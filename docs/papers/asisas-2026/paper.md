# Mother Tree: A Methodology-First, Choreographed Multi-Agent System for Individual–Collective Commercial Intelligence

**Jurg van Vliet, Flavia Paganelli, Jasper Geurtsen**
*Aknostic, Amsterdam, the Netherlands*
`{jurg, flavia, jasper}@aknostic.com`

**Submission:** ASISAS 2026 — *Architecting Secure, Intelligent, and Sovereign Agentic Systems* (workshop at ECSA 2026). Experience report (full paper).

---

**Abstract.** Most agentic systems are capability-first: take a frontier model, give it tools, point it at a goal, and trust autonomy to deliver. We report on *Mother Tree*, a multi-agent commercial-intelligence system that does the opposite — it starts from a sales methodology (the Mycorrhizal Method, drawing on consultative-selling literature and Simard's forest mutualism) and lets the methodology dictate the agents.

Three rejections shaped the architecture. *Choreography over autonomy:* Python jobs on Kubernetes call LLMs at scheduled points, with multi-judge quorum scoring and a designed human-in-the-loop boundary; we rejected open agent-orchestration frameworks as too complex to operationalise for collective use. *Freedom to operate over frontier dependency:* the open-weight-tractable workloads run on European inference via Scaleway, and the workloads where frontier quality still matters (deep extraction, single-message classification, judge arbitration) run on a small, named, replaceable Anthropic surface. *Coach over replacement:* agents train, prep, and debrief salespeople; they never act for them.

Individuals and the group teach each other through the system: signals from delivery work enrich a vector-indexed database that trains the next sales conversation, which in turn surfaces the next signal. We describe two layers — always-on jobs over PostgreSQL/pgvector and a Slack bot over GraphQL — a persona ensemble (Seth Godin, Lawrence Miller), and a discipline engine (pulse, weekly review, monthly retrospective, prep and debrief).

We report what the stack costs in model quality and what it buys in residency, optionality, and independence, and offer *freedom to operate* as a plainer frame than *sovereign*.

**Keywords:** agentic systems · multi-agent architecture · commercial intelligence · choreographed agents · methodology-first design · freedom to operate · European AI inference · multi-perspective scoring · experience report

---

# 1 Introduction

Most agentic systems shipping in 2026 start from the model: take a frontier model, give it tools, point it at a goal, and trust autonomy to do the rest. The model and the orchestration runtime end up shaping the system; the methodology the system serves, if there is one, is added later in prompts and guardrails.

This paper reports on the opposite approach. *Mother Tree* is a multi-agent commercial-intelligence system in production at Aknostic since early 2026, built for consultative sales. It starts from a sales methodology (the Mycorrhizal Method) and lets that methodology dictate the agents.

The inversion produced three architectural rejections:

- **Choreography over autonomy.** Mother Tree has nine named personas but no autonomous-agent loop and no agent runtime. We spent two weeks evaluating agent-orchestration frameworks (those we tested are named in §8.1) and stepped back; the framework's own operating burden, on top of the system using it, did not pay for itself in our setting. What we use instead is Kubernetes CronJobs, plain Python, and LLM calls at named points in a fixed pipeline.
- **Freedom to operate over frontier dependency.** The core ingestion, training, and discipline pipelines run end-to-end on European open-weight inference (Scaleway: Qwen 3.5, Mistral Small, BGE Multilingual Gemma2 embeddings, with Devstral 2, Llama 3.3, and Gemma 3 as scoring judges). Anthropic's Claude Haiku 4.5 and Sonnet 4.6 appear only at the triage and arbitration boundary, and in two operational personas (Spotter and Weaver) that we have under active substitution. Closed frontier models are superior; they are not necessary.
- **Coach over replacement.** Mother Tree never acts on a salesperson's behalf. It trains them, preps them, debriefs them, and feeds signals from their work into the database that trains the next salesperson's next conversation. The link between individuals and the group is the central design claim.

The paper's contributions are correspondingly four:

1. A description and defence of a **methodology-first, choreographed** multi-agent commercial-intelligence system, deployed and used (§3, §4).
2. A demonstration that a **freedom-to-operate stack** on European open-weight inference is enough for non-trivial agentic work, with the costs at the edges named and the benefits reported as concrete properties: data residency by construction, model optionality, cost predictability, and no autonomous-loop lock-in (§5).
3. A working pattern of **individual–group cooperation**: passive signal capture from delivery people, active coaching for salespeople, lighter twice-weekly nudges for everyone else, all linked by one vector-indexed database (§6).
4. **Planned measurement of environmental impact** through KEIT, an open-source Kubernetes emissions monitoring tool we also build and run; the intent is that the conference's *sustainable, responsible autonomy* pillar can be reported in grams of CO₂ rather than asserted, with placeholder numbers in §7 to be replaced before submission.

We use *freedom to operate* throughout as a plainer frame than *sovereign*: *which choices about this system would we lose if a particular dependency were withdrawn?* The claim isn't that *sovereign* is wrong; it has just drifted toward rhetoric.

§2 introduces the Mycorrhizal Method. §3 describes the architecture, including a section on security and trust (§3.5). §4 defends choreography over autonomy. §5 defends freedom-to-operate inference. §6 traces the individual–group loop through a worked example. §7 sets up CO₂ measurement via KEIT (numbers pending). §8 discusses related work, lessons, and future work.

# 2 Background: the Mycorrhizal Method

Mother Tree implements a sales doctrine, the *Mycorrhizal Method*, which synthesises four sources. From **Simard** [Simard et al., *Nature* 1997; Simard, *Finding the Mother Tree*, 2021] and her work on substrate-mediated mutualism among forest trees we take the picture of a network that pre-exists the practitioners, subsidises them, and absorbs their contributions. From **Dixon, Adamson, and Toman**, *The Challenger Sale* identified that the highest-performing sellers do not match prospects' worldviews; they reframe them, and we take the *reframe* as the unit of value in a selling conversation. From Richardson's consultative selling [Richardson, *Perfect Selling*, 2008] we take the structure of the conversation as a sequence with named phases (first impression, probing, diagnosis, co-creation, close, service). From Wintzen's cell-based model of a professional services firm [*Eckart's Notes*] we take the framing of the user roles (*hunter*, *gatherer*, *citizen*) and the principle that a system serving many cells must privilege the substrate over the agents.

Three properties follow that the architecture must support:

1. **Substrate before agents.** The network pre-exists the practitioners. An architecture serving this methodology cannot privilege agency over the substrate. (§3.)
2. **Reframes are first-class.** The unit of value in a selling conversation is the reframe. The system therefore has to store reframes in a way it can address by query, score by panel, and teach from. Burying them in unstructured documents is the failure mode that motivated the schema in §3.1, the multi-judge admission in §4.2, and the training curriculum in §6.
3. **Conversation is structured.** Richardson's stages give us the structure of the prep, the conversation, and the debrief. The architecture instantiates this structure rather than collapsing it into a generic notification stream. (§3.2: discipline engine; §6: hunter flow.)

These properties are upstream of the architecture. They are why the system has the shape it has, rather than the shape a capability-first system would have produced.

# 3 Architecture

Mother Tree's architecture puts the database before the agents. Every persona, prompt, training piece, and briefing reads from one PostgreSQL database, produces text, and writes back. The schedule decides what happens next; the agents are the things that get called when it does.

This differs from a frontier model with persistent vector memory: a model with memory has private state it owns; our substrate has no owner and is read-write by many scheduled processes. Any agent can be swapped without losing memory; the memory cannot be swapped without losing every agent at once.

Two layers wrap the database (Fig. 1). The always-on layer is a set of scheduled jobs that ingest content, extract structured intelligence, score it, generate training material, and notice when a salesperson is overdue for a check-in. The interactive layer is a Slack bot speaking to the database through the GraphQL API; an operator-facing CLI (`mothertree`) calls the same API. Both layers call `jobs/mothertree/intelligence.py`, so there is exactly one path to commercial-intelligence data.

![Fig. 1: Two-layer architecture wrapped around the intelligence substrate. Always-on cronjobs and interactive surfaces both call `intelligence.py`; the inference plane is split between a large European open-weight core (Scaleway) and a small Anthropic boundary.](figures/fig1-architecture.pdf){width=40%}

## 3.1 The intelligence substrate

PostgreSQL 17 with `pgvector` 0.8.2 (CloudNativePG) is the source of truth. PostGraphile exposes the schema as a typed GraphQL API at `mothertree.aknostic.com/graphql`; the schema is the API. Authorisation is described in §3.5.

Six **commercial-intelligence (CI) tables** carry the substantive data: `change` (the change statements the organisation makes about the world), `worldview` (the beliefs and pains its audience already holds), `personas` (the people in those audiences), `competitors` (alternative responses to the same change), `insights` (consultative reframes, evidence, triggers, stakeholder lenses), and `signals` (observations gathered from delivery work or any channel conversation). User-facing tables (`users`, `admins`, `channel_links`, `training_progress`, `enrollment_requests`, `signal_threads`, `contacts`, `companies`) sit around them. Email is the canonical identity; Slack accounts attach to users via `channel_links`, calendar URLs sit on `users` directly.

Every CI table carries a `vector(3584)` embedding produced by **BGE Multilingual Gemma2** on Scaleway. Cosine distance (the `<->` operator) drives the semantic operations on those tables: training-source selection, briefing assembly, signal deduplication, foundation-record dedup before insertion, and organisation-profile element merging at an 85% similarity threshold. Vector search is the primary read pattern for CI data, alongside ID and email lookups for the user-facing tables.

## 3.2 The always-on layer

The always-on layer is a set of declarative cronjobs in `deploy/cronjobs/`, each invoking a subcommand of `jobs/cli.py`. **Foundation ingestion** (weekly) classifies marketing-surface documents and extracts change, worldview, personas, and competitor records context-aware: each document gets existing records as prompt context to suppress duplicates, with a cosine-similarity check before insertion. **Narrative ingestion** (daily) extracts consultative reframes, evidence, triggers, and stakeholder lenses anchored in those foundation records. **Discipline** runs the weekly review (Mondays 07:00 UTC), monthly retrospective (1st of the month, 08:00 UTC), calendar sync (once daily on weekdays; the same run emits prep two business days before each meeting and debrief three days after), and an account-review poll (weekly cron, quarterly effect — each account is processed only when its QBR cycle is due). **Pulse** scans every five minutes for due reminders, stale threads, stale contacts, pipeline nudges, and expired enrollment requests. **Training delivery** (daily) generates the next training piece for each enrolled user according to role, stage, and chapter. **Embed-backfill** generates BGE embeddings for any record that lacks one.

Each job is a self-contained Python entry point with no state outside the database. There is no message queue and no DAG runtime: the cron schedule plus PostgreSQL is the orchestrator.

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

# 4 Choreography over Autonomy

The dominant pattern in agentic systems is to give a frontier model a goal and a set of tools, and to let an autonomous loop decide what to do next. We evaluated this pattern across several agent-orchestration frameworks (§8.1) and rejected it as the basis for a collective commercial tool.

## 4.1 What autonomy implies for a collective tool

Autonomy works for a single user with a discrete task. It fits poorly when the agent serves a collective, where its output enters a substrate read by other people, its decisions accumulate into a structure that subsequent decisions rely on, and its mistakes propagate through other agents that consume its output. Two properties matter most in this setting, and an autonomous loop handles both weakly.

The first is **auditability and reviewability**. The choreography pattern preserves a trace that autonomy hides: each record carries its source document and the run that produced it (`ingestion_log`), and every LLM call has a named entry point in the codebase. The substrate today stores the median of the three judge scores per record as `confidence`; the columns we have not yet added (model-per-record, prompt context, raw judge scores) and the reviewer queue we have not yet built on top of flagged records are named gaps (§3.5, §8.3) rather than denied features. The architectural point is that adding them is a column or a notifier, not an unwind. An autonomous loop with internal tool calls, retries, and self-corrections does not lose this information by accident; it loses it on purpose, because the loop is built to manage internal state rather than expose it. It offers one human boundary per task; the design here is to provide one per LLM call, and we have started where the cost is lowest.

The second is **boundedness**. An autonomous agent can call tools many times before it terminates, and the number of calls is itself a function of the model's reasoning. Cost, latency, and rate limits all become probability distributions over the run rather than functions of the input. A system that runs hundreds of ingestion documents per week, a thousand pulse cycles per day, and a daily training piece for every enrolled user does not want distributional cost; it wants budgets that survive contact with a quarterly forecast.

These frameworks address parts of this through tracing and replay. We tested far enough to conclude that operating the framework (its own ops burden on top of the system using it) costs more than writing the schedule directly. We are also sceptical that any published multi-agent benchmark would survive twelve months in production unchanged; our schedule has, and we attribute that to the cron-and-Python honesty of the pattern more than to any single design choice.

Working through the capability-first version of Mother Tree clarifies the architectural difference. That version would start with a frontier model, give it the tools the cronjobs currently perform (read sitemap, parse document, write PostgreSQL, schedule Slack message), set "improve sales performance" as the goal, and run an autonomous loop per practitioner. The user-facing surface would feel similar; the underlying state would not. Each user would have a private agent with private context, and cross-user mutualism (gatherer signal arriving in hunter prep) would require either a shared agent or an explicit hand-off protocol. The substrate is incidental in that version; in ours, it is the thing the rest of the system is built around.

## 4.2 The choreography pattern

We use a small set of conventions, applied uniformly:

1. **Workflows are scheduled, not driven.** Each pipeline (foundation ingestion, narrative ingestion, training delivery, weekly review, monthly retrospective, calendar sync, pulse) is a Kubernetes CronJob with a fixed schedule. There is no agent that decides when to run; the cron does.
2. **LLM calls happen at known points.** Each call has a name in the codebase (e.g. `extract`, `extract_deep`, `extract_profile`, `score`, `triage`, `arbitrate`, `character_respond`), a model assignment that is either hardcoded or supplied from config, a fixed prompt template, and a fixed input contract. The LLM is a function with a stable signature, not an agent with a goal.
3. **Multi-judge scoring and triage replace self-evaluation.** Every narrative-ingest record is scored by three independent Scaleway judges (Devstral 2 123B, Llama 3.3 70B, Gemma 3 27B) on a 0–1 scale. Decisions are by quorum (`min ≥ 0.7` accepts, `max ≤ 0.4` drops, `spread ≥ 0.3` flags). Flagged records escalate to a Haiku 4.5 triage call that either defers to Sonnet 4.6 arbitration or marks the record `flagged=True` for human review. Triage isn't autonomy; it's a fixed dispatcher acting on a probabilistic input. The reviewer-facing queue on top of the flag is future work (§8.3).
4. **Writes are reversible.** `mothertree dump` and `mothertree restore` are operator-run commands that snapshot the substrate to JSON and restore it. Automating the snapshot is on the gap list.
5. **Idempotency is enforced at the data layer.** Foundation extraction runs a cosine-similarity check against existing records before insertion; signals are deduplicated by thread and content; embeddings are backfilled lazily by `embed-backfill`. Running anything twice is, by construction, identical to running it once.

## 4.3 Trade-offs we accepted

The system **cannot improvise**. If foundation ingestion encounters a document that does not classify as any known type, it falls through to a default extractor; it will not write itself a new pipeline; a human will, at the next opportunity. That is the property that makes the system reviewable.

Latency is **right-time, not real-time**. The pulse runs every five minutes; calendar prep arrives two business days before a meeting; the debrief arrives three days after. We optimise for the right time, which an autonomous agent reasoning about urgency would deliver faster in principle but more inconsistently in practice. The five-minute pulse is the system's unit of attentiveness, and everything that needs to feel responsive runs inside that window.

Throughput is **bounded**. The cron schedule sets the upper bound on extraction volume, not the model. We have so far not encountered a case where this bound was wrong: the substrate accumulates faster than any human consumer can read it.


# 5 Freedom to Operate

We call this *freedom to operate* rather than *sovereignty*. The reframe is not a political move; it is a procurement question we found ourselves answering more usefully under one phrasing than the other.

## 5.1 The reframe

In the European conversation, "sovereign AI" has drifted toward a political register about jurisdiction, national capability, and refusing a foreign government's reach. We do not dispute that register. We observe only that the phrase has been co-opted by the hyperscalers whose dominance it nominally addresses, and that what is left does more rhetorical than operational work. Asking instead which choices about this system would we lose if a particular dependency were withdrawn tomorrow gives us a cleaner answer: a system has freedom to operate when the answer is "few enough to continue." By that test, Mother Tree could continue without US frontier inference, with the quality cost named in §5.3. Section 5.2 shows where the Anthropic dependencies sit today.

## 5.2 The model selection map

Mother Tree's models are configured in `jobs/mothertree/config.py`. Table 1 shows the assignment.

| Role | Model | Provider | Class |
|---|---|---|---|
| Light extraction & classification | Mistral Small 3.2 24B | Scaleway | Open weight, EU |
| Deep extraction (foundation, narrative) | Claude Opus 4.6 | Anthropic | Closed, US |
| Bot conversational tier (default) | Qwen 3.5 397B | Scaleway | Open weight, EU |
| Persona responses (Seth, Lawrence, trainer) | Qwen 3.5 397B | Scaleway | Open weight, EU |
| Embeddings | BGE Multilingual Gemma2 | Scaleway | Open weight, EU |
| Multi-judge scoring (3×) | Devstral 2 123B / Llama 3.3 70B / Gemma 3 27B | Scaleway | Open weight, EU |
| Spotter (signal detection) | Claude Haiku 4.5 | Anthropic | Closed, US |
| Weaver (signal structuring) | Claude Sonnet 4.6 | Anthropic | Closed, US |
| Triage (judge disagreement) | Claude Haiku 4.5 | Anthropic | Closed, US |
| Arbitration | Claude Sonnet 4.6 | Anthropic | Closed, US |
| Bot conversational tier (premium, opt-in) | Claude Sonnet 4.6 | Anthropic | Closed, US |

The shape that matters is the named, replaceable Anthropic surface. **Embeddings, multi-judge scoring, training generation, and persona conversation** run on European open-weight inference on Scaleway. **Deep extraction, single-message classification (Spotter, Weaver), and judge arbitration** run on Anthropic because, as of this writing, no open-weight model we tested was reliable enough at the false-positive rates the work demands. The architectural commitment of the paper is not "no Anthropic in the runtime"; it is that every Anthropic call is named, can be substituted (we have tried), and the substrate, the schedule, and the data layer do not depend on Anthropic-specific features.

## 5.3 The cost

Open-weight models we have tested are materially inferior to frontier proprietary models for the workloads where judgement is concentrated: single-pass classification (Spotter, Weaver, triage, arbitration) and structured deep extraction. Qwen 3.5 397B in the Spotter and Weaver roles produced higher false-positive and false-negative rates on test inputs; for deep extraction it produced thinner reframes and looser schema adherence than Claude Opus 4.6. We choose quality at those points and run Qwen everywhere else, where the output is paragraphs the user reads rather than records the substrate has to live with.

## 5.3.1 Observed properties of the stack

The numbers below come with a piece of context. Our first ingestion run returned 944 foundation records on a corpus we expected to be small — hundreds of near-duplicates differing only in surface phrasing. We rewrote extraction to be context-aware (each document gets the existing records in its prompt) and reran on the same input; the new count was 303. We have been suspicious of model-only benchmarks since.

Corpus: 289 source documents (110 foundation, 179 narrative) from the Aknostic marketing repository and the Clouds of Europe sitemap.

*Context-aware extraction.* Qwen 3.5 397B with existing records injected as prompt context produced 303 foundation records on the same corpus where Mistral Small 3.2 with no context produced 944, a 68% drop in extraction-time duplicates. LLM-driven consolidation across all records (running over the Qwen output) reduced that further to 189, with the strongest effect on personas (28 → 9) and competitors (67 → 17).

*Judge behaviour on this corpus.* A Qwen narrative-extraction run with multi-judge scoring on the test corpus produced 816 scored insights; 815 cleared the quorum-accept threshold and 1 was flagged. Mean judge confidence was 0.87, median 0.88. A separate Opus extraction with cross-record consolidation on the same corpus produced 977 insights (used for downstream training), of which 2 were flagged. We report both because they came from different extraction backends; the architectural property under test (quorum-based admission, not a specific extractor) is the same in either case.

This last number deserves a caveat. A 99.9% auto-accept rate could mean the system is well-calibrated or it could mean the judges (all trained on overlapping internet data) are correlated and the thresholds are lenient. Our corpus is also single-voice: a marketing repository plus one sitemap, both reflecting one organisation's view. We expect higher disagreement on a more heterogeneous corpus. Building a reviewer-facing queue with sampling so we can audit auto-accepted records against human judgement is on the future-work list (§8.3).

## 5.4 The benefit

Four concrete properties come up repeatedly in design conversations:

1. **Data residency at the substrate.** Every byte at rest, every backup, every embedding, and every interaction record lives in European infrastructure (Scaleway, Paris). The Anthropic surface is named in §5.2; whether the deep-extraction call to it counts as a residency violation is a deployment-time decision against the deploying organisation's data-classification regime, not a system-level claim.
2. **Model optionality.** Because the core relies on the OpenAI-compatible API shape, swapping inference providers requires changing one base URL and one set of model identifiers. We have, in the lifetime of the project, swapped extraction models several times without architectural change.
3. **Cost predictability.** Open-weight inference on Scaleway is priced per-token. Frontier providers use tier-based pricing and rate limits that turn forecasting into a step function above certain volumes. Because each cron tick has a known token budget, provider switches are arithmetic.
4. **No autonomous-loop lock-in.** The system does not depend on a particular agent runtime, and so does not inherit a particular runtime's view of which models support tool use, parallel function calling, or specific structured-output formats. The choreography described in §4 makes the inference layer a function, not a partner.


# 6 Mutualism in Practice

Section 3's architecture produces a particular loop. Mother Tree distinguishes three user roles: a **hunter** carries the full sales choreography and is the primary audience of the training engine and discipline rhythm; a **gatherer** is a delivery person with first-hand client contact but no sales choreography, whose Slack messages pass through the Spotter/Weaver/Archivist pipeline to deposit signals into the substrate; a **citizen** is anyone else, on a lighter twice-weekly curriculum. Role escalation (citizen → gatherer → hunter) is admin-gated; first contacts are auto-created as citizens. Consent for signal capture is enforced through enrollment rather than at the message level (§3.5). The loop these roles share is best shown by example.

The trace below illustrates the mechanism with a real reframe from the substrate and a plausible signal that fits it; we anonymise the company. A delivery engineer in a project channel writes "they're worried about NIS2 — every meeting we keep getting pulled back to compliance timelines." The Spotter recognises the signal; the Weaver structures it as `signal{type: "regulatory_concern", topic: "NIS2", company: …, urgency: "high"}`; the Archivist writes it. The signal's embedding lands close to an `insights` row in the substrate whose reframe reads, in part:

> "Sovereignty and cost reduction aren't competing board priorities — they're the same initiative. The reason your cloud bill is so high is the same reason your data is exposed: you're paying a premium to rent infrastructure from a US company that's legally obligated to hand it over."

Some weeks later, a hunter has a meeting with the same company's CTO. Two business days before, the calendar-sync job queries the substrate by vector similarity to company, contact role, and recent signals; the March signal surfaces, and the prep message flags the conversation, names the resonant worldview ("compliance is being imposed faster than we can adapt"), and points the hunter at the reframe above. Three business days after the meeting, the debrief prompt asks what was confirmed, what was rebutted, and what was new; the hunter's answer becomes a signal that the next CI ingestion incorporates.

The loop closes because the gatherer's note, the database, and the hunter's prep are linked by vector similarity, not by anyone writing a report. The gatherer doesn't need to know the hunter exists; the hunter doesn't need to know the gatherer wrote anything; the database accumulates the conversation between them.

**Usage scale at Aknostic.** The always-on layer has run since early 2026. Active end-user usage began 14 April 2026; numbers below cover the 30-day window to 13 May 2026. Four users are enrolled (one hunter, three citizens; no gatherers yet) across four linked Slack accounts. Over the window the system captured 109 signals from channel chatter and recorded 237 Slack interactions (187 with the hunter, 50 across the three citizens). The weekly review cron fired four times and the monthly retrospective once; multiple weekly deliveries during the window misrouted to the wrong Slack account because of a binding bug that has since been fixed. The substrate holds 62 contacts across 64 companies. This is a small deployment in its first weeks, not a mature one.

# 7 Sustaining the Stack: Measured Emissions

The third ASISAS pillar (*sustainable, independent, and responsible autonomy*) is decorative until you can answer it with a number. For a Kubernetes-deployed agentic system, the relevant numbers are watt-hours, grams of CO₂-equivalent, and litres of water.

We measure them, on the same cluster Mother Tree runs on, with KEIT.

## 7.1 KEIT

**KEIT** (the *Kubernetes Emissions Insights Tool*) is an open-source (Apache-2.0) emissions monitoring stack developed by Aknostic [https://github.com/aknostic/keit]. It composes Kepler (per-process energy via kernel performance counters), Prometheus and Grafana (metrics and visualisation), ElectricityMaps (live regional grid carbon intensity, Paris for our Scaleway deployment), and Boavizta (hardware embodied-emission values), all installed via Helm. KEIT runs in its own namespace; its own CO₂ cost is a small constant we account for explicitly.

## 7.2 Per-namespace attribution

The relevant property for an experience report on Mother Tree is that KEIT performs **per-namespace attribution**. Energy is allocated to workloads via Kepler's per-process accounting; embodied emissions are pro-rated across namespaces by node-share; grid intensity is applied uniformly to the cluster's region. The result is a per-namespace daily figure: grams of CO₂-equivalent and litres of water consumed by the `mother-tree` namespace specifically.

This produces the answer the responsibility claim needs.

## 7.3 The numbers

> *§7.3 to be completed by F. Paganelli and J. Geurtsen with operational figures from the Aknostic cluster. Expected content: daily mean CO₂-equivalent for the `mother-tree` namespace broken down by workload class (ingestion, training, pulse, bot, Anthropic egress); daily water use; the KEIT footprint as a fraction of the measured Mother Tree footprint; and reasoned counterfactual comparisons against (i) the same workload through US-hosted frontier inference and (ii) the same workload re-cast as an autonomous-agent loop with retries and tool-call branching.*

## 7.4 What this measures, and what it does not

KEIT measures the operational and embodied emissions of the Kubernetes cluster running Mother Tree; it does not measure the emissions of inference calls that leave the cluster (Scaleway and Anthropic), which we estimate separately from per-call token counts scaled by regional grid intensity. Both estimates are approximate and reported with their assumptions. What KEIT will let us claim, once §7.3 is filled in, is that the part of the system we host has a measured environmental footprint; whether the architectural decisions in §3 and §4 (scheduled cron, no autonomous retry loops) make a measurable difference is a comparison we have not yet run.

# 8 Related Work, Lessons, Future Work

## 8.1 Related work

**Agent orchestration frameworks.** We evaluated frameworks like CrewAI, LangGraph, and AutoGen as candidate runtimes. All present a programming model in which agents pursue goals via tool calls and inter-agent messages, with the framework managing the loop. Our objection (§4.1) is not to the frameworks but to that programming model as the basis for a collective tool: it conflates the agent's internal reasoning with observable system state. Workflow engines such as Airflow, Prefect, and Dagster make the opposite trade-off and are closer in spirit to Mother Tree's schedule, though they are not LLM-aware and lack the multi-judge admission pattern.

**LLM-as-judge and ensemble scoring.** The multi-judge pattern in §4.2 is closest in spirit to recent LLM-as-judge evaluation work, but used here for production *admission* rather than evaluation: the judges decide whether a record enters the substrate, not whether a model output is good.

**Sustainability of agentic systems.** Most published sustainability work for LLM-based systems addresses inference energy at the token or model level rather than at the deployed-system level. We are not aware of prior work measuring an agentic system's footprint per Kubernetes namespace on a live cluster; §7 reports on **KEIT** [Paganelli & Geurtsen, https://github.com/aknostic/keit] as the measurement substrate for that claim.

**Methodology-first design** has parallels in domain-driven design and in the broader claim that doctrine should precede architecture; we are not aware of explicit prior application to agentic-system design.

As an experience report, we make no broader survey claims.

## 8.2 Lessons and three patterns

Three lessons stand out from operating Mother Tree as it currently exists.

1. **Methodology first scales architectural decisions.** When a new model becomes available, the question we ask is not "is this state-of-the-art?" but "does this serve the methodology better than the current model?" The methodology compresses the decision space. Without it, every model release is a refactor.
2. **Choreography is auditable in a way autonomy is not.** Every step has a deterministic trigger and a named LLM call; the substrate records source document, run, and median confidence per record. Other dimensions (model-per-record, prompt context, raw judge scores) are named gaps in §3.5, not hidden state. When something goes wrong three months later, the trace that exists is in the database rather than in an agent's working memory, and the trace that does not yet exist is a column away.
3. **The mutualism is the moat.** A single seller using Mother Tree gets less out of it than a network using Mother Tree, because the substrate that prepares them is built by the network. We did not design this property retrospectively; it fell out of treating individual usage and collective enrichment as one feedback loop.

Three patterns are worth lifting out into the language of architectural patterns, because they generalise beyond sales. *Substrate-mediated mutualism* is a read-write substrate owned by many independent processes; no process owns the state, so individual usage and collective enrichment become a single feedback loop. *Choreographed multi-persona* is many addressable LLM-backed components composed by an external orchestrator (cron, a bot pipeline) rather than by inter-agent messaging; the system is multi-agent in the sense of having many components, without becoming agentic in the sense of having loops of internal reasoning. *Quorum-based admission* uses multi-judge scoring to decide whether a record enters the substrate, not to evaluate model output: the decision is by quorum (`min` for accept, `max` for reject, `spread` for triage), and the design places a human boundary per-LLM-call rather than per-task (the reviewer-facing queue that consumes flagged records is future work, §8.3). We have not seen this third pattern named in the literature; we think it is the smallest defensible alternative to single-model self-scoring in production.

## 8.3 Future work

**Reviewer-facing queue for flagged records.** Quorum-based admission currently marks judge-disagreement records as `flagged=True` and leaves them. Routing flagged records to a human reviewer (a Slack channel or CLI) and sampling auto-accepted records into the same queue for calibration is the most important trust work we owe the system — what turns the quorum pattern from "self-evaluating with three votes" into "three votes plus a human spot-check".

**Shrinking the Anthropic surface.** Deep extraction, the Spotter, and the Weaver are the remaining Anthropic-essential calls in production. Open-weight progress over the next 6–12 months should make at least some of these substitutable; a candidate replacement for Spotter and Weaver (Qwen 3.5 397B with a tightened prompt plus a Devstral verification pass) is under evaluation.



## 8.4 Conclusion

Mother Tree is a methodology-first, choreographed multi-agent system in production: open-weight inference where it suffices, a named replaceable Anthropic surface where frontier quality matters, scheduled jobs in place of autonomous loops, and the individual salesperson and shared database as one feedback loop. The architecture answers the three ASISAS pillars — multi-agent without an agent runtime, trust through auditable scheduling and quorum-based admission, sustainability to be reported in grams of CO₂ rather than asserted (§7, pending) — with the named gaps to close before claiming more.

---

## References

> *To be completed before paper submission. Anchor citations:*
>
> - Simard, S. W., et al. (1997). Net transfer of carbon between ectomycorrhizal tree species in the field. *Nature*, 388(6642), 579–582.
> - Simard, S. W. (2021). *Finding the Mother Tree: Discovering the Wisdom of the Forest*. Knopf.
> - Dixon, M., Adamson, B., & Toman, N. (2011). *The Challenger Sale: Taking Control of the Customer Conversation*. Portfolio.
> - Richardson, L. (2008). *Perfect Selling*. McGraw-Hill.
> - Wintzen, E. (2007). *Eckart's Notes*. Lemniscaat.
> - Paganelli, F., & Geurtsen, J. (2026). KEIT: Kubernetes Emissions Insights Tool. Apache-2.0. https://github.com/aknostic/keit.
> - PostGraphile project; pgvector project; CloudNativePG project; Flux CD project; Kepler project; Boavizta project; ElectricityMaps; Scaleway Generative APIs documentation.
