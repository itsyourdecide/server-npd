from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.models import ComputePlan, UserQuota
from app.virtual_machines.models import VirtualMachine


QUOTA_CONSUMING_STATUSES = (
    "pending",
    "pending_capacity",
    "provisioning",
    "running",
    "stopped",
    "deleting",
)


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
    

async def get_user_compute_usage(db: AsyncSession, user_id: UUID) -> dict[str, int]:
    statement = (
        select(
            func.count(VirtualMachine.id).label("used_vms"),
            func.coalesce(
                func.sum(VirtualMachine.requested_vcpus),
                0,
            ).label("used_vcpus"),
            func.coalesce(
                func.sum(VirtualMachine.requested_memory_mb),
                0,
            ).label("used_memory_mb"),
            func.coalesce(
                func.sum(VirtualMachine.requested_storage_gb),
                0,
            ).label("used_storage_gb"),
        )
        .where(
            VirtualMachine.owner_user_id == user_id,
            VirtualMachine.status.in_(QUOTA_CONSUMING_STATUSES),
        )
    )

    usage = (await db.execute(statement)).one()

    return {
        "used_vms": usage.used_vms,
        "used_vcpus": usage.used_vcpus,
        "used_memory_mb": usage.used_memory_mb,
        "used_storage_gb": usage.used_storage_gb,
    }
    
    