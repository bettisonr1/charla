"""conversations.ended_at

Revision ID: 3c1f5a9d7e42
Revises: 79bc18e0de23
Create Date: 2026-11-04 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3c1f5a9d7e42'
down_revision: Union[str, Sequence[str], None] = '79bc18e0de23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('conversations', sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conversations', 'ended_at')
