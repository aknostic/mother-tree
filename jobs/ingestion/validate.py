"""Field validation and multi-model confidence scoring.

Scoring pipeline:
1. Three independent Scaleway models score each insight (0.0-1.0)
2. Median score + agreement check
3. Auto-accept (all agree >0.7), auto-reject (all agree <0.4)
4. Disagreement → Haiku 4.5 triage
5. Still ambiguous → Sonnet 4.6 arbitration
"""

import json
import statistics

from mothertree.config import (
    CONFIDENCE_AUTO_ACCEPT,
    CONFIDENCE_AUTO_REJECT,
    CONFIDENCE_DISAGREEMENT_SPREAD,
    SCORING_MODELS,
)
from mothertree.llm import arbitrate, score, triage

VALID_INSIGHT_CATEGORIES = {
    "lock-in-freedom",
    "regulatory-pressure",
    "capability-vs-dependency",
    "cost-reality",
    "developer-experience",
    "resilience-reliability",
}

VALID_INSIGHT_FIELDS = {
    "category", "reframe", "evidence", "stakeholder_lens",
    "trigger", "next_step",
}

VALID_PERSONA_FIELDS = {
    "name", "role", "profile", "fears", "motivation", "trigger",
    "communication", "decision_criteria", "objections", "how_to_reach",
}

VALID_CASE_STUDY_FIELDS = {
    "title", "industry", "challenge", "approach",
    "outcome", "relevant_personas", "relevant_insights",
}

VALID_COMPETITOR_FIELDS = {
    "type", "positioning", "when_mentioned", "response",
}

VALID_CHANGE_FIELDS = {"statement", "context"}

VALID_WORLDVIEW_FIELDS = {"persona_name", "persona_id", "belief", "pain", "readiness_signal"}

INTERNAL_FIELDS = {"source", "confidence", "flagged", "scores", "triage_reason"}


def _stringify_text_fields(record: dict, fields: set) -> dict:
    """Ensure fields that should be text are stringified if the LLM returned objects."""
    for field in fields:
        if field in record and not isinstance(record[field], (str, type(None))):
            record[field] = json.dumps(record[field])
    return record


def _validate_record(
    record: dict,
    valid_fields: set,
    required_fields: set,
    text_fields: set,
) -> tuple[dict | None, list[str]]:
    """Generic validation: filter unknown fields, check required, stringify text."""
    errors = []
    unknown = set(record.keys()) - valid_fields - INTERNAL_FIELDS
    if unknown:
        errors.append(f"Unknown fields removed: {unknown}")
        record = {k: v for k, v in record.items() if k in valid_fields | INTERNAL_FIELDS}
    for req in required_fields:
        if not record.get(req):
            errors.append(f"Missing required field: {req}")
            return None, errors
    record = _stringify_text_fields(record, text_fields)
    return record, errors


def validate_change(record: dict) -> tuple[dict | None, list[str]]:
    return _validate_record(record, VALID_CHANGE_FIELDS, {"statement"}, {"statement", "context"})


def validate_worldview(record: dict) -> tuple[dict | None, list[str]]:
    return _validate_record(record, VALID_WORLDVIEW_FIELDS, {"belief"}, {"belief", "pain", "readiness_signal"})


def validate_competitor(record: dict) -> tuple[dict | None, list[str]]:
    return _validate_record(record, VALID_COMPETITOR_FIELDS, {"type"}, {"type", "positioning", "when_mentioned", "response"})


def validate_case_study(record: dict) -> tuple[dict | None, list[str]]:
    return _validate_record(record, VALID_CASE_STUDY_FIELDS, {"title"}, {"title", "industry", "challenge", "approach", "outcome"})


def validate_persona(persona: dict) -> tuple[dict | None, list[str]]:
    """Persona needs extra stringify for JSON fields (decision_criteria, objections)."""
    record, errors = _validate_record(persona, VALID_PERSONA_FIELDS, {"name"}, {"profile", "communication", "how_to_reach"})
    if record is None:
        return None, errors
    record = _stringify_text_fields(record, {"decision_criteria", "objections"})
    return record, errors


def validate_insight(insight: dict) -> tuple[dict | None, list[str]]:
    """Insight needs extra category validation and stakeholder_lens stringify."""
    record, errors = _validate_record(insight, VALID_INSIGHT_FIELDS, {"reframe", "category"}, {"reframe", "evidence", "trigger", "next_step"})
    if record is None:
        return None, errors
    if record["category"] not in VALID_INSIGHT_CATEGORIES:
        errors.append(f"Invalid category: {record['category']}")
        return None, errors
    record = _stringify_text_fields(record, {"stakeholder_lens"})
    return record, errors


# --- Multi-model confidence scoring ---

