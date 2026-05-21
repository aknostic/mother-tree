# Model Selection Policy

## Principles

1. **No OpenAI models.** Not for extraction, scoring, embedding, or any other function. This includes models derived from or branded as OpenAI (e.g., gpt-oss).
2. **Anthropic for the interactive layer and extraction.** Claude models power conversations, strategic output, fast classification, and deep extraction — where quality ceiling directly affects user experience and CI data quality.
3. **Open source for the scoring panel and background processing.** Scaleway open-weight models handle confidence scoring (architectural diversity matters), background extraction (Spotter/Weaver/Archivist), and consolidation. European infrastructure, no vendor lock-in on these functions.
4. **European second.** When choosing between equivalent open-source models, prefer European-origin models (Mistral, European research labs).

## Model roles

### Deep extraction — Claude Opus 4.6

```
Model: claude-opus-4-6
Provider: Anthropic API
Origin: Anthropic (proprietary)
Role: Foundation extraction (change, worldview, personas, competitors)
      and narrative extraction (reframes, evidence, stakeholder lenses,
      triggers). Extended thinking enabled.
Why: Best reasoning model available. The CI data is the foundation of
     everything — training, briefings, conversations all build on it.
     Better extraction = better everything downstream. Opus produces
     sharper change statements, more realistic personas, and reframes
     that hunters can actually use in conversation.
```

### Conversations + strategic output — Claude Sonnet 4.6

```
Model: claude-sonnet-4-6
Provider: Anthropic API
Origin: Anthropic (proprietary)
Role: DM freeform conversations, Seth persona, Lawrence persona,
      trainer consensus, QBR synthesis, weekly/monthly briefings,
      service meeting prep, training exercise generation, on-demand
      account reviews.
Why: Best balance of quality and speed for interactive use. Better
     at natural conversation, follows complex instructions, handles
     nuance. Streams to Slack for real-time feedback. Also used for
     triage arbitration (unchanged).
```

### Fast classification — Claude Haiku 4.5

```
Model: claude-haiku-4-5-20251001
Provider: Anthropic API
Origin: Anthropic (proprietary)
Role: Channel triage (respond/silent/signal), Pulse nudge generation,
      profile extraction (email/calendar/phone from DM text), debrief
      extraction, signal correction parsing. Also bulk triage of
      flagged insights (unchanged).
Why: Fast, cheap, reliable classification. In the hot path of every
     channel message — speed matters. Better than Mistral Small at
     understanding context and making nuanced respond/silent decisions.
```

### Background generation — Qwen 3.5 (397B, MoE 17B active)

```
Model: qwen3.5-397b-a17b
Provider: Scaleway Generative APIs
Origin: Alibaba Cloud / Qwen team (open-weight, Apache 2.0)
Role: Spotter (signal extraction from conversations), Weaver (entity
      resolution), Archivist (CI quality gate), thread summarization,
      consolidation (foundation dedup + profile synthesis).
Why: Strong reasoning on European infrastructure. These are background
     tasks — not user-facing, not latency-sensitive. Keeping them on
     Scaleway preserves European sovereignty for background processing.
```

### Document classification — Mistral Small 3.2 (24B)

```
Model: mistral-small-3.2-24b-instruct-2506
Provider: Scaleway Generative APIs
Origin: Mistral AI, France (open-weight, Apache 2.0, European)
Role: Document classification during ingestion (foundation/narrative/
      mixed/irrelevant), profile element extraction, profile rescanning.
Why: Fast structured output on European infrastructure. Classification
     during ingestion is batch, not interactive — Mistral Small is
     sufficient and keeps this step on Scaleway.
```

### Confidence scoring — three independent judges

Three architecturally different models score each extraction independently. Different training data, different biases, different blind spots. Median score with agreement check.

