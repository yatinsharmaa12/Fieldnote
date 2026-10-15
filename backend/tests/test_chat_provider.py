from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi import HTTPException

from app.api.chat import chat
from app.models.user import User
from app.rag.exceptions import LLMProviderError
from app.rag.generator import GeminiGenerator
from google.genai.errors import ServerError


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr("app.rag.generator.time.sleep", lambda _delay: None)


def test_transient_failure_recovers_and_reads_text_once():
    generator = GeminiGenerator.__new__(GeminiGenerator)
    generator.client = MagicMock()
    generator.model = "test-model"
    response = MagicMock()
    accessor = PropertyMock(return_value=" Answer. ")
    type(response).text = accessor
    generator.client.models.generate_content.side_effect = [
        ServerError(503, {"error": {"message": "overloaded"}}), response,
    ]
    assert generator.generate("prompt") == "Answer."
    assert generator.client.models.generate_content.call_count == 2
    accessor.assert_called_once()


def test_retries_share_remaining_timeout_budget(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("app.rag.generator.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.rag.generator.random.uniform", lambda *_args: 0)
    monkeypatch.setattr("app.rag.generator.time.sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    generator = GeminiGenerator.__new__(GeminiGenerator)
    generator.client = MagicMock()
    generator.model = "test-model"
    def fail(**kwargs):
        clock[0] += 10
        raise ServerError(503, {"error": {"message": "overloaded"}})
    generator.client.models.generate_content.side_effect = fail
    with pytest.raises(LLMProviderError):
        generator.generate("prompt")
    timeouts = [call.kwargs["config"].http_options.timeout for call in generator.client.models.generate_content.call_args_list]
    assert timeouts == [30000, 19500, 8500]


def test_no_retry_when_first_attempt_consumes_budget(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("app.rag.generator.time.monotonic", lambda: clock[0])
    generator = GeminiGenerator.__new__(GeminiGenerator)
    generator.client = MagicMock()
    generator.model = "test-model"
    def fail(**kwargs):
        clock[0] = 30.0
        raise ServerError(503, {"error": {"message": "overloaded"}})
    generator.client.models.generate_content.side_effect = fail
    with pytest.raises(LLMProviderError):
        generator.generate("prompt")
    generator.client.models.generate_content.assert_called_once()


def test_generator_returns_successful_answer_unchanged():
    generator = GeminiGenerator.__new__(GeminiGenerator)
    generator.client = MagicMock()
    generator.model = "test-model"
    generator.client.models.generate_content.return_value.text = "A normal answer."

    assert generator.generate("prompt") == "A normal answer."


@pytest.mark.parametrize("status_code", [503, 504])
def test_generator_translates_transient_gemini_server_errors(status_code):
    generator = GeminiGenerator.__new__(GeminiGenerator)
    generator.client = MagicMock()
    generator.model = "test-model"
    generator.client.models.generate_content.side_effect = ServerError(
        status_code,
        {"error": {"status": "DEADLINE_EXCEEDED", "message": "upstream timeout"}},
    )

    with pytest.raises(LLMProviderError) as error:
        generator.generate("prompt")

    assert error.value.provider_status_code == status_code
    assert generator.client.models.generate_content.call_count == 3
    assert "upstream timeout" not in str(error.value)


def test_chat_translates_provider_failure_to_safe_502():
    db = MagicMock()
    company = MagicMock(id=16)
    db.query.return_value.filter.return_value.first.return_value = company
    user = User(id=4, email="user@example.com", password_hash="unused")

    with patch(
        "app.api.chat.answer_question",
        side_effect=LLMProviderError("provider unavailable", provider_status_code=504),
    ):
        with pytest.raises(HTTPException) as error:
            chat(
                request=MagicMock(company_id=16, question="What is FastAPI?"),
                current_user=user,
                db=db,
            )

    assert error.value.status_code == 502
    assert error.value.detail == "The language model provider is temporarily unavailable. Please try again."
    assert "google" not in error.value.detail.lower()


def test_chat_keeps_retrieval_failures_distinct():
    db = MagicMock()
    company = MagicMock(id=16)
    db.query.return_value.filter.return_value.first.return_value = company
    user = User(id=4, email="user@example.com", password_hash="unused")

    with patch("app.api.chat.answer_question", side_effect=RuntimeError("database unavailable")):
        with pytest.raises(RuntimeError, match="database unavailable"):
            chat(
                request=MagicMock(company_id=16, question="What is FastAPI?"),
                current_user=user,
                db=db,
            )