SCORING_PROMPT = """
Rate the quality of each extracted commercial insight on a scale from 0.0 to 1.0.

Scoring criteria:
- 0.9-1.0: Clear, specific reframe with concrete evidence. Directly usable in a sales conversation.
- 0.7-0.9: Good reframe but evidence could be stronger, or slightly generic. Usable with minor refinement.
- 0.5-0.7: Vague or generic insight. Might be useful but needs human review.
- 0.0-0.5: Not a real insight — a summary, a truism, or irrelevant to consultative selling.

Return ONLY a JSON array of objects: [{{"index": 0, "confidence": 0.85}}, ...]

Insights to score:
{items}
"""


def _build_scoring_items(insights: list[dict]) -> str:
    items = []
    for i, insight in enumerate(insights):
        items.append(
            f'{i}. Reframe: "{insight.get("reframe", "")}" | '
            f'Evidence: "{insight.get("evidence", "")}" | '
            f'Category: {insight.get("category", "unknown")}'
        )
    return "\n".join(items)


def _parse_scores(raw_scores: list[dict], count: int) -> list[float]:
    """Parse score results into a list aligned by index."""
    score_map = {}
    for s in raw_scores:
        idx = s.get("index")
        conf = s.get("confidence")
        if idx is not None and conf is not None:
            score_map[int(idx)] = float(conf)
    return [score_map.get(i, 0.5) for i in range(count)]


def score_insights_multi_model(insights: list[dict]) -> list[dict]:
    """Score insights with three independent models, then triage and arbitrate."""
    if not insights:
        return insights

    items_text = _build_scoring_items(insights)
    prompt = SCORING_PROMPT.format(items=items_text)

    # --- Stage 1: Three independent scorers ---
    all_scores = []
    for model in SCORING_MODELS:
        model_name = model.split("/")[-1] if "/" in model else model
        try:
            raw = score(model, prompt)
            scores = _parse_scores(raw, len(insights))
            all_scores.append(scores)
            print(f"    Scorer {model_name}: {[round(s, 2) for s in scores[:5]]}{'...' if len(scores) > 5 else ''}")
        except Exception as e:
            print(f"    Scorer {model_name} failed: {e}")
            all_scores.append([0.5] * len(insights))

    # --- Stage 2: Median + agreement ---
    for i, insight in enumerate(insights):
        scores = [model_scores[i] for model_scores in all_scores]
        median = statistics.median(scores)
        spread = max(scores) - min(scores)

        insight["scores"] = [round(s, 2) for s in scores]
        insight["confidence"] = round(median, 2)

        if min(scores) >= CONFIDENCE_AUTO_ACCEPT:
            insight["flagged"] = False
        elif max(scores) <= CONFIDENCE_AUTO_REJECT:
            insight["flagged"] = False  # will be filtered by auto-reject in caller
            insight["confidence"] = round(median, 2)
        elif spread >= CONFIDENCE_DISAGREEMENT_SPREAD:
            insight["flagged"] = True  # scorers disagree — needs triage
        else:
            insight["flagged"] = median < CONFIDENCE_AUTO_ACCEPT

    # --- Stage 3: Haiku triage for flagged ---
    flagged_indices = [i for i, ins in enumerate(insights) if ins.get("flagged")]
    if flagged_indices:
        flagged_insights = [insights[i] for i in flagged_indices]
        print(f"    Triaging {len(flagged_insights)} flagged insights with Haiku...")
        try:
            triage_results = triage(flagged_insights)
            escalate_indices = []
            for result in triage_results:
                idx = result.get("index", 0)
                decision = result.get("decision", "human_review")
                reason = result.get("reason", "")
                actual_idx = flagged_indices[idx] if idx < len(flagged_indices) else None
                if actual_idx is not None:
                    insights[actual_idx]["triage_reason"] = reason
                    if decision == "accept":
                        insights[actual_idx]["flagged"] = False
                        insights[actual_idx]["confidence"] = max(insights[actual_idx]["confidence"], CONFIDENCE_AUTO_ACCEPT)
                    elif decision == "reject":
                        insights[actual_idx]["confidence"] = 0.0
                    elif decision == "escalate":
                        escalate_indices.append(actual_idx)
                    # human_review: leave flagged=True

            # --- Stage 4: Sonnet arbitration for escalated ---
            if escalate_indices:
                escalated = [insights[i] for i in escalate_indices]
                print(f"    Arbitrating {len(escalated)} ambiguous insights with Sonnet...")
                try:
                    arb_results = arbitrate(escalated)
                    for result in arb_results:
                        idx = result.get("index", 0)
                        decision = result.get("decision", "reject")
                        actual_idx = escalate_indices[idx] if idx < len(escalate_indices) else None
                        if actual_idx is not None:
                            if decision == "accept":
                                insights[actual_idx]["flagged"] = False
                                insights[actual_idx]["confidence"] = max(insights[actual_idx]["confidence"], CONFIDENCE_AUTO_ACCEPT)
                            else:
                                insights[actual_idx]["confidence"] = 0.0
                except Exception as e:
                    print(f"    Sonnet arbitration failed: {e} — escalated items go to human review")

        except Exception as e:
            print(f"    Haiku triage failed: {e} — flagged items go to human review")

    return insights
