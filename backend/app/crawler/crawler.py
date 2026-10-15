import logging
from datetime import datetime
import hashlib
from collections import deque
from typing import Optional
from urllib.parse import urlparse
from sqlalchemy import func


logger = logging.getLogger(__name__)
from app.crawler.exceptions import RetryableCrawlError, CrawlCancelledError, ResourceLimitError, CrawlTimedOutError
from app.crawler.url_filter import is_crawlable_url
from app.crawler.link_extractor import extract_links, normalize_url
import app.crawler.fetcher as fetcher
from app.crawler.parser import parse_page
import asyncio
from app.core.config import MAX_CRAWL_DURATION_SECONDS, DOMAIN_MIN_DELAY_SECONDS
from app.core.time import now_utc_naive
from app.crawler.url_registry import URLRegistry
from app.crawler.robots import RobotsChecker
from app.domain.job_state import JobState

from app.ingestion.embedding import EmbeddingModel
from app.ingestion.ingest import ingest_page

from app.models.crawl_job import CrawlJob
from app.models.page import CrawledPage
from app.models.url import URLStatus
from app.models.url_db import URL

from app.repositories.page_repository import PageRepository


def update_crawl_progress(
    db,
    crawl_job: CrawlJob,
):
    # Aggregate in PostgreSQL instead of loading every historical URL into
    # Python on every page/discovery update.
    counts = dict(
        db.query(URL.status, func.count(URL.id))
        .filter(
            URL.company_id == crawl_job.company_id,
            URL.status != "deactivated",
        )
        .group_by(URL.status).all()
    )

    crawl_job.pages_discovered = sum(counts.values())
    crawl_job.pages_crawled = counts.get("crawled", 0) + counts.get("indexed", 0)
    crawl_job.pages_indexed = counts.get("indexed", 0)
    crawl_job.pages_failed = counts.get("failed", 0)

    now = now_utc_naive()
    if not crawl_job.last_heartbeat_at or (now - crawl_job.last_heartbeat_at).total_seconds() > 15:
        # Check if the job has been externally cancelled
        current_status = db.query(CrawlJob.status).filter(CrawlJob.id == crawl_job.id).scalar()
        if current_status == JobState.CANCELLED.value:
            raise CrawlCancelledError("Crawl job was cancelled by user")
            
        crawl_job.last_heartbeat_at = now

    db.commit()


