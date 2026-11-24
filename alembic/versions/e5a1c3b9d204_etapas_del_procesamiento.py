"""etapas del procesamiento en recorridos

Revision ID: e5a1c3b9d204
Revises: b4c8e2d17a90
Create Date: 2026-11-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5a1c3b9d204'
down_revision: Union[str, Sequence[str], None] = 'b4c8e2d17a90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('surveys', sa.Column('processing_stages', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('surveys', 'processing_stages')
