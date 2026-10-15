import os
import logging
import atexit
import time
import random
from functools import lru_cache
from threading import Lock

import httpx

from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError, ClientError, ServerError
from google.genai import types

from app.rag.exceptions import LLMProviderError


load_dotenv()

logger = logging.getLogger(__name__)
_client_lock = Lock()


@lru_cache(maxsize=4)
def _get_client(api_key: str):
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=30000,
            # SDK retries can multiply a 30s timeout past the UI deadline.
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    atexit.register(client.close)
    return client


class GeminiGenerator:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise LLMProviderError("The language model provider is not configured.")

        with _client_lock:
            self.client = _get_client(api_key)

        self.model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    def generate(self, prompt: str) -> str:
        deadline = time.monotonic() + 30.0
        try:
            for attempt in range(3):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise httpx.TimeoutException("Provider request budget exhausted")
                try:
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            max_output_tokens=1024,
                            http_options=types.HttpOptions(
                                timeout=max(1, int(remaining * 1000)),
                                retry_options=types.HttpRetryOptions(attempts=1),
                            ),
                        ),
                    )
                    break
                except APIError as error:
                    # Retry only transient server failures, never invalid
                    # models, authentication errors, or quota exhaustion.
                    delay = 0.5 * (2 ** attempt) + random.uniform(0, 0.25)
                    if error.code not in (503, 504) or attempt == 2 or deadline - time.monotonic() <= delay + 1:
                        raise
                    logger.info("Retrying Gemini transient failure status_code=%s attempt=%s", error.code, attempt + 2)
                    time.sleep(delay)
        except (APIError, ClientError, ServerError, httpx.HTTPError) as error:
            status_code = getattr(error, "code", None)
            if status_code is None:
                status_code = getattr(error, "status_code", None)

            logger.warning(
                "Gemini provider failure type=%s status_code=%s",
                type(error).__name__,
                status_code,
            )
            raise LLMProviderError(
                "The language model provider is temporarily unavailable.",
                provider_status_code=status_code,
            ) from error

        # The SDK accessor logs a warning for non-text metadata. Read it once.
        answer = response.text
        if not answer or not answer.strip():
            raise LLMProviderError("Empty response from language model provider.")
        return answer.strip()
