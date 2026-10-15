import asyncio
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from app.models.company import Company
from app.models.crawl_job import CrawlJob
from app.models.page_chunk import PageChunk
from app.models.page import Page
from app.models.user import User
from app.services.crawl_service import run_crawl_job
from app.models.url import URLStatus
from app.models.url_db import URL


@pytest.fixture(autouse=True)
def local_robots(monkeypatch):
    async def load(checker):
        checker.parser.parse([])
        checker.loaded = True
    monkeypatch.setattr("app.crawler.robots.RobotsChecker.load", load)

# Helper to get URL record from DB
def get_url_record(db, company_id, url):
    return (
        db.query(URL)
        .filter(URL.company_id == company_id, URL.normalized_url == url)
        .first()
    )

@pytest.mark.anyio
async def test_incremental_crawl_unchanged_content(db, test_session_local):
    # Setup user, company, and crawl job
    user = User(email="inc-test@example.com", password_hash="unused")
    db.add(user)
    db.commit()
    db.refresh(user)

    company = Company(name="Inc Test Co", website_url="https://example.com", owner_id=user.id)
    db.add(company)
    db.commit()
    db.refresh(company)

    job = CrawlJob(
        company_id=company.id,
        status="QUEUED",
        max_pages=5,
        max_depth=1,
        pages_crawled=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    async def mock_fetch_page(url):
        return "<html><body>content v1</body></html>", 200

    with patch(
        "app.services.crawl_service.SessionLocal", test_session_local
    ), patch(
        "app.services.crawl_service.get_company", return_value=company
    ), patch(
        "app.crawler.fetcher.fetch_page", new_callable=AsyncMock, side_effect=mock_fetch_page
    ):
        await run_crawl_job(job_id=job.id, company_id=company.id)

    db.expire_all()
    completed_job = db.query(CrawlJob).filter(CrawlJob.id == job.id).first()
    assert completed_job.pages_new == 1
    assert completed_job.pages_changed == 0
    assert completed_job.pages_unchanged == 0
    page = db.query(Page).filter(Page.company_id == company.id).first()
    assert page is not None
    assert page.content == "content v1"
    url_rec = get_url_record(db, company.id, "https://example.com")
    assert url_rec.status == URLStatus.INDEXED.value
    assert url_rec.last_seen_at is not None
    first_seen = url_rec.last_seen_at

    async def mock_fetch_same(url):
        return "<html><body>content v1</body></html>", 200

    with patch(
        "app.services.crawl_service.SessionLocal", test_session_local
    ), patch(
        "app.services.crawl_service.get_company", return_value=company
    ), patch(
        "app.crawler.fetcher.fetch_page", new_callable=AsyncMock, side_effect=mock_fetch_same
    ):
        await run_crawl_job(job_id=job.id, company_id=company.id)

    db.expire_all()
    completed_job = db.query(CrawlJob).filter(CrawlJob.id == job.id).first()
    assert completed_job.pages_new == 0
    assert completed_job.pages_changed == 0
    assert completed_job.pages_unchanged == 1
    page_count = db.query(Page).filter(Page.company_id == company.id).count()
    assert page_count == 1
    url_rec2 = get_url_record(db, company.id, "https://example.com")
    assert url_rec2.last_seen_at > first_seen
    assert url_rec2.status == URLStatus.INDEXED.value
    assert url_rec2.crawl_count == 2

    async def mock_fetch_changed(url):
        return "<html><body>content v2</body></html>", 200

    with patch(
        "app.services.crawl_service.SessionLocal", test_session_local
    ), patch(
        "app.services.crawl_service.get_company", return_value=company
    ), patch(
        "app.crawler.fetcher.fetch_page", new_callable=AsyncMock, side_effect=mock_fetch_changed
    ):
        await run_crawl_job(job_id=job.id, company_id=company.id)

    db.expire_all()
    completed_job = db.query(CrawlJob).filter(CrawlJob.id == job.id).first()
    assert completed_job.pages_new == 0
    assert completed_job.pages_changed == 1
    assert completed_job.pages_unchanged == 0

@pytest.mark.anyio
async def test_depth_limited_crawl_preserves_discovered_urls(db, test_session_local, monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.crawler.crawler.asyncio.sleep", sleep)
    # Setup user, company, and crawl job with depth 0 so a discovered link is not visited
    user = User(email="deact-test@example.com", password_hash="unused")
    db.add(user)
    db.commit()
    db.refresh(user)

    company = Company(name="Deact Co", website_url="https://example.com", owner_id=user.id)
    db.add(company)
    db.commit()
    db.refresh(company)

    job = CrawlJob(
        company_id=company.id,
        status="QUEUED",
        max_pages=5,
        max_depth=0,
        pages_crawled=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    async def mock_fetch(url):
        return "<html><body>root</body></html>", 200

    with patch(
        "app.services.crawl_service.SessionLocal", test_session_local
    ), patch(
        "app.services.crawl_service.get_company", return_value=company
    ), patch(
        "app.crawler.fetcher.fetch_page", new_callable=AsyncMock, side_effect=mock_fetch
    ), patch(
        "app.crawler.crawler.extract_links", return_value=["https://example.com/unused"]
    ):
        await run_crawl_job(job_id=job.id, company_id=company.id)

    db.expire_all()
    unused_url = get_url_record(db, company.id, "https://example.com/unused")
    assert unused_url is not None
    assert unused_url.status == URLStatus.QUEUED.value
    assert unused_url.is_active is True
    assert unused_url.last_seen_at is not None
    completed_job = db.query(CrawlJob).filter(CrawlJob.id == job.id).first()
    assert completed_job.pages_deactivated == 0
    sleep.assert_not_awaited()


@pytest.mark.anyio
async def test_failed_changed_page_reingest_rolls_back_previous_chunks(db, test_session_local):
    unique_suffix = uuid4().hex
    user = User(email=f"rollback-test-{unique_suffix}@example.com", password_hash="unused")
    db.add(user)
    db.commit()
    db.refresh(user)

    company = Company(name=f"Rollback Co {unique_suffix}", website_url="https://example.com", owner_id=user.id)
    db.add(company)
    db.commit()
    db.refresh(company)

    job = CrawlJob(
        company_id=company.id,
        status="QUEUED",
        max_pages=5,
        max_depth=1,
        pages_crawled=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    class FakeRobotsChecker:
        def __init__(self, *_args, **_kwargs):
            self.loaded = False

        async def load(self):
            self.loaded = True

        def can_fetch(self, _url, user_agent="*"):
            return True

    class FakeEmbedder:
        def __init__(self):
            self.calls = 0

        def embed_many(self, chunks):
            self.calls += 1
            if self.calls == 1:
                return [[0.1] * 384 for _ in chunks]
            raise RuntimeError("embedding failed")

    fake_embedder = FakeEmbedder()

    async def fetch_v1(url):
        return "<html><body>content v1</body></html>", 200

    async def fetch_v2(url):
        return "<html><body>content v2 changed</body></html>", 200

    with patch("app.services.crawl_service.SessionLocal", test_session_local), patch(
        "app.services.crawl_service.get_company", return_value=company
    ), patch(
        "app.crawler.crawler.RobotsChecker", return_value=FakeRobotsChecker()
    ), patch(
        "app.crawler.crawler.EmbeddingModel", return_value=fake_embedder
    ), patch(
        "app.crawler.fetcher.fetch_page", new_callable=AsyncMock, side_effect=fetch_v1
    ), patch(
        "app.crawler.crawler.extract_links", return_value=[]
    ):
        await run_crawl_job(job_id=job.id, company_id=company.id)

    db.expire_all()
    page = db.query(Page).filter(Page.company_id == company.id).first()
    assert page is not None
    assert page.content == "content v1"
    assert db.query(PageChunk).filter(PageChunk.page_id == page.id).count() == 1
    failed_job = db.query(CrawlJob).filter(CrawlJob.id == job.id).first()
    assert failed_job.pages_changed == 0

    with patch("app.services.crawl_service.SessionLocal", test_session_local), patch(
        "app.services.crawl_service.get_company", return_value=company
    ), patch(
        "app.crawler.crawler.RobotsChecker", return_value=FakeRobotsChecker()
    ), patch(
        "app.crawler.crawler.EmbeddingModel", return_value=fake_embedder
    ), patch(
        "app.crawler.fetcher.fetch_page", new_callable=AsyncMock, side_effect=fetch_v2
    ), patch(
        "app.crawler.crawler.extract_links", return_value=[]
    ):
        await run_crawl_job(job_id=job.id, company_id=company.id)

    db.expire_all()
    page = db.query(Page).filter(Page.company_id == company.id).first()
    assert page.content == "content v1"
    assert db.query(PageChunk).filter(PageChunk.page_id == page.id).count() == 1
    failed_job = db.query(CrawlJob).filter(CrawlJob.id == job.id).first()
    assert failed_job.pages_changed == 0


@pytest.mark.anyio
async def test_failed_fetch_does_not_increment_successful_statistics(db, test_session_local):
    unique_suffix = uuid4().hex
    user = User(email=f"fetch-test-{unique_suffix}@example.com", password_hash="unused")
    db.add(user)
    db.commit()
    db.refresh(user)

    company = Company(name=f"Fetch Co {unique_suffix}", website_url="https://example.com", owner_id=user.id)
    db.add(company)
    db.commit()
    db.refresh(company)

    job = CrawlJob(company_id=company.id, status="QUEUED", max_pages=1, max_depth=0)
    db.add(job)
    db.commit()
    db.refresh(job)

    async def fetch_failure(_url):
        raise RuntimeError("fetch failed")

    with patch("app.services.crawl_service.SessionLocal", test_session_local), patch(
        "app.services.crawl_service.get_company", return_value=company
    ), patch(
        "app.crawler.fetcher.fetch_page", new_callable=AsyncMock, side_effect=fetch_failure
    ):
        await run_crawl_job(job_id=job.id, company_id=company.id)

    db.expire_all()
    failed_job = db.query(CrawlJob).filter(CrawlJob.id == job.id).first()
    assert failed_job.pages_new == 0
    assert failed_job.pages_changed == 0
    assert failed_job.pages_unchanged == 0
    assert failed_job.status == "FAILED"
