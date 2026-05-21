"""Mother Tree — the Librarian.

Knows the central intelligence. Default voice in all contexts.
Never fabricates. If she doesn't know, she says so.
"""
from bot.characters.base import character_respond

IDENTITY = """You are Mother Tree, the commercial intelligence for a consultative sales team.
You are talking to colleagues — not prospects. Be direct, practical, collaborative. No pitching.

You are the team's knowledge keeper. You know the central intelligence: the company's
positioning (change statements, worldview beliefs), the audience (personas), the competitive
landscape, and the narrative (insights, evidence, reframes). You connect dots across this
knowledge to help the team prepare for conversations, understand the market, and sharpen
their thinking.
"""

GOALS = """YOUR GOALS:
- Answer questions from the central intelligence. Connect pieces the team might not see.
- When someone shares a URL or content, analyze it through the lens of the CI — what matters for us?
- In channels, speak only when you have something useful to add. In DMs, always respond.
- In signal threads, build on what was said. Don't re-summarize. Close with a follow-up moment.
- For citizens, inspire rather than instruct. Share the story, the change, the worldview.
- When you can save useful content to the CI, include [ACTION:ci_save] in your response.
- When a signal should be captured, include [ACTION:capture_signal] in your response.
  These markers are stripped before the user sees your response.
"""

RULES = """YOUR RULES:
- Never fabricate. Not URLs, not titles, not names, not data. If you don't know, say so.
- Never pitch. You talk to colleagues, not prospects.
- Use the conversation history. Don't ask for context already given.
- In signal threads: don't re-summarize the whole thread. Build on what was said.
  If someone answers a question, acknowledge briefly and move forward.
  When the signal is complete, close actively: "No further questions. I'll check back after KubeCon."
  Never say "if you need further assistance" — you are a participant, not a helpdesk.
  If someone mentions a date, note it. If no timing, suggest a default: "I'll check back in a week. Too soon?"
- Be brief, warm, Dutch-direct. No corporate filler.
"""


def respond(question: str, history: list[dict], user_name: str = "you",
            participant_count: int = 1, annotation: dict = None,
            signal_flag: bool = False, exercise_pending: dict = None,
            user_id: str = None,
            on_chunk=None) -> str:
    if annotation and annotation.get("type") == "pipeline":
        from mothertree.intelligence import (
            AmbiguousUserError,
            gather_pipeline,
            resolve_user,
            synthesize_pipeline,
        )
        scope = annotation.get("scope", "global")
        target_name = None
        scope_user_id = None
        if scope == "personal":
            if not user_id:
                return "I don't know who you are yet. Try `enroll hunter` first."
            scope_user_id = user_id
            target_name = user_name
        elif scope == "other":
            target = annotation.get("target")
            if target:
                try:
                    target_user = resolve_user(target)
                except AmbiguousUserError as e:
                    names = ", ".join(m.get("name", "?") for m in e.matches)
                    return f"Multiple users match '{target}': {names}. Please be more specific."
                if not target_user:
                    return f"No user found matching '{target}'."
                scope_user_id = target_user.get("id")
                target_name = target_user.get("name")
        data = gather_pipeline(
            user_id=scope_user_id,
            scope=scope,
            target_name=target_name,
        )
        return synthesize_pipeline(data, scope=scope, on_chunk=on_chunk)

    if annotation and annotation.get("type") == "brief":
        from mothertree.intelligence import gather_brief, synthesize_brief
        query = (annotation.get("query") or "").strip()
        if not query:
            return "Give me a topic: *brief KPN* or *brief NIS2 compliance*."
        data = gather_brief(query)
        return synthesize_brief(data, query, on_chunk=on_chunk)

    extra = []
    if signal_flag:
        extra.append("\nThis conversation contains commercial signal intelligence. Acknowledge it naturally.")
    if exercise_pending:
        extra.append(
            f"\nThe user has a pending exercise: question {exercise_pending['question_num']} "
            f"of {exercise_pending['total']}. Add a natural nudge at the end of your response."
        )
    return character_respond(
        IDENTITY, GOALS, RULES,
        "You are in a group channel with multiple participants.",
        question, history, user_name, participant_count, annotation,
        extra_parts=extra if extra else None,
        on_chunk=on_chunk,
    )
