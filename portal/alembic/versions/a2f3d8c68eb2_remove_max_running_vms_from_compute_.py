"""remove max running vms from compute plans

Revision ID: a2f3d8c68eb2
Revises: 960f9479ecad
Create Date: 2026-09-17 23:38:32.911010

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2f3d8c68eb2'
down_revision: Union[str, Sequence[str], None] = '960f9479ecad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_compute_plans_running_vms_limit",
        "compute_plans",
        type_="check",
    )
    op.drop_constraint(
        "ck_compute_plans_max_running_vms_non_negative",
        "compute_plans",
        type_="check",
    )
    op.drop_column("compute_plans", "max_running_vms")


def downgrade() -> None:
    op.add_column(
        "compute_plans",
        sa.Column(
            "max_running_vms",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE compute_plans
        SET max_running_vms = max_vms
        """
    )

    op.alter_column(
        "compute_plans",
        "max_running_vms",
        nullable=False,
    )

    op.create_check_constraint(
        "ck_compute_plans_max_running_vms_non_negative",
        "compute_plans",
        "max_running_vms >= 0",
    )
    op.create_check_constraint(
        "ck_compute_plans_running_vms_limit",
        "compute_plans",
        "max_running_vms <= max_vms",
    )### end Alembic commands ###
