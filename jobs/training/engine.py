"""Exercise generator with stage dispatch.

Generates structured training exercises from the central intelligence.
Stage 0 (instruction) is implemented. Stages 1-4 raise NotImplementedError.
"""
import json
import logging
import random

log = logging.getLogger(__name__)


def generate(system_prompt: str, user_prompt: str, model: str = None) -> str:
    """Delegate to mothertree.llm.generate (lazy import so tests can patch this name)."""
    from mothertree.llm import generate as _generate
    return _generate(system_prompt, user_prompt, model)


def _parse_json(text: str) -> dict:
    """Strip markdown fences and parse JSON. Mirrors mothertree.llm._parse_json."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    if text.startswith("json\n"):
        text = text[5:]
    return json.loads(text)


def fetch_foundation_for_chapter(chapter: int = None, tables: list[str] = None,
                                 query: str = None) -> dict:
    """Delegate to mothertree.graphql_client.fetch_foundation_for_chapter."""
    from mothertree.graphql_client import fetch_foundation_for_chapter as _fetch
    return _fetch(chapter=chapter, tables=tables, query=query)


def generate_exercise(role: str = "hunter", stage: int = 0, chapter: int = 0,
                      practice: bool = False) -> dict:
    """Generate a structured exercise for the given role, stage, and chapter.

    Returns a dict ready to be stored as JSONB in the exercises table.
    Raises NotImplementedError for stages with no chapters defined.
    Raises ValueError if the LLM output doesn't validate.
    """
    from training.curriculum import get_chapter

    ch = get_chapter(role, stage, chapter)
    if not ch:
        raise NotImplementedError(f"Stage {stage} not yet implemented for role {role}")

    data = fetch_foundation_for_chapter(tables=ch["tables"], query=ch["purpose"])
    source_data = _format_source_data(data)

    if practice:
        prompt = _practice_prompt(ch, source_data)
    else:
        prompt = _instruction_prompt(ch, source_data)

    system = (
        "You generate training material for a consultative sales team. "
        "Always respond with valid JSON only. No markdown fences."
    )
    raw = generate(system, prompt)
    content = _parse_json(raw)
    _validate_exercise(content, practice)

    # Shuffle option positions so the correct answer isn't always B
    content["questions"] = [_shuffle_options(q) for q in content["questions"]]

    exercise = {
        "stage": stage,
        "chapter": chapter,
        "chapter_name": ch["name"],
        "trainer": ch["trainer"],
        "type": "practice" if practice else "instruction",
        "questions": content["questions"],
        "source_tables": ch["tables"],
    }
    if not practice:
        exercise["instruction"] = content["instruction"]

    return exercise


def _instruction_prompt(chapter: dict, source_data: str) -> str:
    return f"""Generate training material for the chapter: {chapter["name"]}.

PURPOSE OF THIS CHAPTER:
{chapter["purpose"]}

SOURCE DATA:
{source_data}

GENERATE a JSON object with:
1. "instruction": Teaching text (300-500 words). Teach this as a practitioner would explain it to a new colleague. Direct, concrete, no jargon overload. Use the actual data — real statements, real beliefs, real details. This isn't theory, it's what we actually say. Format for Slack: use *bold* for key concepts, break into short paragraphs, use bullet points where listing items. No headers — just flowing text with structure.

2. "questions": An array of exactly 3 multiple-choice questions that test understanding, not memorization. Each question presents a realistic situation where the trainee applies what they just learned. Each question object has:
   - "question": A scenario (not "which of the following...")
   - "options": {{"A": "...", "B": "...", "C": "..."}} (one correct, two plausible but wrong)
   - "correct": The letter of the correct answer ("A", "B", or "C")
   - "why": One sentence on why the correct answer is stronger
   - "redirect": A thinking prompt the trainee can carry into real conversations (one sentence)"""


def _practice_prompt(chapter: dict, source_data: str) -> str:
    return f"""Generate practice questions for the chapter: {chapter["name"]}.

PURPOSE OF THIS CHAPTER:
{chapter["purpose"]}

SOURCE DATA:
{source_data}

GENERATE a JSON object with:
"questions": An array of exactly 3 multiple-choice questions. These are practice questions for someone who has already read the instruction material. Each question presents a realistic situation. Each question object has:
   - "question": A scenario (not "which of the following...")
   - "options": {{"A": "...", "B": "...", "C": "..."}} (one correct, two plausible but wrong)
   - "correct": The letter of the correct answer ("A", "B", or "C")
   - "why": One sentence on why the correct answer is stronger
   - "redirect": A thinking prompt the trainee can carry into real conversations (one sentence)"""


def _format_source_data(data: dict) -> str:
    """Format foundation query results into readable text for the prompt."""
    parts = []
    for table, rows in data.items():
        if not rows:
            continue
        parts.append(f"### {table}")
        for row in rows:
            fields = ", ".join(f"{k}: {v}" for k, v in row.items() if v)
            parts.append(f"- {fields}")
    return "\n".join(parts)


def _shuffle_options(question: dict) -> dict:
    """Randomize the position of the correct answer within options.

    LLMs have a strong bias toward placing the correct answer at B.
    This shuffles A/B/C so the correct answer lands at a random position.
    """
    correct_letter = question["correct"]
    options = question["options"]
    correct_text = options[correct_letter]

    # Collect all option texts and shuffle
    items = list(options.values())
    random.shuffle(items)

    # Rebuild options with shuffled order
    letters = ["A", "B", "C"]
    new_options = dict(zip(letters, items))
    new_correct = next(letter for letter, text in new_options.items() if text == correct_text)

    return {**question, "options": new_options, "correct": new_correct}


def _validate_exercise(content: dict, practice: bool) -> None:
    """Validate the LLM-generated exercise structure."""
    if not practice and "instruction" not in content:
        raise ValueError("Missing instruction text in exercise")
    if "questions" not in content:
        raise ValueError("Missing questions in exercise")
    if len(content["questions"]) != 3:
        raise ValueError(f"Expected 3 questions, got {len(content['questions'])}")
    for i, q in enumerate(content["questions"]):
        for field in ("question", "options", "correct", "why", "redirect"):
            if field not in q:
                raise ValueError(f"Question {i} missing field: {field}")
        if q["correct"] not in ("A", "B", "C"):
            raise ValueError(f"Question {i} correct answer must be A, B, or C")
