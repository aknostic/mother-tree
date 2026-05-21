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
4. **Planned measurement of environmental impact** through KEIT, an open-source Kubernetes emissions monitoring tool we also build and run; the intent is that the conference's *sustainable, responsible autonomy* pillar can be reported in grams of CO₂ rather than asserted (numbers reported in §7).

We use *freedom to operate* throughout as a plainer frame than *sovereign*: *which choices about this system would we lose if a particular dependency were withdrawn?* The claim isn't that *sovereign* is wrong; it has just drifted toward rhetoric.

§2 introduces the Mycorrhizal Method. §3 describes the architecture, including a section on security and trust (§3.5). §4 defends choreography over autonomy. §5 defends freedom-to-operate inference. §6 traces the individual–group loop through a worked example. §7 sets up CO₂ measurement via KEIT (numbers pending). §8 discusses related work, lessons, and future work.
