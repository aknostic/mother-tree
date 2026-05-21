"""Unified memory interface for DM, channel, and thread contexts."""
import os

from mothertree.config import GENERATION_MODEL
from mothertree.graphql_client import (
    append_channel_message,
    append_dm_message,
    append_thread_message,
    get_or_create_channel_memory,
    get_or_create_dm_conversation,
    get_or_create_thread_memory,
    get_thread_memory_or_signal_thread,
)
from mothertree.llm import chat_conversation

DM_MAX_MESSAGES = int(os.environ.get("DM_MAX_MESSAGES", "200"))
CHANNEL_MAX_MESSAGES = int(os.environ.get("CHANNEL_MAX_MESSAGES", "200"))
THREAD_MAX_MESSAGES = int(os.environ.get("THREAD_MAX_MESSAGES", "100"))


def get_memory(context_type: str, **kwargs) -> dict:
    """Get conversation memory for a context.

    Returns dict with keys: messages, store_type, store_id, and context-specific fields.
    """
    if context_type == "dm":
        conv = get_or_create_dm_conversation(kwargs["user_id"])
        return {
            "messages": conv["messages"],
            "store_type": "dm",
            "store_id": conv["id"],
            "user_id": kwargs["user_id"],
        }
    elif context_type == "channel":
        mem = get_or_create_channel_memory(kwargs["channel_id"], kwargs.get("channel_name"))
        return {
            "messages": mem["messages"],
            "store_type": "channel",
            "store_id": mem["id"],
            "channel_id": kwargs["channel_id"],
        }
    elif context_type == "thread":
        mem = get_thread_memory_or_signal_thread(kwargs["thread_ts"], kwargs["channel_id"])
        if mem is None:
            mem = get_or_create_thread_memory(kwargs["thread_ts"], kwargs["channel_id"],
                                               owner_user_id=kwargs.get("owner_user_id"))
        return {
            "messages": mem.get("messages", []),
            "store_type": "thread",
            "store_id": mem.get("id"),
            "thread_ts": kwargs["thread_ts"],
            "channel_id": kwargs["channel_id"],
            "_legacy": mem.get("_legacy", False),
        }
    raise ValueError(f"Unknown context_type: {context_type}")


def append_message(memory_ctx: dict, role: str, content: str, name: str = None, annotation: dict = None) -> None:
    """Append a message to the appropriate memory store."""
    if memory_ctx["store_type"] == "dm":
        append_dm_message(memory_ctx["store_id"], role=role, content=content)
    elif memory_ctx["store_type"] == "channel":
        append_channel_message(memory_ctx["channel_id"], role=role, content=content, name=name)
    elif memory_ctx["store_type"] == "thread":
        append_thread_message(memory_ctx["thread_ts"], memory_ctx["channel_id"], role=role, content=content, name=name)


def window_messages(messages: list[dict], max_messages: int = 200) -> list[dict]:
    """Return the last max_messages from a message list."""
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


def get_max_messages(context_type: str) -> int:
    """Get the max message window for a context type."""
    return {"dm": DM_MAX_MESSAGES, "channel": CHANNEL_MAX_MESSAGES, "thread": THREAD_MAX_MESSAGES}[context_type]


def summarize_old_messages(messages: list[dict], max_messages: int = 100) -> list[dict]:
    """Summarize oldest messages when a thread exceeds max_messages.

    Keeps the newest max_messages and summarizes the rest into a single
    system message prepended to the list.
    """
    if len(messages) <= max_messages:
        return messages
    old = messages[:-max_messages]
    recent = messages[-max_messages:]
    summary_prompt = [
        {"role": "system", "content": "Summarize this conversation history. Preserve: who said what, key decisions, open questions, action items. Be concise."},
        {"role": "user", "content": "\n".join(f"[{m.get('name', m['role'])}]: {m['content']}" for m in old if m.get('content'))},
    ]
    try:
        summary = chat_conversation(summary_prompt, model=GENERATION_MODEL)
    except Exception:
        return recent
    summary_msg = {"role": "system", "content": f"Summary of earlier conversation:\n{summary}"}
    return [summary_msg] + recent
