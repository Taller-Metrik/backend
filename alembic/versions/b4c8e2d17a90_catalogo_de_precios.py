"""catalogo de precios

Revision ID: b4c8e2d17a90
Revises: 7d3e9a1f4b2c
Create Date: 2026-11-10 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4c8e2d17a90'
down_revision: Union[str, Sequence[str], None] = '7d3e9a1f4b2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'material_prices',
        sa.Column('key', sa.String(length=40), nullable=False),
        sa.Column('store', sa.String(length=40), nullable=False),
        sa.Column('product_name', sa.String(length=200), nullable=True),
        sa.Column('url', sa.String(length=300), nullable=True),
        sa.Column('price', sa.Numeric(precision=10, scale=2, asdecimal=False), nullable=True),
        sa.Column('available', sa.Boolean(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('error', sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'user_prices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=40), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2, asdecimal=False), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', name='uq_user_price_key'),
    )
    op.create_index(op.f('ix_user_prices_user_id'), 'user_prices', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_prices_user_id'), table_name='user_prices')
    op.drop_table('user_prices')
    op.drop_table('material_prices')
