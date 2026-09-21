from sqlalchemy.ext.asyncio import AsyncSession

from app.operations.models import Operation
from app.proxmox.contracts import CreateVmRequest, ProviderTask, ProxmoxAdapter
from app.virtual_machines.models import VirtualMachine
from datetime import UTC, datetime


async def start_create_vm_operation(
        db: AsyncSession,
        operation: Operation,
        adapter: ProxmoxAdapter,
) -> None:

    if operation.operation_type != "vm.create":
        raise RuntimeError("invalid operation type")

    if operation.status != "pending":
        raise RuntimeError("operation is not pending")

    if operation.provider_task_id is not None:
        raise RuntimeError("operation has already been started")

    vm = await db.get(VirtualMachine, operation.virtual_machine_id)

    if vm is None:
        raise RuntimeError("virtual machine is missed")

    
    request = CreateVmRequest(
        vm_id=vm.id,
        image_id=vm.image_id,
        vcpus=vm.requested_vcpus,
        memory_mb=vm.requested_memory_mb,
        storage_gb=vm.requested_storage_gb,
    )

    task = await adapter.create_vm(request)

    operation.provider_task_id = task.task_id
    operation.status = "processing"
    operation.attempts += 1

    vm.provider_vmid = task.vmid
    vm.provider_node = task.node
    vm.status = "provisioning"

    await db.flush()


async def refresh_create_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:
    if operation.operation_type != "vm.create":
        raise RuntimeError("invalid operation type")

    if operation.status != "processing":
        raise RuntimeError("operation is not processing")

    if operation.provider_task_id is None:
        raise RuntimeError("operation has no provider task id")

    vm = await db.get(VirtualMachine, operation.virtual_machine_id)

    if vm is None:
        raise RuntimeError("virtual machine is missing")

    if vm.provider_vmid is None:
        raise RuntimeError("virtual machine has no provider VMID")

    if vm.provider_node is None:
        raise RuntimeError("virtual machine has no provider node")

    task = ProviderTask(
        task_id=operation.provider_task_id,
        vmid=vm.provider_vmid,
        node=vm.provider_node,
    )

    task_status = await adapter.get_task_status(task)

    if task_status.status == "running":
        operation.updated_at = datetime.now(UTC)
        await db.flush()
        return

    if task_status.status == "succeeded":
        operation.status = "succeeded"
        operation.last_error_code = None
        vm.status = "running"

    elif task_status.status == "failed":
        operation.status = "failed"
        operation.last_error_code = (
            task_status.error_code or "provider_task_failed"
        )
        vm.status = "failed"

    else:
        raise RuntimeError("unknown provider task status")

    await db.flush()


async def process_create_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:
    if operation.status == "pending":
        await start_create_vm_operation(db, operation, adapter)

    elif operation.status == "processing":
        await refresh_create_vm_operation(db, operation, adapter)

    else:
        raise RuntimeError("operation cannot be processed")