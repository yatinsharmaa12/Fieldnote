"""Add incremental crawl statistics

Revision ID: 8b4e0f5f2a1c
Revises: cd360119ffea
Create Date: 2026-08-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b4e0f5f2a1c"
down_revision: Union[str, Sequence[str], None] = "cd360119ffea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "crawl_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("crawl_jobs")}
    for name in ("pages_new", "pages_changed", "pages_unchanged", "pages_deactivated"):
        if name not in columns:
            op.add_column("crawl_jobs", sa.Column(name, sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "crawl_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("crawl_jobs")}
    for name in ("pages_deactivated", "pages_unchanged", "pages_changed", "pages_new"):
        if name in columns:
            op.drop_column("crawl_jobs", name)
