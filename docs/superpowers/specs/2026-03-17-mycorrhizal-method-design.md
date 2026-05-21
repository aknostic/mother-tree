# The Mycorrhizal Method — Sales Methodology Design Spec

> *"A forest is much more than what you see." — Suzanne Simard*

## Context

Aknostic is a European cloud-native and Kubernetes consultancy expanding across Europe through Eckard Wintzen's cell division model. We are practitioners who sell, not salespeople who consult. We find clients through reputation, stories, and network — three pillars that generate warmth but lack choreography to convert reliably into pipeline.

This document defines the Mycorrhizal Method: Aknostic's sales methodology. It synthesizes the Challenger Sale's teaching framework, Richardson's consultative principles, social selling's content-to-conversation mechanics, Suzanne Simard's network intelligence research, and Wintzen's cell division philosophy.

The methodology is the commercial DNA every Aknostic cell inherits. It is a living body of knowledge that grows with every engagement, every signal, every cell.

**Scope:** This spec defines the methodology and the platform architecture for v1 — one team, Aknostic NL.

**Primary audience:** The current Aknostic team (Pim and Jurg as hunters, Jasper and Flavia as gatherers, Matthijs as farmer).

---

## 1. Root System — Core Principles

Five beliefs that anchor the methodology. Everything else evolves; these stay stable unless the company's identity changes.

### 1.1 Freedom to operate

Your systems should work for you. You should be able to change vendors, move providers, or walk away from us — because you have that freedom. We build for this. We practice this. You keep us because you want to, not because you have to.

The proof is in our client relationships. Sanoma Learning has been with us for 12 years — showing continuous growth, now asking us to help plan their future. Consumentenbond for 6 years. They stay because working with us makes everything resilient and reliable, not because they cannot leave.

### 1.2 Assessment is the first product

We do not pitch, then sell, then deliver. The first thing a client buys is clarity about their own situation — a lock-in audit, an independence assessment, a CTO retainer. The assessment is valuable to them and diagnostic for us. If it does not reveal a problem worth solving together, we part as friends.

### 1.3 Qualify for mutual respect

Not every client is our client. We look for organizations where initiative and expertise are valued, not just capacity. We would rather lose a deal early than win one that damages our people. Qualification is not just "can they pay" — it is "can we do our best work here."

### 1.4 Teach, don't pitch

Every interaction should leave the other person knowing something they did not know before. A LinkedIn post, a conference conversation, a Clouds of Europe article, or a formal assessment — value comes from sharing insight, not selling services. Teaching builds the reputation that makes selling unnecessary.

### 1.5 The network feeds the forest

No cell, no person, no engagement exists in isolation. Every signal, every relationship, every lesson learned makes the whole network smarter. Sharing is not overhead — it is the mechanism by which small teams outperform large ones.

---

## 2. Roles — Hunters, Gatherers, Farmers

Three roles defined by function, not hierarchy. People shift between roles depending on context.

### 2.1 Hunters

The commercial engine. Hunters run the full choreography from insight to engagement. In the current team: Jurg and Pim.

**Key behaviors:**
- Lead qualification conversations
- Deliver the teaching choreography (reframe, assessment, engagement)
- Maintain the active pipeline
- Decide when to walk away
- Feed learnings back into the network

### 2.2 Gatherers

Visible in the field, bringing back commercial fuel. Gatherers are primarily engaged in delivery, but their work generates reputation through excellent client work, stories through content and talks, and signals through the relationships they build while delivering. In the current team: Jasper and Flavia.

**Key behaviors:**
- Share insights from delivery work (what clients struggle with, what patterns emerge)
- Create content — talks, articles, case studies, LinkedIn posts
- Spot signals during engagements (adjacent problems, new stakeholders, referral opportunities)
- Hand off signals and contacts to hunters with context

Gatherers hand off signals via Slack — "talked to X at client Y, they mentioned Z." Mother Tree captures it, enriches it, and routes it to the right hunter.

### 2.3 Farmers

Tend the infrastructure and keep the village running so hunters can hunt and gatherers can gather. In the current team: Matthijs.

**Key behaviors:**
- Build and maintain the marketing presence, website, and tooling
- Keep operational systems running
- Support the team's commercial activities with infrastructure
- Participate in community and maintain visibility

