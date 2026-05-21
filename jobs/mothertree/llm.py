"""LLM clients — shared across all Mother Tree components."""

import json
import logging

from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from mothertree.config import (
    ANTHROPIC_API_KEY,
    ARBITRATION_MODEL,
    CONVERSATION_MODEL,
    DEEP_EXTRACTION_MODEL,
    FAST_MODEL,
    GENERATION_MODEL,
    SCALEWAY_AI_API_KEY,
    SCALEWAY_AI_BASE_URL,
    TRIAGE_MODEL,
)

log = logging.getLogger(__name__)

# Thinking models (like Qwen 3.5) use internal reasoning that consumes tokens.
# Cap the thinking budget so visible output tokens are guaranteed.
THINKING_BUDGET = {"thinking": {"type": "enabled", "budget_tokens": 4096}}

# Scaleway — extraction, scoring, generation, embedding. Construct only when a
# key is configured so the package can be imported in environments without
# credentials (CI, tests). Runtime calls will fail loudly if scaleway is None.
scaleway = (
    OpenAI(base_url=SCALEWAY_AI_BASE_URL, api_key=SCALEWAY_AI_API_KEY)
    if SCALEWAY_AI_API_KEY
    else None
)

# Anthropic — triage and arbitration only
anthropic_client = None
if ANTHROPIC_API_KEY:
    import anthropic
    anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _is_claude(model: str) -> bool:
    """Check if a model ID is a Claude model (routes to Anthropic)."""
    return model.startswith("claude-")


