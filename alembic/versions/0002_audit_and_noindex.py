"""audit_log (append-only) and noindex_rules

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("resolved_question", sa.Text(), nullable=False),
        sa.Column("retrieved_document_ids", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_conversation_id", "audit_log", ["conversation_id"])
    op.create_index("ix_audit_log_customer_id", "audit_log", ["customer_id"])

    op.create_table(
        "noindex_rules",
        sa.Column("pattern", sa.String(), primary_key=True),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Defense in depth beyond application-code discipline: the app's own DB
    # role loses the ability to UPDATE or DELETE audit rows, so an append-only
    # port (AuditLog) is backed by an append-only grant, not just convention.
    # Adjust the role name to whatever the app actually connects as in each
    # environment before running this migration outside local docker-compose.
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM bank_rag")


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON audit_log TO bank_rag")
    op.drop_table("noindex_rules")
    op.drop_index("ix_audit_log_customer_id", table_name="audit_log")
    op.drop_index("ix_audit_log_conversation_id", table_name="audit_log")
    op.drop_table("audit_log")
