from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.models import ComputePlan, UserQuota


async def assign_starter_quota(
        db: AsyncSession, 
        user_id: UUID,
) -> UserQuota:
    statement = select(ComputePlan).where(
        ComputePlan.code == 'starter'
    )
    plan = await db.scalar(statement)

    if plan is None:
        raise RuntimeError("compute plan is missing")
    elif plan.is_active is False:
        raise RuntimeError("compute plan is inactive")

    uq = UserQuota(
        user_id=user_id,
        compute_plan_id=plan.id,
        status='active',
    )
    db.add(uq)

    return uq
    
