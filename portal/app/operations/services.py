from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.operations.models import Operation
from app.proxmox.contracts import (
    CreateVmRequest,
    ProviderCloneResult,
    ProviderDeleteResult,
    ProviderPlacement,
    ProviderTask,
    ProxmoxAdapter,
)
from app.ssh_keys.models import SshPublicKey
from app.virtual_machines.models import VirtualMachine


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

    if operation.phase != "clone":
        raise RuntimeError("operation is not in clone phase")

    vm = await db.get(VirtualMachine, operation.virtual_machine_id)

    if vm is None:
        raise RuntimeError("virtual machine is missing")

    request = await _build_create_vm_request(db, vm)

    # Одно поле есть, другого нет — данные в неконсистентном состоянии.
    if (vm.provider_node is None) != (vm.provider_vmid is None):
        raise RuntimeError("incomplete provider placement")

    # Первый проход: только выбираем место и сохраняем его.
    if vm.provider_node is None:
        target = await adapter.choose_clone_target(request)
        vm.provider_node = target.node
        vm.provider_vmid = target.vmid
        return

    # Второй проход: используем именно сохранённые node и VMID.
    result = await adapter.clone_vm(
        request,
        node=vm.provider_node,
        vmid=vm.provider_vmid,
    )

    if result.state == "submitted":
        task = result.task

        if task is None:
            raise RuntimeError("submitted clone has no provider task")

        if task.node != vm.provider_node or task.vmid != vm.provider_vmid:
            raise RuntimeError(
                "provider task targets another virtual machine"
            )

        operation.provider_task_id = task.task_id
        operation.status = "processing"
        vm.status = "provisioning"

    elif result.state == "in_progress":
        if result.task is not None:
            raise RuntimeError(
                "recovered clone unexpectedly has a provider task"
            )

        # Без UPID воркер дальше сверяет состояние VM, не отправляя clone повторно.
        operation.updated_at = datetime.now(UTC)
        vm.status = "provisioning"

    elif result.state == "succeeded":
        if result.task is not None:
            raise RuntimeError(
                "recovered clone unexpectedly has a provider task"
            )

        # Clone уже завершился раньше, но его UPID не сохранился.
        operation.phase = "configure"
        operation.status = "pending"
        operation.provider_task_id = None
        operation.last_error_code = None
        vm.status = "provisioning"

    else:
        raise RuntimeError(
            f"unknown clone result state: {result.state}"
        )

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
        operation.last_error_code = None
        operation.updated_at = datetime.now(UTC)
        await db.flush()
        return

    if task_status.status == "succeeded":
        if operation.phase == "clone":
            operation.phase = "configure"
            operation.status = "pending"
        elif operation.phase == "configure":
            operation.phase = "resize"
            operation.status = "pending"
        elif operation.phase == "resize":
            operation.phase = "start"
            operation.status = "pending"
        elif operation.phase == "start":
            operation.phase = "complete"
            operation.status = "succeeded"
            vm.status = "running"
        else:
            raise RuntimeError(f"unsupported create phase: {operation.phase}")

        operation.provider_task_id = None
        operation.last_error_code = None

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
        if operation.phase == "clone":
            await start_create_vm_operation(db, operation, adapter)
        elif operation.phase == "configure":
            await start_configure_vm_operation(db, operation, adapter)
        elif operation.phase == "resize":
            await start_resize_vm_operation(db, operation, adapter)
        elif operation.phase == "start":
            await start_initial_vm_operation(db, operation, adapter)
        else:
            raise RuntimeError(f"unsupported create phase: {operation.phase}")

    elif operation.status == "processing":
        await refresh_create_vm_operation(db, operation, adapter)

    else:
        raise RuntimeError("operation cannot be processed")


async def prepare_create_vm_dispatch(
    db: AsyncSession,
    operation: Operation,
) -> tuple[CreateVmRequest | None, ProviderPlacement]:
    if operation.operation_type != "vm.create" or operation.status != "pending":
        raise RuntimeError("operation is not a pending VM create")

    if operation.provider_task_id is not None:
        raise RuntimeError("pending create already has a provider task")

    if operation.phase not in {"clone", "configure", "resize", "start"}:
        raise RuntimeError(f"unsupported create phase: {operation.phase}")

    vm = await _get_lifecycle_vm(db, operation)
    request = None if operation.phase == "start" else await _build_create_vm_request(db, vm)

    operation.status = "processing"
    operation.phase = f"dispatch_create_{operation.phase}"
    operation.attempts += 1
    operation.updated_at = datetime.now(UTC)

    return request, ProviderPlacement(node=vm.provider_node, vmid=vm.provider_vmid)


