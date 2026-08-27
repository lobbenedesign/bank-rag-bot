"""add locator_kind/locator_pattern to noindex_rules (granular exclusion)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("noindex_rules", sa.Column("locator_kind", sa.String(), nullable=True))
    op.add_column("noindex_rules", sa.Column("locator_pattern", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("noindex_rules", "locator_pattern")
    op.drop_column("noindex_rules", "locator_kind")
