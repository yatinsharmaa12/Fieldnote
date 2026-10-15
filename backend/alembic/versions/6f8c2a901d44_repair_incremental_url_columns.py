"""Repair incremental URL columns on legacy databases.

Revision ID: 6f8c2a901d44
Revises: 2d5e91a8b301
"""
from alembic import op
import sqlalchemy as sa

revision = "6f8c2a901d44"
down_revision = "2d5e91a8b301"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns("urls")}
    if "last_seen_at" not in columns:
        op.add_column("urls", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
        # Preserve historical knowledge without pretending these URLs were
        # visited during the current crawl.
        op.execute(sa.text("UPDATE urls SET last_seen_at = COALESCE(last_crawled_at, first_discovered_at)"))
    if "is_active" not in columns:
        op.add_column("urls", sa.Column("is_active", sa.Boolean(), nullable=True))
    # Existing explicit inactive flags must survive the repair.
    op.execute(sa.text("UPDATE urls SET is_active = (status <> 'deactivated') WHERE is_active IS NULL"))
    op.execute(sa.text("UPDATE urls SET is_active = FALSE WHERE status = 'deactivated' AND is_active IS TRUE"))
    op.alter_column("urls", "is_active", existing_type=sa.Boolean(), nullable=False)


def downgrade():
    # These columns may have existed before Alembic tracked them. Retain them
    # and their data rather than deleting user history on downgrade.
    pass
