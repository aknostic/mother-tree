"""Tests for organization profile — three isolated units.

Unit 1: classify_document — document type classification
Unit 2: extract_profile — profile element extraction
Unit 3: merge_element — database deduplication and storage
"""
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Unit 1: classify_document
# ---------------------------------------------------------------------------

class TestClassifyDocument:
    """Classify a document as foundation, narrative, mixed, or irrelevant."""

    @patch("ingestion.profile.extract_structured")
    def test_classifies_foundation(self, mock_extract):
        from ingestion.profile import classify_document
        mock_extract.return_value = {"document_type": "foundation"}
        assert classify_document("Brand positioning doc") == "foundation"

    @patch("ingestion.profile.extract_structured")
    def test_classifies_narrative(self, mock_extract):
        from ingestion.profile import classify_document
        mock_extract.return_value = {"document_type": "narrative"}
        assert classify_document("Case study about replacing Qualtrics") == "narrative"

    @patch("ingestion.profile.extract_structured")
    def test_classifies_mixed(self, mock_extract):
        from ingestion.profile import classify_document
        mock_extract.return_value = {"document_type": "mixed"}
        assert classify_document("Pitch with positioning and case study") == "mixed"

    @patch("ingestion.profile.extract_structured")
    def test_classifies_irrelevant(self, mock_extract):
        from ingestion.profile import classify_document
        mock_extract.return_value = {"document_type": "irrelevant"}
        assert classify_document("Meeting notes") == "irrelevant"

    @patch("ingestion.profile.extract_structured")
    def test_normalizes_uppercase(self, mock_extract):
        from ingestion.profile import classify_document
        mock_extract.return_value = {"document_type": "FOUNDATION"}
        assert classify_document("Some doc") == "foundation"

    @patch("ingestion.profile.extract_structured")
    def test_returns_unknown_on_invalid_type(self, mock_extract):
        from ingestion.profile import classify_document
        mock_extract.return_value = {"document_type": "something_else"}
        assert classify_document("Some doc") == "unknown"

    @patch("ingestion.profile.extract_structured")
    def test_returns_unknown_on_llm_failure(self, mock_extract):
        from ingestion.profile import classify_document
        mock_extract.side_effect = Exception("LLM timeout")
        assert classify_document("Some doc") == "unknown"

    @patch("ingestion.profile.extract_structured")
    def test_returns_unknown_on_missing_key(self, mock_extract):
        from ingestion.profile import classify_document
        mock_extract.return_value = {"wrong_key": "foundation"}
        assert classify_document("Some doc") == "unknown"


# ---------------------------------------------------------------------------
# Unit 2: extract_profile
# ---------------------------------------------------------------------------

