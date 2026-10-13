"""Add last_heartbeat_at to crawl_jobs

Revision ID: cd360119ffea
Revises: 4207836894c0
Create Date: 2026-08-31 01:00:35.262904

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd360119ffea'
down_revision: Union[str, Sequence[str], None] = '4207836894c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    inspector = sa.inspect(op.get_bind())
    if "crawl_jobs" not in inspector.get_table_names():
        return
    if "last_heartbeat_at" not in {column["name"] for column in inspector.get_columns("crawl_jobs")}:
        op.add_column('crawl_jobs', sa.Column('last_heartbeat_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    inspector = sa.inspect(op.get_bind())
    if "crawl_jobs" in inspector.get_table_names() and "last_heartbeat_at" in {column["name"] for column in inspector.get_columns("crawl_jobs")}:
        op.drop_column('crawl_jobs', 'last_heartbeat_at')
