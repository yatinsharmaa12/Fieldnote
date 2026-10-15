from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from app.api.company_crawl import (
    crawl_company,
    get_crawl_job,
    list_crawl_jobs,
)
from app.models.user import User


def test_company_owner_can_crawl():
    db = MagicMock()

    company = MagicMock()
    company.id = 12
    company.name = "Test Company"
    company.website_url = "https://example.com"

    (
        db.query.return_value
        .filter.return_value
        .first.return_value
    ) = company

    job = MagicMock()
    job.id = 99
    job.status = "QUEUED"

    user = User(
        id=3,
        email="test@example.com",
        password_hash="unused",
    )

    request = MagicMock()
    request.max_pages = 5
    request.max_depth = 1

    with patch(
        "app.api.company_crawl.create_crawl_job",
        return_value=job,
    ) as mock_create_job, patch(
        "app.api.company_crawl.enqueue_crawl"
    ) as mock_enqueue:

        result = crawl_company(
            company_id=12,
            request=request,
            current_user=user,
            db=db,
        )

    mock_create_job.assert_called_once_with(
        db=db,
        company_id=12,
        max_pages=5,
        max_depth=1,
    )

    mock_enqueue.assert_called_once_with(
        99,
        12,
    )

    assert result["job_id"] == 99
    assert result["company_id"] == 12
    assert result["company_name"] == "Test Company"
    assert result["start_url"] == "https://example.com"
    assert result["status"] == "QUEUED"

def test_company_owner_cannot_crawl_unowned_company():
    db = MagicMock()
    user = User(
        id=3,
        email="test@example.com",
        password_hash="unused",
    )

    request = MagicMock()
    request.max_pages = 5
    request.max_depth = 1

    with patch(
        "app.api.company_crawl.get_company_for_user",
        return_value=None,
    ):
        with pytest.raises(HTTPException) as error:
            crawl_company(
                company_id=1,
                request=request,
                current_user=user,
                db=db,
            )

    assert error.value.status_code == 404
    assert error.value.detail == "Company not found"

def test_company_crawl_requires_authentication():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    response = client.post(
        "/companies/12/crawl",
        json={
            "max_pages": 1,
            "max_depth": 0,
        },
    )

    assert response.status_code == 401

def test_owner_can_view_crawl_job():
    db = MagicMock()

    company = MagicMock()
    company.id = 12

    job = MagicMock()
    job.id = 99
    job.company_id = 12
    job.status = "COMPLETED"
    job.max_pages = 5
    job.max_depth = 1
    job.pages_crawled = 2
    job.error = None
    job.created_at = None
    job.started_at = None
    job.completed_at = None
    job.pages_discovered = 0
    job.pages_indexed = 0
    job.pages_failed = 0
    job.pages_new = 0
    job.pages_changed = 0
    job.pages_unchanged = 0
    job.pages_deactivated = 0

    user = User(
        id=3,
        email="test@example.com",
        password_hash="unused",
    )

    with patch(
        "app.api.company_crawl.get_company_for_user",
        return_value=company,
    ), patch(
        "app.api.company_crawl.get_crawl_job_for_company",
        return_value=job,
    ) as mock_get_job:

        result = get_crawl_job(
            company_id=12,
            job_id=99,
            current_user=user,
            db=db,
        )

    mock_get_job.assert_called_once_with(
        db=db,
        job_id=99,
        company_id=12,
    )

    assert result["job_id"] == 99
    assert result["company_id"] == 12
    assert result["status"] == "COMPLETED"
    assert result["pages_crawled"] == 2
    assert result["pages_new"] == 0
    assert result["pages_changed"] == 0
    assert result["pages_unchanged"] == 0
    assert result["pages_deactivated"] == 0
    assert result["duration_seconds"] is None


