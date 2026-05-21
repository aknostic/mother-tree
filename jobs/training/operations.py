"""Training state machine — enroll, deliver, start, score.

Pure functions: they take enrollment/conversation dicts and return strings.
Side effects (DB writes, Slack) are delegated to callers.
"""
import logging
from datetime import UTC, datetime

from mothertree.graphql_client import (
    advance_user,
    cancel_stale_conversations,
    create_conversation,
    create_user,
    get_active_conversation,
    get_responses_for_exercise,
    get_training_progress,
    get_user_by_email,
    insert_exercise,
    insert_response,
    update_conversation,
    upsert_training_progress,
)
from training.curriculum import get_stage_name, get_stages, get_total_chapters
from training.engine import generate_exercise
from training.score import score_response

log = logging.getLogger(__name__)

PROFICIENCY_THRESHOLD = 0.6

STAGE_HALF_LIVES = {
    0: 30,   # foundation knowledge
    1: 14,   # conversation/offering skills
    2: 14,   # conversation/offering skills
    3: 21,   # applied skills
    4: 21,   # applied skills
}


def calculate_proficiency(initial_score: float, days_elapsed: float, half_life: int) -> float:
    """Calculate current proficiency using half-life decay."""
    if days_elapsed <= 0:
        return initial_score
    return initial_score * (0.5 ** (days_elapsed / half_life))


def get_half_life(stage: int) -> int:
    """Get the half-life in days for a given stage."""
    return STAGE_HALF_LIVES.get(stage, 21)


def record_chapter_score(enrollment_id: str, role: str, stage: int,
                         chapter: int, exercise_id: str) -> float:
    """Calculate and record proficiency score for a completed chapter.

    Returns the score (0.0-1.0).
    """
    responses = get_responses_for_exercise(exercise_id)
    if not responses:
        return 0.0
    correct_count = sum(1 for r in responses if r.get("correct"))
    score = correct_count / len(responses)

    area = f"{role}:{stage}:{chapter}"
    upsert_training_progress(user_id=enrollment_id, area=area, score=score)
    return score


def get_decayed_chapters(enrollment_id: str) -> list[dict]:
    """Find chapters where proficiency has decayed below threshold."""
    progress = get_training_progress(enrollment_id)
    now = datetime.now(UTC)
    decayed = []
    for p in progress:
        parts = p["area"].split(":")
        if len(parts) != 3:
            continue
        stage = int(parts[1])
        half_life = get_half_life(stage)
        updated = datetime.fromisoformat(p["updated_at"])
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        days = (now - updated).total_seconds() / 86400
        current = calculate_proficiency(p["score"], days, half_life)
        if current < PROFICIENCY_THRESHOLD:
            decayed.append({
                "area": p["area"],
                "role": parts[0],
                "stage": stage,
                "chapter": int(parts[2]),
                "current_proficiency": round(current, 2),
                "original_score": p["score"],
                "days_since_activity": round(days),
            })
    return sorted(decayed, key=lambda x: x["current_proficiency"])


def format_progress(enrollment: dict) -> str:
    """Format a progress summary for an enrollment.

    Shows current position, completed chapters, streak, and any decayed areas.
    """
    role = enrollment["role"]
    stage = enrollment.get("currentStage", enrollment.get("current_stage", 0))
    chapter = enrollment.get("currentChapter", enrollment.get("current_chapter", 0))
    streak = enrollment.get("streak") or 0

    stage_name = get_stage_name(role, stage)
    total_stages = len(get_stages(role))
    total_chapters = get_total_chapters(role, stage)

    # Count completed chapters across all stages
    completed = sum(
        get_total_chapters(role, s)
        for s in range(stage)
    ) + chapter
    total_all = sum(
        get_total_chapters(role, s)
        for s in range(total_stages)
    )

    lines = [
        f"*{stage_name}* (stage {stage + 1}/{total_stages}), chapter {chapter + 1}/{total_chapters}",
        f"{completed}/{total_all} chapters completed",
    ]

    if streak > 0:
        lines.append(f"Streak: {streak} day{'s' if streak != 1 else ''}")

    enrollment_id = enrollment.get("id")
    decayed = get_decayed_chapters(enrollment_id) if enrollment_id else []
    if decayed:
        areas = [f"{d['area'].split(':')[0]} ch.{d['chapter'] + 1}"
                 for d in decayed[:3]]
        lines.append(f"Ready to practice: {', '.join(areas)}")

    return "\n".join(lines)


CITIZEN_INTERACTIONS_PER_STAGE = 5


