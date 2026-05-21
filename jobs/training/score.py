"""Scoring with stage dispatch.

Stage 0: deterministic multiple-choice (compare answer to correct).
Stages 1-4: raise NotImplementedError.
"""


def score_response(stage: int, question: dict, response: str) -> dict:
    """Score a trainee's response to a question.

    Returns dict with:
        correct: bool
        feedback: str (formatted for Slack DM)
    """
    if stage != 0:
        raise NotImplementedError(f"Scoring for stage {stage} not yet implemented")

    return _score_mc(question, response)


def _score_mc(question: dict, response: str) -> dict:
    """Score a multiple-choice response. Deterministic: compare to correct answer."""
    answer = response.strip().upper()
    correct_letter = question["correct"]

    if answer not in ("A", "B", "C"):
        return {
            "correct": False,
            "feedback": f"Please reply with A, B, or C.\n\nThe answer is {correct_letter}.",
        }

    if answer == correct_letter:
        return {
            "correct": True,
            "feedback": f"\u2713 Right.\n\n{question['why']}",
        }

    correct_text = question["options"][correct_letter]
    why = question["why"]
    # Strip trailing period to splice into sentence, then lowercase for flow
    why_lc = why.rstrip(".").lower()
    return {
        "correct": False,
        "feedback": (
            f"Not quite \u2014 it's {correct_letter}.\n\n"
            f"\"{correct_text}\" is stronger because {why_lc}.\n\n"
            f"Try this: {question['redirect']}"
        ),
    }
