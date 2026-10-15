from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.time import now_utc_naive

from app.models.url import URLRecord, URLStatus
from app.models.url_db import URL
from app.crawler.link_extractor import normalize_url


class URLRegistry:
    def __init__(self, db: Session, company_id: int):
        self.db = db
        self.company_id = company_id

    def add(
        self,
        url: str,
        status: URLStatus = URLStatus.DISCOVERED,
        depth: int = 0,
        discovered_from: Optional[str] = None,
    ) -> URLRecord:

        normalized_url = normalize_url(url, url)

        if not normalized_url:
            raise ValueError(f"Invalid URL: {url}")

        record = (
            self.db.query(URL)
            .filter(
                URL.company_id == self.company_id,
                URL.normalized_url == normalized_url,
            )
            .first()
        )

        if record:
            # Update existing record's status and timestamps for incremental crawl
            record.status = status.value
            record.last_seen_at = now_utc_naive()
            record.last_error = None
            record.is_active = status != URLStatus.DEACTIVATED
            # Preserve depth, discovered_from if already set; otherwise update
            if depth is not None:
                record.depth = depth
            if discovered_from is not None:
                record.discovered_from = discovered_from
            self.db.commit()
            self.db.refresh(record)
            return self._to_record(record)

        record = URL(
            company_id=self.company_id,
            url=normalized_url,
            normalized_url=normalized_url,
            status=status.value,
            depth=depth,
            discovered_from=discovered_from,
            last_seen_at=now_utc_naive(),
            is_active=status != URLStatus.DEACTIVATED,
        )

        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        return self._to_record(record)

    def get(self, url: str) -> Optional[URLRecord]:

        normalized_url = normalize_url(url, url)

        if not normalized_url:
            return None

        record = (
            self.db.query(URL)
            .filter(
                URL.company_id == self.company_id,
                URL.normalized_url == normalized_url,
            )
            .first()
        )

        if not record:
            return None

        return self._to_record(record)

    def update_status(
        self,
        url: str,
        status: URLStatus,
        error: Optional[str] = None,
        http_status: Optional[int] = None,
    ) -> None:

        normalized_url = normalize_url(url, url)

        if not normalized_url:
            return

        record = (
            self.db.query(URL)
            .filter(
                URL.company_id == self.company_id,
                URL.normalized_url == normalized_url,
            )
            .first()
        )

        if not record:
            return

        record.status = status.value
        record.last_error = error
        record.last_seen_at = now_utc_naive()
        record.is_active = status != URLStatus.DEACTIVATED

        if http_status is not None:
            record.http_status = http_status

        if status == URLStatus.CRAWLED:
            record.last_crawled_at = now_utc_naive()
            record.crawl_count += 1

        self.db.commit()

    def deactivate_unseen(self, cutoff: datetime) -> int:
        # Deactivate URLs that were not seen during the crawl (last_seen_at is None)
        # or whose last_seen_at is older than the crawl start time.
        result = self.db.query(URL).filter(
            URL.company_id == self.company_id,
            URL.status != URLStatus.DEACTIVATED.value,
            URL.is_active.is_(True),
            (URL.last_seen_at < cutoff) | (URL.last_seen_at == None),
        ).update(
            {"status": URLStatus.DEACTIVATED.value, "is_active": False},
            synchronize_session=False,
        )
        self.db.commit()
        return result

    def all(self) -> list[URLRecord]:

        records = (
            self.db.query(URL)
            .filter(URL.company_id == self.company_id)
            .all()
        )

        return [
            self._to_record(record)
            for record in records
        ]

    def count(self) -> int:

        return (
            self.db.query(URL)
            .filter(URL.company_id == self.company_id)
            .count()
        )

    @staticmethod
    def _to_record(record: URL) -> URLRecord:

        return URLRecord(
            url=record.url,
            status=URLStatus(record.status),
            depth=record.depth,
            discovered_from=record.discovered_from,
            error=record.last_error,
        )