class TestExtractProfile:
    """Extract profile elements from a document."""

    @patch("ingestion.profile.extract_structured")
    def test_extracts_elements(self, mock_extract):
        from ingestion.profile import extract_profile
        mock_extract.return_value = [
            {"type": "identity", "content": "Cloud-native consultancy", "confidence": 0.9},
            {"type": "audience", "content": "CTO / VP Engineering", "confidence": 0.8},
        ]
        result = extract_profile("Brand positioning doc")
        assert len(result) == 2
        assert result[0]["type"] == "identity"
        assert result[1]["type"] == "audience"

    @patch("ingestion.profile.extract_structured")
    def test_returns_empty_for_no_elements(self, mock_extract):
        from ingestion.profile import extract_profile
        mock_extract.return_value = []
        assert extract_profile("Random content") == []

    @patch("ingestion.profile.extract_structured")
    def test_filters_invalid_types(self, mock_extract):
        from ingestion.profile import extract_profile
        mock_extract.return_value = [
            {"type": "identity", "content": "Cloud consultancy", "confidence": 0.9},
            {"type": "bad_type", "content": "Should be dropped", "confidence": 0.5},
        ]
        result = extract_profile("Some content")
        assert len(result) == 1
        assert result[0]["type"] == "identity"

    @patch("ingestion.profile.extract_structured")
    def test_normalizes_uppercase_types(self, mock_extract):
        from ingestion.profile import extract_profile
        mock_extract.return_value = [
            {"type": "IDENTITY", "content": "Cloud consultancy", "confidence": 0.9},
            {"type": "CHANGE", "content": "From lock-in to freedom", "confidence": 0.8},
        ]
        result = extract_profile("Some content")
        assert len(result) == 2
        assert result[0]["type"] == "identity"
        assert result[1]["type"] == "change"

    @patch("ingestion.profile.extract_structured")
    def test_skips_elements_without_content(self, mock_extract):
        from ingestion.profile import extract_profile
        mock_extract.return_value = [
            {"type": "identity", "content": "", "confidence": 0.9},
            {"type": "change", "content": "Real change", "confidence": 0.8},
        ]
        result = extract_profile("Some content")
        assert len(result) == 1
        assert result[0]["type"] == "change"

    @patch("ingestion.profile.extract_structured")
    def test_skips_non_dict_elements(self, mock_extract):
        from ingestion.profile import extract_profile
        mock_extract.return_value = [
            "some string that should be skipped",
            {"type": "identity", "content": "Real element", "confidence": 0.9},
        ]
        result = extract_profile("Some content")
        assert len(result) == 1

    @patch("ingestion.profile.extract_structured")
    def test_returns_empty_on_llm_failure(self, mock_extract):
        from ingestion.profile import extract_profile
        mock_extract.side_effect = Exception("LLM timeout")
        assert extract_profile("Some content") == []


class TestRescanProfile:
    """Rescan profile with foundation context."""

    @patch("ingestion.profile.extract_structured")
    def test_rescan_includes_foundation_context(self, mock_extract):
        from ingestion.profile import rescan_profile
        mock_extract.return_value = [
            {"type": "identity", "content": "Refined identity", "confidence": 0.95},
        ]
        rescan_profile(
            content="Some content",
            foundation_context="Change: We help organizations...",
            current_profile="Identity: Cloud consultancy",
        )
        prompt = mock_extract.call_args[0][1]
        assert "foundation" in prompt.lower()
        assert "We help organizations" in prompt

    @patch("ingestion.profile.extract_structured")
    def test_rescan_includes_current_profile(self, mock_extract):
        from ingestion.profile import rescan_profile
        mock_extract.return_value = []
        rescan_profile(
            content="Some content",
            foundation_context="Change: test",
            current_profile="Identity: Cloud consultancy",
        )
        prompt = mock_extract.call_args[0][1]
        assert "Cloud consultancy" in prompt


# ---------------------------------------------------------------------------
# Unit 3: merge_element
# ---------------------------------------------------------------------------

class TestMergeElement:
    """Merge profile elements with deduplication."""

    @patch("ingestion.profile.get_organization_profile")
    @patch("ingestion.profile.insert_organization_element")
    def test_inserts_new_element(self, mock_insert, mock_get):
        from ingestion.profile import merge_element
        mock_get.return_value = []
        mock_insert.return_value = "new-id"
        action = merge_element({"type": "identity", "content": "Cloud consultancy", "confidence": 0.9})
        assert action == "inserted"
        mock_insert.assert_called_once()
        call_args = mock_insert.call_args[0][0]
        assert call_args["element_type"] == "identity"
        assert call_args["content"] == "Cloud consultancy"
        assert call_args["source_count"] == 1

    @patch("ingestion.profile.get_organization_profile")
    @patch("ingestion.profile.update_organization_element")
    def test_updates_exact_match(self, mock_update, mock_get):
        from ingestion.profile import merge_element
        mock_get.return_value = [
            {"id": "existing-id", "element_type": "identity", "content": "Cloud consultancy", "confidence": 0.7, "source_count": 2},
        ]
        action = merge_element({"type": "identity", "content": "Cloud consultancy", "confidence": 0.9})
        assert action == "updated"
        mock_update.assert_called_once()
        call_id = mock_update.call_args[0][0]
        call_updates = mock_update.call_args[0][1]
        assert call_id == "existing-id"
        assert call_updates["confidence"] == 0.9  # higher of 0.7 and 0.9
        assert call_updates["source_count"] == 3  # 2 + 1

    @patch("ingestion.profile.get_organization_profile")
    @patch("ingestion.profile.insert_organization_element")
    def test_inserts_different_content_same_type(self, mock_insert, mock_get):
        from ingestion.profile import merge_element
        mock_get.return_value = [
            {"id": "existing-id", "element_type": "identity", "content": "Cloud consultancy", "confidence": 0.7, "source_count": 2},
        ]
        mock_insert.return_value = "new-id"
        action = merge_element({"type": "identity", "content": "Platform engineering firm", "confidence": 0.8})
        assert action == "inserted"
        mock_insert.assert_called_once()

    @patch("ingestion.profile.get_organization_profile")
    @patch("ingestion.profile.insert_organization_element")
    def test_ignores_different_type_when_matching(self, mock_insert, mock_get):
        from ingestion.profile import merge_element
        mock_get.return_value = [
            {"id": "existing-id", "element_type": "change", "content": "Cloud consultancy", "confidence": 0.7, "source_count": 2},
        ]
        mock_insert.return_value = "new-id"
        # Same content but different type — should insert, not update
        action = merge_element({"type": "identity", "content": "Cloud consultancy", "confidence": 0.9})
        assert action == "inserted"