async def finish_create_vm_dispatch(
    db: AsyncSession,
    operation: Operation,
    phase: str,
    result: ProviderCloneResult | ProviderTask | None,
) -> None:
    if operation.operation_type != "vm.create" or operation.status != "processing":
        raise RuntimeError("operation is not dispatching VM create")

    if operation.phase != f"dispatch_create_{phase}" or operation.provider_task_id is not None:
        raise RuntimeError("VM create dispatch state changed")

    vm = await _get_lifecycle_vm(db, operation)

    if phase == "clone":
        if not isinstance(result, ProviderCloneResult):
            raise RuntimeError("invalid provider clone result")

        if result.state == "in_progress":
            if result.task is not None:
                raise RuntimeError("in-progress clone unexpectedly has a provider task")
            operation.phase = "reconcile_create_clone"
            operation.last_error_code = "provider_outcome_unknown"
            operation.updated_at = datetime.now(UTC)
            vm.status = "provisioning"
            return

        if result.state == "succeeded":
            if result.task is not None:
                raise RuntimeError("completed clone unexpectedly has a provider task")
            operation.status = "pending"
            operation.phase = "configure"
            operation.last_error_code = None
            vm.status = "provisioning"
            return

        if result.state != "submitted" or result.task is None:
            raise RuntimeError("submitted clone has no provider task")
        task = result.task
        vm.status = "provisioning"

    else:
        if result is not None and not isinstance(result, ProviderTask):
            raise RuntimeError("invalid provider task result")
        task = result

    if task is not None:
        if task.node != vm.provider_node or task.vmid != vm.provider_vmid:
            raise RuntimeError("provider task targets another virtual machine")
        operation.provider_task_id = task.task_id
        operation.phase = phase
        operation.last_error_code = None
        return

    if phase == "configure":
        operation.status = "pending"
        operation.phase = "resize"
    elif phase == "resize":
        operation.status = "pending"
        operation.phase = "start"
    elif phase == "start":
        operation.status = "succeeded"
        operation.phase = "complete"
        vm.status = "running"
    else:
        raise RuntimeError(f"unsupported create dispatch phase: {phase}")
    operation.last_error_code = None


async def reconcile_create_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:
    if operation.operation_type != "vm.create" or operation.status != "processing":
        raise RuntimeError("invalid create operation")

    if operation.provider_task_id is not None:
        raise RuntimeError("reconciling create already has a provider task")

    phase = operation.phase
    if phase not in {
        "dispatch_create_clone", "reconcile_create_clone",
        "dispatch_create_configure", "reconcile_create_configure",
        "dispatch_create_resize", "reconcile_create_resize",
        "dispatch_create_start", "reconcile_create_start",
    }:
        raise RuntimeError(f"unsupported create reconciliation phase: {phase}")

    vm = await _get_lifecycle_vm(db, operation)

    if phase.endswith("_clone") or phase.endswith("_start"):
        state = await adapter.get_vm_power_state(
            vm.id, node=vm.provider_node, vmid=vm.provider_vmid,
        )

        if phase.endswith("_clone") and state.status == "stopped" and not state.locked:
            operation.status = "pending"
            operation.phase = "configure"
            operation.last_error_code = None
            vm.status = "provisioning"
            return

        if phase.endswith("_start") and state.status == "running" and not state.locked:
            operation.status = "succeeded"
            operation.phase = "complete"
            operation.last_error_code = None
            vm.status = "running"
            return

    # Configure и resize нельзя безопасно повторить без проверки их параметров.
    # После одной сверки оставляем операцию для ручного разбора без опроса каждые 10 секунд.
    if phase.endswith(("_configure", "_resize")):
        operation.phase = phase.replace("dispatch_", "needs_review_", 1).replace(
            "reconcile_", "needs_review_", 1,
        )
    else:
        operation.phase = phase.replace("dispatch_", "reconcile_", 1)
    operation.last_error_code = "provider_outcome_unknown"
    operation.updated_at = datetime.now(UTC)