def _split_system_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Split system message from chat messages for Anthropic API.

    Anthropic requires system prompt as a separate parameter, not in messages.
    """
    system = ""
    chat_messages = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            chat_messages.append(m)
    if not chat_messages:
        chat_messages = [{"role": "user", "content": "hello"}]
    return system, chat_messages


def _parse_json(text: str) -> dict | list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    if text.startswith("json\n"):
        text = text[5:]
    return json.loads(text)


def extract(content: str, instruction: str, model: str = None) -> dict | list:
    """Extract structured data using the fast model."""
    model = model or FAST_MODEL
    if _is_claude(model) and anthropic_client:
        response = anthropic_client.messages.create(
            model=model, max_tokens=4096,
            system="You extract structured data from documents. Always respond with valid JSON only, no markdown fences, no explanation.",
            messages=[{"role": "user", "content": f"{instruction}\n\n---\n\n{content}"}],
        )
        text = response.content[0].text
        if not text:
            raise RuntimeError(f"Empty response from {model}")
        return _parse_json(text)
    response = scaleway.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You extract structured data from documents. Always respond with valid JSON only, no markdown fences, no explanation."},
            {"role": "user", "content": f"{instruction}\n\n---\n\n{content}"},
        ],
        temperature=0.1,
        max_tokens=4096,
        timeout=120,
    )
    text = response.choices[0].message.content
    if not text:
        raise RuntimeError(f"Empty response from {model}")
    return _parse_json(text)


def extract_deep(content: str, instruction: str, model: str = None) -> dict | list:
    """Extract structured data using the deep extraction model.

    Used for foundation and narrative extraction where judgment matters —
    distinguishing company positioning from case studies, crafting reframes
    that would actually work in a conversation.
    """
    model = model or DEEP_EXTRACTION_MODEL
    if _is_claude(model) and anthropic_client:
        response = anthropic_client.messages.create(
            model=model, max_tokens=16000,
            thinking={"type": "adaptive"},
            system="You extract structured data from documents. Always respond with valid JSON only, no markdown fences, no explanation.",
            messages=[{"role": "user", "content": f"{instruction}\n\n---\n\n{content}"}],
        )
        text_blocks = [b.text for b in response.content if b.type == "text"]
        text = text_blocks[0] if text_blocks else ""
        if not text:
            raise RuntimeError(f"Empty response from {model} (thinking may have consumed all tokens)")
        return _parse_json(text)
    response = scaleway.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You extract structured data from documents. Always respond with valid JSON only, no markdown fences, no explanation."},
            {"role": "user", "content": f"{instruction}\n\n---\n\n{content}"},
        ],
        temperature=0.1,
        max_tokens=16000,
        timeout=180,
        extra_body=THINKING_BUDGET,
    )
    text = response.choices[0].message.content
    if not text:
        raise RuntimeError(f"Empty response from {model} (thinking may have consumed all tokens)")
    return _parse_json(text)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=2, min=2, max=15),
    retry=retry_if_exception_type(RuntimeError),
    before_sleep=lambda rs: log.warning(f"generate: empty response, retrying ({rs.attempt_number})"),
)
def generate(system_prompt: str, user_prompt: str, model: str = None) -> str:
    """Generate text using the conversation model."""
    model = model or CONVERSATION_MODEL
    if _is_claude(model) and anthropic_client:
        response = anthropic_client.messages.create(
            model=model, max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text
        if not text:
            raise RuntimeError(f"Empty response from {model}")
        return text
    response = scaleway.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=8000,
        timeout=120,
        extra_body=THINKING_BUDGET,
    )
    text = response.choices[0].message.content
    if not text:
        raise RuntimeError(f"Empty response from {model} (thinking may have consumed all tokens)")
    return text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((json.JSONDecodeError, RuntimeError)),
)
def consolidate(messages: list[dict], model: str = None) -> dict | list:
    """LLM call for consolidation — low temp, high tokens, JSON output."""
    response = scaleway.chat.completions.create(
        model=model or GENERATION_MODEL,
        messages=messages,
        temperature=0.1,
        max_tokens=16000,
        timeout=180,
        extra_body=THINKING_BUDGET,
    )
    text = response.choices[0].message.content
    if not text:
        raise RuntimeError(f"Empty response from {model or GENERATION_MODEL} (thinking may have consumed all tokens)")
    return _parse_json(text)


def chat(messages: list[dict], model: str = None) -> str:
    """Multi-turn chat using the fast model."""
    model = model or FAST_MODEL
    if _is_claude(model) and anthropic_client:
        system, chat_messages = _split_system_messages(messages)
        response = anthropic_client.messages.create(
            model=model, max_tokens=300,
            system=system or "You are Mother Tree.",
            messages=chat_messages,
        )
        return response.content[0].text.strip()
    response = scaleway.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=300,
        timeout=30,
    )
    return response.choices[0].message.content.strip()


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=2, min=2, max=15),
    retry=retry_if_exception_type(RuntimeError),
    before_sleep=lambda rs: log.warning(f"chat_conversation: empty response, retrying ({rs.attempt_number})"),
)
def chat_conversation(messages: list[dict], model: str = None, on_chunk=None) -> str:
    """Multi-turn conversation for DM freeform chat.

    Uses the conversation model with higher token limit and temperature
    than the quick chat() function used for signal threads.

    If on_chunk is provided, streams the response and calls on_chunk(text_so_far)
    periodically. Returns the full text when complete.
    """
    model = model or CONVERSATION_MODEL
    if _is_claude(model) and anthropic_client:
        system, chat_messages = _split_system_messages(messages)
        if on_chunk:
            import time
            text = ""
            last_update = 0
            with anthropic_client.messages.stream(
                model=model, max_tokens=8000,
                system=system or "You are Mother Tree.",
                messages=chat_messages,
            ) as stream:
                for chunk in stream.text_stream:
                    text += chunk
                    now = time.time()
                    if now - last_update > 0.8 and len(text) > 20:
                        on_chunk(text)
                        last_update = now
            if text:
                on_chunk(text)
            if not text:
                raise RuntimeError(f"Empty response from {model}")
            return text
        response = anthropic_client.messages.create(
            model=model, max_tokens=8000,
            system=system or "You are Mother Tree.",
            messages=chat_messages,
        )
        text = response.content[0].text
        if not text:
            raise RuntimeError(f"Empty response from {model}")
        return text
    # Scaleway (OpenAI-compatible) path
    if on_chunk:
        stream = scaleway.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=8000,
            timeout=120,
            stream=True,
            extra_body=THINKING_BUDGET,
        )
        text = ""
        last_update = 0
        import time
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices[0].delta else None
            if delta:
                text += delta
                now = time.time()
                if now - last_update > 0.8 and len(text) > 20:
                    on_chunk(text)
                    last_update = now
        if text:
            on_chunk(text)  # final update
        if not text:
            raise RuntimeError(f"Empty response from {model} (thinking may have consumed all tokens)")
        return text
    response = scaleway.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=8000,
        timeout=120,
        extra_body=THINKING_BUDGET,
    )
    text = response.choices[0].message.content
    if not text:
        raise RuntimeError(f"Empty response from {model} (thinking may have consumed all tokens)")
    return text


def score(model: str, prompt: str) -> list[dict]:
    """Score insights using a specific model."""
    response = scaleway.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You evaluate the quality of commercial insights. Always respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=2048,
    )
    return _parse_json(response.choices[0].message.content.strip())


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=60),
    retry=retry_if_exception_type(Exception),
)
def triage(insights: list[dict]) -> list[dict]:
    """Triage flagged insights using Claude Haiku 4.5."""
    if not anthropic_client:
        return [{"index": i, "decision": "human_review"} for i in range(len(insights))]
    items = [f'{i}. "{ins.get("reframe", "")}" — scores: {ins.get("scores", [])}' for i, ins in enumerate(insights)]
    response = anthropic_client.messages.create(
        model=TRIAGE_MODEL, max_tokens=2048,
        system="Triage commercial insights: accept, reject, or escalate. JSON only: [{index, decision, reason}]",
        messages=[{"role": "user", "content": "Triage:\n" + "\n".join(items)}],
    )
    return _parse_json(response.content[0].text.strip())


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=60),
    retry=retry_if_exception_type(Exception),
)
def arbitrate(insights: list[dict]) -> list[dict]:
    """Final arbitration using Claude Sonnet 4.6."""
    if not anthropic_client:
        return [{"index": i, "decision": "human_review"} for i in range(len(insights))]
    items = [f'{i}. "{ins.get("reframe", "")}" — scores: {ins.get("scores", [])}' for i, ins in enumerate(insights)]
    response = anthropic_client.messages.create(
        model=ARBITRATION_MODEL, max_tokens=2048,
        system="Final decision on commercial insights: accept or reject. JSON only: [{index, decision, reason}]",
        messages=[{"role": "user", "content": "Arbitrate:\n" + "\n".join(items)}],
    )
    return _parse_json(response.content[0].text.strip())


_embed_cache: dict[str, list[float]] = {}
_EMBED_CACHE_MAX = 50


def embed(text: str) -> list[float]:
    """Generate an embedding vector for text using the embedding model.

    Caches recent results to avoid repeated API calls for the same query
    during a single conversation turn (context fetch searches multiple tables).
    """
    if text in _embed_cache:
        return _embed_cache[text]
    from mothertree.config import EMBEDDING_MODEL
    response = scaleway.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[text],
    )
    result = response.data[0].embedding
    if len(_embed_cache) >= _EMBED_CACHE_MAX:
        _embed_cache.pop(next(iter(_embed_cache)))
    _embed_cache[text] = result
    return result
