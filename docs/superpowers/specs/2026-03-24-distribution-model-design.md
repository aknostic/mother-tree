# Distribution Model Design — Open Source + Subscription

## Summary

Mother Tree ships as an opinionated open source project (EUPL 1.2) and a managed subscription service. The code is identical. The subscription delivers operational convenience: onboarding, hosting, continuous improvement. Target audience: small (2-10 person) consultative sales teams who hate their CRM.

## 1. Wardley Map

Value chain from user need to infrastructure:

```
                    Genesis    Custom     Product    Commodity
                    ·          ·          ·          ·
User Need           ·          ·          ·          ·
"Win more deals     ░░░░░░░    ·          ·          ·
 without CRM pain"  ·          ·          ·          ·
                    ·          ·          ·          ·
Methodology         ·          ░░░░░░░    ·          ·
(Mycorrhizal        ·          ·          ·          ·
 Method)            ·          ·          ·          ·
                    ·          ·          ·          ·
Conversational      ·          ░░░░░░░░░░░·          ·
Coach (Slack bot)   ·          ·          ·          ·
                    ·          ·          ·          ·
Training Engine     ·          ·          ░░░░░░░    ·
                    ·          ·          ·          ·
Content Pipeline    ·          ·          ░░░░░░░    ·
(extract/score)     ·          ·          ·          ·
                    ·          ·          ·          ·
CRM Intelligence    ·          ░░░░░░░░░░░·          ·
(contacts/signals/  ·          ·          ·          ·
 pipeline — passive)·          ·          ·          ·
                    ·          ·          ·          ·
Onboarding          ·          ░░░░░░░    ·          ·
(web wizard→Slack)  ·          ·          ·          ·
                    ·          ·          ·          ·
LLM Inference       ·          ·          ·          ░░░░░░░
(Scaleway/open)     ·          ·          ·          ·
                    ·          ·          ·          ·
Compute + Storage   ·          ·          ·          ░░░░░░░
(Scaleway K8s/PG)   ·          ·          ·          ·
```

Key strategic moves:

- CRM intelligence sits in custom-to-product. Traditional CRMs pushed it to product but made it painful (data entry). Mother Tree rebuilds it as passive — intelligence is a byproduct of the coaching relationship.
- The conversational coach spans custom-to-product. Persona interactions (Seth, Lawrence) feel custom; the pipeline is productized.
- LLM inference and compute are commodity. No differentiation here — pick the right commodity (Scaleway, open-weight, European).
- The play: compete against CRMs in the product phase by offering something that feels custom (a coach that knows your deals) but runs on commodity infrastructure.

Competitive positioning:

- Folk / Attio / Close: commoditizing CRMs. Race to the bottom on UI and integrations.
- Gong / Chorus: product-stage conversation intelligence. Enterprise-priced, recording-dependent.
- Generic LLM wrappers: no methodology, no memory, no discipline. Commodity.
- Mother Tree: custom-to-product gap. Methodology-driven coach that builds intelligence passively. Nobody else here for small teams.

The moat is the methodology, not the code. Open-sourcing makes it stronger (credibility, adoption), not weaker, because executing the methodology requires the discipline the platform enforces.

## 2. Distribution Model

Two channels, one codebase.

### Open source (EUPL 1.2)

Full repository on GitHub. Opinionated stack — Scaleway, PostgreSQL, Hasura, open-weight models. No abstraction layers, no cloud-agnostic pretense. Methodology docs included.

What ships:
- Full codebase (jobs/, bot/, training/, ingestion/, reminders/)
- Methodology docs (principles, choreography, qualification, roles)
- Database schema + Hasura metadata
- Deploy manifests (Scaleway K8s, Flux CD)
- Model selection policy
- CLI tools
- Documentation sufficient to self-host on Scaleway

What doesn't ship:
- Organization-specific content (foundation/narrative data)
- Managed service infrastructure (multi-tenant orchestration, billing, onboarding wizard)

Opinionated means:
- Scaleway is the cloud. No AWS/GCP/Azure abstraction.
- PostgreSQL + Hasura is the data layer. No "bring your own database."
- Open-weight models on Scaleway Generative APIs. No OpenAI, no generic LLM adapter.
- Slack is the interface. No Discord/Teams/generic chat abstraction.
- Fork if you want something different.

Purpose of open source: trust ("you can see everything, you can leave anytime, your data is yours"), credibility (methodology is public and reviewable), technical evaluation. Not the primary funnel — the target audience is non-technical.

### Subscription (mother-tree.eu)

The actual product experience. Web wizard to Slack to coach in minutes. Managed Scaleway infrastructure, isolated per customer. Continuous pipeline improvements, model updates, schema migrations.

Subscription customers run the exact same code. No enterprise edition, no hidden features. The managed service is operational convenience, not feature gating.

