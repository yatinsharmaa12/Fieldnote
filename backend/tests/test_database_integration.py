import os
from urllib.parse import urlparse

from sqlalchemy import text


def test_database_connection(db):
    result = db.execute(
        text("SELECT current_database()")
    ).scalar()

    assert result == urlparse(os.environ["TEST_DATABASE_URL"]).path.lstrip("/")
