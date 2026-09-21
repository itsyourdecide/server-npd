from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.models import ComputePlan, UserQuota
from app.compute.services import get_user_compute_usage
from app.operations.models import Operation
from app.virtual_machines.models import VirtualMachine
from app.virtual_machines.schemas import VirtualMachineCreate

ALLOWED_IMAGE_IDS = {"almalinux-9"}


async def create_vm(
    db: AsyncSession,
    user_id: UUID,
    request_model: VirtualMachineCreate,
    idempotency_key: str
) -> VirtualMachine:

    statement = select(UserQuota).where(
        UserQuota.user_id == user_id
        ).with_for_update()

    quota = await db.scalar(statement)

    if quota is None:
            raise RuntimeError("user quota is missing")
    
    existing_vm = await _get_existing_vm_for_create_request(
        db,
        idempotency_key=idempotency_key,
        user_id=user_id,
        request_model=request_model,
    )

    if existing_vm is not None:
        return existing_vm

    
    if quota.status != "active":
        raise PermissionError("user quota is suspended")

    if request_model.image_id not in ALLOWED_IMAGE_IDS:
        raise ValueError("image is not allowed")

    plan = await db.get(ComputePlan, quota.compute_plan_id)

    if plan is None:
        raise RuntimeError("compute plan is missing")

    
    usage = await get_user_compute_usage(db, user_id)

    _validate_vm_quota(plan=plan, usage=usage, request_model=request_model)

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

    operation = Operation(
        virtual_machine_id=vm.id,
        operation_type="vm.create",
        status="pending",
        idempotency_key=idempotency_key,
    )

    db.add(operation)
    await db.flush()

    return vm


async def _get_existing_vm_for_create_request(
    db: AsyncSession,
    idempotency_key: str,
    user_id: UUID,
    request_model: VirtualMachineCreate,
) -> VirtualMachine | None:
    
    operation = await db.scalar(
        select(Operation).where(
            Operation.idempotency_key == idempotency_key
        )
    )

    if operation is None:
        return None
    
    if operation.operation_type != "vm.create":
        raise ValueError("idempotency key already used")

    vm = await db.get(VirtualMachine, operation.virtual_machine_id)

    if vm is None:
        raise RuntimeError("operation references missing VM")

    if vm.owner_user_id != user_id:
        raise ValueError("idempotency key already used")

    request_matches = (
        vm.requested_vcpus == request_model.requested_vcpus
        and vm.requested_memory_mb == request_model.requested_memory_mb
        and vm.requested_storage_gb == request_model.requested_storage_gb
        and vm.image_id == request_model.image_id
    )

    if request_matches is False:
        raise ValueError(
            "idempotency key reused with different request"
        )

    return vm


def _validate_vm_quota(
    plan: ComputePlan,
    usage: dict[str, int],
    request_model: VirtualMachineCreate,
) -> None:
    
    if usage["used_vms"] + 1 > plan.max_vms:
            raise ValueError("VM limit exceeded")
        
    if (usage["used_vcpus"] + request_model.requested_vcpus > plan.max_total_vcpus):
        raise ValueError("vCPU limit exceeded")
        
    if (usage["used_memory_mb"] + request_model.requested_memory_mb > plan.max_total_memory_mb):
        raise ValueError("memory limit exceeded")
    
    if (usage["used_storage_gb"] + request_model.requested_storage_gb > plan.max_total_storage_gb):
        raise ValueError("storage limit exceeded")