"""Detect phase — fast pattern matching that produces annotations instead of responses.

Training/exercise patterns are scoped to DM only (participant_count == 1).
Global commands and URL detection work in all contexts.
"""
import logging
import re

from bot.enrich import extract_urls, fetch_and_follow
from mothertree.ask import PERSONAS

log = logging.getLogger(__name__)

GLOBAL_COMMANDS = {"enroll", "status", "progress", "stats", "help", "review", "accounts", "pipeline", "brief"}


# ---------------------------------------------------------------------------
# Helper functions (mockable at module level)
# ---------------------------------------------------------------------------

def deliver_next(enrollment: dict, user_id: str = None) -> dict:
    """Deliver the next training piece for the enrollment.

    Returns {"content": text} or an error dict.
    """
    from training.operations import deliver_chapter
    try:
        text = deliver_chapter(enrollment)
        if text is None:
            return {"error": "stage_complete", "message": "Stage 0 complete."}
        return {"content": text}
    except Exception as exc:
        log.exception("deliver_next failed")
        return {"error": str(exc)}


def score_exercise_answer(active_exercise: dict, enrollment: dict, answer: str) -> dict:
    """Score a multiple-choice answer against the active exercise.

    Wraps score_response + insert_response + progression logic.
    Returns {"correct": bool, "feedback": str, "progress": dict}.
    """
    from mothertree.graphql_client import insert_response
    from training.score import score_response
    try:
        exercise = active_exercise["exercise"]["content"]
        current_q = active_exercise.get("current_question", 0)
        questions = exercise.get("questions", [])
        if current_q < 0 or current_q >= len(questions):
            return {"correct": False, "feedback": "No active question.", "progress": {}}
        question = questions[current_q]
        result = score_response(
            stage=active_exercise.get("stage", 0),
            question=question,
            response=answer,
        )
        insert_response(
            exercise_id=active_exercise.get("exercise_id"),
            user_id=enrollment.get("id"),
            response=answer,
            question_index=current_q,
            correct=result["correct"],
            feedback=result["feedback"],
        )
        return {
            "correct": result["correct"],
            "feedback": result["feedback"],
            "progress": {"question": current_q, "total": len(questions)},
        }
    except Exception as exc:
        log.exception("score_exercise_answer failed")
        return {"correct": False, "feedback": str(exc), "progress": {}}


