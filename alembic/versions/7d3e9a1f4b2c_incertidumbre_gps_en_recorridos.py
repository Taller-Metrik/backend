"""incertidumbre gps en recorridos

Revision ID: 7d3e9a1f4b2c
Revises: c0788a245c13
Create Date: 2026-11-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7d3e9a1f4b2c'
down_revision: Union[str, Sequence[str], None] = 'c0788a245c13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('surveys', sa.Column('uncertainty', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('surveys', 'uncertainty')