async def _build_create_vm_request(
    db: AsyncSession,
    vm: VirtualMachine,
) -> CreateVmRequest:
    
    if vm.ssh_public_key_id is None:
        raise RuntimeError("virtual machine has no SSH public key")
    
    ssh_key = await db.get(SshPublicKey, vm.ssh_public_key_id)
    
    if ssh_key is None:
        raise RuntimeError("virtual machine references missing SSH public key")
    
    if ssh_key.owner_user_id != vm.owner_user_id:
        raise RuntimeError("SSH public key belongs to another user")
    
    request = CreateVmRequest(
        vm_id=vm.id,
        image_id=vm.image_id,
        vcpus=vm.requested_vcpus,
        memory_mb=vm.requested_memory_mb,
        storage_gb=vm.requested_storage_gb,
        ssh_public_key=ssh_key.public_key,
    )

    return request


async def start_configure_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:
    
    if operation.status != "pending":
        raise RuntimeError("operation is not pending")

    if operation.phase != "configure":
        raise RuntimeError("operation phase is not configure")

    vm = await db.get(VirtualMachine, operation.virtual_machine_id)

    if vm is None:
        raise RuntimeError("virtual machine is missed")

    if vm.provider_node is None:
        raise RuntimeError("virtual machine provider node is missed")

    if vm.provider_vmid is None:
        raise RuntimeError("virtual machine provider vmid is missed")

    request = await _build_create_vm_request(db, vm)

    task = await adapter.configure_vm(request, node=vm.provider_node, vmid=vm.provider_vmid)

    if task is None:
        operation.phase = "resize"
        operation.status = "pending"
        operation.provider_task_id = None

    else:
        operation.phase = "configure"
        operation.status = "processing"
        operation.provider_task_id = task.task_id


async def start_resize_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:

    if operation.status != "pending":
            raise RuntimeError("operation is not pending")

    if operation.phase != "resize":
        raise RuntimeError("operation phase is not resize")

    vm = await db.get(VirtualMachine, operation.virtual_machine_id)

    if vm is None:
            raise RuntimeError("virtual machine is missed")

    if vm.provider_node is None:
        raise RuntimeError("virtual machine provider node is missed")

    if vm.provider_vmid is None:
        raise RuntimeError("virtual machine provider vmid is missed")

    request = await _build_create_vm_request(db, vm)

    task = await adapter.resize_vm_disk(
        request,
        node=vm.provider_node,
        vmid=vm.provider_vmid,
    )

    if task is None:
        operation.phase = "start"
        operation.status = "pending"
        operation.provider_task_id = None
        return

    operation.status = "processing"
    operation.provider_task_id = task.task_id


async def start_initial_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:

    if operation.status != "pending":
            raise RuntimeError("operation is not pending")

    if operation.phase != "start":
        raise RuntimeError("operation phase is not start")

    vm = await db.get(VirtualMachine, operation.virtual_machine_id)

    if vm is None:
            raise RuntimeError("virtual machine is missed")

    if vm.provider_node is None:
        raise RuntimeError("virtual machine provider node is missed")

    if vm.provider_vmid is None:
        raise RuntimeError("virtual machine provider vmid is missed")

    task = await adapter.start_vm(
        vm.id,
        node=vm.provider_node,
        vmid=vm.provider_vmid,
    )

    if task is None:
        operation.phase = "complete"
        operation.status = "succeeded"
        operation.provider_task_id = None
        operation.last_error_code = None
        vm.status = "running"
        return

    operation.provider_task_id = task.task_id
    operation.status = "processing"


