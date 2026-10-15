import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.db.database import Base


@pytest.mark.parametrize("initialized", [False, True, "legacy"])
def test_upgrade_head_builds_or_preserves_schema_and_persists(initialized):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "migration_test_" + uuid4().hex
    config = Config("alembic.ini")
    try:
        # Each case uses a dedicated schema in the test database.
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.execute(text('CREATE SCHEMA "' + schema + '"'))
        with engine.connect() as connection:
            connection.execute(text('SET search_path TO "' + schema + '", public'))
            connection.commit()
            if initialized:
                Base.metadata.create_all(bind=connection)
                connection.execute(text("INSERT INTO users (email, password_hash, created_at) VALUES ('migration@example.com', 'unused', NOW())"))
                if initialized == "legacy":
                    connection.execute(text("ALTER TABLE urls DROP COLUMN is_active, DROP COLUMN last_seen_at"))
                    connection.execute(text("INSERT INTO companies (owner_id, name, website_url, created_at) SELECT id, 'Legacy', 'https://example.com', NOW() FROM users"))
                    connection.execute(text("""
                        INSERT INTO urls (company_id, url, normalized_url, status, depth, first_discovered_at, last_crawled_at, crawl_count)
                        SELECT id, 'https://example.com/' || state, 'https://example.com/' || state,
                               state, 0, '2025-01-01'::timestamp, '2025-02-01'::timestamp, 1
                        FROM companies CROSS JOIN (VALUES ('indexed'), ('deactivated')) AS states(state)
                    """))
                connection.commit()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            # An independent connection proves Alembic committed the revision.
        with engine.connect() as connection:
            connection.execute(text('SET search_path TO "' + schema + '", public'))
            assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names(schema=schema))
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "6f8c2a901d44"
            columns = {column["name"]: column for column in inspect(connection).get_columns("urls", schema=schema)}
            assert "last_seen_at" in columns
            assert columns["is_active"]["nullable"] is False
            if initialized == "legacy":
                assert dict(connection.execute(text("SELECT status, is_active FROM urls")).all()) == {"indexed": True, "deactivated": False}
                assert connection.execute(text("SELECT COUNT(*) FROM urls WHERE last_seen_at = last_crawled_at")).scalar() == 2
            indexes = {item["name"] for item in inspect(connection).get_indexes("page_chunks", schema=schema)}
            assert "ix_page_chunks_page_id" in indexes
            if initialized:
                assert connection.execute(text("SELECT email FROM users")).scalar() == "migration@example.com"
            connection.commit()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")  # idempotent
    finally:
        with engine.begin() as connection:
            connection.execute(text('DROP SCHEMA IF EXISTS "' + schema + '" CASCADE'))
        engine.dispose()
