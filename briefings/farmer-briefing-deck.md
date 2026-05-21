# Mother Tree — Farmer Briefing

> **What's live now:** PostgreSQL 17 + pgvector 0.8.2 with vector embeddings on all CI tables, PostGraphile GraphQL, content ingestion CLI (dual-lens with Qwen 3.5, context-aware extraction, multi-model scoring, embeddings on insert), Slack bot with character ensemble, training engine with CronJob deployed (hunter/gatherer/farmer/citizen), calendar integration (iCal sync), discipline engine (stale checks, weekly review, monthly retrospective), semantic search + briefing command, `/mothertree` Claude Code skill, GitLab CI with kaniko, Flux CD deployment. **Coming soon:** Signal scanner (RSS/news/job boards).

---

## What is Mother Tree?

Mother Tree is our commercial intelligence platform. It connects everything we do — the relationships we build, the signals we pick up, the content we create, the assessments we deliver — into one system that gets smarter with every interaction.

Named after Suzanne Simard's research on how forests communicate underground. The biggest trees feed the seedlings. The network makes every tree stronger. That's what we're building.

It's not a CRM. It's the system that makes our way of selling actually work.

---

## Why we need this

We have three commercial strengths: reputation (publications, talks, credibility), stories (LinkedIn, thought leadership), and network (we know a lot of people, and people like us).

The problem: these three pillars generate warmth but not enough heat. Individually, none of them converts reliably into pipeline. Mother Tree connects them — and it needs someone to make sure the system actually works. That's you.

---

## The core message

**"You keep us because you want to, not because you have to."**

This is our version of freedom to operate — applied to our own client relationships. We don't create dependency. We transfer capability. Clients stay because they choose to, not because they're locked in.

The proof is in long-term client relationships — clients who stay for years and grow with you. They stay because working with you makes everything resilient and reliable — and the infrastructure you build and maintain is part of why that's true. The website, the tools, the platform — these are the ground the whole methodology stands on.

---

## Five principles

1. **Freedom to operate** — your systems should work for you. That starts with our relationship with you.

2. **Assessment is the first product** — we don't pitch and then sell. The first thing a client buys is clarity about their own situation.

3. **Qualify for mutual respect** — not every client is our client. We look for organizations where initiative and expertise are valued.

4. **Teach, don't pitch** — every interaction leaves the other person knowing something they didn't before. That's how reputation compounds.

5. **The network feeds the forest** — every signal, every lesson learned, every relationship makes the whole network smarter.

---

## Your role: Farmer

We have three roles in this system:

**Hunters** — run the full commercial choreography. Turn signals into conversations, conversations into assessments, assessments into engagements.

**Gatherers** — visible in the field, bringing back signals and stories from delivery work.

**Farmers** (you) — keep the village running so hunters can hunt and gatherers can gather.

As a farmer, your superpower is making things work. The marketing presence, the website, the operational systems — you built them around Jurg's core ideas and you take pride that they work. Mother Tree extends that role into the commercial platform itself. You're not just maintaining a website anymore — you're maintaining the system that powers our entire sales operation.

---

## What farmers do

You make the methodology operational. Without the infrastructure, the principles are just words on a page.

**Maintain the Mother Tree platform.** PostgreSQL, PostGraphile, and scheduled jobs running on our Scaleway Kubernetes cluster. You monitor them, keep them healthy, handle updates. Think of it like maintaining Stalwart or Authentik — infrastructure that just runs.

**Manage the scheduled jobs.** CronJobs that scan for signals, deliver training refreshers, check for stale relationships, and generate pipeline reviews. You configure them — which keywords to monitor, which schedules to run, how signals get routed. When the team says "we need it to also watch for X," you update the job config.

**Manage the Slack integration.** The bot that delivers training, collects debriefs, and forwards gatherer signals. You set it up, manage the tokens, and make sure messages flow.

