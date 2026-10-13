from sqlalchemy import text

from app.db.database import Base, engine
from app.models.page_chunk import PageChunk
from app.models.company import Company
from app.models.url_db import URL
from app.models.page_db import Page
from app.models.user import User
from app.models.crawl_job import CrawlJob

def init_db():
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database tables created successfully.")
