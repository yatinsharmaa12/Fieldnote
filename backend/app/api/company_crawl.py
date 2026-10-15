from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_crawl_rate_limit
from app.core.time import now_utc_naive
from app.db.session import get_db
from app.models.user import User

from app.queue.crawl_queue import enqueue_crawl

from app.repositories.company_repository import (
    get_company_for_user,
)

from app.repositories.crawl_job_repository import (
    create_crawl_job,
    get_crawl_job_for_company,
    list_crawl_jobs_for_company,
)

from app.services.crawl_service import cancel_crawl_job

router = APIRouter(
    prefix="/companies",
    tags=["Company Crawler"],
)


class CrawlCompanyRequest(BaseModel):

    max_pages: int = Field(
        default=5,
        ge=1,
        le=100,
    )

    max_depth: int = Field(
        default=1,
        ge=0,
        le=10,
    )


SAFE_CANCEL_MESSAGE = "Cancelled by user"

STATUS_ERROR_MESSAGES = {
    "FAILED": "Crawl failed. Check the website is reachable and try again.",
    "TIMED_OUT": "Crawl exceeded the maximum duration.",
    "QUEUED": "Crawl will be retried.",
}


def sanitize_job_error(status: str, error) -> Optional[str]:
    # Presentation-layer guard: raw DB errors may contain SSRF targets,
    # resolved IPs, file paths, or provider internals. Full details stay
    # in server logs/DB for operators; API callers get a generic message
    # plus job_id for support reference.
    if not error:
        return None
    if status == "CANCELLED" and error == SAFE_CANCEL_MESSAGE:
        return error
    return STATUS_ERROR_MESSAGES.get(status, "Crawl failed. Please try again.")


def crawl_job_response(job):
    duration_seconds = None
    if job.started_at is not None:
        if job.completed_at is not None:
            duration_seconds = max(
                0.0,
                (job.completed_at - job.started_at).total_seconds(),
            )
        elif job.status == "RUNNING":
            duration_seconds = max(
                0.0,
                (now_utc_naive() - job.started_at).total_seconds(),
            )

    return {
        "job_id": job.id,
        "company_id": job.company_id,
        "status": job.status,

        "max_pages": job.max_pages,
        "max_depth": job.max_depth,

        "pages_discovered": job.pages_discovered,
        "pages_crawled": job.pages_crawled,
        "pages_indexed": job.pages_indexed,
        "pages_failed": job.pages_failed,
        "pages_new": job.pages_new,
        "pages_changed": job.pages_changed,
        "pages_unchanged": job.pages_unchanged,
        "pages_deactivated": job.pages_deactivated,
        "attempt_count": job.attempt_count,

        "error": sanitize_job_error(job.status, job.error),

        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "duration_seconds": duration_seconds,
    }


@router.post("/{company_id}/crawl")
def crawl_company(
    company_id: int,
    request: CrawlCompanyRequest,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(
        get_db
    ),
    http_request: Request = None,  # type: ignore[assignment]
):
    check_crawl_rate_limit(http_request, current_user.id)

    company = get_company_for_user(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
    )

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    job = create_crawl_job(
        db=db,
        company_id=company.id,
        max_pages=request.max_pages,
        max_depth=request.max_depth,
    )

    enqueue_crawl(
        job.id,
        company.id,
    )

    return {
        "job_id": job.id,
        "company_id": company.id,
        "company_name": company.name,
        "start_url": company.website_url,
        "status": job.status,
    }


@router.post("/{company_id}/crawl-jobs/{job_id}/cancel")
def cancel_job(
    company_id: int,
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = get_company_for_user(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
    )

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    success = cancel_crawl_job(db, job_id, company.id)
    if not success:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")

    return {"message": "Job cancelled"}


@router.get(
    "/{company_id}/crawl-jobs/{job_id}"
)
def get_crawl_job(
    company_id: int,
    job_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(
        get_db
    ),
):

    company = get_company_for_user(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
    )

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    job = get_crawl_job_for_company(
        db=db,
        job_id=job_id,
        company_id=company.id,
    )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Crawl job not found",
        )

    return crawl_job_response(job)


@router.get(
    "/{company_id}/crawl-jobs"
)
def list_crawl_jobs(
    company_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(
        get_db
    ),
):

    company = get_company_for_user(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
    )

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    jobs = list_crawl_jobs_for_company(
        db=db,
        company_id=company.id,
    )

    return [
        crawl_job_response(job)
        for job in jobs
    ]
