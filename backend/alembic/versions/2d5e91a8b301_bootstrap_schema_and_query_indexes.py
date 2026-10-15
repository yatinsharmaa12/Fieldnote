"""Bootstrap missing base tables and index company-scoped queries.

Revision ID: 2d5e91a8b301
Revises: 8b4e0f5f2a1c
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "2d5e91a8b301"
down_revision = "8b4e0f5f2a1c"
branch_labels = None
depends_on = None


INDEXES = {
    "companies": [("ix_companies_owner_id", ["owner_id"])],
    "crawl_jobs": [("ix_crawl_jobs_company_id", ["company_id"])],
    "pages": [("ix_pages_company_id", ["company_id"]), ("ix_pages_url_id", ["url_id"])],
    "page_chunks": [("ix_page_chunks_page_id", ["page_id"])],
}


def base_schema():
    # Frozen schema, intentionally independent of future application models.
    metadata = sa.MetaData()
    sa.Table("users", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False))
    sa.Table("companies", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("website_url", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False))
    sa.Table("urls", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("normalized_url", sa.String(2048), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("depth", sa.Integer, nullable=False),
        sa.Column("discovered_from", sa.String(2048)),
        sa.Column("first_discovered_at", sa.DateTime, nullable=False),
        sa.Column("last_crawled_at", sa.DateTime),
        sa.Column("crawl_count", sa.Integer, nullable=False),
        sa.Column("http_status", sa.Integer),
        sa.Column("last_error", sa.Text),
        sa.Column("last_seen_at", sa.DateTime),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.UniqueConstraint("company_id", "normalized_url", name="uq_company_normalized_url"))
    sa.Table("pages", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url_id", sa.Integer, sa.ForeignKey("urls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("http_status", sa.Integer),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("crawled_at", sa.DateTime, nullable=False))
    sa.Table("page_chunks", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("page_id", sa.Integer, sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False))
    sa.Table("crawl_jobs", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("max_pages", sa.Integer, nullable=False),
        sa.Column("max_depth", sa.Integer, nullable=False),
        *(sa.Column(name, sa.Integer, nullable=False, server_default="0") for name in (
            "pages_discovered", "pages_crawled", "pages_indexed", "pages_failed",
            "pages_new", "pages_changed", "pages_unchanged", "pages_deactivated", "attempt_count")),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime),
        sa.Column("last_heartbeat_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime))
    return metadata


def upgrade():
    bind = op.get_bind()
    base_schema().create_all(bind=bind, checkfirst=True)
    for table, indexes in INDEXES.items():
        existing = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
        for name, columns in indexes:
            if name not in existing:
                op.create_index(name, table, columns)


def downgrade():
    for table, indexes in reversed(list(INDEXES.items())):
        existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
        for name, _columns in indexes:
            if name in existing:
                op.drop_index(name, table_name=table)
    # Preserve base tables: they may predate Alembic and contain user data.