def test_crawl_job_response_duration_for_completed_and_running_jobs():
    completed = MagicMock()
    completed.id = 1
    completed.company_id = 2
    completed.status = "COMPLETED"
    completed.max_pages = 5
    completed.max_depth = 1
    completed.pages_discovered = 1
    completed.pages_crawled = 1
    completed.pages_indexed = 1
    completed.pages_failed = 0
    completed.pages_new = 1
    completed.pages_changed = 0
    completed.pages_unchanged = 0
    completed.pages_deactivated = 0
    completed.error = None
    completed.created_at = None
    completed.started_at = datetime(2026, 1, 1, 12, 0, 0)
    completed.completed_at = completed.started_at + timedelta(seconds=12.5)

    from app.api.company_crawl import crawl_job_response

    assert crawl_job_response(completed)["duration_seconds"] == 12.5

    running = SimpleNamespace(**{
        "id": 1, "company_id": 2, "status": "RUNNING", "max_pages": 5,
        "max_depth": 1, "pages_discovered": 1, "pages_crawled": 1,
        "pages_indexed": 1, "pages_failed": 0, "pages_new": 1,
        "pages_changed": 0, "pages_unchanged": 0, "pages_deactivated": 0,
        "error": None, "created_at": None, "started_at": completed.started_at,
        "completed_at": None, "attempt_count": 1,
    })
    with patch(
        "app.api.company_crawl.now_utc_naive",
        return_value=running.started_at + timedelta(seconds=3),
    ):
        assert crawl_job_response(running)["duration_seconds"] == 3.0

def test_crawl_job_not_found():
    db = MagicMock()

    company = MagicMock()
    company.id = 12

    user = User(
        id=3,
        email="test@example.com",
        password_hash="unused",
    )

    with patch(
        "app.api.company_crawl.get_company_for_user",
        return_value=company,
    ), patch(
        "app.api.company_crawl.get_crawl_job_for_company",
        return_value=None,
    ):

        with pytest.raises(HTTPException) as error:
            get_crawl_job(
                company_id=12,
                job_id=999,
                current_user=user,
                db=db,
            )

    assert error.value.status_code == 404
    assert error.value.detail == "Crawl job not found"

def test_owner_can_list_crawl_jobs():
    db = MagicMock()

    company = MagicMock()
    company.id = 12

    job1 = MagicMock()
    job1.id = 99
    job1.company_id = 12
    job1.status = "COMPLETED"
    job1.max_pages = 5
    job1.max_depth = 1
    job1.pages_crawled = 2
    job1.error = None
    job1.created_at = None
    job1.started_at = None
    job1.completed_at = None

    job2 = MagicMock()
    job2.id = 98
    job2.company_id = 12
    job2.status = "FAILED"
    job2.max_pages = 10
    job2.max_depth = 2
    job2.pages_crawled = 1
    job2.error = "Crawler crashed"
    job2.created_at = None
    job2.started_at = None
    job2.completed_at = None

    user = User(
        id=3,
        email="test@example.com",
        password_hash="unused",
    )

    with patch(
        "app.api.company_crawl.get_company_for_user",
        return_value=company,
    ), patch(
        "app.api.company_crawl.list_crawl_jobs_for_company",
        return_value=[job1, job2],
    ) as mock_list:

        result = list_crawl_jobs(
            company_id=12,
            current_user=user,
            db=db,
        )

    mock_list.assert_called_once_with(
        db=db,
        company_id=12,
    )

    assert len(result) == 2
    assert result[0]["job_id"] == 99
    assert result[0]["status"] == "COMPLETED"
    assert result[1]["job_id"] == 98
    assert result[1]["status"] == "FAILED"
    # API sanitizes raw DB errors; internal detail stays server-side.
    assert result[1]["error"] == (
        "Crawl failed. Check the website is reachable and try again."
    )
    assert "Crawler crashed" not in result[1]["error"]

def test_list_crawl_jobs_rejects_unowned_company():
    db = MagicMock()

    user = User(
        id=3,
        email="test@example.com",
        password_hash="unused",
    )

    with patch(
        "app.api.company_crawl.get_company_for_user",
        return_value=None,
    ):
        with pytest.raises(HTTPException) as error:
            list_crawl_jobs(
                company_id=12,
                current_user=user,
                db=db,
            )

    assert error.value.status_code == 404
    assert error.value.detail == "Company not found"
