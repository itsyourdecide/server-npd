from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.models import ComputePlan, UserQuota
from app.compute.services import get_user_compute_usage
from app.virtual_machines.models import VirtualMachine
from app.virtual_machines.schemas import VirtualMachineCreate

ALLOWED_IMAGE_IDS = {"almalinux-9"}


async def create_vm(
    db: AsyncSession,
    user_id: UUID,
    request_model: VirtualMachineCreate,
) -> VirtualMachine:

    if request_model.image_id not in ALLOWED_IMAGE_IDS:
        raise ValueError("image is not allowed")

    statement = select(UserQuota).where(
        UserQuota.user_id == user_id
        ).with_for_update()

    quota = await db.scalar(statement)

    if quota is None:
        raise RuntimeError("user quota is missing")
    
    if quota.status != "active":
        raise PermissionError("user quota is suspended")


    plan = await db.get(ComputePlan, quota.compute_plan_id)

    if plan is None:
        raise RuntimeError("compute plan is missing")

    
    usage = await get_user_compute_usage(db, user_id)

    if usage["used_vms"] + 1 > plan.max_vms:
        raise ValueError("VM limit exceeded")
    
    if (usage["used_vcpus"] + request_model.requested_vcpus > plan.max_total_vcpus):
        raise ValueError("vCPU limit exceeded")
    
    if (usage["used_memory_mb"] + request_model.requested_memory_mb > plan.max_total_memory_mb):
        raise ValueError("memory limit exceeded")

    if (usage["used_storage_gb"] + request_model.requested_storage_gb > plan.max_total_storage_gb):
        raise ValueError("storage limit exceeded")

    vm = VirtualMachine(
        owner_user_id=user_id,
        status="pending",
        requested_vcpus=request_model.requested_vcpus,
        requested_memory_mb=request_model.requested_memory_mb,
        requested_storage_gb=request_model.requested_storage_gb,
        image_id=request_model.image_id,
    )

    db.add(vm)
    await db.flush()

    return vm