def advance_citizen(enrollment: dict) -> None:
    """Advance a citizen's progression counter.

    Citizens use current_chapter as an interaction counter (0-4).
    At 5 interactions, advance to the next stage and reset chapter to 0.
    """
    chapter = enrollment.get("current_chapter", 0) + 1
    stage = enrollment.get("current_stage", 0)

    if chapter >= CITIZEN_INTERACTIONS_PER_STAGE:
        # Advance to next stage
        from training.curriculum import get_stages
        total_stages = len(get_stages("citizen"))
        next_stage = stage + 1
        if next_stage < total_stages:
            advance_user(enrollment["id"], current_chapter=0, current_stage=next_stage)
        else:
            # Program complete — stay at last stage
            advance_user(enrollment["id"], current_chapter=chapter)
    else:
        advance_user(enrollment["id"], current_chapter=chapter)


def citizen_daily_check(enrollment: dict) -> str | None:
    """Daily check for a citizen enrollment. Returns inspiration text or None.

    Citizens get proactive inspiration (nudges) — same stage-aware content
    as when they say 'next', delivered by the CronJob.
    """
    from bot.detect import generate_citizen_inspiration

    result = generate_citizen_inspiration(enrollment, enrollment.get("id"))
    if result.get("advance"):
        advance_citizen(enrollment)
    return result.get("content")


def enroll(email: str, name: str, role: str) -> str:
    """Enroll a user by email and create them as a team contact."""
    existing = get_user_by_email(email)
    if existing:
        return f"You're already enrolled as {existing['role']}."

    user = create_user(email, name, role)

    # Create as a team contact linked to Aknostic
    try:
        from mothertree.graphql_client import find_or_create_contact, graphql
        aknostic = graphql("""
        query { allCompaniesList(condition: {name: "Aknostic"}, first: 1) { id } }
        """)
        company_id = aknostic["allCompaniesList"][0]["id"] if aknostic.get("allCompaniesList") else None
        if not company_id:
            from mothertree.entities import find_or_create_company
            co = find_or_create_company("Aknostic")
            company_id = co.get("id") if isinstance(co, dict) else None

        find_or_create_contact(
            full_name=name,
            user_id=user["id"],
            owner_user_id=user["id"],
            is_team=True,
            company_id=company_id,
            role=role,
        )
    except Exception:
        log.warning("Failed to create team contact for %s", name)

    if role == "citizen":
        return "Welcome. I'll share one idea at a time about what we do and why it matters. Say *next* in a DM whenever you're curious."

    details_prompt = (
        f"Enrolled as {role}. Say *next* in a DM to start your first chapter.\n\n"
        f"A few things that help me support you better:\n"
        f"• What's your email? (for meeting prep matching)\n"
        f"• What days do you work? (so I don't nudge you on off days)\n"
        f"• Got a calendar URL? (iCal — I can prep you before meetings and prompt debriefs after)\n\n"
        f"_You can share these anytime. Just tell me in a DM._"
    )
    return details_prompt


def deliver_chapter(enrollment: dict) -> str | None:
    """Generate and persist the next chapter for an enrollment.

    Returns formatted instruction text, or None if the stage is complete.
    Cancels any stale conversations before creating a new one.
    """
    role = enrollment["role"]
    stage = enrollment.get("currentStage", enrollment.get("current_stage", 0))
    chapter = enrollment.get("currentChapter", enrollment.get("current_chapter", 0))
    total = get_total_chapters(role, stage)

    if chapter >= total:
        log.info("Stage %d complete for enrollment %s", stage, enrollment["id"])
        return None

    cancel_stale_conversations(enrollment["id"])

    exercise = generate_exercise(role=role, stage=stage, chapter=chapter)

    exercise_id = insert_exercise(
        user_id=enrollment["id"],
        stage=stage,
        chapter=chapter,
        exercise_type=exercise["type"],
        content=exercise,
        source_tables=exercise["source_tables"],
    )

    create_conversation(
        user_id=enrollment["id"],
        exercise_id=exercise_id,
        stage=stage,
        state="waiting_response",
        current_question=-1,
    )

    display_num = chapter + 1
    return (
        f"*Chapter {display_num} of {total}: {exercise['chapter_name']}*\n\n"
        f"{exercise['instruction']}\n\n"
        f"Ready for the questions? Reply *go* when you've read this."
    )


def start_exercises(active_conversation: dict | None) -> str | None:
    """Handle the 'go' command — transition from instruction to first question.

    Returns the first question formatted for Slack, or None if no active conversation.
    """
    if active_conversation is None:
        return None

    update_conversation(active_conversation["id"], current_question=0)

    exercise = active_conversation["exercise"]["content"]
    question = exercise["questions"][0]
    total = len(exercise["questions"])
    return _format_question(question, num=1, total=total)