Farmers make Stages 1 and 2 possible. The website that builds credibility, the tools that prospects download, the operational systems that let hunters focus on hunting — farmers build and maintain all of it. Without this foundation, the methodology has no ground to stand on.

The farmer maintains the Mother Tree platform — PostgreSQL, Hasura, scheduled jobs, Slack integration. The system that makes the methodology operational.

---

## 3. Nutrient Flow — The Choreography

How signals become engagements. Not a linear funnel — a flow with multiple entry points, qualification gates, and feedback loops. Prospects can enter at any stage; pick up where the relationship already is.

### Stage 1: Soil — Presence

Before any conversation happens, you exist in the landscape. This work means people already know who you are when you meet.

- Clouds of Europe content (gatherers and hunters)
- LinkedIn storytelling (everyone, especially gatherers)
- Community presence — CNCF, meetups, events (everyone)
- Reputation markers — KEIT, books, talks (accumulated credibility)
- Tools and frameworks published openly (lock-in audit self-service version, independence checklist)

This stage never stops. It is not "top of funnel" — it is the environment in which everything else grows.

### Stage 2: Signal — Something moves

Someone or something creates a reason to engage. Signals come from multiple sources:

- A gatherer hears something at a client ("their sister company is struggling with X")
- A hunter spots something on LinkedIn (leadership change, new role posted, regulatory comment)
- Inbound — someone reads an article, attends office hours, downloads a tool
- Network — someone you know makes an introduction
- Market — regulatory deadline approaching (NIS2, DORA, EU Data Act)

**Qualification gate:** Is this worth a conversation? Quick assessment: is there a real problem we can solve, for an organization we would want to work with?

Mother Tree captures signals from Slack messages, email forwards, and scheduled scans of regulatory calendars and job boards. Low friction. The platform routes signals to the right hunter with context.

### Stage 3: Reframe — The first real conversation

The Challenger teaching moment. Share an insight the prospect has not considered. Not a pitch — a perspective shift.

Example reframes:
- "Your multi-cloud strategy is not multi-cloud — it is multi-vendor lock-in"
- "NIS2 requires supply chain control by [date] — have you mapped your cloud dependencies?"
- "You are spending €X maintaining hyperscaler-specific tooling that would be portable on Kubernetes"
- "Your developers are locked into vendor-specific workflows that limit hiring and knowledge transfer"

The reframe works because it comes from a practitioner, not a salesperson. You teach, you do not sell.

The insight library lives in PostgreSQL — tagged by stakeholder persona, market, and regulatory trigger. Vector-embedded for semantic search. Updated as regulations evolve and new patterns emerge.

### Stage 4: Diagnosis — Assessment as first product and mutual respect gate

The client buys clarity. Three weeks of work, priced at €40-50k to signal investment, not cost. Assessment types include:

- Lock-in audit
- Independence assessment
- CTO retainer
- TCO analysis

The assessment is the deepest qualification gate. You read signals across three phases:

**Pre-engagement dynamics:** How do they negotiate the price? Hard haggling signals they see you as a vendor, not a partner. Procurement-led engagement or scope squeezing ("do it in one week for half") are walk-away signals.

**Engagement dynamics:** Do they make time? Are they open? Is initiative welcome, or does it feel like encroachment? Do you have access to the people and systems you need? Are there signs of organizational dysfunction — blame culture, political maneuvering, toxic dynamics?

**Closure dynamics:** Do findings land as collaborative insights, or does it feel like a scolding disguised as a report? Do they have energy to act on what was found, or does the report go into a drawer?

If the signals are wrong at any phase, part as friends. The assessment delivered value regardless. Reputation compounds.

Assessment templates live in Git (versioned, improved with each use). Each assessment's findings feed learnings back into the insight library in PostgreSQL.

### Stage 5: Proposal — The build engagement

If diagnosis confirms fit, propose the consultancy engagement (12-18 months). By this point:

- They trust you (from the assessment)
- They have seen your work quality firsthand
- The case was made by their own data, not your pitch
- You have qualified them as thoroughly as they have qualified you

