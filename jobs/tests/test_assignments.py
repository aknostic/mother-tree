"""LLM-assessed tests — assignments with confidence scoring.

Each test is an assignment: execute something, then have a scoring
model assess whether the output meets the criteria. Same pipeline
as content scoring — no string matching, just confidence.

Run with: RUN_LLM_TESTS=1 pytest tests/test_assignments.py -v
"""

import json
import statistics

import pytest

from mothertree.config import SCORING_MODELS
from mothertree.llm import scaleway

pytestmark = pytest.mark.llm

CONFIDENCE_THRESHOLD = 0.6  # more lenient than production (0.7) — tests are harder


def assess_confidence(output: str, criteria: str) -> float:
    """Have scoring models assess whether output meets criteria.

    Returns median confidence across models.
    """
    prompt = f"""Rate how well this output meets the criteria. Return ONLY a JSON object:
{{"confidence": 0.0 to 1.0, "reason": "one sentence"}}

CRITERIA:
{criteria}

OUTPUT TO ASSESS:
{output}"""

    scores = []
    for model in SCORING_MODELS[:2]:  # use 2 models for speed in tests
        try:
            response = scaleway.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You assess output quality. Return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=100,
                timeout=30,
            )
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rstrip("`").strip()
            data = json.loads(text)
            scores.append(data.get("confidence", 0.5))
        except Exception:
            scores.append(0.5)

    return statistics.median(scores) if scores else 0.5


# --- Foundation extraction assignments ---

class TestFoundationAssignments:

    def test_brand_extraction_captures_change(self):
        from pathlib import Path

        from ingestion.extract import extract_foundation

        brand = Path("/Users/jurg/Projects/marketing/Aknostic/foundation/brand.md")
        if not brand.exists():
            pytest.skip("Marketing repo not available")
        content = brand.read_text()[:5000]
        result = extract_foundation(content)

        output = json.dumps(result, indent=2)
        confidence = assess_confidence(
            output,
            "Should extract change statements about ownership, freedom to operate, "
            "or independence from vendors. Should extract worldview about audience pain "
            "(cost, lock-in, compliance). Records should have 'type' field."
        )
        assert confidence >= CONFIDENCE_THRESHOLD, f"Brand extraction confidence: {confidence}"


# --- Persona quality assignments ---

class TestPersonaAssignments:

    def test_saga_grounded_in_intelligence(self):
        from mothertree.ask import ask
        response = ask("saga", "What is the change we offer?", user_name="test")

        confidence = assess_confidence(
            response,
            "Saga should describe a transformation — from dependency to ownership, "
            "from renting to owning, from vendor control to freedom. Should reference "
            "the audience's pain (cost, lock-in) and the worldview (they believe independence "
            "is possible). Should NOT be generic marketing advice — should be specific to "
            "the company's positioning in the central intelligence."
        )
        assert confidence >= CONFIDENCE_THRESHOLD, f"Saga grounding confidence: {confidence}"

    def test_lena_practical_and_service_oriented(self):
        from mothertree.ask import ask
        response = ask("lena", "How do I approach a first meeting?", user_name="test")

        confidence = assess_confidence(
            response,
            "Lena should give practical consultative diagnostic advice: "
            "listen first, ask open-ended questions, probe for the real problem, "
            "co-create understanding, build trust through service. Should reference "
            "the company's specific offerings when relevant. Should NOT be a pitch — "
            "should be about earning the right to a deeper conversation."
        )
        assert confidence >= CONFIDENCE_THRESHOLD, f"Lena grounding confidence: {confidence}"

    def test_trainer_consensus_unified(self):
        from mothertree.ask import ask
        response = ask("trainer", "practice objection handling", user_name="test")

        confidence = assess_confidence(
            response,
            "The trainer should produce ONE coherent exercise, not two separate perspectives. "
            "Should incorporate marketing strategy (worldview, reframe, positioning) AND "
            "consultative selling (listen, diagnose, co-create). The output should feel like "
            "one expert trainer, not Saga and Lena arguing. Should address the trainee "
            "by name and be practical."
        )
        assert confidence >= CONFIDENCE_THRESHOLD, f"Trainer consensus confidence: {confidence}"


# --- Foundation consistency assignments ---

class TestConsistencyAssignments:

    def test_site_aligns_with_marketing_repo(self):
        """The site and marketing repo should produce consistent foundation data."""
        from mothertree.graphql_client import graphql

        result = graphql("""
        {
          marketing: allChangesList(filter: {source: {includesInsensitive: "marketing"}}, first: 5) { statement }
          site: allChangesList(filter: {source: {includesInsensitive: "aknostic.com"}}, first: 5) { statement }
        }
        """)

        if not result.get("marketing") or not result.get("site"):
            pytest.skip("Need both sources ingested")

        marketing_stmts = "\n".join(c["statement"] for c in result["marketing"])
        site_stmts = "\n".join(c["statement"] for c in result["site"])

        confidence = assess_confidence(
            f"MARKETING REPO:\n{marketing_stmts}\n\nSITE:\n{site_stmts}",
            "Both sources should describe the same company and the same change. "
            "They should agree on: ownership/freedom as the transformation, "
            "open source as the approach, cost reduction as a benefit, "
            "capability transfer as the delivery model. Minor wording differences "
            "are fine. Contradictions are not."
        )
        assert confidence >= CONFIDENCE_THRESHOLD, f"Source consistency confidence: {confidence}"

    def test_canonical_reflects_frameworks(self):
        """The canonical positioning should be a valid application of Saga's framework."""
        from mothertree.graphql_client import graphql

        canonical = graphql('{ allChangesList(condition: {source: "canonical"}) { statement context } }')
        saga = graphql('{ allChangesList(condition: {source: "framework:saga"}) { statement } }')

        if not canonical.get("allChangesList") or not saga.get("allChangesList"):
            pytest.skip("Need canonical and framework records")

        confidence = assess_confidence(
            f"SAGA'S FRAMEWORK:\n{saga['allChangesList'][0]['statement']}\n\n"
            f"CANONICAL POSITIONING:\n{canonical['allChangesList'][0]['statement']}",
            "The canonical positioning should be a specific application of Saga's framework. "
            "Saga says 'The Change is the transformation you offer — what the customer becomes.' "
            "The canonical change should describe a specific transformation (from dependency to "
            "ownership, from SaaS costs to controlled infrastructure). It should be concrete "
            "where the framework is abstract."
        )
        assert confidence >= CONFIDENCE_THRESHOLD, f"Canonical-framework alignment: {confidence}"
