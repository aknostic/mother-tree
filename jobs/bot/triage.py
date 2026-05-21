"""Triage: cheap LLM call deciding respond/signal/silent."""
import logging

from mothertree.llm import extract

log = logging.getLogger(__name__)

TRIAGE_SYSTEM = """You decide whether Mother Tree should respond to a message and whether it contains commercial signal intelligence.

Return JSON only:
{"respond": true/false, "signal": {"capture": true/false, "confidence": 0.0-1.0}, "reason": "one sentence"}

Rules:
- If this is a DM (1 participant), respond is ALWAYS true.
- Respond when: direct question, request for help, Mother Tree has something useful to add.
- Stay silent when: people talking to each other, small talk, reactions, greetings between colleagues.
- Signal capture: intelligence about a prospect, client, market, competitor, or event.
- Be conservative in channels — if unsure, stay silent."""


def _build_triage_prompt(text: str, participant_count: int, recent_messages: list[dict]) -> str:
    """Build the triage prompt with context."""
    context = ""
    if recent_messages:
        context = "\nRecent messages:\n" + "\n".join(
            f"- [{m.get('name', 'someone')}]: {m['content'][:100]}"
            for m in recent_messages[-5:]
        )
    return f"Participants: {participant_count}\n{context}\n\nNew message: {text}"


def _call_triage_llm(prompt: str) -> dict:
    """Make the triage LLM call."""
    return extract(prompt, TRIAGE_SYSTEM)


def triage(text: str, participant_count: int, recent_messages: list[dict]) -> dict:
    """Run triage on a message. Returns {respond, signal, reason}."""
    prompt = _build_triage_prompt(text, participant_count, recent_messages)
    try:
        result = _call_triage_llm(prompt)
    except Exception as e:
        log.warning(f"Triage LLM failed: {e}")
        return {
            "respond": participant_count == 1,
            "signal": {"capture": False, "confidence": 0.0},
            "reason": "triage failed",
        }

    # DM override: always respond
    if participant_count == 1:
        result["respond"] = True

    return result
