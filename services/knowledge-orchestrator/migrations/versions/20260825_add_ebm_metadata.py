"""add EBM evidence metadata

Revision ID: 20260825_ebm
Revises: 20260825_scope
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_ebm"
down_revision: Union[str, None] = "20260825_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("source_type", sa.String(length=32), nullable=False, server_default="unknown"))
    op.add_column("knowledge_documents", sa.Column("evidence_level", sa.String(length=16), nullable=False, server_default="unknown"))
    op.add_column("knowledge_documents", sa.Column("guideline_year", sa.Integer(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("source_credibility", sa.Float(), nullable=False, server_default="0.5"))
    op.add_column("knowledge_documents", sa.Column("evidence_metadata_origin", sa.String(length=16), nullable=False, server_default="inferred"))
    op.create_index(op.f("ix_knowledge_documents_source_type"), "knowledge_documents", ["source_type"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_guideline_year"), "knowledge_documents", ["guideline_year"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_documents_guideline_year"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_source_type"), table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "evidence_metadata_origin")
    op.drop_column("knowledge_documents", "source_credibility")
    op.drop_column("knowledge_documents", "guideline_year")
    op.drop_column("knowledge_documents", "evidence_level")
    op.drop_column("knowledge_documents", "source_type")
