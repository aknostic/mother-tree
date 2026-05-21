"""Tests for the graphql() helper — error surfacing in particular."""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestGraphqlErrorSurfacing:
    """4xx responses must carry the PostGraphile error body into the exception."""

    @patch("mothertree.graphql_client.httpx.post")
    def test_400_includes_errors_array_in_exception(self, mock_post):
        mock_resp = MagicMock(
            status_code=400,
            text=json.dumps({"errors": [{"message": "field 'snoozedUntil' is not defined"}]}),
        )
        mock_resp.json.return_value = {
            "errors": [{"message": "field 'snoozedUntil' is not defined"}]
        }
        mock_post.return_value = mock_resp

        from mothertree.graphql_client import graphql
        with pytest.raises(RuntimeError) as exc:
            graphql("mutation { foo }")

        msg = str(exc.value)
        assert "400" in msg
        assert "snoozedUntil" in msg

    @patch("mothertree.graphql_client.httpx.post")
    def test_400_with_non_json_body_includes_raw_text(self, mock_post):
        mock_resp = MagicMock(status_code=400, text="upstream went sideways")
        mock_resp.json.side_effect = ValueError("not json")
        mock_post.return_value = mock_resp

        from mothertree.graphql_client import graphql
        with pytest.raises(RuntimeError) as exc:
            graphql("query { foo }")

        assert "upstream went sideways" in str(exc.value)

    @patch("mothertree.graphql_client.httpx.post")
    def test_200_with_errors_field_still_raises(self, mock_post):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"errors": [{"message": "constraint failed"}]}
        mock_post.return_value = mock_resp

        from mothertree.graphql_client import graphql
        with pytest.raises(RuntimeError) as exc:
            graphql("mutation { foo }")

        assert "constraint failed" in str(exc.value)
