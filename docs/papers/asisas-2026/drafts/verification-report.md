# Full-document fact-check — ASISAS 2026 submission

Verified against the production cluster (`mother-tree` namespace, PostgreSQL via `mother-tree-db-1`), the source repo, and `docs/runbook.md` on 2026-05-11.

Categories:
- **TRUE** — verified to match code or live state.
- **FALSE** — contradicted by code or live state.
- **PARTLY** — claim is partly accurate but overstates or understates.
- **UNVERIFIABLE** — subjective, historical, or out of my access.
- **STALE** — was true when written; live state has since changed.

---

## The big-ticket findings (rank-ordered by impact)

### 1. Deep extraction runs on Claude Opus 4.6, not Qwen 3.5 397B

This is the most consequential single error. It contradicts the paper's core "freedom to operate" thesis.

- `config.py` sets `DEEP_EXTRACTION_MODEL = "claude-opus-4-6"` as the default.
- No production cronjob manifest overrides this env var.
- `extract_deep(content, prompt)` is called from `ingestion/extract.py:175,199` (foundation extraction and narrative extraction) with **no `model` argument**, so it falls through to `DEEP_EXTRACTION_MODEL`.
- `llm.py:114` routes Claude-family models to Anthropic.

**Affected claims:**
- §1 introduction: "core ... runs end-to-end on European open-weight inference"
- §3.2: "Anthropic models touch production ingestion" only at triage/arbitration
- §5.2 Table 1: "Deep extraction (foundation, narrative): Qwen 3.5 397B, Scaleway"
- §5.4 #1: "Every byte of customer data, every model call ... lives within European jurisdiction"
- §8.4 conclusion: "free of frontier-model dependency, all at once, in production"

**Fix paths**:
- Honest paper edit — describe deep extraction as Anthropic; redo §5.2 table; soften §1, §5.4, §8.4 claims; OR
- Production fix first — set `DEEP_EXTRACTION_MODEL=qwen3.5-397b-a17b` in cronjob env, redeploy, then write the paper as already written. This makes the paper true going forward, but the historical ingestion was on Opus.

### 2. The whole consent narrative is fabricated

The paper twice claims a consent flow that doesn't exist.

- `users` table has no consent column (verified live).
- `identity.py:resolve_user` auto-creates as citizen with no consent ask.
- Spotter runs on every message in every channel the bot is in.

**Affected claims:**
- §3.5 Consent paragraph (full)
- §6 gatherer "(with consent) to deposit signals"
- §8.3 future work "where consenting organisations share patterns"

### 3. The `#mt-review` queue and 1% sampling are inventions

Both were added in earlier "self-criticism" edits and not implemented.

- No `#mt-review` channel referenced anywhere in the code.
- Flagged records (`flagged=True`) just sit in the `insights` table with no notification, no Slack post, no queue.
- No sampling code anywhere.

**Affected claims:**
- §3.5 Trust ("`#mt-review` queue exists ... sample at 1%")
- §4.2 ("routes to a human reviewer in `#mt-review`")
- §5.3.1 ("We currently sample auto-accepted records into the review queue at 1% to test")
- §8.2 patterns ("the human boundary sits per-LLM-call")

### 4. Row-level security claim is false

- `pg_policies` is empty.
- No tables have `rowsecurity=true`.
- Real authz is a single shared `x-hasura-admin-secret` header check in `deploy/graphql/server.js`.

**Affected claims:**
- §3.1 "authorisation is row-level security in the database"
- §3.5 "Authorisation lives in the database" / "PostGraphile exposes the schema through PostgreSQL row-level security"

### 5. "Containers do not yet run as non-root" is the opposite of reality

Both `Dockerfile.bot` (line 13) and `Dockerfile.jobs` (line 19) have `USER 1000:1000`.

**Affected claim:**
- §3.5 hardening gaps

### 6. §7.3 is a TODO placeholder, but §1, §7.1, §7.2, §7.4, §8.4 claim measurement is done

- §1 contribution #4 says "Measured environmental impact".
- §7.1 says "we measure them ... with KEIT" and "we account for [KEIT's own footprint] explicitly".
- §7.4 says "Both estimates are approximate **and reported with their assumptions**" — but nothing is reported.
- §8.4 says "a sustainability claim reported in grams of CO₂ rather than asserted in slogans" — but no number is reported.

KEIT itself exists on GitHub. Whether it's deployed on the cluster is unverifiable from my namespace-scoped kubeconfig.

---

## Section-by-section summary

### Abstract