The proposal should frame the engagement as capability transfer: we do this together so you can operate independently. The client gains freedom — the freedom to keep you because they choose to, or to run it themselves. This is the "freedom to operate" principle applied to the engagement itself.

**The capability transfer narrative:** Prospects sometimes wonder: "If you make us independent, why would we keep paying you?" The answer is in our track record. Sanoma Learning: 12 years, continuous growth, now asking us to help plan their future. Consumentenbond: 6 years. We transfer capability for the current challenge. The world keeps changing — new regulations, new technology shifts, new scaling problems. Clients come back because we earned the relationship, not because we engineered dependency. Each engagement ends with the client stronger, more resilient, more reliable. That strength is our best referral — and why they keep choosing us.

### Stage 6: Sustain — Operate and grow

In production, 24/7 support is the natural extension. This stage feeds the entire cycle:

- Gatherers inside the engagement spot adjacent opportunities
- Delivery work generates stories and content for Stage 1
- Patterns across engagements feed the insight library
- Client success is the strongest reputation signal

The flow loops: Stage 6 feeds Stage 1 and Stage 2 continuously.

---

## 4. Qualification Framework — Walk-Away Signals

A field guide, not a checklist. Organized by when you encounter the signal.

### Before assessment (Stage 2-3)

- **Engagement shape is wrong** — no budget authority, innovation theater, "just exploring." Filter through messaging.
- **No real problem** — curious about cloud independence but nothing is pressing. Worth a coffee, not an assessment.
- **Client readiness absent** — they want the outcome but will not change anything. These tend to self-select out.

### During assessment (Stage 4)

**Pre-engagement dynamics:**
- Hard price negotiation — they see €40-50k as a cost to minimize, not an investment in clarity
- Procurement-led engagement — you talk to purchasing, not to people with the problem
- Scope squeezing — "can you do it in one week for half the price"

**Engagement dynamics:**
- They do not make time — meetings get rescheduled, key people absent
- Information gatekeeping — no access to the people or systems needed
- Servant signals — initiative received as overstepping, questions received as criticism
- Organizational dysfunction — blame culture, political maneuvering, toxic team dynamics

**Closure dynamics:**
- Findings land as scolding — they feel judged, not informed
- Report goes into a drawer — no energy to act on findings
- Credit dynamics — someone claims findings as their own idea (this can be fine — it means the insights landed)

### The walk-away conversation

When signals say "don't proceed," the assessment delivered value regardless. "We found X, Y, Z. Our honest recommendation is [whatever is true]. If the timing or fit is right later, we are here." Principle #1 in action: part as friends, reputation intact, having taught them something real. "We qualified for mutual respect" is better language than "we lost the deal."

A scheduled monthly analysis surfaces patterns across assessments — "organizations with X characteristic tend to be poor fits" — turning individual instinct into collective intelligence.

---

## 5. Insight Library

The Challenger model runs on insights — reframes that teach prospects something about their own situation. The methodology defines the structure for building, maintaining, and sharing these.

### Anatomy of an insight

Each insight contains:
- **The reframe** — the one-sentence perspective shift
- **The evidence** — what makes it credible (data, regulation, client pattern)
- **The stakeholder lens** — how it lands for CTO vs CISO vs CFO vs CEO
- **The trigger** — what makes it timely (regulatory deadline, market shift, news event)
- **The next step** — where it leads (usually toward an assessment)

### Categories

Insights cluster around five domains:
- **Lock-in / freedom to operate** — hidden costs, switching barriers, EU Data Act implications
- **Regulatory pressure** — NIS2, DORA, EU Cloud Sovereignty Framework (SEAL levels)
- **Capability vs dependency** — platform team productivity, skill portability, vendor-specific vs cloud-native
- **Cost reality** — TCO including hidden costs, contract traps, long-term trajectory
- **Developer experience** — tooling lock-in, hiring constraints, knowledge transfer barriers, developer productivity
- **Resilience and reliability** — what 12-year client relationships teach about operational maturity, continuous growth, and building systems that last

### Tailoring by stakeholder

The same insight lands differently depending on who hears it. For each insight, consider the lens:

