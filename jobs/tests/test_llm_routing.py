"""Tests for LLM model routing — Claude models use Anthropic SDK."""
from unittest.mock import MagicMock, patch


class TestIsClaudeModel:
    def test_claude_sonnet(self):
        from mothertree.llm import _is_claude
        assert _is_claude("claude-sonnet-4-6") is True

    def test_claude_haiku(self):
        from mothertree.llm import _is_claude
        assert _is_claude("claude-haiku-4-5-20251001") is True

    def test_claude_opus(self):
        from mothertree.llm import _is_claude
        assert _is_claude("claude-opus-4-6") is True

    def test_qwen(self):
        from mothertree.llm import _is_claude
        assert _is_claude("qwen3.5-397b-a17b") is False

    def test_mistral(self):
        from mothertree.llm import _is_claude
        assert _is_claude("mistral-small-3.2-24b-instruct-2506") is False


class TestSplitSystemMessages:
    def test_extracts_system(self):
        from mothertree.llm import _split_system_messages
        system, msgs = _split_system_messages([
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "hello"},
        ])
        assert system == "You are helpful"
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_no_system(self):
        from mothertree.llm import _split_system_messages
        system, msgs = _split_system_messages([
            {"role": "user", "content": "hello"},
        ])
        assert system == ""
        assert len(msgs) == 1

    def test_empty_messages(self):
        from mothertree.llm import _split_system_messages
        system, msgs = _split_system_messages([])
        assert system == ""
        assert len(msgs) == 1  # fallback hello


class TestGenerateRouting:
    @patch("mothertree.llm.anthropic_client")
    def test_routes_claude_to_anthropic(self, mock_client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello from Sonnet")]
        mock_client.messages.create.return_value = mock_response
        from mothertree.llm import generate
        result = generate("system", "user", model="claude-sonnet-4-6")
        assert result == "Hello from Sonnet"
        mock_client.messages.create.assert_called_once()

    @patch("mothertree.llm.scaleway")
    def test_routes_qwen_to_scaleway(self, mock_scaleway):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello from Qwen"))]
        mock_scaleway.chat.completions.create.return_value = mock_response
        from mothertree.llm import generate
        result = generate("system", "user", model="qwen3.5-397b-a17b")
        assert result == "Hello from Qwen"


class TestExtractRouting:
    @patch("mothertree.llm.anthropic_client")
    def test_routes_claude_to_anthropic(self, mock_client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"items": []}')]
        mock_client.messages.create.return_value = mock_response
        from mothertree.llm import extract
        result = extract("content", "instruction", model="claude-haiku-4-5-20251001")
        assert result == {"items": []}

    @patch("mothertree.llm.scaleway")
    def test_routes_mistral_to_scaleway(self, mock_scaleway):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"items": []}'))]
        mock_scaleway.chat.completions.create.return_value = mock_response
        from mothertree.llm import extract
        result = extract("content", "instruction", model="mistral-small-3.2-24b-instruct-2506")
        assert result == {"items": []}


class TestChatConversationRouting:
    @patch("mothertree.llm.anthropic_client")
    def test_routes_claude_to_anthropic(self, mock_client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Anthropic reply")]
        mock_client.messages.create.return_value = mock_response
        from mothertree.llm import chat_conversation
        result = chat_conversation(
            [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
            model="claude-sonnet-4-6",
        )
        assert result == "Anthropic reply"