class TestMergeElements:
    """Batch merge with stats."""

    @patch("ingestion.profile.merge_element")
    def test_counts_actions(self, mock_merge):
        from ingestion.profile import merge_elements
        mock_merge.side_effect = ["inserted", "updated", "inserted"]
        stats = merge_elements([
            {"type": "identity", "content": "A", "confidence": 0.9},
            {"type": "identity", "content": "A", "confidence": 0.8},
            {"type": "change", "content": "B", "confidence": 0.7},
        ])
        assert stats["inserted"] == 2
        assert stats["updated"] == 1
        assert stats["skipped"] == 0

    @patch("ingestion.profile.merge_element")
    def test_skips_empty_content(self, mock_merge):
        from ingestion.profile import merge_elements
        stats = merge_elements([
            {"type": "identity", "content": "", "confidence": 0.9},
            {"type": "identity", "confidence": 0.8},
        ])
        assert stats["skipped"] == 2
        mock_merge.assert_not_called()


# ---------------------------------------------------------------------------
# Unit 4: consolidate_profile
# ---------------------------------------------------------------------------

class TestConsolidateProfile:
    """Consolidate profile — deduplicate and synthesize."""

    @patch("ingestion.profile.extract_structured")
    def test_consolidates_duplicates(self, mock_extract):
        from ingestion.profile import consolidate_profile
        mock_extract.return_value = [
            {"type": "identity", "content": "European cloud consultancy", "confidence": 0.95},
            {"type": "change", "content": "From vendor lock-in to freedom to operate", "confidence": 0.9},
        ]
        elements = [
            {"type": "identity", "content": "Cloud-native consultancy"},
            {"type": "identity", "content": "Cloud infrastructure consultancy"},
            {"type": "identity", "content": "European cloud consultancy"},
            {"type": "change", "content": "From lock-in to freedom"},
            {"type": "change", "content": "From vendor lock-in to freedom to operate"},
        ]
        result = consolidate_profile(elements)
        assert len(result) == 2
        assert result[0]["type"] == "identity"
        assert result[1]["type"] == "change"

    @patch("ingestion.profile.extract_structured")
    def test_prompt_includes_all_elements(self, mock_extract):
        from ingestion.profile import consolidate_profile
        mock_extract.return_value = []
        consolidate_profile([
            {"type": "identity", "content": "Cloud consultancy"},
            {"type": "audience", "content": "CTOs"},
        ])
        prompt = mock_extract.call_args[0][1]
        assert "Cloud consultancy" in prompt
        assert "CTOs" in prompt

    def test_empty_input_returns_empty(self):
        from ingestion.profile import consolidate_profile
        assert consolidate_profile([]) == []

    @patch("ingestion.profile.extract_structured")
    def test_falls_back_to_originals_on_failure(self, mock_extract):
        from ingestion.profile import consolidate_profile
        mock_extract.side_effect = Exception("LLM timeout")
        elements = [{"type": "identity", "content": "Cloud consultancy"}]
        result = consolidate_profile(elements)
        assert result == elements