- **CTO / VP Engineering** — cares about technical migration risk, team capability, platform choice, developer productivity. Speaks in systems and architecture. The reframe: "Your platform team is maintaining vendor-specific tooling instead of building portable skills."
- **CISO / Security lead** — cares about NIS2, DORA, compliance deadlines, data residency, supply chain control. Speaks in risk and regulation. The reframe: "Can you demonstrate supply chain control to your regulator by the deadline?"
- **CFO / Procurement** — cares about TCO, contract flexibility (EU Data Act), vendor concentration risk. Speaks in cost and optionality. The reframe: "Your cloud contract includes switching costs you have never calculated."
- **CEO / Board** — cares about strategic autonomy, competitive positioning, geopolitical risk. Speaks in business outcomes. The reframe: "Your technology strategy depends on decisions made in Seattle."

You do not need to master all four lenses on day one. Start with the stakeholder you are talking to. The insight library tags each reframe with its strongest stakeholder fit.

### How the library grows

- Hunters add insights from prospect conversations ("three prospects this month asked about X")
- Gatherers add insights from delivery work ("every financial services client hits this DORA wall")
- Market signals update triggers (regulation dates change, new legislation announced)
- Each assessment refines the evidence base (real data replaces assumptions)

When a hunter prepares for a conversation, the Claude Code skill surfaces relevant insights from the library based on the prospect's industry, role, and regulatory exposure. Gatherers feed the library through Slack.

---

## 6. The Living Methodology — How It Grows

The methodology improves with every engagement, every signal, every retrospective.

### Learning loops

**Per-engagement:** After every assessment, a brief retrospective. What insights landed? What qualification signals did we read correctly or miss? What did we learn about this industry or stakeholder type? Feeds the insight library and qualification framework.

**Per-quarter:** Hunters and gatherers review patterns together. What are prospects asking about? What content generates conversations? What objections recur? Where are the insight library gaps? Feeds Clouds of Europe content strategy and tool development.

### What gets versioned

- Insight library — insights added, updated, retired as markets shift
- Assessment toolkit — templates improve with every use
- Qualification signals — new patterns codified as collective experience grows

### What stays stable

- The five root principles
- The role definitions (hunters, gatherers, farmers)
- The choreography stages (soil through sustain)

### The publishable layer

The principles, choreography, and the thinking behind them are publishable — a Clouds of Europe article series, a talk, eventually a short book. This is the Challenger move applied to the methodology itself: teach the market how you think about selling, and the people who resonate find you. The what is free; the how is what clients get through engagement.

---

## 7. Scheduled Intelligence

The always-on layer runs as Kubernetes CronJobs calling Scaleway Generative APIs (Mistral). No autonomous agents — scheduled workflows that call an LLM when they need intelligence.

### Scheduled jobs

**Signal scanner** (weekdays 7 AM) — scans regulatory calendars (NIS2, DORA, EU Data Act), job boards, and news for signals matching configured keywords. Creates signal records in PostgreSQL, links to existing companies, flags high-relevance signals for hunter attention via Slack.

**Daily training refresher** (weekdays 8 AM) — delivers a short Duolingo-style exercise to each hunter via Slack DM. One insight to practice, one scenario to respond to. Adapts to the hunter's weak spots based on training_progress data.

**Stale relationship check** (daily) — queries contacts with no recent interaction above the temperature threshold. Sends reminder to the responsible hunter via Slack.

**Calendar sync** (hourly) — reads Google Calendar, identifies upcoming meetings with known contacts. Pre-meeting: surfaces context and reframe suggestions. Post-meeting: prompts for debrief if no notes exist. Moving window: 7 days for hunters, 2 weeks for gatherers, 2 months for farmers.

**Weekly pipeline review** (Mondays 9 AM) — generates a summary of pipeline state: conversations by stage, stale items, upcoming follow-ups. Delivered to hunters via Slack.

**Monthly retrospective** (first Monday) — pipeline health, insight usage patterns, training progress per hunter.

### The human-machine boundary

Scheduled jobs enrich, detect, surface, and suggest. Humans decide, qualify, relate, and teach. The system never sends a message to a prospect. It never makes a qualification judgment. It makes hunters smarter and gatherers more effective by handling work that does not require human judgment.

---

## 9. Platform Architecture — Two-Layer Intelligence

The methodology needs an always-on intelligence layer (scanning, monitoring, reminding) and an interactive layer (briefings, drafting, synthesis). These are different problems with different solutions.