def generate_citizen_inspiration(enrollment: dict, user_id: str = None) -> dict:
    """Generate a stage-aware inspiration message for a citizen-role user.

    Citizens progress through 4 stages (5 interactions each):
    - Stage 0: change statements
    - Stage 1: worldview beliefs
    - Stage 2: insights (things to notice)
    - Stage 3: gatherer transition conversation

    Returns {"content": str, "advance": bool} where advance=True means
    current_chapter should be incremented (and stage advanced at 5).
    """
    from mothertree.ask import ask_with_history
    from mothertree.graphql_client import get_or_create_dm_conversation, graphql, search_similar
    from training.curriculum import get_chapter, get_stage_name, get_stages

    stage = enrollment.get("current_stage", 0)
    chapter = enrollment.get("current_chapter", 0)
    name = enrollment.get("name", "you")
    total_stages = len(get_stages("citizen"))

    # Past the last stage — program complete
    if stage >= total_stages:
        return {
            "content": "You've seen the full picture. If you want to go deeper, say `enroll gatherer`.",
            "advance": False,
        }

    stage_name = get_stage_name("citizen", stage)
    ch = get_chapter("citizen", stage, 0)
    tables = ch["tables"]

    # Fetch one record using semantic search (personal relevance) with offset fallback
    source_record = None
    if tables:
        table = tables[0]
        # Try semantic search using chapter purpose as query
        try:
            similar = search_similar(table, ch["purpose"], limit=5, threshold=0.05)
            if similar and len(similar) > chapter % len(similar):
                source_record = similar[chapter % len(similar)]
        except Exception:
            pass
        # Fallback: offset-based
        if not source_record:
            TABLE_GQL = {
                "change": "allChangesList",
                "worldview": "allWorldviewsList",
                "insights": "allInsightsList",
            }
            gql_name = TABLE_GQL.get(table, f"all{table.title()}sList")
            fields = ("statement, context" if table == "change"
                      else "belief, pain" if table == "worldview"
                      else "reframe, evidence, trigger" if table == "insights"
                      else "content")
            offset_val = (stage * 5 + chapter) % 50
            rows = graphql(
                f"query {{ {gql_name}(first: 1, offset: {offset_val}, orderBy: CONFIDENCE_DESC) {{ id, {fields} }} }}",
            )
            if rows.get(gql_name):
                source_record = rows[gql_name][0]

    # Build stage-specific prompt
    if stage == 3:
        # Gatherer transition — a conversation, not a one-liner
        prompt = (
            f"You're talking to {name}, a colleague who's been receiving inspiration "
            f"about our mission for a while now. They've seen the change we offer, "
            f"the worldview of our audience, and started noticing signals in their own work.\n\n"
            f"Now have a genuine conversation about becoming a gatherer. Explain:\n"
            f"- What gatherers do (notice signals in delivery, share them naturally)\n"
            f"- Why it helps the team (every signal makes everyone smarter)\n"
            f"- It's not about selling — it's about noticing and sharing\n"
            f"- They can say `enroll gatherer` when they're ready\n\n"
            f"Be warm and conversational. This is a colleague, not a recruit. "
            f"If they have questions, answer them. Don't push."
        )
    else:
        stage_prompts = {
            0: (
                f"Share one change statement from our organization — what transformation we offer. "
                f"Here's the raw data: {source_record}\n\n"
                f"Wrap this in 2-3 warm sentences for {name}. Don't quote it literally — "
                f"make it feel like a colleague sharing a belief worth holding. "
                f"End with something that makes them think."
            ),
            1: (
                f"Share one worldview insight — what the people we help believe and feel. "
                f"Here's the raw data: {source_record}\n\n"
                f"Wrap this in 2-3 empathetic sentences for {name}. "
                f"Help them see the world through our audience's eyes. "
                f"End with something they might recognize in their own work."
            ),
            2: (
                f"Share one insight — a signal or pattern worth noticing. "
                f"Here's the raw data: {source_record}\n\n"
                f"Frame this for {name} as something to watch for in their own work. "
                f"2-3 sentences. Not 'you should do X' — more 'next time you see Y, "
                f"notice how it connects to what we do.'"
            ),
        }
        prompt = stage_prompts.get(stage, stage_prompts[0])

    # Get conversation history to avoid repetition
    history = []
    if user_id:
        try:
            dm_conv = get_or_create_dm_conversation(user_id)
            history = dm_conv.get("messages", [])
        except Exception:
            pass

    content = ask_with_history(
        question=prompt,
        history=history,
        user_name=name,
    )

    # Add progress indicator (except for stage 3 conversation)
    if stage < 3:
        progress_note = f"\n\n_{stage_name} ({chapter + 1}/5)_"
        content = content + progress_note

    return {"content": content, "advance": True}


# ---------------------------------------------------------------------------
# Main detect function
# ---------------------------------------------------------------------------

