import os
import logging

from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError, ClientError, ServerError
from google.genai import types

from app.rag.exceptions import LLMProviderError


load_dotenv()

logger = logging.getLogger(__name__)


class GeminiGenerator:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set"
            )

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=30000,
            ),
        )

        self.model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    def generate(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
        except (APIError, ClientError, ServerError) as error:
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

        if response.text is None:
            raise LLMProviderError("Empty response from language model provider.")
        return response.text