### Architectural principle

**Always-on layer** — scheduled workflows on Kubernetes, calling European LLMs when they need intelligence. Runs 24/7 on Scaleway. No external AI vendor dependency. If every US AI provider shuts down tomorrow, this layer continues.

**Interactive layer** — human-triggered, session-based. A Claude Code skill that connects to the central intelligence via GraphQL. The practitioner chooses their own model.

### Why not an agent framework

For 90% of what the always-on layer does, scheduled workflows are sufficient. Signal scanning, regulatory monitoring, stale relationship detection, pipeline reviews — these are cron jobs that sometimes call an LLM, not autonomous agents that reason independently. The intelligence is in the data, the schema, and the prompts — not in an agent framework.

### Stack

```
┌─────────────────────────────────────┐
│  Hunter interfaces                  │
│  Claude Code skill  |  Slack DM     │
└───────────┬─────────────────────────┘
            │ GraphQL
┌───────────▼─────────────────────────┐
│  Hasura (auto-generated GraphQL)    │
│  Typed, documented, subscriptions   │
└───────────┬─────────────────────────┘
            │
┌───────────▼─────────────────────────┐
│  PostgreSQL + pgvector              │
│  (CloudNativePG on K8s)             │
│                                     │
│  contacts, companies, signals,      │
│  interactions, insights,            │
│  assessments, training_progress     │
└─────────────────────────────────────┘
            │
┌───────────▼─────────────────────────┐
│  Scheduled jobs (K8s CronJobs)      │
│  - morning signal scan              │
│  - daily training refresher         │
│  - weekly pipeline review           │
│  - stale relationship check         │
│  - calendar sync                    │
└───────────┬─────────────────────────┘
            │ API call
┌───────────▼─────────────────────────┐
│  Scaleway Generative APIs         │
│  Mistral Small / Nemo              │
│                                     │
└─────────────────────────────────────┘
```

All on Scaleway. All European. All infrastructure we understand.

### Component choices

**PostgreSQL + pgvector** — relational data AND vector search in one store. Contacts, companies, signals are relational. Semantic search over insights and interaction notes uses pgvector. CloudNativePG operator handles backups and lifecycle on Kubernetes.

**Hasura** — auto-generates a typed, documented GraphQL API from the PostgreSQL schema. Zero backend code for basic CRUD. Subscriptions for real-time signal notifications. Introspection means the schema IS the documentation. Self-hostable, open source.

**Scaleway Generative APIs** — `https://api.scaleway.ai/v1`, OpenAI-compatible. Mistral Small 3 (24B) for structured extraction, pay-per-token. European models on European infrastructure.

**Kubernetes CronJobs** — scheduled intelligence tasks. Each job is a container that queries the database, optionally calls the LLM, and writes results back. Simple, observable, debuggable.

**Claude Code skill** — the interactive layer. Wraps the GraphQL API with methodology-aware prompting. Hunters use `/mothertree briefing "Company X"` or `/mothertree pipeline` from Claude Code. Works with any model the practitioner chooses.

### Role-to-interface mapping

- **Hunters** — Claude Code skill (briefings, prep, pipeline), Slack DM (training, reminders, debrief prompts)
- **Gatherers** — Slack (low-friction signal handover from delivery context)
- **Farmers** — Kubernetes admin (CloudNativePG, Hasura, CronJobs, Scaleway infrastructure)

### Data model

PostgreSQL with pgvector. Seven core entities plus training state:

**Contacts** — people, with relationship temperature (warm/hot/cold), communication channels, last interaction date, LinkedIn profile.

**Companies** — organizations, with industry, market, cloud stack, regulatory exposure, employee count.

**Signals** — incoming intelligence from any source. A gatherer's Slack message, a regulatory deadline, a job posting. Status lifecycle: `new → reviewed → acted_on → archived`. Linked to contacts and companies where applicable.

**Interactions** — every meaningful touchpoint with a contact. Type (call, email, meeting, event, LinkedIn), summary, source role, next action, next action date.

**Insights** — the reframe library. Reframe text, evidence, stakeholder lens, category, trigger, next step, freshness score. Vector-embedded for semantic search.

