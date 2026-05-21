"""Shared constants, rules, and utilities for all characters."""
import json
import re

from mothertree.config import GENERATION_MODEL
from mothertree.intelligence import format_context_for_prompt, gather_context
from mothertree.llm import chat_conversation

# -- Model defaults (characters override only when needed) --
DEFAULT_MODEL = GENERATION_MODEL
DEFAULT_TEMPERATURE = 0.7

# -- Annotation types that carry facts (must be stated exactly) --
FACTUAL_ANNOTATION_TYPES = {
    "status", "stats", "enrolled", "answer",
    "progress", "enroll", "profile_saved",
}

# -- Shared rules --
NO_HALLUCINATION_RULES = """
RULES — NON-NEGOTIABLE:
Your credibility depends on these rules. Break one and the user stops trusting you.

1. NEVER FABRICATE. Not URLs, not titles, not times, not room numbers, not names.
   If you don't have specific data, say so clearly. Examples:
   - User asks for session titles you don't have → "I can't see individual sessions on this page."
   - User asks you to "pick 3 talks" but you have no talk data → "I don't have the session list. Share a page that shows individual talks and I'll help you pick."
   - User asks for a link you don't have → "I don't have that link."
   NEVER fill in details you don't have, even when directly asked. Saying "I don't have that" is always better than guessing.
   THIS INCLUDES TITLES. If you did not receive a list of specific session titles, talk names, or article headlines in your context, you MUST NOT generate them. A title in *italics* or quotes that you made up is still fabrication.

2. ONLY STATE WHAT YOU CAN SEE. You receive fetched URL content in annotations.
   Only reference facts that appear in that content. If a page is a landing page
   without session details, say exactly that. Do not extrapolate, guess, or
   "helpfully" provide details that aren't in the source.

3. WHEN YOU CAN'T HELP DIRECTLY, REDIRECT. Suggest what the user can do:
   "Check the event app" or "Share the page that lists individual sessions."
   Offer to help once they have the data: "Send me the session list and I'll pick the ones that matter for us."

- You have the conversation history. Use it. Don't ask for context already given.
"""

SLACK_FORMATTING_RULES = """
FORMATTING — YOU ARE WRITING FOR SLACK:
• Use *bold* for emphasis (single asterisk both sides). NEVER use **double asterisks**.
• Use plain text for everything else. Do NOT use _underscores_ for italic.
• Bullets: use • only. NEVER use - or * as bullet markers.
• NEVER use # headings, --- rules, or [markdown](links).
• NEVER generate URLs.

LENGTH:
Keep responses under 150 words unless the user asks for detail or you are delivering training or factual content (status, stats, progress). Prefer one clear paragraph over multiple sections. No bullet lists unless comparing options.
"""


def build_messages(system: str, history: list[dict], question: str) -> list[dict]:
    """Build the message list for an LLM call.

    System message first, then history (user/assistant only — system messages
    from history are dropped to avoid multiple system messages which some
    models reject), then the new user question.
    """
    messages = [{"role": "system", "content": system}]
    for msg in history:
        if msg.get("role") in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})
    return messages


def fix_slack_formatting(text: str) -> str:
    """Convert any remaining Markdown to Slack formatting."""
    # **bold** → *bold*
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    # *text_ or *text_ (hybrid bold/italic) → *text*
    text = re.sub(r'\*([^*\n]+)_', r'*\1*', text)
    # _text* (reverse hybrid) → *text*
    text = re.sub(r'_([^_\n]+)\*', r'*\1*', text)
    # _text_ (italic) → plain text (we told the model not to use italic)
    text = re.sub(r'_([^_\n]+)_', r'\1', text)
    # ## headings → *bold*
    text = re.sub(r'#{1,6}\s+(.+?)(?=$|\n)', r'*\1*', text, flags=re.MULTILINE)
    # --- rules → remove
    text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
    # [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # - bullets → •
    text = re.sub(r'^- ', '• ', text, flags=re.MULTILINE)
    return text


def character_respond(
    identity: str, goals: str, rules: str,
    third_person_label: str,
    question: str, history: list[dict],
    user_name: str = "you", participant_count: int = 1,
    annotation: dict = None, model: str = None,
    extra_parts: list[str] = None,
    on_chunk=None,
) -> str:
    """Shared respond flow for all character modules."""
    ci_context = format_context_for_prompt(gather_context())
    parts = [identity, SLACK_FORMATTING_RULES, goals, rules]
    parts.append(f"\nCENTRAL INTELLIGENCE:\n{ci_context}")
    parts.append(f"\nYou are talking to {user_name}.")

    if participant_count > 1:
        parts.append(f"You are in a group channel. Present your perspective in third person: '{third_person_label}'")

    ann_ctx = build_annotation_context(annotation)
    if ann_ctx:
        parts.append(ann_ctx)

    if extra_parts:
        parts.extend(extra_parts)

    parts.append(NO_HALLUCINATION_RULES)
    system = "\n".join(parts)

    return chat_conversation(build_messages(system, history, question), model=model or DEFAULT_MODEL, on_chunk=on_chunk)


def build_annotation_context(annotation: dict | None) -> str:
    """Build the annotation section of a prompt.

    Factual annotations get FACTS label (state exactly).
    Contextual annotations get CONTEXT label (weave naturally).
    """
    if not annotation:
        return ""
    ann_type = annotation.get("type", "")
    if ann_type in FACTUAL_ANNOTATION_TYPES:
        return (
            f"\n\nFACTS (state these exactly, do not rephrase or omit any values):"
            f"\n{json.dumps(annotation, default=str)}"
            f"\nPresent these facts conversationally but do not change the values."
        )
    return (
        f"\n\nCONTEXT ({ann_type}):"
        f"\n{json.dumps(annotation, default=str)}"
        f"\nWeave this into your response naturally."
    )