def detect(
    text: str,
    participant_count: int,
    enrolled: bool = False,
    enrollment: dict = None,
    active_exercise: dict = None,
    user_id: str = None,
    bot_user_id: str = None,
) -> dict:
    """Pattern-match a message and produce annotations.

    Returns a result dict with:
        annotation: dict | None  — structured data for the response phase
        persona: str | None      — persona to invoke (seth, lawrence, trainer)
        must_respond: bool       — True if the bot was explicitly addressed
        clean_text: str          — text with mention/prefix stripped
        pattern_matched: bool    — True if a training/command pattern was consumed
        exercise_pending: dict | None — nudge info when exercise is in progress
    """
    result = {
        "annotation": None,
        "persona": None,
        "must_respond": False,
        "clean_text": text,
        "pattern_matched": False,
        "exercise_pending": None,
    }

    clean = text.strip()

    # ------------------------------------------------------------------
    # 1. Strip @bot mention
    # ------------------------------------------------------------------
    if bot_user_id:
        mention_pat = re.compile(r"<@" + re.escape(bot_user_id) + r">", re.IGNORECASE)
        if mention_pat.search(clean):
            clean = mention_pat.sub("", clean).strip()
            result["must_respond"] = True

    result["clean_text"] = clean

    parts = clean.split()
    first = parts[0].lower() if parts else ""

    # ------------------------------------------------------------------
    # 3. Global commands (work everywhere)
    # ------------------------------------------------------------------
    if first in GLOBAL_COMMANDS:
        result["pattern_matched"] = True
        result["must_respond"] = True

        if first == "status":
            enrollment_data = enrollment
            if enrollment_data:
                from training.operations import format_progress
                result["annotation"] = {
                    "type": "status",
                    "stage": enrollment_data.get("current_stage"),
                    "chapter": enrollment_data.get("current_chapter"),
                    "streak": enrollment_data.get("streak"),
                    "role": enrollment_data.get("role"),
                    "progress": format_progress(enrollment_data),
                }
            else:
                result["annotation"] = {"type": "status", "enrolled": False}

        elif first == "enroll":
            role = parts[1].lower() if len(parts) > 1 else None
            result["annotation"] = {"type": "enroll", "role": role}

        elif first == "stats":
            result["annotation"] = {"type": "stats", "data": {}}

        elif first == "progress":
            result["annotation"] = {"type": "progress"}

        elif first == "help":
            result["annotation"] = {"type": "help"}

        elif first == "review":
            company_name = " ".join(parts[1:]) if len(parts) > 1 else None
            result["annotation"] = {"type": "account_review", "company": company_name}

        elif first == "accounts":
            result["annotation"] = {"type": "account_list"}

        return result

    # ------------------------------------------------------------------
    # 4. Persona patterns ("ask seth ...", "ask lawrence ...", "ask trainer ...")
    # ------------------------------------------------------------------
    if first == "ask" and len(parts) >= 2:
        persona_name = parts[1].lower()
        if persona_name in PERSONAS or persona_name == "trainer":
            rest = " ".join(parts[2:])
            result["persona"] = persona_name
            result["clean_text"] = rest
            result["pattern_matched"] = True
            result["must_respond"] = True
            result["annotation"] = {"type": "persona", "persona": persona_name, "question": rest}
            return result

    # ------------------------------------------------------------------
    # 5. DM-only account commands (no enrollment required)
    # ------------------------------------------------------------------
    if participant_count == 1:
        # Nudge another user or self-remind
        if first in ("nudge", "remind", "ping") and len(parts) >= 2:
            if parts[1].lower() == "me":
                context = " ".join(parts[2:]) if len(parts) > 2 else ""
                result["pattern_matched"] = True
                result["must_respond"] = True
                result["annotation"] = {"type": "self_remind", "context": context}
                return result
            target_name = parts[1]
            context = " ".join(parts[2:]) if len(parts) > 2 else ""
            result["pattern_matched"] = True
            result["must_respond"] = True
            result["annotation"] = {"type": "nudge", "target": target_name, "context": context}
            return result

        # "check back <when>" / "follow up <when>"
        if first in ("check", "follow") and len(parts) >= 2:
            if (first == "check" and parts[1].lower() == "back") or \
               (first == "follow" and parts[1].lower() == "up"):
                context = " ".join(parts[2:]) if len(parts) > 2 else ""
                result["pattern_matched"] = True
                result["must_respond"] = True
                result["annotation"] = {"type": "self_remind", "context": context}
                return result

        # Account plan creation/update
        if first == "account" and len(parts) >= 3 and parts[1].lower() == "plan":
            company_name = " ".join(parts[2:])
            result["pattern_matched"] = True
            result["must_respond"] = True
            result["annotation"] = {"type": "account_plan", "company": company_name}
            return result

        # Service meeting debrief
        if first == "service" and len(parts) >= 2 and parts[1].lower() == "meeting":
            content = " ".join(parts[2:]) if len(parts) > 2 else ""
            result["pattern_matched"] = True
            result["must_respond"] = True
            result["annotation"] = {"type": "service_meeting", "content": content}
            return result

    # ------------------------------------------------------------------
    # 5b. DM-only training patterns (participant_count == 1)
    # ------------------------------------------------------------------
    if participant_count == 1 and enrolled:
        role = (enrollment or {}).get("role")

        # "next" — deliver next training piece (or citizen inspiration)
        if first == "next":
            result["pattern_matched"] = True
            result["must_respond"] = True
            if role == "citizen":
                inspiration = generate_citizen_inspiration(enrollment, user_id)
                result["annotation"] = {
                    "type": "citizen_inspiration",
                    "content": inspiration["content"],
                }
                # Advance citizen progression
                if inspiration.get("advance"):
                    from training.operations import advance_citizen
                    advance_citizen(enrollment)
            else:
                delivered = deliver_next(enrollment, user_id)
                result["annotation"] = {
                    "type": "training_delivered",
                    **delivered,
                }
            return result

        # "go" — start exercise
        if first == "go":
            result["pattern_matched"] = True
            result["must_respond"] = True
            result["annotation"] = {"type": "exercise_start"}
            return result

        # "practice [topic]" — practice delivery
        if first == "practice":
            result["pattern_matched"] = True
            result["must_respond"] = True
            topic = parts[1].lower() if len(parts) > 1 else None
            result["annotation"] = {"type": "practice_delivered", "topic": topic}
            return result

        # Single letter answer (A/B/C) — score against active exercise
        if clean.upper() in ("A", "B", "C"):
            if active_exercise:
                scored = score_exercise_answer(active_exercise, enrollment, clean.upper())
                result["pattern_matched"] = True
                result["must_respond"] = True
                result["annotation"] = {
                    "type": "answer_scored",
                    **scored,
                }
                return result
            # No active exercise — fall through (no match)
            # result stays pattern_matched=False

    # ------------------------------------------------------------------
    # 6. URL detection (works everywhere, up to 3 URLs in parallel)
    # ------------------------------------------------------------------
    urls = extract_urls(clean)
    if urls:
        import threading
        from concurrent.futures import ThreadPoolExecutor
        urls = urls[:3]
        follow_budget = threading.Semaphore(2)
        with ThreadPoolExecutor(max_workers=3) as pool:
            fetched = list(pool.map(lambda u: fetch_and_follow(u, follow_budget), urls))

        result["must_respond"] = True
        url_results = []
        url_failures = []
        for url, content in zip(urls, fetched, strict=False):
            if content:
                url_results.append({"url": url, "content": content})
            else:
                url_failures.append(url)

        if url_results:
            if len(url_results) == 1:
                result["annotation"] = {
                    "type": "url_content",
                    "url": url_results[0]["url"],
                    "content": url_results[0]["content"],
                }
            else:
                result["annotation"] = {
                    "type": "url_content",
                    "urls": [r["url"] for r in url_results],
                    "content": "\n\n---\n\n".join(
                        f"[{r['url']}]\n{r['content']}" for r in url_results
                    ),
                }
        else:
            result["annotation"] = {
                "type": "url_failed",
                "url": url_failures[0] if url_failures else urls[0],
            }
        return result

    # ------------------------------------------------------------------
    # 7. Exercise pending nudge
    # ------------------------------------------------------------------
    if active_exercise and participant_count == 1:
        questions = (active_exercise.get("exercise") or {}).get("content", {}).get("questions", [])
        current_q = active_exercise.get("current_question", 0)
        if questions and current_q >= 0:
            result["exercise_pending"] = {
                "question_num": current_q + 1,
                "total": len(questions),
            }

    return result
