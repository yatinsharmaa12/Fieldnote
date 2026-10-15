import logging
from datetime import datetime

from app.crawler.crawler import crawl_site


logger = logging.getLogger(__name__)
from app.crawler.exceptions import RetryableCrawlError, CrawlCancelledError, ResourceLimitError, CrawlTimedOutError
from app.db.database import SessionLocal
from app.domain.job_state import JobState, transition_job_state
from app.models.crawl_job import CrawlJob
from app.repositories.company_repository import get_company


async def run_crawl_job(
    job_id: int,
    company_id: int,
):
    db = SessionLocal()

    try:
        job = (
            db.query(CrawlJob)
            .filter(
                CrawlJob.id == job_id,
                CrawlJob.company_id == company_id,
            )
            .first()
        )

        if not job:
            return

        company = get_company(
            db=db,
            company_id=company_id,
        )

        if not company:
            transition_job_state(job, JobState.FAILED, "Company not found")
            db.commit()
            return
            
        if job.status == JobState.CANCELLED.value:
            # Job was cancelled while sitting in the queue
            return

        # If the job was previously completed, reset it to QUEUED before starting.
        if job.status == JobState.COMPLETED.value:
            transition_job_state(job, JobState.QUEUED)
        transition_job_state(job, JobState.RUNNING)

        job.pages_discovered = 0
        job.pages_crawled = 0
        job.pages_indexed = 0
        job.pages_failed = 0
        job.pages_new = 0
        job.pages_changed = 0
        job.pages_unchanged = 0
        job.pages_deactivated = 0

        db.commit()

        try:
            pages, _ = await crawl_site(
                company.website_url,
                db=db,
                company_id=company.id,
                max_pages=job.max_pages,
                max_depth=job.max_depth,
                crawl_job=job,
            )

            job.pages_crawled = len(pages)

            db.refresh(job, attribute_names=["status"])
            if job.status == JobState.CANCELLED.value:
                return
            transition_job_state(job, JobState.COMPLETED)

            db.commit()

        except CrawlCancelledError as error:
            # Refresh to ensure we have the latest status (which should be CANCELLED)
            db.refresh(job)
            if job.status != JobState.CANCELLED.value:
                transition_job_state(job, JobState.CANCELLED, str(error))
                db.commit()
            return

        except CrawlTimedOutError as error:
            db.refresh(job)
            if job.status != JobState.CANCELLED.value:
                transition_job_state(job, JobState.TIMED_OUT, str(error))
                db.commit()
            return

        except RetryableCrawlError as error:
            db.rollback()
            db.refresh(job)
            if job.status == JobState.CANCELLED.value:
                return
            logger.warning("Crawl job %s retryable failure: %s", job.id, error)
            transition_job_state(job, JobState.QUEUED, str(error))
            db.commit()
            raise

        except Exception as error:
            logger.exception("Crawl job %s failed", job.id)
            db.rollback()
            db.refresh(job)
            if job.status != JobState.CANCELLED.value:
                transition_job_state(job, JobState.FAILED, str(error))
                db.commit()
            
    finally:
        db.close()


def cancel_crawl_job(db, job_id: int, company_id: int) -> bool:
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id, CrawlJob.company_id == company_id).first()
    if not job:
        return False
        
    if job.status in {JobState.QUEUED.value, JobState.RUNNING.value}:
        transition_job_state(job, JobState.CANCELLED, "Cancelled by user")
        db.commit()
        return True
        
    # Cannot cancel if already COMPLETED, FAILED, or CANCELLED
    return False