**Assessments** — active and completed engagements. Type, status, start date, findings, qualification signals across three phases (pre-engagement, during, closure), outcome.

**Patterns** — cross-engagement intelligence. Type, description, frequency, source count, last seen.

**Training progress** — per-hunter. Methodology areas covered, refresher history, weak spots, streak data. Feeds the coaching system.

### V1 features: Hunter training and discipline

The first features to build — what makes Mother Tree immediately useful to hunters.

**Training:**

*Initial narrative development* — guided interactive sessions through the methodology. Not reading docs — a conversation where the hunter practices reframes, gets feedback, internalizes the choreography through their own experience.

*Daily refreshers (Duolingo-style)* — short, daily, delivered via Slack DM. One insight to practice, one scenario to respond to. Adapts to the hunter's weak spots. Tracks progress and streaks.

*Conversation prep* — before a meeting (pulled from Google Calendar): surfaces what Mother Tree knows about the contact and company, suggests relevant reframes, asks the hunter for their goal. After: prompts for debrief, processes notes into interactions and signals, asks about anonymization.

**Discipline:**

*Daily rhythm* — morning: signal queue review, today's meetings with prep. End of day: debrief prompt for meetings that happened.

*Weekly rhythm* — Monday: pipeline review (where is each conversation, what needs attention, what's gone cold). Friday: retrospective prompt.

*Monthly rhythm* — pipeline health summary, insight library review, training progress.

*Reminders* — follow-up reminders based on next_action dates. Stale relationship alerts. Calendar-driven: flag meetings 2-3 weeks out that need prep action now.

**Calendar integration:**

Moving window around today, adapted by role:
- Hunters: 7-day window for debriefs and prep, plus flags for meetings 2-3 weeks out
- Gatherers: 2-week window
- Farmers: 2-month window

Cold start: scan past calendar entries for meetings without debriefs. Prompt for retroactive notes. Backfills Mother Tree with real data from day one.

### Deployment

Runs in a dedicated namespace on the groupware team's existing Scaleway Kubernetes cluster. Deployed via Flux CD — groupware configures their Flux to sync Mother Tree manifests from this GitLab repo.

**In our namespace (we manage):**
```
namespace: mother-tree
├── CloudNativePG (PostgreSQL + pgvector)
│   └── Single instance for v1
│
├── Hasura (GraphQL engine)
│   └── Connected to PostgreSQL, auto-generated API
│
├── CronJobs (scheduled intelligence)
│   ├── signal-scanner (weekdays 7 AM)
│   ├── daily-refresher (weekdays 8 AM)
│   ├── stale-check (daily)
│   ├── weekly-review (Mondays 9 AM)
│   └── calendar-sync (hourly)
│
└── Slack bot (training, signals, reminders)
```

**Provisioned by groupware (via OpenTofu):**
- Scaleway Generative APIs key (`https://api.scaleway.ai/v1`, mistral-small-3.2-24b-instruct-2506)
- S3 bucket: `groupware-mother-tree-backups` at `s3.fr-par.scw.cloud`
- DNS: `mothertree.aknostic.com` with TLS via cluster gateway

### What this is NOT

- Not an agent framework. No autonomous reasoning. Scheduled jobs that call an LLM when needed.
- Not a CRM with a UI. The interfaces are Claude Code and Slack. A dashboard comes later if needed.
- Not multi-cell. V1 is one team — Aknostic NL. Cell expansion is a future concern.

---

## Open Questions for Future Design

1. **Assessment pricing by market** — does €40-50k hold across European markets, or does it need local calibration?
2. **Content-to-conversation metrics** — which Clouds of Europe content types generate the most signals?
3. **Clouds of Europe integration** — how does community engagement data flow into Mother Tree? Webhook into the signal scanner is the likely path.
4. **Gamification design** — the Duolingo-style training needs game mechanics (streaks, levels, unlocks) that make methodology practice feel rewarding, not imposed. Design this with Pim, not for Pim.
5. **Meeting minutes anonymization** — the workflow needs explicit consent per debrief. What's the default? What gets anonymized? How do we handle client-sensitive information in the training data?
6. **Account management** — the methodology covers sales (Soil → Sustain). Account management is a separate discipline that needs its own treatment, eventually.