Priority of subscription value:
1. Onboarding + training — help you get from zero to first training session
2. Continuous improvement — pipeline upgrades, model evaluations, schema migrations
3. Managed hosting — your instance on our Scaleway infrastructure
4. Shared infrastructure — multi-tenant, isolated data, lower cost than self-hosting

### What keeps teams subscribed

The coach creates a daily rhythm: morning refreshers, meeting prep, conversation debriefs, weekly progress. The intelligence layer gets smarter with every interaction — contacts warm up, signals accumulate, the reframe sharpens. After a month, Mother Tree knows your deals better than your CRM ever did, and you never typed a single activity log. Leaving means losing that accumulated intelligence and the discipline it enforces. The methodology is the habit; the platform is the accountability.

### Self-host to managed migration

If a self-hosted team wants to move to managed: PostgreSQL dump, import into their managed instance, connect Slack. The schema is identical. We provide a migration guide and CLI tool. The open source promise is meaningless if migration is painful.

## 3. Pricing

### Seat pricing

- 29 EUR/seat/month for hunters, gatherers, and farmers (active users)
- Citizens free, fair use policy (they receive, they don't operate)
- Positioned as CRM replacement, not add-on

Competitive context:
- Folk: 20-40 EUR/seat/month
- Attio: 34-36 EUR/seat/month
- Close: 49 EUR/seat/month

Mother Tree replaces these, not adds to them. Lateral move in budget, vertical move in value.

### Inference pass-through

- 1 EUR per million input tokens
- 5 EUR per million output tokens
- Transparent: "We run open-weight models on European infrastructure. You pay what they cost."

Actual Scaleway costs vs. customer charge:

| Model | Role | Our cost (in/out per 1M) | Customer pays (in/out per 1M) |
|-------|------|--------------------------|-------------------------------|
| Mistral Small 3.2 | Extraction, message triage | 0.15 / 0.35 | 1.00 / 5.00 |
| Devstral 2 123B | Generation, scoring | 0.40 / 2.00 | 1.00 / 5.00 |
| Llama 3.3 70B | Scoring | 0.90 / 0.90 | 1.00 / 5.00 |
| Gemma 3 27B | Scoring | 0.25 / 0.50 | 1.00 / 5.00 |
| BGE Gemma2 | Embedding | 0.10 / — | 1.00 / — |

Estimated monthly token consumption per hunter: ~1.8M input tokens, ~1M output tokens (from triage, conversations, training, scoring, extraction). A 5-hunter team: ~9M input + ~5M output = ~34 EUR/month inference at 1/5 rate. Our actual Scaleway cost: ~16 EUR/month. Seats: 5 × 29 = 145 EUR/month. Total revenue: ~179 EUR/month. Inference margin: ~53%.

### Onboarding

Bundled into the first month. No separate fee. Web wizard + Slack-guided setup. Manual help absorbed as investment in learning what self-serve should be.

## 4. LLM Architecture and Cost Control

### Two layers, two billing relationships

Always-on layer (included in subscription, Scaleway):
- Mistral Small 3.2 — extraction, message triage (should I respond? is there a signal?)
- Devstral 2 123B — generation, scoring, training
- Llama 3.3 70B — scoring
- Gemma 3 27B — scoring
- BGE Gemma2 — embedding
- Pass-through at 1 / 5 EUR per million tokens

Optional layer (bring your own Anthropic key):
- Haiku 4.5 — insight triage (batch review of flagged insights when 3 judges disagree)
- Sonnet 4.6 — final arbitration (rare, only when Haiku is still ambiguous)
- Billed directly by Anthropic to the customer

### Arbitration threshold

Customers control how much Anthropic usage they want. Configurable per team:

| Setting | Default | Controls |
|---------|---------|----------|
| `arbitration_mode` | `queue` | `off` / `queue` / `auto` |
| `escalation_spread` | `0.3` | Judge disagreement threshold (higher = less escalation) |

Three modes:
- `off` — No Anthropic key needed. Disagreements go to human review queue in Slack. Fully independent — zero non-European dependencies.
- `queue` (default) — Disagreements batch for daily Haiku triage. Predictable costs.
- `auto` — Real-time escalation on every disagreement. Highest quality, highest Anthropic spend.

No Anthropic key at all: everything still works. Three judges auto-accept/auto-reject ~90% of insights. Remaining 10% queue for human review in Slack DM with inline accept/reject buttons.

Freedom-to-operate story made concrete: zero non-European dependencies possible. Anthropic is an accelerator, not a requirement.

## 5. Onboarding Flow

### The 10-minute path

```
mother-tree.eu
  → "Connect your team" (landing page)
  → Sign up (email, team name)
  → Install Slack app (OAuth)
  → Paste website URL
  → Optional: upload 1-2 case studies
  → "Meet your coach" → redirects to Slack DM

Slack DM (Mother Tree speaks first):
  → "Hi, I'm reading your site now. While I do that —
     what does your team sell, in one sentence?"
  → User responds
  → "Got it. And who's your ideal buyer?"
  → User responds
  → "Your site gave me a lot to work with. Here's what
     I see as your core reframe: [insight]. Sound right?"
  → First training exercise lands within the hour
```

Behind the curtain:
1. Slack OAuth connects workspace, discovers channels
2. Website URL triggers ingestion pipeline (Mistral extraction, 3-judge scoring)
3. Conversational onboarding in DM seeds foundation tables (change, worldview, personas)
4. First exercise generated from real content, not templates

Design principles:
- The bot never says "setup complete." It just starts being useful. Transition from onboarding to daily use is invisible.
- Whoever connects Slack is auto-enrolled. They choose their role (hunter, gatherer, or farmer).
- They invite others via DM: "Add @name as a hunter."
- Citizens are never enrolled — they exist in channels where Mother Tree is present.

## 6. Open Source License

EUPL 1.2 (European Union Public License).

Why EUPL over AGPL:
- Same network copyleft (Article 5: "communicating to the public" covers SaaS use)
- EU jurisdiction by default — disputes governed by EU law, home court advantage
- Drafted by the European Commission, valid in all 22 EU languages
- Broader explicit compatibility (AGPL, GPL, LGPL, MPL, EPL)
- Aligns with Scaleway choice and freedom-to-operate positioning
- The threat model is non-EU cloud providers reselling; EUPL is stronger in EU courts

No external contributors expected. The open source channel serves trust and evaluation, not community contribution (see Section 2). Unfamiliarity of EUPL outside Europe is not a concern.

## 7. GraphQL Layer — Hasura v2 Now, PostGraphile Migration Path

Current: Hasura v2.44.0 (Apache 2.0). Single container, admin secret auth, built-in console. Works, stable, no issues.

Why not Hasura v3: v3 (DDN) requires an enterprise license for self-hosting. The CLI, web console, and LSP are proprietary. Shipping a proprietary dependency in a EUPL project contradicts the freedom-to-operate promise.

Migration target if needed: PostGraphile V5 (MIT license). Node.js, PostgreSQL-native, schema-driven.

| | Hasura v2 (current) | PostGraphile V5 (migration target) |
|--|---------------------|-------------------------------------|
| License | Apache 2.0 | MIT |
| Runtime | Haskell binary, single container | Node.js library or standalone server |
| Auth model | Admin secret + role-based | PostgreSQL RLS (row-level security) |
| Multi-tenant | One instance per tenant, or app-level filtering | Single instance, RLS isolates tenants at the database level |
| Console | Built-in web UI | None — schema-driven, GraphiQL |
| Real-time | Built-in subscriptions | Via pg LISTEN/NOTIFY |

PostGraphile is the stronger choice for multi-tenant. With RLS, tenant isolation is enforced by PostgreSQL itself — one database, one GraphQL server, row-level policies guarantee that customer A never sees customer B's data. This is simpler, cheaper, and more secure than running a Hasura instance per customer or building application-level tenant filtering.

Decision: stay on Hasura v2 for development and open source release (single-tenant). Migrate to PostGraphile when building the managed multi-tenant service. The migration is mechanical — same PostgreSQL schema, same queries, add RLS policies, swap the GraphQL endpoint. The multi-tenant architecture spec should evaluate this migration as part of its scope.

## 8. Domains

- mother-tree.eu — primary (subscription landing, onboarding)
- mother-tree.nl — Dutch market
- mother-tree.de — German market
- mother-tree.fr — French market

## Next Spec Needed

Multi-tenant architecture. Leading option: single PostgreSQL database with RLS policies, PostGraphile as the GraphQL layer, one shared K8s deployment. This is cheaper and simpler than instance-per-customer. The multi-tenant spec should cover: RLS policy design, tenant onboarding automation, PostGraphile migration from Hasura v2, data isolation verification, and whether the 29 EUR price point holds with shared infrastructure costs.

## Open Questions

- Billing integration: Stripe? European alternative?
- Fair use policy for citizens: what's the threshold?
- Onboarding wizard: build or buy (e.g., simple Next.js app on Scaleway)?
- Content ingestion limits per plan, if any?
- GDPR data processing agreements for managed customers
- Data portability: what does "your data is yours" look like as an export? PostgreSQL dump? GraphQL export? CSV?
- Trial or free tier: 29 EUR/seat/month needs a try-before-you-buy path for non-technical teams
- Rate limiting and abuse prevention: misconfigured bot could run up inference costs
- Backup SLA for managed customers: recovery time, retention period
- Monitoring per customer: how do we know when an instance is degraded?