**Maintain the marketing and content infrastructure.** The website, the thought leadership platform, the LinkedIn tooling. This feeds the Soil stage of the choreography — the always-on presence that means people know who we are before we talk to them.

**Backups and data integrity.** PostgreSQL is the collective intelligence. CloudNativePG handles automated backups to Scaleway Object Storage.

---

## The technical stack

```
Scaleway Kubernetes cluster
├── CloudNativePG (PostgreSQL 17 + pgvector 0.8.2)
│   ├── All contacts, signals, interactions, insights
│   ├── Vector embeddings on all CI tables (BGE Multilingual Gemma2, 3584 dimensions)
│   └── Automated backups to Scaleway Object Storage
│
├── PostGraphile (GraphQL engine)
│   ├── Auto-generated API from the database schema
│   └── Used by the Claude Code skill and scheduled jobs
│
├── CronJobs (scheduled intelligence)
│   ├── training-deliver (weekdays — training + citizen inspiration)
│   ├── stale-check (weekdays 08:00 — hot: 7d, warm: 14d)
│   ├── weekly-review (Mondays 08:00 — pipeline summary)
│   ├── monthly-retrospective (1st of month 09:00 — LLM-synthesized)
│   ├── calendar-sync (hourly — iCal feeds, prep + debrief)
│   └── signal-scanner (planned — RSS/news/job boards)
│
├── Slack bot (notifications and training delivery)
│
└── Scaleway Generative APIs
    ├── Qwen 3.5 397B (generation, deep extraction)
    ├── Mistral Small 3.2 (classification)
    ├── Devstral 2 123B / Llama 3.3 70B / Gemma 3 27B (scoring)
    └── BGE Multilingual Gemma2 (embeddings)
```

Key tools:
- `kubectl` — manage the cluster, check job status, view logs
- Scaleway console — infrastructure, inference endpoints, backups

---

## How the pieces connect

```
  Gatherer (Slack msg)  ──→  Slack bot  ──→  PostgreSQL  ──→  Hunter (Claude Code skill)
  Signal scanner (cron) ──→  Mistral   ──→  PostgreSQL  ──→  Slack DM (notifications)
  Website (content)     ──→  (Soil)    ──→  (reputation)
```

You maintain all three paths. The Slack integration that receives messages. The scheduled jobs that process and enrich them. The marketing infrastructure that keeps us visible.

When a hunter says "I need the system to also track job postings in DACH," you add keywords to the signal scanner config. When a gatherer says "can I also forward signals via email," you add a webhook endpoint.

---

## What changes for you

Your current work — website, marketing, operational tooling — stays. Mother Tree adds a new layer: the commercial platform. Specifically:

**New responsibilities:**
- Kubernetes workloads: CloudNativePG, PostGraphile, CronJobs (like any other service on the cluster)
- Slack bot configuration and credentials
- Database backups and integrity (CloudNativePG handles most of this automatically)
- Supporting the team when they need something changed or added

**What this feels like:**
- Same patterns as the rest of our Scaleway infrastructure. Kubernetes, Helm, GitOps.
- PostGraphile auto-generates the GraphQL API from the database schema. No custom backend code for basic operations.
- CronJobs are just containers with a schedule. Configure, deploy, monitor.
- When things work, they're invisible. That's the goal.

---

## What happens next

**Week 1:** We deploy Mother Tree on the Scaleway cluster together. PostgreSQL, PostGraphile, Slack bot. Verify data flows: a gatherer drops a message, it appears in the database, a hunter can query it.

**Week 2-4:** Activate the scheduled jobs. Signal scanner, daily refreshers, stale relationship checks. Tune the schedules and thresholds. Set up monitoring.

**Month 2:** The system is in daily use. Hunters get training and prep, gatherers drop signals, the scanner runs every morning. Your job shifts to maintenance and responding to "can we also..." requests from the team.

**Ongoing:** As Mother Tree grows — more contacts, more signals, more patterns — you're the one who keeps it healthy.

You built the village. Now you keep it running while the hunters hunt and the gatherers gather.
