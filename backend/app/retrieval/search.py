from app.db.database import SessionLocal
from app.ingestion.embedding import EmbeddingModel
from app.models.page_chunk import PageChunk
from app.models.page_db import Page
from app.models.url_db import URL


DEFAULT_MAX_DISTANCE = 0.90


MAX_QUERY_CHARS = 2000


def search_chunks(
    query: str,
    company_id: int,
    limit: int = 5,
    max_distance: float = DEFAULT_MAX_DISTANCE,
):
    # Cheap rejection before touching the embedding model / DB.
    cleaned = (query or "").strip()
    if not cleaned:
        raise ValueError("Query must not be empty")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"Query must be at most {MAX_QUERY_CHARS} characters")

    embedder = EmbeddingModel()
    query_embedding = embedder.embed(query)

    db = SessionLocal()

    try:
        distance = PageChunk.embedding.cosine_distance(
            query_embedding
        )

        results = (
            db.query(
                PageChunk,
                Page.url,
                Page.title,
                distance.label("distance"),
            )
            .join(
                Page,
                Page.id == PageChunk.page_id,
            )
            .join(URL, URL.id == Page.url_id)
            .filter(
                Page.company_id == company_id,
            )
            .filter(URL.is_active.is_(True))
            .filter(
                distance <= max_distance,
            )
            .order_by(
                distance
            )
            .limit(limit)
            .all()
        )

        return results

    finally:
        db.close()
