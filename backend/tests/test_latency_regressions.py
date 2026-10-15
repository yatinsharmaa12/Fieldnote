from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import httpx
import pytest
from google.genai.errors import ClientError

from app.ingestion.embedding import EmbeddingModel, _embed_query
from app.rag.exceptions import LLMProviderError
from app.rag.generator import GeminiGenerator, _get_client


def test_repeated_queries_reuse_vectors_without_sharing_mutable_lists():
    _embed_query.cache_clear()
    model = MagicMock()
    model.encode.return_value.tolist.return_value = [0.1, 0.2]
    with patch("app.ingestion.embedding._get_shared_model", return_value=model):
        embedder = EmbeddingModel()
        with ThreadPoolExecutor(max_workers=4) as executor:
            vectors = list(executor.map(embedder.embed, ["same question"] * 8))
        vectors[0][0] = 99
        assert embedder.embed(" same question ") == [0.1, 0.2]
    model.encode.assert_called_once_with("same question")
    _embed_query.cache_clear()


def test_provider_reuses_connections_and_does_not_multiply_timeouts(monkeypatch):
    _get_client.cache_clear()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with patch("app.rag.generator.genai.Client") as factory, patch("app.rag.generator.atexit.register"):
        assert GeminiGenerator().client is GeminiGenerator().client
        factory.assert_called_once()
        options = factory.call_args.kwargs["http_options"]
        assert options.timeout == 30000
        assert options.retry_options.attempts == 1
    _get_client.cache_clear()


@pytest.mark.parametrize("error", [
    httpx.ReadTimeout("private upstream detail"),
    ClientError(429, {"error": {"message": "quota secret"}}),
])
def test_provider_network_and_quota_failures_are_safe(error):
    generator = GeminiGenerator.__new__(GeminiGenerator)
    generator.client = MagicMock()
    generator.model = "test"
    generator.client.models.generate_content.side_effect = error
    with pytest.raises(LLMProviderError, match="temporarily unavailable"):
        generator.generate("prompt")


@pytest.mark.parametrize("text", [None, "", "   "])
def test_blank_provider_responses_fail_safely(text):
    generator = GeminiGenerator.__new__(GeminiGenerator)
    generator.client = MagicMock()
    generator.model = "test"
    generator.client.models.generate_content.return_value.text = text
    with pytest.raises(LLMProviderError, match="Empty response"):
        generator.generate("prompt")
