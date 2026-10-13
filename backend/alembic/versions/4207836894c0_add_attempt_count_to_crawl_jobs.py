"""Add attempt_count to crawl_jobs

Revision ID: 4207836894c0
Revises: f168f90a87a5
Create Date: 2026-08-31 00:55:37.030878

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4207836894c0'
down_revision: Union[str, Sequence[str], None] = 'f168f90a87a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    inspector = sa.inspect(op.get_bind())
    if "crawl_jobs" not in inspector.get_table_names():
        return
    if "attempt_count" not in {column["name"] for column in inspector.get_columns("crawl_jobs")}:
        op.add_column('crawl_jobs', sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    inspector = sa.inspect(op.get_bind())
    if "crawl_jobs" in inspector.get_table_names() and "attempt_count" in {column["name"] for column in inspector.get_columns("crawl_jobs")}:
        op.drop_column('crawl_jobs', 'attempt_count')
