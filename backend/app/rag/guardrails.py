import re
from hashlib import sha256
from typing import Iterable


NOT_FOUND_RESPONSE = "The website does not provide enough information to answer that."
IRRELEVANT_RESPONSE = "I can only answer questions related to this company's website."

_INJECTION_PATTERNS = (
    re.compile(r"\b(ignore|disregard|forget|override)\b.{0,80}\b(previous|prior|system|developer|instructions?)\b", re.I | re.S),
    re.compile(r"\b(reveal|show|print|repeat|disclose|tell me|what is)\b.{0,80}\b(system prompt|developer message|hidden instructions?)\b", re.I | re.S),
    re.compile(r"\b(reveal|show|give|provide|dump|list|tell me|what is)\b.{0,80}\b(api key|access token|bearer token|password|secret|credential)s?\b", re.I | re.S),
    re.compile(r"\b(bypass|disable|ignore)\b.{0,80}\b(grounding|website|safety|guardrails?)\b", re.I | re.S),
    re.compile(r"\b(you are now|act as|pretend to be|change your role)\b", re.I),
    re.compile(r"\b(follow|execute|obey)\b.{0,80}\b(instructions?|commands?)\b.{0,80}\b(retrieved|website|context|document)\b", re.I | re.S),
)

_OUTPUT_SECRET_PATTERNS = (
    re.compile(r"\b(api[_ -]?key|access[_ -]?token|bearer\s+token|password|secret|private key|credential)s?\b", re.I),
    re.compile(r"\b(system prompt|developer message|hidden instructions?)\b", re.I),
    re.compile(r"\b(ignore|disregard)\b.{0,80}\b(previous|prior|system|developer|instructions?)\b", re.I | re.S),
)

_WORD_PATTERN = re.compile(r"[a-z0-9]{3,}")


def contains_prompt_injection(question: str) -> bool:
    """Detect common attempts to change the assistant's instruction hierarchy."""
    cleaned = " ".join((question or "").split())
    return any(pattern.search(cleaned) for pattern in _INJECTION_PATTERNS)


def safe_log_id(value: str) -> str:
    """Return a non-reversible identifier suitable for security logs."""
    return sha256((value or "").encode("utf-8")).hexdigest()[:12]


def _tokens(value: str) -> set[str]:
    return set(_WORD_PATTERN.findall((value or "").lower()))


def _has_supported_claims(answer: str, evidence: str) -> bool:
    answer_tokens = _tokens(answer)
    evidence_tokens = _tokens(evidence)
    if not answer_tokens or not evidence_tokens:
        return False

    overlap = answer_tokens & evidence_tokens
    if not overlap:
        return False

    answer_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", answer))
    evidence_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", evidence))
    return answer_numbers <= evidence_numbers


def validate_answer(answer: str, question: str, evidence: Iterable[str]) -> bool:
    """Validate a generated answer without sending another prompt to an LLM."""
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 12000:
        return False
    if any(pattern.search(answer) for pattern in _OUTPUT_SECRET_PATTERNS):
        return False

    evidence_text = "\n".join(item for item in evidence if item)
    if not evidence_text:
        return False
    return _has_supported_claims(answer, evidence_text)