async def process_start_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:

    if operation.operation_type != "vm.start":
        raise RuntimeError("invalid operation type")

    if operation.status != "processing":
        raise RuntimeError("operation cannot be processed")
    
    vm = await db.get(VirtualMachine, operation.virtual_machine_id)
    if vm is None:
            raise RuntimeError("virtual machine is missed")
    if vm.provider_node is None:
        raise RuntimeError("virtual machine provider node is missed")
    if vm.provider_vmid is None:
        raise RuntimeError("virtual machine provider vmid is missed")

    
    if operation.provider_task_id is None:
        raise RuntimeError("processing operation has no provider task")
    
    task = ProviderTask(
        task_id=operation.provider_task_id,
        vmid=vm.provider_vmid,
        node=vm.provider_node,
    )
    task_status = await adapter.get_task_status(task)

    if task_status.status == "running":
        operation.phase = "await_task"
        operation.last_error_code = None
        operation.updated_at = datetime.now(UTC)
        await db.flush()
        return

    if task_status.status == "succeeded":
        operation.status = "succeeded"
        operation.phase = "complete"
        operation.provider_task_id = None
        operation.last_error_code = None
        vm.status = "running"
        return

    if task_status.status == "failed":
        operation.status = "failed"
        operation.last_error_code = (
            task_status.error_code or "provider_task_failed"
        )
        return

    raise RuntimeError(f"unknown provider task status: {task_status.status}")


async def prepare_start_vm_dispatch(
    db: AsyncSession,
    operation: Operation,
) -> ProviderPlacement:
    if operation.operation_type != "vm.start" or operation.status != "pending":
        raise RuntimeError("operation is not a pending VM start")

    if operation.provider_task_id is not None:
        raise RuntimeError("pending operation already has a provider task")

    vm = await _get_lifecycle_vm(db, operation)

    # Сохраняем маркер ДО вызова Proxmox. После сбоя нельзя вслепую повторить start.
    operation.status = "processing"
    operation.phase = "dispatching"
    operation.attempts += 1
    operation.updated_at = datetime.now(UTC)

    return ProviderPlacement(node=vm.provider_node, vmid=vm.provider_vmid)


async def finish_start_vm_dispatch(
    db: AsyncSession,
    operation: Operation,
    task: ProviderTask | None,
) -> None:
    if operation.operation_type != "vm.start" or operation.phase != "dispatching":
        raise RuntimeError("VM start is not dispatching")

    if operation.status != "processing" or operation.provider_task_id is not None:
        raise RuntimeError("invalid VM start dispatch state")

    vm = await _get_lifecycle_vm(db, operation)

    if task is None:
        operation.status = "succeeded"
        operation.phase = "complete"
        operation.last_error_code = None
        vm.status = "running"
        return

    if task.node != vm.provider_node or task.vmid != vm.provider_vmid:
        raise RuntimeError("provider task targets another virtual machine")

    operation.provider_task_id = task.task_id
    operation.phase = "await_task"
    operation.last_error_code = None


async def reconcile_start_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:
    if operation.operation_type != "vm.start" or operation.status != "processing":
        raise RuntimeError("invalid VM start operation")

    if operation.phase not in {"dispatching", "reconcile"}:
        raise RuntimeError("VM start does not need reconciliation")

    if operation.provider_task_id is not None:
        raise RuntimeError("reconciling operation already has a provider task")

    vm = await _get_lifecycle_vm(db, operation)
    state = await adapter.get_vm_power_state(
        vm.id,
        node=vm.provider_node,
        vmid=vm.provider_vmid,
    )

    if state.status == "running" and not state.locked:
        operation.status = "succeeded"
        operation.phase = "complete"
        operation.last_error_code = None
        vm.status = "running"
        return

    # Нет UPID, а результат ещё не подтверждён. Дальше только чтение состояния.
    operation.phase = "reconcile"
    operation.last_error_code = "provider_outcome_unknown"
    operation.updated_at = datetime.now(UTC)


async def _get_lifecycle_vm(
    db: AsyncSession,
    operation: Operation,
) -> VirtualMachine:
    vm = await db.get(VirtualMachine, operation.virtual_machine_id)

    if vm is None:
        raise RuntimeError("virtual machine is missing")

    if vm.provider_node is None or vm.provider_vmid is None:
        raise RuntimeError("virtual machine has incomplete provider placement")

    return vm


