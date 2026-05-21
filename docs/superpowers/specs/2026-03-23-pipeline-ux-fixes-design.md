# Pipeline UX Fixes: Thinking Indicator, Thread Eagerness, Fact Preservation

## Problem

Three UX issues in the Slack bot pipeline:

1. **Thinking indicator flash in channels.** Mother Tree posts "_thinking..._" as a message, then updates or deletes it. In the main channel timeline this causes a visible flash — a reply appears and vanishes. In threads and DMs it works fine.

2. **Thread reply silence.** When someone replies in a thread Mother Tree is already participating in, triage sometimes decides to stay silent. She should always respond in threads where she has already spoken.

3. **Fact mangling.** Annotations like enrollment status, stats, and scores get the instruction "weave this data into your response naturally." The LLM rephrases factual values — saying "good progress" instead of "Stage 0, Chapter 2, streak 3 days."

## Fix 1: Thinking reaction in channels

### Current behavior

`_post_thinking()` in `pipeline.py:85-96` posts a message (`chat_postMessage`) with `"_thinking..._"`. `_resolve_thinking()` updates it with the real response via `chat_update`. `_delete_thinking()` removes it via `chat_delete` when triage says silent.

### Change

When `context_type == "channel"` and `reply_thread_ts == ts` (top-level, not a thread reply), use a reaction on the user's message instead of posting a reply.

**Return type change:** All three thinking functions change from `str | None` to `dict | None`. The parameter `thinking_ts` in `_resolve_thinking` and `_delete_thinking` is renamed to `thinking_info` with type `dict | None`.

