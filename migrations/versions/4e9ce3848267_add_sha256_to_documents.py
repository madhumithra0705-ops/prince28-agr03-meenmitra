"""add sha256 to documents

Revision ID: 4e9ce3848267
Revises: 924078ec9bae
Create Date: 2026-11-18 21:59:21.611146
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4e9ce3848267"
down_revision: Union[str, Sequence[str], None] = "924078ec9bae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("sha256", sa.String(length=64), nullable=True),
    )

    op.execute(
        """
        UPDATE documents
        SET sha256 = metadata ->> 'sha256'
        WHERE metadata IS NOT NULL
          AND metadata ? 'sha256'
        """
    )


def downgrade() -> None:
    op.drop_column("documents", "sha256")