async def prepare_lifecycle_dispatch(
    db: AsyncSession,
    operation: Operation,
) -> tuple[str, ProviderPlacement]:
    if operation.status != "pending" or operation.provider_task_id is not None:
        raise RuntimeError("lifecycle operation is not ready for dispatch")

    if operation.operation_type == "vm.shutdown":
        command = "shutdown"
    elif operation.operation_type == "vm.stop":
        command = "stop"
    elif operation.operation_type == "vm.delete":
        command = "delete"
    elif operation.operation_type == "vm.reboot" and operation.phase in {"shutdown", "start"}:
        command = operation.phase
    else:
        raise RuntimeError("unsupported lifecycle operation")

    vm = await _get_lifecycle_vm(db, operation)

    # Как и для start, сначала фиксируем возможную отправку команды в БД.
    operation.status = "processing"
    operation.phase = (
        f"dispatch_reboot_{command}"
        if operation.operation_type == "vm.reboot"
        else f"dispatch_{command}"
    )
    operation.attempts += 1
    operation.updated_at = datetime.now(UTC)

    if command == "delete":
        vm.status = "deleting"

    return command, ProviderPlacement(node=vm.provider_node, vmid=vm.provider_vmid)


async def finish_lifecycle_dispatch(
    db: AsyncSession,
    operation: Operation,
    result: ProviderTask | ProviderDeleteResult | None,
) -> None:
    if operation.status != "processing" or operation.provider_task_id is not None:
        raise RuntimeError("invalid lifecycle dispatch state")

    vm = await _get_lifecycle_vm(db, operation)

    if operation.operation_type == "vm.delete":
        if operation.phase != "dispatch_delete" or not isinstance(result, ProviderDeleteResult):
            raise RuntimeError("invalid delete result")

        if result.state == "succeeded":
            if result.task is not None:
                raise RuntimeError("completed delete unexpectedly has a provider task")
            operation.status = "succeeded"
            operation.phase = "complete"
            operation.last_error_code = None
            vm.status = "deleted"
            return

        if result.state == "in_progress":
            if result.task is not None:
                raise RuntimeError("in-progress delete unexpectedly has a provider task")
            operation.phase = "reconcile_delete"
            operation.last_error_code = "provider_outcome_unknown"
            operation.updated_at = datetime.now(UTC)
            return

        if result.state != "submitted" or result.task is None:
            raise RuntimeError("submitted delete has no provider task")
        task = result.task

    else:
        if result is not None and not isinstance(result, ProviderTask):
            raise RuntimeError("invalid lifecycle provider task")
        task = result

    if task is not None:
        if task.node != vm.provider_node or task.vmid != vm.provider_vmid:
            raise RuntimeError("provider task targets another virtual machine")
        operation.provider_task_id = task.task_id
        operation.last_error_code = None

        if operation.operation_type == "vm.reboot":
            if operation.phase == "dispatch_reboot_shutdown":
                operation.phase = "shutdown"
            elif operation.phase == "dispatch_reboot_start":
                operation.phase = "start"
            else:
                raise RuntimeError("unsupported reboot dispatch phase")
        else:
            operation.phase = "await_task"
        return

    if operation.phase in {"dispatch_shutdown", "dispatch_stop"}:
        operation.status = "succeeded"
        operation.phase = "complete"
        operation.last_error_code = None
        vm.status = "stopped"
    elif operation.phase == "dispatch_reboot_shutdown":
        operation.status = "pending"
        operation.phase = "start"
        operation.last_error_code = None
        vm.status = "stopped"
    elif operation.phase == "dispatch_reboot_start":
        operation.status = "succeeded"
        operation.phase = "complete"
        operation.last_error_code = None
        vm.status = "running"
    else:
        raise RuntimeError(f"unsupported lifecycle dispatch phase: {operation.phase}")