async def crawl_site(
    start_url: str,
    db,
    company_id: int,
    max_pages: int = 5,
    max_depth: int = 1,
    crawl_job: Optional[CrawlJob] = None,
) -> tuple[list[CrawledPage], URLRegistry]:

    # -------------------------------------------------
    # NORMALIZE START URL
    # -------------------------------------------------

    normalized_start_url = normalize_url(
        start_url,
        start_url,
    )

    if not normalized_start_url:
        raise ValueError(
            f"Invalid start URL: {start_url}"
        )

    start_url = normalized_start_url

    # -------------------------------------------------
    # CRAWL QUEUE
    # -------------------------------------------------

    queue = deque([
        (start_url, 0)
    ])

    # URLs processed during THIS crawl only.
    visited_this_crawl = set()
    scheduled_urls = {start_url}
    partial_crawl = False

    # -------------------------------------------------
    # SERVICES
    # -------------------------------------------------

    registry = URLRegistry(
        db=db,
        company_id=company_id,
    )

    page_repository = PageRepository(db)

    # -------------------------------------------------
    # ROBOTS.TXT (cheap network check first — do not touch the
    # heavy embedding model until the start URL validates)
    # -------------------------------------------------

    robots = RobotsChecker(start_url)

    await robots.load()

    # Resolve the shared model only for pages that actually need ingestion.
    embedder = None

    # -------------------------------------------------
    # RESULTS
    # -------------------------------------------------

    pages = []

    start_domain = urlparse(
        start_url
    ).hostname

    # -------------------------------------------------
    # REGISTER START URL
    # -------------------------------------------------

    registry.add(
        start_url,
        status=URLStatus.QUEUED,
        depth=0,
    )

    registry.update_status(
        start_url,
        URLStatus.QUEUED,
    )

    if crawl_job:
        update_crawl_progress(
            db,
            crawl_job,
        )

    # -------------------------------------------------
    # MAIN CRAWL LOOP
    # -------------------------------------------------
    # Initialize per-domain throttle and overall duration tracking
    last_request_at: dict[str, datetime] = {}
    crawl_start_time = now_utc_naive()

    while queue and len(pages) < max_pages:

        current_url, current_depth = queue.popleft()

        # -------------------------------------------------
        # PREVENT DUPLICATES
        # -------------------------------------------------

        if current_url in visited_this_crawl:
            continue

        visited_this_crawl.add(
            current_url
        )

        # -------------------------------------------------
        # GET URL REGISTRY RECORD
        # -------------------------------------------------

        record = registry.get(
            current_url
        )

        if not record:
            continue

        # -------------------------------------------------
        # DOMAIN CHECK
        # -------------------------------------------------

        if urlparse(
            current_url
        ).hostname != start_domain:
            continue

        # -------------------------------------------------
        # DEPTH CHECK
        # -------------------------------------------------

        if current_depth > max_depth:
            partial_crawl = True
            continue

        # -------------------------------------------------
        # MAX CRAWL DURATION CHECK
        # -------------------------------------------------
        if (now_utc_naive() - crawl_start_time).total_seconds() > MAX_CRAWL_DURATION_SECONDS:
            raise CrawlTimedOutError("Crawl job exceeded maximum duration")

        # -------------------------------------------------
        # ROBOTS CHECK
        # -------------------------------------------------

        if not robots.can_fetch(current_url, user_agent="SiteAgent/1.0"):
            partial_crawl = True

            registry.update_status(
                current_url,
                URLStatus.SKIPPED,
            )

            if crawl_job:
                update_crawl_progress(
                    db,
                    crawl_job,
                )

            if current_url == start_url:
                raise ValueError("The starting URL disallows crawling in robots.txt")
            continue

        # Throttle actual requests, not URLs discarded by scope/depth/robots.
        host = urlparse(current_url).hostname
        now = now_utc_naive()
        last_at = last_request_at.get(host)
        if last_at:
            elapsed = (now - last_at).total_seconds()
            if elapsed < DOMAIN_MIN_DELAY_SECONDS:
                await asyncio.sleep(DOMAIN_MIN_DELAY_SECONDS - elapsed)
        last_request_at[host] = now_utc_naive()

        # -------------------------------------------------
        # MARK AS CRAWLING
        # -------------------------------------------------

        registry.update_status(
            current_url,
            URLStatus.CRAWLING,
        )

        # -------------------------------------------------
        # FETCH + PARSE + INGEST
        # -------------------------------------------------

        try:

            # -------------------------------------------------
            # FETCH
            # -------------------------------------------------

            html, http_status = await fetcher.fetch_page(
                current_url
            )

            # -------------------------------------------------
            # PARSE
            # -------------------------------------------------

            title, content = parse_page(
                html
            )

            # -------------------------------------------------
            # EXTRACT LINKS
            # -------------------------------------------------

            links = extract_links(
                html,
                current_url,
                depth=current_depth + 1,
            )

            # -------------------------------------------------
            # CONTENT HASH
            # -------------------------------------------------

            content_hash = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()

            # -------------------------------------------------
            # FIND URL DATABASE RECORD
            # -------------------------------------------------

            db_url = (
                db.query(URL)
                .filter(
                    URL.company_id == company_id,
                    URL.normalized_url == current_url,
                )
                .first()
            )

            if not db_url:
                raise ValueError(
                    f"URL record not found: {current_url}"
                )

            # -------------------------------------------------
            # CHECK EXISTING PAGE
            # -------------------------------------------------

            existing_page = (
                page_repository.get_by_url(
                    company_id=company_id,
                    url_id=db_url.id,
                )
            )

            # -------------------------------------------------
            # NEW PAGE
            # -------------------------------------------------

            if existing_page is None:
                try:
                    page = page_repository.create(
                        company_id=company_id,
                        url_id=db_url.id,
                        url=current_url,
                        title=title,
                        content=content,
                        http_status=http_status,
                        content_hash=content_hash,
                        commit=False,
                    )

                    if embedder is None:
                        embedder = EmbeddingModel()
                    ingest_page(
                        page.id,
                        db=db,
                        embedder=embedder,
                        commit=False,
                    )

                    db.commit()
                except Exception:
                    db.rollback()
                    raise

                print(
                    f"Created and ingested Page {page.id}"
                )
                if crawl_job:
                    crawl_job.pages_new += 1

            # -------------------------------------------------
            # EXISTING PAGE
            # -------------------------------------------------

            else:

                page = existing_page

                # -------------------------------------------------
                # CONTENT CHANGED
                # -------------------------------------------------

                if page.content_hash != content_hash:

                    try:
                        page_repository.update(
                            page=page,
                            title=title,
                            content=content,
                            http_status=http_status,
                            content_hash=content_hash,
                            commit=False,
                        )

                        if embedder is None:
                            embedder = EmbeddingModel()
                        ingest_page(
                            page.id,
                            db=db,
                            embedder=embedder,
                            replace_existing=True,
                            commit=False,
                        )

                        db.commit()
                    except Exception:
                        db.rollback()
                        raise

                    print(
                        f"Updated and re-ingested Page {page.id}"
                    )
                    if crawl_job:
                        crawl_job.pages_changed += 1

                # -------------------------------------------------
                # CONTENT UNCHANGED
                # -------------------------------------------------

                else:

                    print(
                        f"Page {page.id} unchanged, "
                        f"skipping ingestion"
                    )
                    if crawl_job:
                        crawl_job.pages_unchanged += 1

        # -------------------------------------------------
        # CRAWL ERROR
        # -------------------------------------------------

        except (CrawlTimedOutError, CrawlCancelledError):
            # Job lifecycle transitions belong to crawl_service.
            raise
        except (RetryableCrawlError, ResourceLimitError) as error:
            partial_crawl = True
            # A failure fetching the entry point invalidates the whole run.
            # For discovered pages, retain the error and continue the queue.
            if current_url == start_url:
                raise
            logger.warning("Crawl error %s -> %s", current_url, error)
            registry.update_status(current_url, URLStatus.FAILED, str(error))
            if crawl_job:
                update_crawl_progress(db, crawl_job)
            continue
        except Exception as error:
            partial_crawl = True

            logger.warning("Crawl error %s -> %s", current_url, error)

            error_http_status = None

            response = getattr(
                error,
                "response",
                None,
            )

            if response is not None:
                error_http_status = getattr(
                    response,
                    "status_code",
                    None,
                )

            registry.update_status(
                current_url,
                URLStatus.FAILED,
                str(error),
                http_status=error_http_status,
            )

            # Update job progress even when page fails.
            if crawl_job:
                update_crawl_progress(
                    db,
                    crawl_job,
                )

            if current_url == start_url:
                raise
            continue

        # -------------------------------------------------
        # SUCCESSFUL CRAWL RESULT
        # -------------------------------------------------

        page_result = CrawledPage(
            url=current_url,
            title=title,
            content=content,
            links=links,
            status="success",
        )

        pages.append(
            page_result
        )

        # -------------------------------------------------
        # UPDATE URL STATUS
        # -------------------------------------------------

        registry.update_status(
            current_url,
            URLStatus.CRAWLED,
            http_status=http_status,
        )

        registry.update_status(
            current_url,
            URLStatus.INDEXED,
            http_status=http_status,
        )

        # -------------------------------------------------
        # UPDATE PROGRESS
        # -------------------------------------------------

        if crawl_job:
            update_crawl_progress(
                db,
                crawl_job,
            )

        # -------------------------------------------------
        # DISCOVER NEW LINKS
        # -------------------------------------------------

        for link in links:
            if link in scheduled_urls:
                continue
            scheduled_urls.add(link)

            # -------------------------------------------------
            # FILE / URL FILTER
            # -------------------------------------------------

            if not is_crawlable_url(
                link
            ):
                continue

            # -------------------------------------------------
            # ROBOTS CHECK
            # -------------------------------------------------

            if not robots.can_fetch(
                link,
                user_agent="SiteAgent/1.0",
            ):
                partial_crawl = True

                registry.add(
                    link,
                    status=URLStatus.SKIPPED,
                    depth=current_depth + 1,
                    discovered_from=current_url,
                )

                continue

            # -------------------------------------------------
            # ALREADY VISITED
            # -------------------------------------------------

            if link in visited_this_crawl:
                continue

            next_depth = (
                current_depth + 1
            )

            # -------------------------------------------------
            # REGISTER URL
            # -------------------------------------------------

            registry.add(
                link,
                status=URLStatus.QUEUED,
                depth=next_depth,
                discovered_from=current_url,
            )

            # -------------------------------------------------
            # ADD TO QUEUE
            # -------------------------------------------------

            if next_depth <= max_depth:

                queue.append(
                    (
                        link,
                        next_depth,
                    )
                )
            else:
                partial_crawl = True

        # -------------------------------------------------
        # UPDATE PROGRESS AFTER DISCOVERY
        # -------------------------------------------------

        if crawl_job:
            update_crawl_progress(
                db,
                crawl_job,
            )

    # -------------------------------------------------
    # FINAL PROGRESS UPDATE
    # -------------------------------------------------

    if crawl_job:
        update_crawl_progress(
            db,
            crawl_job,
        )

    # Deactivate URLs not seen in this crawl (soft delete)
    # A limited or failed traversal cannot establish that an old page vanished.
    deactivated_count = (
        registry.deactivate_unseen(cutoff=crawl_start_time)
        if not queue and not partial_crawl else 0
    )
    if crawl_job:
        crawl_job.pages_deactivated += deactivated_count
        db.commit()

    return pages, registry
