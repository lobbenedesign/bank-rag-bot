"""initial schema: document_metadata

Revision ID: 0001
Revises:
Create Date: 2026-08-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_metadata",
        sa.Column("source_id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("audience", sa.String(), nullable=False),
        sa.Column("uploaded_by", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_metadata_audience", "document_metadata", ["audience"])


def downgrade() -> None:
    op.drop_index("ix_document_metadata_audience", table_name="document_metadata")
    op.drop_table("document_metadata")