async def reconcile_lifecycle_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:
    if operation.status != "processing" or operation.provider_task_id is not None:
        raise RuntimeError("lifecycle operation does not need reconciliation")

    phase = operation.phase
    allowed_phases = {
        "dispatch_shutdown", "reconcile_shutdown",
        "dispatch_stop", "reconcile_stop",
        "dispatch_delete", "reconcile_delete",
        "dispatch_reboot_shutdown", "reconcile_reboot_shutdown",
        "dispatch_reboot_start", "reconcile_reboot_start",
    }
    if phase not in allowed_phases:
        raise RuntimeError(f"unsupported lifecycle reconciliation phase: {phase}")

    vm = await _get_lifecycle_vm(db, operation)
    state = await adapter.get_vm_power_state(
        vm.id, node=vm.provider_node, vmid=vm.provider_vmid,
    )

    if phase in {"dispatch_delete", "reconcile_delete"} and state.status == "missing":
        operation.status = "succeeded"
        operation.phase = "complete"
        operation.last_error_code = None
        vm.status = "deleted"
        return

    if state.status == "stopped" and not state.locked:
        if phase in {"dispatch_shutdown", "reconcile_shutdown", "dispatch_stop", "reconcile_stop"}:
            operation.status = "succeeded"
            operation.phase = "complete"
            operation.last_error_code = None
            vm.status = "stopped"
            return

        if phase in {"dispatch_reboot_shutdown", "reconcile_reboot_shutdown"}:
            operation.status = "pending"
            operation.phase = "start"
            operation.last_error_code = None
            vm.status = "stopped"
            return

    if state.status == "running" and not state.locked:
        if phase in {"dispatch_reboot_start", "reconcile_reboot_start"}:
            operation.status = "succeeded"
            operation.phase = "complete"
            operation.last_error_code = None
            vm.status = "running"
            return

    # Цель не подтверждена: команда не отправляется повторно без UPID.
    operation.phase = phase.replace("dispatch_", "reconcile_", 1)
    operation.last_error_code = "provider_outcome_unknown"
    operation.updated_at = datetime.now(UTC)


async def process_power_off_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:
    if operation.operation_type not in {"vm.shutdown", "vm.stop"}:
        raise RuntimeError("invalid operation type")

    if operation.status not in {"pending", "processing"}:
        raise RuntimeError("operation cannot be processed")

    vm = await _get_lifecycle_vm(db, operation)

    if operation.status == "pending":
        if operation.provider_task_id is not None:
            raise RuntimeError("pending operation already has a provider task")

        if operation.operation_type == "vm.shutdown":
            task = await adapter.shutdown_vm(
                vm.id, node=vm.provider_node, vmid=vm.provider_vmid,
            )
        else:
            task = await adapter.stop_vm(
                vm.id, node=vm.provider_node, vmid=vm.provider_vmid,
            )

        if task is None:
            # После сбоя ответа Proxmox VM уже могла успеть выключиться.
            operation.status = "succeeded"
            operation.phase = "complete"
            operation.last_error_code = None
            vm.status = "stopped"
            return

        if task.node != vm.provider_node or task.vmid != vm.provider_vmid:
            raise RuntimeError("provider task targets another virtual machine")

        operation.provider_task_id = task.task_id
        operation.status = "processing"
        operation.attempts += 1
        return

    if operation.provider_task_id is None:
        raise RuntimeError("processing operation has no provider task")

    task = ProviderTask(
        task_id=operation.provider_task_id,
        node=vm.provider_node,
        vmid=vm.provider_vmid,
    )
    task_status = await adapter.get_task_status(task)

    if task_status.status == "running":
        operation.updated_at = datetime.now(UTC)
        return

    if task_status.status == "succeeded":
        operation.status = "succeeded"
        operation.phase = "complete"
        operation.provider_task_id = None
        operation.last_error_code = None
        vm.status = "stopped"
        return

    if task_status.status == "failed":
        operation.status = "failed"
        operation.last_error_code = task_status.error_code or "provider_task_failed"
        return

    raise RuntimeError(f"unknown provider task status: {task_status.status}")


