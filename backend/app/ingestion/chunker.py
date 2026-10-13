import re
import tiktoken


try:
    encoding = tiktoken.get_encoding("cl100k_base")
except Exception:
    # tiktoken downloads this encoding the first time it is used.  Crawls
    # should remain available in offline workers; whitespace is a conservative
    # fallback for the small (200-token) ingestion chunks.
    encoding = None


def token_count(text: str) -> int:
    if encoding is None:
        return len(text.split())
    return len(encoding.encode(text))


def split_long_sentence(
    sentence: str,
    chunk_size: int,
) -> list[str]:

    words = sentence.split()

    # Fast path for pathological input (e.g. minified blob with no
    # sentence breaks): per-word token_count() is O(n^2) encodes and
    # burns CPU. Fixed windows keep it O(n) with no data loss.
    if len(words) > 800:
        parts = [
            " ".join(words[i : i + 300]) for i in range(0, len(words), 300)
        ]
        fixed: list[str] = []
        for part in parts:
            if token_count(part) <= chunk_size:
                fixed.append(part)
            else:
                fixed.extend(split_long_sentence(part, chunk_size))
        return fixed

    parts = []
    current_words = []

    for word in words:
        candidate = " ".join(current_words + [word])

        if token_count(candidate) <= chunk_size:
            current_words.append(word)
        else:
            if current_words:
                parts.append(" ".join(current_words))

            current_words = [word]

    if current_words:
        parts.append(" ".join(current_words))

    return parts


def chunk_text(
    text: str,
    chunk_size: int = 400,
    overlap_tokens: int = 50,
) -> list[str]:

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    sections = []
    current_section = []

    for line in lines:
        if line.startswith("#"):
            if current_section:
                sections.append("\n".join(current_section))

            current_section = [line]

        else:
            current_section.append(line)

    if current_section:
        sections.append("\n".join(current_section))

    chunks = []

    def trailing_overlap(sentences: list[str]) -> list[str]:
        """Keep complete trailing sentences up to the overlap token budget."""
        if overlap_tokens <= 0:
            return []
        overlap: list[str] = []
        used_tokens = 0
        for sentence in reversed(sentences):
            sentence_tokens = token_count(sentence)
            if overlap and used_tokens + sentence_tokens > overlap_tokens:
                break
            if not overlap and sentence_tokens > overlap_tokens:
                overlap.append(sentence)
                break
            overlap.append(sentence)
            used_tokens += sentence_tokens
        return list(reversed(overlap))

    for section in sections:
        sentences = []

        for paragraph in section.splitlines():
            parts = re.split(
                r"(?<=[.!?])\s+",
                paragraph,
            )

            for sentence in parts:
                sentence = sentence.strip()

                if not sentence:
                    continue

                if token_count(sentence) <= chunk_size:
                    sentences.append(sentence)
                else:
                    sentences.extend(
                        split_long_sentence(
                            sentence,
                            chunk_size,
                        )
                    )

        current_sentences = []

        for sentence in sentences:
            candidate = " ".join(
                current_sentences + [sentence]
            )

            if token_count(candidate) <= chunk_size:
                current_sentences.append(sentence)

            else:
                if current_sentences:
                    chunks.append(
                        " ".join(current_sentences)
                    )

                current_sentences = trailing_overlap(current_sentences)
                if token_count(" ".join(current_sentences + [sentence])) > chunk_size:
                    current_sentences = []
                current_sentences.append(sentence)

        if current_sentences:
            chunks.append(
                " ".join(current_sentences)
            )

    return chunks