# ---------------------------------------------------------------------------
# Fetch profile for prompt injection
# ---------------------------------------------------------------------------

class TestFetchProfile:
    """Fetch formats profile for prompt injection."""

    @patch("ingestion.profile.get_organization_profile")
    def test_formats_by_type(self, mock_get):
        from ingestion.profile import fetch_organization_profile
        mock_get.return_value = [
            {"id": "1", "element_type": "identity", "content": "Cloud consultancy", "confidence": 0.9, "source_count": 5},
            {"id": "2", "element_type": "change", "content": "From lock-in to freedom", "confidence": 0.85, "source_count": 3},
            {"id": "3", "element_type": "audience", "content": "CTO / VP Engineering", "confidence": 0.8, "source_count": 4},
        ]
        result = fetch_organization_profile()
        assert "Identity:" in result
        assert "Cloud consultancy" in result
        assert "Change:" in result
        assert "Audience:" in result

    @patch("ingestion.profile.get_organization_profile")
    def test_empty_profile(self, mock_get):
        from ingestion.profile import fetch_organization_profile
        mock_get.return_value = []
        assert fetch_organization_profile() == ""


# ---------------------------------------------------------------------------
# Embedding (standalone utility, not part of the three units)
# ---------------------------------------------------------------------------

class TestEmbedding:
    """Embedding function for future similarity matching."""

    @patch("mothertree.llm.scaleway")
    def test_embed_returns_vector(self, mock_scw):
        from mothertree.llm import embed
        mock_scw.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 3584)]
        )
        result = embed("test text")
        assert len(result) == 3584

    @patch("mothertree.llm.scaleway")
    def test_embed_uses_embedding_model(self, mock_scw):
        from mothertree.config import EMBEDDING_MODEL
        from mothertree.llm import _embed_cache, embed
        _embed_cache.clear()
        mock_scw.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 3584)]
        )
        embed("test text for model check")
        mock_scw.embeddings.create.assert_called_once()
        assert mock_scw.embeddings.create.call_args[1]["model"] == EMBEDDING_MODEL


# ---------------------------------------------------------------------------
# Four-pass orchestration and profile-aware extraction tests removed.
# The profile module exists for future use but the pipeline uses the
# original single-pass extraction for now.
# ---------------------------------------------------------------------------


class TestConsolidateCLIFlow:
    """Test that the consolidate command runs profile consolidation after foundation."""

    @patch("ingestion.profile.extract_structured")
    @patch("mothertree.graphql_client.graphql")
    def test_consolidate_profile_called_with_org_elements(self, mock_gql, mock_extract):
        """get_organization_profile → consolidate_profile → merge_elements."""
        def gql_side_effect(query, *args, **kwargs):
            if "allOrganizationsList" in query and "id }" in query:
                # delete_all_organization fetches IDs — return empty so no deletes run
                return {"allOrganizationsList": []}
            if "allOrganizationsList" in query:
                return {"allOrganizationsList": [
                    {"id": "1", "element_type": "identity", "content": "We build IDPs", "confidence": 0.8, "source_count": 1},
                    {"id": "2", "element_type": "identity", "content": "We build and operate IDPs", "confidence": 0.7, "source_count": 1},
                ]}
            if "createOrganization" in query:
                return {"createOrganization": {"organization": {"id": "new-1"}}}
            return {}

        mock_gql.side_effect = gql_side_effect
        mock_extract.return_value = [
            {"type": "identity", "content": "We build and operate IDPs on open source", "confidence": 0.9},
        ]
        from ingestion.ingest import consolidate_organization_profile
        result = consolidate_organization_profile()
        assert result["consolidated"] >= 1
