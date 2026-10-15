from threading import Lock
from functools import lru_cache

from sentence_transformers import SentenceTransformer


MODEL_NAME = "all-MiniLM-L6-v2"

_shared_model = None
_shared_lock = Lock()
_query_lock = Lock()


@lru_cache(maxsize=256)
def _embed_query(text: str) -> tuple[float, ...]:
    # Cache only query vectors, never answers or retrieved company content.
    return tuple(_get_shared_model().encode(text).tolist())


def _get_shared_model():
    global _shared_model
    if _shared_model is None:
        with _shared_lock:
            if _shared_model is None:
                _shared_model = SentenceTransformer(MODEL_NAME)
    return _shared_model


class EmbeddingModel:
    @property
    def model(self):
        # Resolve only when content actually needs embedding.
        return _get_shared_model()

    def embed(self, text: str) -> list[float]:
        # Coalesce simultaneous identical queries and bound memory use.
        with _query_lock:
            return list(_embed_query(text.strip()))

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts).tolist()