```
1. Devstral 2 123B Instruct
   Model: devstral-2-123b-instruct-2512
   Provider: Scaleway Generative APIs
   Origin: Mistral (open-weight, European)
   Role: Primary scorer — strong structured JSON output, European origin
   Why: Reliable JSON compliance, different architecture from Qwen, European.
        DeepSeek R1 70B was evaluated but returns reasoning tokens instead
        of JSON via Scaleway API — not usable for structured scoring.

2. Llama 3.3 70B Instruct
   Model: llama-3.3-70b-instruct
   Provider: Scaleway Generative APIs
   Origin: Meta (open-weight, Llama license)
   Role: Instruction-following scorer — reliable rubric adherence
   Why: Best instruction-following (IFEval 92.1), different training corpus

3. Gemma 3 27B IT
   Model: gemma-3-27b-it
   Provider: Scaleway Generative APIs
   Origin: Google DeepMind (open-weight)
   Role: Third independent perspective, cheapest scorer
   Why: Different architecture entirely, catches what the other two miss
```

### Embedding — BGE Multilingual Gemma2

```
Model: bge-multilingual-gemma2
Provider: Scaleway Generative APIs
Origin: BAAI (open-weight)
Role: Vector embeddings for semantic search (active on all CI tables)
Dimension: 3584
Why: Multilingual (important for European content), available on Scaleway.
     Embeddings generated on insert for all CI tables (insights, change,
     worldview, personas, competitors, signals, organization). Used for
     fetch_context similarity search, training source selection, cross-table
     briefings, signal dedup, and org profile merging (85% similarity).
```

## Pipeline flow

```
Content source (marketing repo, CoE, aknostic.com)
    │
    ├── Foundation lens ──► Opus 4.6 (deep extraction) ──► foundation tables
    │                       Mistral Small 3.2 (classification, Scaleway)
    │                       Context-aware: existing records injected to avoid duplicates
    │                       Pre-insert dedup as safety net
    │                       No scoring (foundation reflects our own positioning)
    │
    └── Narrative lens ──► Opus 4.6 (deep extraction) ──► field validation
                                                              │
                                                              ▼
                           Three independent scorers (Devstral 2, Llama 3.3, Gemma 3 — Scaleway)
                                                              │
                               ├── All agree high (>0.7) ──── auto-accept
                               ├── All agree low (<0.4) ───── auto-reject
                               ├── Disagreement (spread >0.3) flag
                               │       │
                               │       ▼
                               │   Haiku 4.5 ──── triage
                               │       │
                               │       ├── Clear ──── done
                               │       └── Ambiguous ── escalate
                               │               │
                               │               ▼
                               └────────── Sonnet 4.6 ──── arbitration

Bot conversations, personas, training ──► Sonnet 4.6 (streaming)
Channel triage, Pulse nudges ──► Haiku 4.5 (fast)
Background extraction (Spotter/Weaver) ──► Qwen 3.5 (Scaleway)
```

## Sovereignty posture

The scoring panel and background processing run on European infrastructure (Scaleway) using open-weight models. Document classification during ingestion stays on Scaleway (Mistral Small).

The interactive layer (conversations, personas, triage) and content extraction (foundation + narrative) go through Anthropic. This is a conscious tradeoff: better UX and CI data quality vs. pure European sovereignty. User conversations and extracted content pass through Anthropic's API.

If Anthropic becomes unavailable:
- Bot conversations fall back to Qwen 3.5 on Scaleway (set `CONVERSATION_MODEL` env var)
- Fast classification falls back to Mistral Small (set `FAST_MODEL` env var)
- Deep extraction falls back to Qwen 3.5 (set `DEEP_EXTRACTION_MODEL` env var)
- The scoring panel continues without interruption (Scaleway)
- Background extraction continues without interruption (Scaleway)

All model assignments are configurable via environment variables — no code change needed to switch providers.

## Excluded models

| Model | Reason |
|-------|--------|
| gpt-oss-120b | OpenAI-derived. Policy: no OpenAI models. |
| Any OpenAI API model | Policy: no OpenAI models. |
| Any model requiring OpenAI API key | Policy: no OpenAI dependency. |
| deepseek-r1-distill-llama-70b | Reasoning-only on Scaleway — returns thinking tokens, not structured JSON. Not usable for scoring. |
