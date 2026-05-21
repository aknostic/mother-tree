# ASISAS 2026 — Narrative

**Submission type:** Experience Report (full paper, up to 16 pages, Springer LNCS)
**Venue:** ASISAS 2026 — Architecting Secure, Intelligent, and Sovereign Agentic Systems (workshop at ECSA 2026)
**Authors:** Jurg van Vliet, Flavia Paganelli, Jasper Geurtsen — Aknostic, Amsterdam, the Netherlands

## Naming

Project name in the paper: **Mother Tree**. Methodology name: **Mycorrhizal Method**. The paper presents Mother Tree as a worked example of a class of systems we call *commercial agent systems* — multi-agent commercial-intelligence systems designed for individual–collective mutualism.

## The provocation (paper's opening move)

Most agentic systems shipping today are **capability-first**: take a frontier model, grant it tools, point it at a goal, and trust autonomy to deliver. Mother Tree is the inversion. **It starts from a methodology — the Mycorrhizal Method, drawn from Challenger, Richardson, Simard's forest mutualism, and Wintzen's cell-based organising — and lets the methodology dictate the agents.** Agents in Mother Tree do not pursue goals. They serve a doctrine.

This inversion produced three concrete rejections, each defendable as an architectural decision:

1. **Choreography over autonomy.** No autonomous goal-seeking loops. Scheduled Python jobs on Kubernetes + LLM calls at known points + multi-judge scoring + human-in-the-loop. We evaluated and rejected agent-orchestration frameworks (e.g. OpenClaw) as too complex to operationalise for collective use.
2. **Freedom to operate over frontier dependency.** The core pipeline runs entirely on European open-weight inference (Scaleway: Qwen 3.5, Mistral Small, BGE Multilingual Gemma2 embeddings, Devstral / Llama / Gemma as judges). Anthropic's Haiku and Sonnet appear only at the triage/arbitration boundary — a small, expensive surface inside a cheap European core. Closed frontier models are *superior*; they are not *necessary*.
3. **Coach, not replacement.** Mother Tree does not write emails for hunters. It trains them, preps them, debriefs them, and weaves the signals from their work into the substrate that trains the next hunter's next conversation.

## The mutualism (the paper's central architectural claim)

The individual and the collective are **mutualistic by design, not by reporting**. The standard commercial-software pattern is "individual uses tool, organisation skims a dashboard." Mother Tree closes the loop:

- **Hunters** (consultative sellers) get coaching, conversation prep, debriefs, and a daily/weekly/monthly rhythm.
- **Gatherers** (delivery people) surface signals from project work in any channel — passively, conversationally.
- Signals enrich the **CI substrate** (insights, change, worldview, personas, competitors), vector-indexed via pgvector.
- The substrate is what trains the next hunter conversation, surfaces the next worldview, writes the next briefing.

Every interaction makes the next interaction better, on **both** ends. The collective is not a side-effect; it is the design.

## The architecture in one breath

Two layers. **Always-on**: PostgreSQL + pgvector + PostGraphile + scheduled workflows on Kubernetes, all on European infrastructure. **Interactive**: a Slack bot that participates in any channel as a conversational citizen; an operator CLI (`mothertree`) calls the same GraphQL API. **Persona ensemble**: Seth Godin (positioning), Lawrence Miller (consultative selling), trainer consensus (both at once). **Discipline engine**: pulse every 5 min, weekly review Mondays, monthly retrospective, calendar-aware prep/debrief 2 days before / 3 days after. *(Note: the system itself is built using Claude Code; that is a development tool, not part of the runtime.)*

No agent framework. No autonomous loops. One database, many choreographed jobs, two interactive surfaces, a persona ensemble, and a vector substrate underneath all of it.

## What the paper contributes

- **A pattern** — methodology-first, choreographed, mutualistic. Generalisable beyond sales.
- **A defence** — choreography is sufficient for commercial work; autonomy is overclaim. We argue this with the actual workflows.
- **A demonstration** — a working freedom-to-operate stack on European inference, deployed and used. We name what it cost (latency, edge-case reasoning quality) and what it bought (data residency, model optionality, no lock-in).
- **A reframing of "sovereign"** — we offer *freedom to operate* as the more precise, less politically captured term the conference title hints at, and define it operationally rather than aspirationally.

## Proposed paper structure (~16 pp + refs)

1. Introduction — the capability-first default and our inversion (~1.5 pp)
2. Background — Mycorrhizal Method; Simard, Challenger, Richardson, Wintzen (~2 pp)
3. Architecture — two layers, persona ensemble, vector substrate, discipline engine (~4 pp)
4. Choreography over autonomy — workflows, multi-judge scoring, human-in-the-loop (~2 pp)
5. Freedom to operate — model selection, where Anthropic appears, what it cost (~1.5 pp)
6. Mutualism in practice — hunter / gatherer / citizen flows, signal-to-substrate loop (~2 pp)
7. Lessons & limits — what worked, what didn't, what we'd do differently (~1.5 pp); KEIT as a second worked example of the freedom-to-operate stack
8. Related work, future work, conclusion (~1.5 pp)

## Confirmed decisions

- Submission type: experience report, full paper (16 pp).
- Project name in paper: Mother Tree.
- "OpenClaw" name-dropped in paper as the rejected framework class.
- Authors: Jurg van Vliet, Flavia Paganelli, Jasper Geurtsen — Aknostic.
- KEIT (github.com/aknostic/keit, running on Scaleway via the groupware project) referenced in §7 or §8 as a second worked example of the freedom-to-operate stack, anchoring Flavia and Jasper's contribution.
