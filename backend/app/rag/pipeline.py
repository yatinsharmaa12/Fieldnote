import logging

from app.rag.generator import GeminiGenerator
from app.rag.guardrails import (
    IRRELEVANT_RESPONSE,
    NOT_FOUND_RESPONSE,
    contains_prompt_injection,
    safe_log_id,
    validate_answer,
)
from app.rag.prompt import build_prompt
from app.retrieval.context import build_context
from app.retrieval.search import search_chunks


MAX_QUESTION_CHARS = 2000
logger = logging.getLogger(__name__)


def answer_question(
    question: str,
    company_id: int,
) -> dict:
    cleaned = (question or "").strip()
    if not cleaned:
        raise ValueError("Question must not be empty")
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError(f"Question must be at most {MAX_QUESTION_CHARS} characters")

    if contains_prompt_injection(cleaned):
        logger.info("chat_guardrail_rejected question_id=%s reason=prompt_injection", safe_log_id(cleaned))
        return {
            "answer": IRRELEVANT_RESPONSE,
            "sources": [],
        }

    results = search_chunks(
        question,
        company_id=company_id,
    )

    if not results:
        return {
            "answer": NOT_FOUND_RESPONSE,
            "sources": [],
        }

    context = build_context(results)
    prompt = build_prompt(question, context)

    generator = GeminiGenerator()
    answer = generator.generate(prompt)

    if not validate_answer(
        answer=answer,
        question=cleaned,
        evidence=(chunk.content for chunk, _url, _title, _distance in results),
    ):
        logger.warning(
            "chat_guardrail_fallback question_id=%s company_id=%s reason=output_validation",
            safe_log_id(cleaned),
            company_id,
        )
        answer = NOT_FOUND_RESPONSE

    sources = []
    seen_urls = set()

    for chunk, url, title, distance in results:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append({"title": title, "url": url})

    return {
        "answer": answer,
        "sources": sources,
    }
