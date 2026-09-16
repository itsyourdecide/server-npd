"""backfill starter user quotas

Revision ID: 1b47a1f1aaff
Revises: d3c70f1c2755
Create Date: 2026-09-16 22:47:40.316329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b47a1f1aaff'
down_revision: Union[str, Sequence[str], None] = 'd3c70f1c2755'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    statement = sa.text(
        """
        INSERT INTO user_quota (
            user_id,
            compute_plan_id,
            status
        )
        SELECT
            users.id,
            compute_plans.id,
            'active'
        FROM users CROSS JOIN compute_plans

        WHERE compute_plans.code = 'starter'
        AND NOT EXISTS (
            SELECT 1
            FROM user_quota
            WHERE user_quota.user_id = users.id
        )
        """
    )

    op.execute(statement)


def downgrade() -> None:
    """Downgrade schema."""
    pass
