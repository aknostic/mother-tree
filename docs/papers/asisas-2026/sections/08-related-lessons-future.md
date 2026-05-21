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

Three patterns generalise beyond sales. *Substrate-mediated mutualism* is a read-write substrate owned by many independent processes; no process owns the state, so individual usage and collective enrichment become one feedback loop. *Choreographed multi-persona* is many addressable LLM-backed components composed by an external orchestrator rather than by inter-agent messaging — multi-agent without being agentic. *Quorum-based admission* uses multi-judge scoring to decide whether a record enters the substrate, not to evaluate model output: the decision is by quorum (`min` accept, `max` reject, `spread` triage), and the human boundary sits per-LLM-call rather than per-task. We have not seen this third pattern named in the literature; we think it is the smallest defensible alternative to single-model self-scoring in production.

## 8.3 Future work

**Reviewer-facing queue for flagged records.** The substrate marks judge-disagreement records as `flagged=True` and leaves them. Routing those to a human reviewer and sampling auto-accepted records into the same queue is the most important trust work we owe the system — what turns the quorum pattern from "three votes" into "three votes plus a human spot-check".

**Shrinking the Anthropic surface.** Deep extraction, the Spotter, and the Weaver are the remaining Anthropic-essential calls; a candidate replacement (Qwen 3.5 397B with a tightened prompt plus Devstral verification) is under evaluation.



## 8.4 Conclusion

Mother Tree is a methodology-first, choreographed multi-agent system in production: open-weight inference where it suffices, a named replaceable Anthropic surface where frontier quality matters, and the individual salesperson and shared database as one feedback loop. It answers the three ASISAS pillars — multi-agent without an agent runtime, trust through auditable scheduling and quorum admission, sustainability to be reported in grams of CO₂ rather than asserted (§7, pending) — with the named gaps to close before claiming more.
