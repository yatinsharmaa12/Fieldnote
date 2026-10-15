import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.db.database import Base


@pytest.mark.parametrize("initialized", [False, True])
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
                connection.commit()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            # An independent connection proves Alembic committed the revision.
        with engine.connect() as connection:
            connection.execute(text('SET search_path TO "' + schema + '", public'))
            assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names(schema=schema))
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "2d5e91a8b301"
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
