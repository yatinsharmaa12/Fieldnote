from logging.config import fileConfig

from sqlalchemy import engine_from_config, text
from sqlalchemy import pool
import os
from alembic import context
from app.db.database import Base

# Import all models so SQLAlchemy knows about every table
from app.models.user import User
from app.models.company import Company
from app.models.url_db import URL
from app.models.page_db import Page
from app.models.page_chunk import PageChunk
from app.models.crawl_job import CrawlJob

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
from dotenv import load_dotenv

load_dotenv()
# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata


target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    

    url = os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        run_on_connection(supplied_connection)
        return

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        run_on_connection(connection)


def run_on_connection(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    # Configure Alembic before executing SQL: otherwise SQLAlchemy autobegin
    # makes Alembic treat the transaction as external and it rolls back on exit.
    with context.begin_transaction():
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