async def process_reboot_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:
    if operation.operation_type != "vm.reboot":
        raise RuntimeError("invalid operation type")

    if operation.status not in {"pending", "processing"}:
        raise RuntimeError("operation cannot be processed")

    if operation.phase not in {"shutdown", "start"}:
        raise RuntimeError(f"unsupported reboot phase: {operation.phase}")

    vm = await _get_lifecycle_vm(db, operation)

    if operation.status == "pending":
        if operation.provider_task_id is not None:
            raise RuntimeError("pending operation already has a provider task")

        if operation.phase == "shutdown":
            task = await adapter.shutdown_vm(
                vm.id, node=vm.provider_node, vmid=vm.provider_vmid,
            )
        else:
            task = await adapter.start_vm(
                vm.id, node=vm.provider_node, vmid=vm.provider_vmid,
            )

        if task is None:
            if operation.phase == "shutdown":
                # Фазу сохраняем в БД: после рестарта воркер начнёт с запуска.
                operation.phase = "start"
                vm.status = "stopped"
            else:
                operation.status = "succeeded"
                operation.phase = "complete"
                operation.last_error_code = None
                vm.status = "running"
            return

        if task.node != vm.provider_node or task.vmid != vm.provider_vmid:
            raise RuntimeError("provider task targets another virtual machine")

        operation.provider_task_id = task.task_id
        operation.status = "processing"
        operation.attempts += 1
        return

    if operation.provider_task_id is None:
        raise RuntimeError("processing operation has no provider task")

    task = ProviderTask(
        task_id=operation.provider_task_id,
        node=vm.provider_node,
        vmid=vm.provider_vmid,
    )
    task_status = await adapter.get_task_status(task)

    if task_status.status == "running":
        operation.updated_at = datetime.now(UTC)
        return

    if task_status.status == "succeeded":
        operation.provider_task_id = None
        operation.last_error_code = None

        if operation.phase == "shutdown":
            operation.phase = "start"
            operation.status = "pending"
            vm.status = "stopped"
        else:
            operation.status = "succeeded"
            operation.phase = "complete"
            vm.status = "running"
        return

    if task_status.status == "failed":
        operation.status = "failed"
        operation.last_error_code = task_status.error_code or "provider_task_failed"
        return

    raise RuntimeError(f"unknown provider task status: {task_status.status}")


async def process_delete_vm_operation(
    db: AsyncSession,
    operation: Operation,
    adapter: ProxmoxAdapter,
) -> None:
    if operation.operation_type != "vm.delete":
        raise RuntimeError("invalid operation type")

    if operation.status not in {"pending", "processing"}:
        raise RuntimeError("operation cannot be processed")

    vm = await _get_lifecycle_vm(db, operation)

    if operation.status == "pending":
        if operation.provider_task_id is not None:
            raise RuntimeError("pending operation already has a provider task")

        result = await adapter.delete_vm(
            vm.id, node=vm.provider_node, vmid=vm.provider_vmid,
        )

        if result.state == "submitted":
            task = result.task

            if task is None:
                raise RuntimeError("submitted delete has no provider task")

            if task.node != vm.provider_node or task.vmid != vm.provider_vmid:
                raise RuntimeError("provider task targets another virtual machine")

            operation.provider_task_id = task.task_id
            operation.status = "processing"
            operation.attempts += 1
            vm.status = "deleting"

        elif result.state == "in_progress":
            if result.task is not None:
                raise RuntimeError("in-progress delete unexpectedly has a provider task")

            # UPID мог потеряться при сбое; повторно проверим VM позже.
            operation.updated_at = datetime.now(UTC)
            vm.status = "deleting"

        elif result.state == "succeeded":
            if result.task is not None:
                raise RuntimeError("completed delete unexpectedly has a provider task")

            # Историю VM и операции оставляем в БД, а квоту освобождает статус deleted.
            operation.status = "succeeded"
            operation.phase = "complete"
            operation.last_error_code = None
            vm.status = "deleted"

        else:
            raise RuntimeError(f"unknown delete result state: {result.state}")

        return

    if operation.provider_task_id is None:
        raise RuntimeError("processing operation has no provider task")

    task = ProviderTask(
        task_id=operation.provider_task_id,
        node=vm.provider_node,
        vmid=vm.provider_vmid,
    )
    task_status = await adapter.get_task_status(task)

    if task_status.status == "running":
        operation.updated_at = datetime.now(UTC)
        return

    if task_status.status == "succeeded":
        operation.status = "succeeded"
        operation.phase = "complete"
        operation.provider_task_id = None
        operation.last_error_code = None
        vm.status = "deleted"
        return

    if task_status.status == "failed":
        operation.status = "failed"
        operation.last_error_code = task_status.error_code or "provider_task_failed"
        # Не освобождаем квоту: Proxmox мог удалить лишь часть ресурсов.
        vm.status = "deleting"
        return

    raise RuntimeError(f"unknown provider task status: {task_status.status}")
