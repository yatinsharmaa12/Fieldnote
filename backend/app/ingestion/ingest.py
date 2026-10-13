from sqlalchemy.orm import Session

from app.ingestion.cleaner import clean_text
from app.ingestion.chunker import chunk_text
from app.ingestion.embedding import EmbeddingModel
from app.models.page_db import Page
from app.models.page_chunk import PageChunk


MAX_CONTENT_CHARS = 50000
MAX_CHUNKS_PER_PAGE = 100


def ingest_page(
    page_id: int,
    db: Session,
    embedder: EmbeddingModel,
    replace_existing: bool = False,
    commit: bool = True,
):
    try:
        page = (
            db.query(Page)
            .filter(Page.id == page_id)
            .first()
        )

        if page is None:
            raise ValueError(
                f"Page {page_id} not found"
            )

        existing_chunks = (
            db.query(PageChunk)
            .filter(PageChunk.page_id == page.id)
            .count()
        )

        if existing_chunks > 0:

            if not replace_existing:
                print(
                    f"Page {page.id} already ingested"
                )
                return

            db.query(PageChunk).filter(
                PageChunk.page_id == page.id
            ).delete(
                synchronize_session=False
            )

            print(
                f"Removed {existing_chunks} old chunks "
                f"from Page {page.id}"
            )

        cleaned = clean_text(page.content)

        # Bound per-page work: a 5MB hostile page must not become
        # thousands of chunks/embeddings/DB rows (worker 30m timeout x3).
        if len(cleaned) > MAX_CONTENT_CHARS:
            cleaned = cleaned[:MAX_CONTENT_CHARS]

        chunks = chunk_text(
            cleaned,
            chunk_size=200,
            overlap_tokens=30,
        )

        if not chunks:
            print(
                f"Page {page.id} contains no chunks"
            )
            return

        if len(chunks) > MAX_CHUNKS_PER_PAGE:
            chunks = chunks[:MAX_CHUNKS_PER_PAGE]

        embeddings = embedder.embed_many(chunks)

        for index, (chunk, embedding) in enumerate(
            zip(chunks, embeddings)
        ):
            page_chunk = PageChunk(
                page_id=page.id,
                chunk_index=index,
                content=chunk,
                embedding=embedding,
            )

            db.add(page_chunk)

        if commit:
            db.commit()
        else:
            db.flush()

        print(
            f"Ingested Page {page.id}: "
            f"{len(chunks)} chunks"
        )
    except Exception:
        db.rollback()
        raise
