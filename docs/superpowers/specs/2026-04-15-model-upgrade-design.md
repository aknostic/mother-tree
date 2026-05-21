# Model Upgrade — Anthropic for Interactive + Extraction Layers

## Problem

All bot conversations, strategic output (briefings, training), and content extraction run on Qwen 3.5 and Mistral Small via Scaleway. Quality ceiling is noticeable in conversations (generic responses, missed nuance), extraction (sharp-enough-but-not-great reframes), and fast classification (triage misses).

## Decision

Upgrade to Anthropic models across three tiers. Keep the scoring panel, background extraction, consolidation, and embeddings on Scaleway.

## Model Assignment

### Opus 4.6 — deep extraction (batch pipeline)

Foundation and narrative `extract_deep()`. These feed everything downstream — training, briefings, conversations. Better extraction = better everything.

- `extract_deep()` in `llm.py`
- Config: `DEEP_EXTRACTION_MODEL = "claude-opus-4-6"`

### Sonnet 4.6 — conversations + strategic output

All user-facing generation: DM freeform, Seth, Lawrence, trainer consensus, QBR synthesis, weekly/monthly briefings, service meeting prep, training exercises.

- `generate()` and `chat_conversation()` in `llm.py`
- Config: `CONVERSATION_MODEL = "claude-sonnet-4-6"` (replaces `GENERATION_MODEL` for interactive use)

### Haiku 4.5 — fast classification

Channel triage, Pulse nudge generation, profile extraction, debrief extraction. Speed-critical, in the hot path.

- `extract()` and `chat()` in `llm.py`
- Config: `FAST_MODEL = "claude-haiku-4-5-20251001"` (replaces `EXTRACTION_MODEL` for interactive use)

### Unchanged (Scaleway)

| Function | Model | Why |
|---|---|---|
| Scoring judges | Devstral 2, Llama 3.3, Gemma 3 | Independence panel — architectural diversity matters |
| Background extraction (Spotter/Weaver/Archivist) | Qwen 3.5 | Not user-facing, sovereignty |
| Consolidation | Qwen 3.5 | Batch dedup, sovereignty |
| Embeddings | BGE Multilingual Gemma2 | No Anthropic alternative |

## Architecture Change

### Routing in `llm.py`

Each LLM function gains model routing: if the model ID starts with `claude-`, use `anthropic_client`. Otherwise use `scaleway` (OpenAI-compatible). This keeps backward compatibility — callers can still pass a Scaleway model explicitly.

### Streaming

The Anthropic SDK streams differently from OpenAI-compatible APIs:

```python
# OpenAI-compatible (current)
stream = scaleway.chat.completions.create(..., stream=True)
for chunk in stream:
    delta = chunk.choices[0].delta.content

# Anthropic SDK
with anthropic_client.messages.stream(...) as stream:
    for text in stream.text_stream:
        ...
```

Both paths needed in `chat_conversation()`.

### Thinking budget

Qwen 3.5 uses `extra_body={"thinking": {"type": "enabled", "budget_tokens": 4096}}`. Anthropic uses `thinking={"type": "enabled", "budget_tokens": 4096}` as a top-level parameter. Only Opus needs thinking for extraction; Sonnet and Haiku don't need it for their tasks.

### Streaming gap fix

Seth and Lawrence personas currently don't receive `on_chunk` — they block silently. Fix this by passing `on_chunk` through in `_get_response()`.

## Config Changes

```python
# New model constants
CONVERSATION_MODEL = "claude-sonnet-4-6"
FAST_MODEL = "claude-haiku-4-5-20251001"
DEEP_EXTRACTION_MODEL = "claude-opus-4-6"

# Keep for backward compat (batch pipeline, background)
GENERATION_MODEL = "qwen3.5-397b-a17b"      # Spotter, Weaver, Archivist, consolidation
EXTRACTION_MODEL = "mistral-small-3.2-24b-instruct-2506"  # document classification
```

## Callers to Update

### Use CONVERSATION_MODEL (Sonnet 4.6)

- `generate()` default model
- `chat_conversation()` default model
- All discipline modules (weekly, monthly, QBR, calendar, service meeting)
- Training generation (`training/engine.py`, `training/generate.py`)

### Use FAST_MODEL (Haiku 4.5)

- `extract()` default model
- `chat()` default model
- Dispatcher triage
- Pipeline profile extraction
- Pulse nudge generation

### Use DEEP_EXTRACTION_MODEL (Opus 4.6)

- `extract_deep()` default model
- Foundation + narrative ingestion

### Keep GENERATION_MODEL (Qwen 3.5, explicit)

- `bot/characters/spotter.py` — pass `model=GENERATION_MODEL` explicitly
- `bot/characters/weaver.py` — pass `model=GENERATION_MODEL` explicitly
- `bot/characters/archivist.py` — pass `model=GENERATION_MODEL` explicitly
- `ingestion/ingest.py` consolidation — pass `model=GENERATION_MODEL` explicitly
- `bot/memory.py` summarization — pass `model=GENERATION_MODEL` explicitly

### Keep EXTRACTION_MODEL (Mistral Small, explicit)

- `ingestion/profile.py` document classification — pass `model=EXTRACTION_MODEL` explicitly

## Testing

- Existing tests mock LLM calls — no API calls in tests
- Add tests for model routing logic (claude- prefix → Anthropic client)
- Verify streaming works with Anthropic SDK mock

## Policy Update

Update `docs/model-selection-policy.md`:
- Interactive layer + extraction: Anthropic (Opus, Sonnet, Haiku)
- Scoring panel + background processing: Scaleway open-source
- Sovereignty: CI data pipeline scoring remains European; conversations and extraction go through Anthropic
