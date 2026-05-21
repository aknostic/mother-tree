# Abstract — ASISAS 2026

**Title:** Mother Tree: A Methodology-First, Choreographed Multi-Agent System for Individual–Collective Commercial Intelligence

**Authors:** Jurg van Vliet, Flavia Paganelli, Jasper Geurtsen — Aknostic, Amsterdam, the Netherlands

---

**Abstract.** Most agentic systems are capability-first: take a frontier model, give it tools, point it at a goal, and trust autonomy to deliver. We report on *Mother Tree*, a multi-agent commercial-intelligence system that does the opposite — it starts from a sales methodology (the Mycorrhizal Method, drawing on consultative-selling literature and Simard's forest mutualism) and lets the methodology dictate the agents.

Three rejections shaped the architecture. *Choreography over autonomy:* Python jobs on Kubernetes call LLMs at scheduled points, with multi-judge quorum scoring and a designed human-in-the-loop boundary; we rejected open agent-orchestration frameworks as too complex to operationalise for collective use. *Freedom to operate over frontier dependency:* the workloads open-weight models handle well run on European inference via Scaleway, and the workloads where frontier quality still matters (deep extraction, single-message classification, judge arbitration) run on a small, named, replaceable Anthropic surface. *Coach over replacement:* agents train, prep, and debrief salespeople; they never act for them.

Individuals and the group teach each other through the system: signals from delivery work enrich a vector-indexed database that trains the next sales conversation, which in turn surfaces the next signal. We describe two layers — always-on jobs over PostgreSQL/pgvector and a Slack bot over GraphQL — a persona ensemble (Seth Godin, Lawrence Miller), and a discipline engine (pulse, weekly review, monthly retrospective, prep and debrief).

We report what the stack costs in model quality and what it buys in residency, optionality, and independence, and offer *freedom to operate* as a plainer frame than *sovereign*.

**Keywords:** agentic systems · multi-agent architecture · commercial intelligence · choreographed agents · methodology-first design · freedom to operate · European AI inference · multi-perspective scoring · experience report
