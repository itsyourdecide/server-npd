"""add vm lifecycle operation types

Revision ID: a7c43a5f40c2
Revises: 4fa6b2ff7397
Create Date: 2026-09-24 03:01:16.604888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c43a5f40c2'
down_revision: Union[str, Sequence[str], None] = '4fa6b2ff7397'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "operation_type_list",
        "operations",
        type_="check",
    )

    op.create_check_constraint(
        "operation_type_list",
        "operations",
        """
        operation_type IN (
            'vm.create',
            'vm.start',
            'vm.shutdown',
            'vm.stop',
            'vm.reboot',
            'vm.delete'
        )
        """,
    )


def downgrade() -> None:
    op.drop_constraint(
        "operation_type_list",
        "operations",
        type_="check",
    )

    op.create_check_constraint(
        "operation_type_list",
        "operations",
        """
        operation_type IN (
            'vm.create',
            'vm.start',
            'vm.stop',
            'vm.delete'
        )
        """,
    )