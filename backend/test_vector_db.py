from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from app.models.page_db import Page
from app.db.database import SessionLocal
from app.models.page_chunk import PageChunk


def main() -> None:
    model = SentenceTransformer("all-MiniLM-L6-v2")
    content = "Redis is an in-memory database."
    embedding = model.encode(content).tolist()
    db = SessionLocal()
    try:
        chunk = PageChunk(
            page_id=1,
            chunk_index=999,
            content=content,
            embedding=embedding,
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)
        print("Inserted ID:", chunk.id)
        print("Embedding dimensions:", len(chunk.embedding))
    finally:
        db.close()


if __name__ == "__main__":
    main()
