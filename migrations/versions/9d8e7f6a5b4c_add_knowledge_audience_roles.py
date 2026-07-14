"""add knowledge audience roles

Revision ID: 9d8e7f6a5b4c
Revises: 6c4e1b9a3d2f
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d8e7f6a5b4c"
down_revision: Union[str, Sequence[str], None] = "6c4e1b9a3d2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_items",
        sa.Column("audience_roles", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("knowledge_items", "audience_roles")
