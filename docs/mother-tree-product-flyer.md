# Mother Tree

**Commercial intelligence for consultative sales teams.**

---

## The problem

Your team has expertise, relationships, and reputation. But warmth doesn't convert to pipeline on its own. Conversations happen and insights are lost. Signals are spotted but not followed up. New team members take months to learn what veterans know instinctively. Your sales methodology exists in people's heads, not in a system.

## What Mother Tree does

Mother Tree is the always-on intelligence layer that connects your marketing, your sales methodology, and your daily conversations into a system that gets smarter with every interaction.

**It ingests your content** — marketing materials, published articles, case studies — and extracts structured positioning (the change you offer, the worldview you speak to, the stories that prove it).

**It listens to your team** — signals shared in Slack, meeting debriefs, conference encounters — and enriches them with context, identifies contacts and opportunities, and tracks where each prospect stands.

**It trains your team** — guided by two expert personas (marketing strategist + consultative selling coach) who co-train in consensus. Daily exercises, scenario practice, meeting prep — all generated from your live intelligence, adapting to each person's role and progress.

**It remembers everything** — every contact, every interaction, every insight. When you prepare for a meeting, Mother Tree knows the history. When a new article is published, it becomes a training exercise within hours.

## How it works

```
Your content                    Your team                    Mother Tree
─────────────                   ─────────                    ───────────
Marketing docs ──┐                                          ┌── Central intelligence
Blog posts      ─┤              Signals in Slack ──────────→│   (PostgreSQL + GraphQL)
Published articles┤             Meeting debriefs ──────────→│
Case studies    ──┘             Conference notes ──────────→│── Training engine
                                                            │   (seth + lawrence consensus)
                 Foundation     Conversation                │
                 + Narrative    layer                       │── Signal enrichment
                 extraction                                 │   (intent classification,
                                                            │    entity extraction)
                                                            │
                                                            └── Opportunity lifecycle
                                                                (soil → sustain)
```

## The sales methodology

Mother Tree implements the **Mycorrhizal Method** — a sales choreography for consultative, relationship-driven teams:

**Soil** → Your content exists in the landscape before any conversation happens.
**Signal** → Someone whose worldview aligns does something visible.
**Reframe** → You share an insight that shifts how they see their situation.
**Diagnosis** → They buy clarity. The assessment is the first product.
**Proposal** → You offer to guide the change together.
**Sustain** → The engagement delivers capability. The client tells the story to others.

Each stage adds something to the prospect: awareness, perspective, clarity, a plan, capability. Mother Tree tracks where each opportunity stands and helps your team advance it.

## The training

Two expert personas, trained on your content, co-train your team:

**Seth** (marketing strategy) — teaches the change, the worldview, the story. "Who are we talking to? What do they believe? How do our stories create soil?"

**Lawrence** (consultative selling) — teaches the consultative conversation. "How do you probe for the real problem? How do you co-create solutions? How do you close without pitching?"

**Trainer** — their consensus. One exercise, both perspectives. The marketing framework meets the sales method.

Training adapts to role (hunters get full training, gatherers focus on signals and stories, farmers understand the methodology to support the team) and progresses from structured exercises through open-ended scenarios to real meeting prep.

## The technology

**European infrastructure.** Runs on Scaleway Kubernetes with European open-weight models (Mistral). No data leaves European jurisdiction for the core pipeline.

**Content-agnostic.** Mother Tree defines the structure. You bring your content. Change the marketing repo, the training changes.

**Three-model quality scoring.** Every extracted insight is independently scored by three different AI models. Flagged items are triaged by a fourth. Only validated intelligence enters the training system.

**Open standards.** PostgreSQL, GraphQL (Hasura), Kubernetes, GitOps (Flux). No proprietary platform dependency.

## What you get

| For hunters | For gatherers | For farmers |
|-------------|---------------|-------------|
| Meeting prep with reframes | Drop signals in Slack — done | Deploy and maintain the platform |
| Daily training exercises | Content creates soil automatically | Configure ingestion and CronJobs |
| Pipeline visibility | Training on what makes good signals | Monitor the intelligence |
| Opportunity stage tracking | Stories feed the methodology | Manage the training schedule |

## The interface

**Slack:** `/mothertree ask seth "is our worldview clear?"` — instant answers from the central intelligence. Signal capture, thread conversations, enrichment. Training exercises via DM.

**Claude Code:** `/mothertree ask trainer "practice NIS2 objections"` — same intelligence, same personas, from your terminal.

**Hasura console:** Browse, query, and manage the central intelligence directly.

## What it costs

Mother Tree runs on your infrastructure. The costs are:

- **Scaleway Kubernetes** — shared cluster, minimal resource footprint (~€10-20/month incremental)
- **Scaleway Generative APIs** — pay-per-token for extraction and scoring (~€50-100/month depending on content volume)
- **Anthropic** (optional) — for triage and arbitration of flagged content (~€10-30/month)

No per-seat licensing. No vendor lock-in. No data leaving your control.

## Who it's for

Consultative sales teams at relationship-driven businesses. 5-50 people. Expertise-based services. Long sales cycles. Small deal volume, high deal value. Teams where the sales challenge isn't volume but choreography — connecting warmth, expertise, and reputation into pipeline.

---

*Mother Tree is named after Suzanne Simard's research on how forests communicate underground. The biggest trees feed the seedlings. The network makes every tree stronger.*

*Your platform, your intelligence, your freedom to operate.*