| Claim | Status |
|---|---|
| Python jobs on Kubernetes at scheduled points | TRUE |
| Multi-judge scoring **and a human in the loop** | PARTLY — scoring yes, no actual human-in-loop queue |
| Rejected frameworks like OpenClaw | UNVERIFIABLE (OpenClaw not findable; abstract still names it) |
| Core runs on European open-weight inference via Scaleway | **FALSE** (Opus for deep extraction) |
| Proprietary models appear only at triage and arbitration | **FALSE** (also Spotter, Weaver, Opus extraction) — also contradicts §1 line in same paper |
| "Signals from delivery work" | **MISLEADING** (0 gatherers; signals come from hunter's channels) |
| "We report what the stack costs in model quality" | **OVERSTATED** (§5.3 says no head-to-head) |

### §1 Introduction

| Claim | Status |
|---|---|
| "In production at Aknostic since early 2026" | TRUE (loose) |
| Nine named personas | TRUE |
| Two weeks evaluating agent-orchestration frameworks | UNVERIFIABLE |
| Anthropic only at triage/arbitration boundary + Spotter/Weaver | FALSE (also Opus for deep extraction) |
| Contribution 3: "passive signal capture from **delivery people**, ... lighter **weekly** nudges for everyone else" | **WRONG** — 0 delivery people enrolled; citizen nudges are *twice weekly* (Tue/Thu), not weekly |
| Contribution 4: "Measured environmental impact" | **OVERCLAIM** — §7.3 is TODO |
| Section preview "§7 reports measured CO₂ via KEIT" | **FALSE** — §7.3 unwritten |

### §2 Background

All four citations are real publications used in defensible ways. **No false claims.**

### §3 Architecture (excluding §3.5, separately verified)

| Claim | Status |
|---|---|
| PostgreSQL 17 + pgvector 0.8.2 (CloudNativePG) | TRUE (live: PG 17.9, pgvector 0.8.2) |
| PostGraphile at `mothertree.aknostic.com/graphql` | TRUE |
| "authorisation is row-level security in the database" (§3.1) | **FALSE** (no RLS, no policies) |
| Six CI tables listed | TRUE |
| User-facing tables include **`enrollments`** | **FALSE** — table is named `training_progress`, plus `enrollment_requests` for pending requests; no `enrollments` table exists |
| "Slack and calendar URLs attach via `channel_links`" | **PARTLY FALSE** — calendar URLs live on `users.calendar_url`, not in `channel_links` |
| `vector(3584)` BGE Multilingual Gemma2 embeddings on CI tables | TRUE |
| 85% similarity threshold for organisation-profile merge | TRUE (`profile.py:190`) |
| "Every read of the database goes through vector search" | **FALSE/OVERSTATED** — many reads (users, contacts, ID lookups) don't |
| Foundation ingestion weekly, narrative ingestion daily, pulse every 5 min, embed-backfill | TRUE |
| **Discipline weekly review (Mondays 08:00)** | TIMEZONE DRIFT — cron is `0 7 * * 1` UTC = 09:00 CEST (today, summer); 08:00 in CET winter |
| **Monthly retrospective (1st of the month, 09:00)** | **OFF BY ONE HOUR** — cron is `0 8 1 * *` UTC = 10:00 CEST / 09:00 CET |
| **Calendar sync (twice daily)** | **FALSE** — cron is `0 6 * * 1-5` once daily; one run handles both prep and debrief windows |
| **Quarterly QBR** | MISLEADING — cron fires weekly (`0 7 * * 1`); the script gates with `get_due_qbrs()`, so the *effective* cadence depends on data |
| Multi-judge thresholds | TRUE |
| "This is the entire surface on which Anthropic models touch production ingestion" | **FALSE** — Opus (Anthropic) is the default deep extraction model |
| Deployment: namespace, Flux, kaniko, CloudNativePG, Scaleway Paris | TRUE |

### §3.5 Security and trust (rewritten draft in `drafts/03.5-rewrite.md`)

All findings detailed in the earlier separate fact-check. Eleven of ~28 claims false.

### §4 Choreography

| Claim | Status |
|---|---|
| 7 named LLM functions listed | 3/7 don't exist as named (`score_insight`, `triage_disagreement`, `respond_as_seth`, `weave_signal`) — actual functions are `score`, `triage`, `character_respond`, and there's no `weave_signal` |
| Multi-judge thresholds and decisions | TRUE |
| "routes to a human reviewer in `#mt-review`" | **FALSE** |
| "The substrate is dumped to JSON before each consolidation pass" | **FALSE** — manual CLI only |
| Idempotency (cosine-sim dedup, embed-backfill lazy) | TRUE |

### §5 Freedom to Operate

| Claim | Status |
|---|---|
| Model table — most entries | TRUE |
| **Deep extraction = Qwen 3.5 397B on Scaleway** | **FALSE** (Opus) |
| "Core ingestion and training pipelines run end-to-end on European open-weight inference" | **FALSE** (same) |
| §5.3.1 corpus 289 docs (110 foundation + 179 narrative) | TRUE |
| §5.3.1 944 → 303 → 189 dedup numbers | TRUE |
| §5.3.1 1,416 → 977 insights | TRUE |
| §5.3.1 815/816 auto-accept, mean 0.87 | TRUE |
| §5.3.1 "We currently sample auto-accepted records into the review queue at 1%" | **FALSE** |
| §5.4 #1 European jurisdiction for every model call | **FALSE** (Opus calls) |
| §5.4 #2 "swapped extraction models four times" | UNVERIFIABLE |

### §6 Mutualism

| Claim | Status |
|---|---|
| Three roles, escalation admin-gated, citizens auto-created | TRUE |
| Gatherer "(with consent)" | **FALSE** |
| **"The trace is real; we anonymise the company"** | **MISLEADING** — first signal is 2026-04-14, but the trace says "In March". Mechanism is real; specific scenario is illustrative |
| Reframe quote from substrate | TRUE |
| Usage scale numbers (3 users, 1 hunter / 2 citizens, 4 Slack links) | **STALE** — today's Matthijs auto-create made it 4 users / 1 hunter / 3 citizens / 4 Slack links |
| 96 signals, 210 interactions, 61 contacts, 62 companies | TRUE |
| Four weekly reviews, one monthly retro | TRUE (and today's weekly silently failed before manual rerun — worth noting if we want full honesty) |

### §7 KEIT

| Claim | Status |
|---|---|
| KEIT as Apache-2.0 open-source tool | TRUE (GitHub) |
| KEIT composition | TRUE per upstream |
| "**We measure them, on the same cluster Mother Tree runs on, with KEIT**" | **UNVERIFIABLE** — my kubeconfig is namespace-scoped to `mother-tree`. The §7.3 TODO implies no measurements yet |
| "KEIT runs in its own namespace; its own CO₂ cost is a small constant we account for explicitly" | **OVERCLAIM** — implies measurement, but §7.3 is TODO |
| §7.4 "Both estimates are approximate **and reported with their assumptions**" | **FALSE** — nothing reported |
| "the architectural decisions in §3 and §4 ... make a measurable difference" | **OVERCLAIM** — nothing measured comparatively |

### §8 Related Work / Lessons / Future / Conclusion

| Claim | Status |
|---|---|
| Frameworks evaluated (CrewAI, LangGraph, AutoGen) | UNVERIFIABLE |
| Lesson #2 "fixed model assignment, recorded input" | PARTLY (per §3.5 findings) |
| Pattern: "human boundary per-LLM-call" | **FALSE** (no human boundary actually exists) |
| Future work: candidate Spotter/Weaver replacement under evaluation | UNVERIFIABLE |
| **§8.4 "runs its core on European open-weight inference"** | **FALSE** |
| **§8.4 "sustainability claim reported in grams of CO₂"** | **FALSE** |
| **§8.4 "free of frontier-model dependency"** | **FALSE** |

---

## Tally

Across the paper there are roughly **120 verifiable claims**. Of those:

- **TRUE: ~75** (system specs, schema, citations, cron mechanics, model names, observed numbers)
- **FALSE: ~22** (centred on RLS, consent, review queue, deep-extraction model, several conclusion sentences)
- **PARTLY / OVERSTATED: ~13**
- **UNVERIFIABLE: ~8** (claims about evaluation history, internal processes, future work)
- **STALE: ~2** (usage scale paragraph after today's events)

The false claims concentrate in four areas: **security/trust (§3.5)**, **consent (§6, §3.5, §8.3)**, **review queue / human-in-the-loop (§3.5, §4.2, §5.3.1, §8.2)**, and **the European-only core (§1, §3.2, §5.2, §5.4, §8.4)** — the last of which is the largest because it's load-bearing for the freedom-to-operate thesis.

The Opus-for-deep-extraction issue is the one that most needs a decision before any honest version of the paper ships: either (a) change the production config so Qwen handles deep extraction and the paper becomes true, or (b) rewrite the European-only-core claims to acknowledge Anthropic is in the deep-extraction path too. (a) is two lines in a cronjob manifest; (b) is a rewrite of several core paragraphs.
