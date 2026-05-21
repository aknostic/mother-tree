"""Conversation engine — one function handles all Mother Tree responses.

Same code for DM, channel, and thread. Same code for commands, training,
personas, and freeform conversation.
"""
import logging

from bot.characters.base import fix_slack_formatting as _fix_slack_formatting
from bot.markers import extract_action_markers, extract_content_markers
from bot.memory import append_message, get_max_messages, window_messages
from mothertree.ask import ask_with_history

log = logging.getLogger(__name__)


# Fallback responses when the LLM fails. Kept in sync with pipeline._fallback —
# direct-handler intents (snooze, nudge, debrief, ...) get specific messages so
# the user can tell what was attempted, not just that "something went wrong".
FALLBACKS = {
    # Data-render fallbacks.
    "enrolled": "Welcome to Mother Tree, {name}. Enrolled as {role}.",
    "status": "Stage {stage}, Chapter {chapter}. Streak: {streak} days.",
    "stats": "Stats loaded.",
    "help": "Just talk to me. In DMs: enroll, status, next, go, practice, ask saga/lena/trainer. In channels: @Mother Tree followed by your question.",
    "progress": "Progress loaded.",
    "answer_scored": "{feedback}",
    "training_delivered": "{content}",
    "exercise_started": "{question}",
    "practice_delivered": "{content}",
    "citizen_inspiration": "{content}",
    "error": "{message}",
    # Direct-handler failures.
    "snooze": "I read that as a snooze request (matched '{match}') but couldn't save it. If you didn't mean to snooze, ignore me — I'll get smarter.",
    "nudge": "Couldn't set the nudge for *{target}*. Try again in a moment, or DM me `nudge {target} <message>`.",
    "self_remind": "Couldn't set the reminder. Try `remind me <when> <what>`.",
    "debrief": "Couldn't process the debrief just now. Try sending the notes again.",
    "service_meeting": "Couldn't log the service meeting. Try again in a moment.",
    "account_plan": "Couldn't update the account plan. Try again in a moment.",
    "account_review": "Couldn't load the account review. Try again in a moment.",
    "account_list": "Couldn't list account plans. Try again in a moment.",
    "pipeline": "Couldn't load the pipeline view. Try again in a moment.",
    "brief": "Couldn't run the brief. Try again in a moment.",
    "admin": "Admin command failed. Try again in a moment.",
    "completion": "Got it — but couldn't update the trail. Try again in a moment.",
}


def _fallback_response(annotation: dict = None) -> str:
    """Generate a static fallback response based on annotation type."""
    if annotation is None:
        return "Sorry, I'm having trouble thinking right now. Try again in a moment."

    ann_type = annotation.get("type", "")
    template = FALLBACKS.get(ann_type, "Something went wrong. Try again in a moment.")

    try:
        return template.format(**annotation)
    except (KeyError, IndexError):
        return template


def converse(text: str, memory_ctx: dict, user_name: str = "you",
             annotation: dict = None, persona: str = None,
             signal_flag: bool = False, participant_count: int = 1,
             exercise_pending: dict = None) -> dict:
    """Run the conversation engine.

    Returns {"response": str, "actions": list[str]}
    """
    # Window messages to fit context
    max_msgs = get_max_messages(memory_ctx["store_type"])
    history = window_messages(memory_ctx["messages"], max_msgs)

    # Persist user message to memory
    try:
        append_message(memory_ctx, role="user", content=text, name=user_name)
    except Exception:
        log.exception("Failed to persist user message")

    # Persist annotation as system message if present
    if annotation:
        try:
            import json
            append_message(memory_ctx, role="system", content=json.dumps(annotation))
        except Exception:
            log.exception("Failed to persist annotation")

    # Call LLM
    try:
        response = ask_with_history(
            question=text,
            history=history,
            persona=persona,
            user_name=user_name,
            annotation=annotation,
            signal_flag=signal_flag,
            participant_count=participant_count,
            exercise_pending=exercise_pending,
        )
    except Exception:
        log.exception("Conversation engine LLM call failed")
        response = _fallback_response(annotation)
        return {"response": response, "actions": []}

    # Guard against Mistral tool-calling syntax leaking through
    if response.startswith("[TOOL_CALLS]"):
        log.warning("LLM returned tool-calling syntax, falling back: %s", response[:200])
        response = _fallback_response(annotation)
        return {"response": response, "actions": []}

    # Extract action markers
    actions, response = extract_action_markers(response)

    # Extract and replace content markers
    content_types, response = extract_content_markers(response)
    if "training" in content_types and annotation and annotation.get("content"):
        # Re-insert annotation content where the marker was stripped
        if response:
            response = f"{response}\n\n{annotation['content']}"
        else:
            response = annotation["content"]

    # Fix Slack formatting
    response = _fix_slack_formatting(response)

    # Persist assistant response
    try:
        append_message(memory_ctx, role="assistant", content=response)
    except Exception:
        log.exception("Failed to persist assistant response")

    return {"response": response, "actions": actions}