**`_post_thinking()`** gains two new parameters: `context_type` and `message_ts` (the user's message ts). If channel top-level (context_type == "channel"): call `reactions_add(name="thought_balloon", channel=channel_id, timestamp=message_ts)`. Return `{"type": "reaction", "ts": message_ts}`. Otherwise, post the message as before and return `{"type": "message", "ts": thinking_ts}`.

**`_resolve_thinking()`** takes `thinking_info: dict | None` instead of `thinking_ts: str | None`. If type is "reaction": call `reactions_remove(name="thought_balloon", channel=channel_id, timestamp=thinking_info["ts"])`, then post the response as a new message starting a thread on the user's message: `chat_postMessage(channel=channel_id, thread_ts=thinking_info["ts"], text=response)`. The stored `ts` serves double duty — it is both the reaction target and the thread parent. If type is "message": `chat_update` as before.

**`_delete_thinking()`** takes `thinking_info: dict | None`. If type is "reaction": call `reactions_remove`. If type is "message": `chat_delete` as before.

**In `_process_message()`** line 139: pass `context_type` and `ts` to `_post_thinking()`. Update all references from `thinking_ts` to `thinking_info`.

### Files changed

`jobs/bot/pipeline.py` — modify `_post_thinking`, `_resolve_thinking`, `_delete_thinking`, and their call sites in `_process_message`.

## Fix 2: Thread reply eagerness

### Current behavior

`pipeline.py:186-187` runs triage for all non-pattern-matched messages. Triage prompt says "be conservative in channels — if unsure, stay silent." No distinction between channel top-level and thread replies where Mother Tree already participates.

### Change

Before calling `triage()`, check if we are in a thread and Mother Tree has previously responded. If so, skip triage and force respond.

In `pipeline.py` around line 186, replace:

```python
triage_result = triage(clean_text, participant_count, memory_ctx["messages"][-5:])
```

With:

```python
# Always respond in threads where Mother Tree already participates
in_active_thread = (
    context_type == "thread"
    and any(m.get("role") == "assistant" for m in memory_ctx["messages"])
)
if in_active_thread:
    triage_result = {"respond": True, "signal": {"capture": False, "confidence": 0.0}, "reason": "active thread participant"}
else:
    triage_result = triage(clean_text, participant_count, memory_ctx["messages"][-5:])
```

No LLM call. No new function. Check thread memory for any assistant message.

### Files changed

`jobs/bot/pipeline.py` — add thread eagerness check before triage call.

## Fix 3: Fact preservation in prompts

### Current behavior

In `ask_with_history()` at `ask.py:408-411`, all annotations get:

```
SYSTEM ANNOTATION (status):
{JSON}
Weave this data into your response naturally.
```

The CONTEXT AWARENESS section in `build_system_prompt()` also says "weave these into your response naturally."

### Change

Split annotations into factual and contextual. Factual annotations contain structured data that must be stated accurately. Contextual annotations contain content to discuss freely.

**Factual types:** `status`, `stats`, `enrolled`, `answer_scored`, `progress`, `exercise_started`, `enroll`

**Contextual types:** `url_content`, `training_delivered`, `citizen_inspiration`, `practice_delivered`, `persona`, `error`, `help`

In `ask_with_history()`, replace lines 408-411:

```python
if annotation:
    ann_type = annotation.get("type", "")
    if ann_type in FACTUAL_ANNOTATION_TYPES:
        system += f"\n\nFACTS (state these exactly, do not rephrase or omit any values):\n{json.dumps(annotation, default=str)}"
        system += "\nPresent these facts conversationally but do not change the values."
    else:
        system += f"\n\nCONTEXT ({ann_type}):\n{json.dumps(annotation, default=str)}"
        system += "\nWeave this into your response naturally."
```

Add constant at module level:

```python
FACTUAL_ANNOTATION_TYPES = {
    "status", "stats", "enrolled", "answer_scored",
    "progress", "exercise_started", "enroll",
}
```

Update `build_system_prompt()` CONTEXT AWARENESS section — replace "Weave these into your response naturally" with:

```
You may receive FACTS or CONTEXT from the system. State FACTS exactly
as given — do not rephrase values, numbers, or status information.
Discuss CONTEXT naturally. You are a person sharing information, not
a system displaying output.
```

### Files changed

`jobs/mothertree/ask.py` — add `FACTUAL_ANNOTATION_TYPES` constant, modify annotation injection in `ask_with_history()`, update CONTEXT AWARENESS text in `build_system_prompt()`.

## Testing

### Fix 1 tests

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_thinking_reaction_in_channel` | context_type="channel", top-level message | `reactions_add` called, not `chat_postMessage` |
| `test_thinking_message_in_thread` | context_type="thread" | `chat_postMessage` called as before |
| `test_thinking_message_in_dm` | context_type="dm" | `chat_postMessage` called as before |
| `test_resolve_thinking_reaction` | thinking type="reaction" | `reactions_remove` called, then `chat_postMessage` |
| `test_resolve_thinking_message` | thinking type="message" | `chat_update` called as before |
| `test_resolve_thinking_reaction_threads` | thinking type="reaction", resolve called | `chat_postMessage` called with `thread_ts` set to user's message ts |
| `test_delete_thinking_reaction` | thinking type="reaction" | `reactions_remove` called |

### Fix 2 tests

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_thread_always_responds_when_participated` | context_type="thread", memory has assistant message | triage not called, respond=True |
| `test_thread_triages_when_not_participated` | context_type="thread", memory has no assistant messages | triage called normally |
| `test_channel_still_triages` | context_type="channel" | triage called regardless of memory |

### Fix 3 tests

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_factual_annotation_uses_facts_label` | annotation type="status" | System prompt contains "FACTS" not "CONTEXT" |
| `test_contextual_annotation_uses_context_label` | annotation type="url_content" | System prompt contains "CONTEXT" not "FACTS" |
| `test_factual_prompt_says_state_exactly` | annotation type="enrolled" | System prompt contains "state these exactly" |
| `test_context_awareness_updated` | No annotation | build_system_prompt() contains "State FACTS exactly" |

## Files changed summary

| File | Changes |
|------|---------|
| `jobs/bot/pipeline.py` | Thinking reaction for channels, thread eagerness check |
| `jobs/mothertree/ask.py` | FACTUAL_ANNOTATION_TYPES constant, split annotation injection, update CONTEXT AWARENESS |
| `jobs/tests/test_pipeline_ux.py` | New test file for all three fixes |
