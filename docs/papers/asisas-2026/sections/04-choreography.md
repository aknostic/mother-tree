# 4 Choreography over Autonomy

The dominant pattern in agentic systems is to give a frontier model a goal and a set of tools, and to let an autonomous loop decide what to do next. We evaluated this pattern across several agent-orchestration frameworks (§8.1) and rejected it as the basis for a collective commercial tool.

## 4.1 What autonomy implies for a collective tool

Autonomy works for a single user with a discrete task. It fits poorly when the agent serves a collective, where its output enters a substrate read by other people, its decisions accumulate into a structure that subsequent decisions rely on, and its mistakes propagate through other agents that consume its output. Two properties matter most in this setting, and an autonomous loop handles both weakly.

The first is **auditability and reviewability**. The choreography pattern preserves a trace that autonomy hides: each record carries its source document and the run that produced it (`ingestion_log`), and every LLM call has a named entry point in the codebase. The substrate today stores the median of the three judge scores per record as `confidence`; the columns we have not yet added (model-per-record, prompt context, raw judge scores) and the reviewer queue we have not yet built on top of flagged records are named gaps (§3.5, §8.3) rather than denied features. The architectural point is that adding them is a column or a notifier, not an unwind. An autonomous loop with internal tool calls, retries, and self-corrections does not lose this information by accident; it loses it on purpose, because the loop is built to manage internal state rather than expose it. It offers one human boundary per task; the design here is to provide one per LLM call, and we have started where the cost is lowest.

The second is **boundedness**. An autonomous agent's tool-call count is itself a function of the model's reasoning, so cost, latency, and rate limits become probability distributions over the run rather than functions of the input. A system running hundreds of ingestion documents per week, a thousand pulse cycles per day, and a daily training piece per user does not want distributional cost; it wants budgets that survive a quarterly forecast.

A capability-first version of Mother Tree would start with a frontier model, give it the tools the cronjobs currently perform (read sitemap, parse document, write PostgreSQL, schedule Slack message), set "improve sales performance" as the goal, and run an autonomous loop per practitioner. Each user would have a private agent with private context, and cross-user mutualism (gatherer signal arriving in hunter prep) would require either a shared agent or an explicit hand-off protocol. The substrate is incidental in that version; in ours, it is the thing the rest of the system is built around.

## 4.2 The choreography pattern

We use a small set of conventions, applied uniformly:

1. **Workflows are scheduled, not driven.** Each pipeline (foundation ingestion, narrative ingestion, training delivery, weekly review, monthly retrospective, calendar sync, pulse) is a Kubernetes CronJob with a fixed schedule. There is no agent that decides when to run; the cron does.
2. **LLM calls happen at known points.** Each call has a name in the codebase (e.g. `extract`, `extract_deep`, `extract_profile`, `score`, `triage`, `arbitrate`, `character_respond`), a model assignment that is either hardcoded or supplied from config, a fixed prompt template, and a fixed input contract. The LLM is a function with a stable signature, not an agent with a goal.
3. **Multi-judge scoring and triage replace self-evaluation.** Every narrative-ingest record is scored by three independent Scaleway judges (Devstral 2 123B, Llama 3.3 70B, Gemma 3 27B) on a 0–1 scale. Decisions are by quorum (`min ≥ 0.7` accepts, `max ≤ 0.4` drops, `spread ≥ 0.3` flags). Flagged records escalate to a Haiku 4.5 triage call that either defers to Sonnet 4.6 arbitration or marks the record `flagged=True` for human review. Triage isn't autonomy; it's a fixed dispatcher acting on a probabilistic input. The reviewer-facing queue on top of the flag is future work (§8.3).
4. **Writes are reversible.** `mothertree dump` and `mothertree restore` are operator-run commands that snapshot the substrate to JSON and restore it. Automating the snapshot is on the gap list.
5. **Idempotency is enforced at the data layer.** Foundation extraction runs a cosine-similarity check against existing records before insertion; signals are deduplicated by thread and content; embeddings are backfilled lazily by `embed-backfill`. Running anything twice converges to the same substrate state, by construction of the dedup checks rather than by deterministic LLM output.

## 4.3 Trade-offs we accepted

The system **cannot improvise**. Documents that do not classify fall through to a default extractor; a new pipeline is written by a human, not by the system. That is the property that makes it reviewable. Latency is **right-time, not real-time**: the pulse runs every five minutes, calendar prep arrives two business days before a meeting, the debrief three days after. Throughput is **bounded** by the cron schedule, not the model; we have not yet hit a case where the substrate accumulates slower than human consumers can read.

