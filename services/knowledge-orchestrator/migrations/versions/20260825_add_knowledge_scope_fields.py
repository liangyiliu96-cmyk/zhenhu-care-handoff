"""add knowledge scope fields

Revision ID: 20260825_scope
Revises: ee629101ba58
Create Date: 2026-08-25 18:35:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_scope"
down_revision: Union[str, None] = "ee629101ba58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("layer", sa.String(length=32), nullable=True, comment="知识层级：L1-L16 或业务扩展层"))
    op.add_column("knowledge_documents", sa.Column("disease_id", sa.String(length=128), nullable=True, comment="适用病种 ID"))
    op.add_column("knowledge_documents", sa.Column("department", sa.String(length=64), nullable=True, comment="适用科室"))
    op.create_index(op.f("ix_knowledge_documents_layer"), "knowledge_documents", ["layer"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_disease_id"), "knowledge_documents", ["disease_id"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_department"), "knowledge_documents", ["department"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_documents_department"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_disease_id"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_layer"), table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "department")
    op.drop_column("knowledge_documents", "disease_id")
    op.drop_column("knowledge_documents", "layer")