def score_answer(active_conversation: dict, enrollment: dict, answer: str) -> str:
    """Score an answer, persist the response, and advance state.

    If more questions remain: advance current_question and return feedback + next question.
    If last question: mark conversation complete, advance enrollment, return completion message.
    """
    exercise = active_conversation["exercise"]["content"]
    questions = exercise["questions"]
    current_q = active_conversation["current_question"]
    stage = active_conversation["stage"]
    total = len(questions)

    question = questions[current_q]
    scored = score_response(stage=stage, question=question, response=answer)
    feedback = scored["feedback"]

    insert_response(
        exercise_id=active_conversation["exercise_id"],
        user_id=enrollment["id"],
        response=answer,
        question_index=current_q,
        correct=scored["correct"],
        feedback=feedback,
    )

    is_last = current_q >= total - 1

    if is_last:
        update_conversation(active_conversation["id"], state="complete")

        # Record proficiency
        current_chapter = enrollment.get("currentChapter", enrollment.get("current_chapter", 0))
        record_chapter_score(
            enrollment_id=enrollment["id"],
            role=enrollment["role"],
            stage=stage,
            chapter=current_chapter,
            exercise_id=active_conversation["exercise_id"],
        )

        # Determine what comes next
        next_chapter = current_chapter + 1
        total_chapters = get_total_chapters(enrollment["role"], stage)

        if next_chapter >= total_chapters:
            # Stage complete — check if there's a next stage
            next_stage = stage + 1
            total_stages = len(get_stages(enrollment["role"]))

            if next_stage >= total_stages:
                # Program complete!
                advance_user(enrollment["id"], current_chapter=next_chapter)
                return (
                    f"{feedback}\n\n"
                    f"*Congratulations!* You've completed the full training program. "
                    f"Refreshers will keep your skills sharp."
                )
            else:
                # Advance to next stage
                next_stage_name = get_stage_name(enrollment["role"], next_stage)
                advance_user(enrollment["id"], current_chapter=0, current_stage=next_stage)
                return (
                    f"{feedback}\n\n"
                    f"*Stage complete!* Next up: *{next_stage_name}*. "
                    f"Reply *next* when you're ready."
                )
        else:
            # More chapters in this stage
            advance_user(enrollment["id"], current_chapter=next_chapter)
            return (
                f"{feedback}\n\n"
                f"*Chapter complete.* I'll have the next chapter ready tomorrow. "
                f"Or reply *next* if you want to continue."
            )

    next_q = current_q + 1
    update_conversation(active_conversation["id"], current_question=next_q)
    next_question = _format_question(questions[next_q], num=next_q + 1, total=total)
    return f"{feedback}\n\n{next_question}"


def deliver_refresher(enrollment: dict, stage: int, chapter: int) -> str:
    """Deliver a refresher (practice questions) for a specific chapter."""
    role = enrollment["role"]
    cancel_stale_conversations(enrollment["id"])

    exercise = generate_exercise(role=role, stage=stage, chapter=chapter, practice=True)

    exercise_id = insert_exercise(
        user_id=enrollment["id"], stage=stage, chapter=chapter,
        exercise_type="refresher", content=exercise,
        source_tables=exercise["source_tables"],
    )
    # Refreshers skip instruction — go straight to questions (current_question=0)
    create_conversation(
        user_id=enrollment["id"], exercise_id=exercise_id,
        stage=stage, state="waiting_response", current_question=0,
    )

    from training.curriculum import get_chapter
    ch = get_chapter(role, stage, chapter)
    question = exercise["questions"][0]
    total = len(exercise["questions"])

    decayed = get_decayed_chapters(enrollment["id"])
    proficiency = next(
        (d["current_proficiency"] for d in decayed
         if d["stage"] == stage and d["chapter"] == chapter),
        None,
    )
    decay_note = " — it's been a while since we practiced this" if proficiency is not None else ""
    header = f"*{ch['name']}*{decay_note}\nLet's practice.\n\n"
    return header + _format_question(question, 1, total)


def daily_check(enrollment: dict) -> str | None:
    """Daily CronJob check for one enrollment. Returns message to send, or None.

    Priority:
    1. Skip if mid-chapter (active conversation exists)
    2. Deliver next chapter if idle
    3. If stage complete, check for decayed chapters → refresher
    4. Nothing to do → return None
    """
    enrollment_id = enrollment["id"]

    active = get_active_conversation(enrollment_id)
    if active:
        return None

    result = deliver_chapter(enrollment)
    if result:
        return result

    decayed = get_decayed_chapters(enrollment_id)
    if decayed:
        worst = decayed[0]
        return deliver_refresher(enrollment, worst["stage"], worst["chapter"])

    return None


def _format_question(question: dict, num: int, total: int) -> str:
    """Format a multiple-choice question for Slack."""
    opts = "\n".join(
        f"{letter}) {text}" for letter, text in question["options"].items()
    )
    return f"*Question {num} of {total}*\n\n{question['question']}\n\n{opts}"
