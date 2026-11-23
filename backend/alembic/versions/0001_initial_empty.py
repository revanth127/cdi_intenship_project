"""empty initial migration

Revision ID: 0001_initial_empty
Revises: 
Create Date: 2026-11-23 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_initial_empty'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Empty initial baseline migration that runs cleanly."""
    pass


def downgrade() -> None:
    """Revert empty initial baseline migration."""
    pass
