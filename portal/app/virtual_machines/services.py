from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.models import ComputePlan, UserQuota
from app.compute.services import get_user_compute_usage
from app.operations.models import Operation
from app.ssh_keys.models import SshPublicKey
from app.virtual_machines.models import VirtualMachine
from app.virtual_machines.schemas import VirtualMachineCreate

IMAGE_MIN_STORAGE_GB = {
    "almalinux-9": 10,
}


async def create_vm(
    db: AsyncSession,
    user_id: UUID,
    request_model: VirtualMachineCreate,
    idempotency_key: str
) -> VirtualMachine:

    ssh_key = await db.scalar(select(SshPublicKey).where(
        SshPublicKey.id == request_model.ssh_public_key_id,
        SshPublicKey.owner_user_id == user_id
        )
    )

    if ssh_key is None:
        raise ValueError("SSH public key not found or does not belong to user")
                              
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

    minimum_storage_gb = IMAGE_MIN_STORAGE_GB.get(request_model.image_id)

    if minimum_storage_gb is None:
        raise ValueError("image is not allowed")

    if request_model.requested_storage_gb < minimum_storage_gb:
        raise ValueError(
            f"storage must be at least {minimum_storage_gb} GB for this image"
        )

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
        ssh_public_key_id=request_model.ssh_public_key_id,
    )

    db.add(vm)
    await db.flush()

    operation = Operation(
        virtual_machine_id=vm.id,
        operation_type="vm.create",
        status="pending",
        phase="clone",
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
        and vm.ssh_public_key_id == request_model.ssh_public_key_id
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


async def enqueue_vm_operation(
    db: AsyncSession,
    *,
    user_id: UUID,
    vm_id: UUID,
    operation_type: str,
    idempotency_key: str,
) -> Operation:

    allowed_statuses = {
        "vm.start": {"stopped"},
        "vm.shutdown": {"running"},
        "vm.stop": {"running"},
        "vm.reboot": {"running"},
        "vm.delete": {"stopped"},
    }

    if operation_type not in allowed_statuses:
        raise ValueError("unsupported VM operation")


    vm = await db.scalar(select(VirtualMachine).where(
            VirtualMachine.id == vm_id,
            VirtualMachine.owner_user_id == user_id
        ).with_for_update()
    )

    if vm is None:
        raise LookupError("virtual machine not found")


    existing = await db.scalar(
        select(Operation).where(
            Operation.idempotency_key == idempotency_key
        )
    )

    if existing is not None:
        if (
            existing.virtual_machine_id != vm.id
            or existing.operation_type != operation_type
        ):
            raise ValueError("idempotency key already used")

        return existing


    active_operation = await db.scalar(
        select(Operation).where(
            Operation.virtual_machine_id == vm_id,
            Operation.status.in_(("pending", "processing")),
        ).limit(1)
    )

    if active_operation is not None:
        raise ValueError("virtual machine already has an active operation")

    if vm.status not in allowed_statuses[operation_type]:
        raise ValueError(f"cannot perform {operation_type} while VM is {vm.status}")

    new_operation = Operation(
        virtual_machine_id=vm.id,
        operation_type=operation_type,
        status="pending",
        phase="shutdown" if operation_type == "vm.reboot" else None,
        idempotency_key=idempotency_key,
    )

    db.add(new_operation)
    await db.flush()
    return new_operation