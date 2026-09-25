import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.operations.models import Operation
from app.operations.services import (
    process_delete_vm_operation,
    process_power_off_vm_operation,
    process_reboot_vm_operation,
)
from app.proxmox.contracts import ProviderDeleteResult, ProviderTaskStatus
from app.proxmox.errors import ProviderResourceConflictError
from app.proxmox.fake import FakeProxmoxAdapter
from app.proxmox.http_adapter import HttpProxmoxAdapter
from app.virtual_machines.models import VirtualMachine
from app.virtual_machines.router import router


def make_operation(operation_type: str) -> tuple[VirtualMachine, Operation, FakeProxmoxAdapter, AsyncMock]:
    adapter = FakeProxmoxAdapter()
    vm_id = uuid4()
    vm = VirtualMachine(
        id=vm_id,
        status="stopped" if operation_type == "vm.delete" else "running",
        provider_node="fake-node",
        provider_vmid=adapter._vmid_for_vm_id(vm_id),
    )
    operation = Operation(
        virtual_machine_id=vm_id,
        operation_type=operation_type,
        status="pending",
        phase="shutdown" if operation_type == "vm.reboot" else None,
        attempts=0,
        provider_task_id=None,
    )
    db = AsyncMock()
    db.get.return_value = vm
    return vm, operation, adapter, db


@pytest.mark.parametrize("operation_type", ["vm.shutdown", "vm.stop"])
def test_power_off_finishes_after_provider_task(operation_type: str) -> None:
    vm, operation, adapter, db = make_operation(operation_type)

    asyncio.run(process_power_off_vm_operation(db, operation, adapter))
    assert operation.status == "processing"
    assert operation.provider_task_id is not None
    assert operation.attempts == 1
    assert vm.status == "running"

    asyncio.run(process_power_off_vm_operation(db, operation, adapter))
    assert operation.status == "succeeded"
    assert operation.provider_task_id is None
    assert vm.status == "stopped"


def test_shutdown_recovers_when_vm_is_already_stopped() -> None:
    vm, operation, adapter, db = make_operation("vm.shutdown")
    adapter.shutdown_vm = AsyncMock(return_value=None)

    asyncio.run(process_power_off_vm_operation(db, operation, adapter))

    assert operation.status == "succeeded"
    assert operation.provider_task_id is None
    assert vm.status == "stopped"


def test_reboot_saves_phase_between_shutdown_and_start() -> None:
    vm, operation, adapter, db = make_operation("vm.reboot")

    asyncio.run(process_reboot_vm_operation(db, operation, adapter))
    assert operation.status == "processing"
    assert operation.phase == "shutdown"

    asyncio.run(process_reboot_vm_operation(db, operation, adapter))
    assert operation.status == "pending"
    assert operation.phase == "start"
    assert operation.provider_task_id is None
    assert vm.status == "stopped"

    asyncio.run(process_reboot_vm_operation(db, operation, adapter))
    assert operation.status == "processing"
    assert operation.phase == "start"
    assert operation.attempts == 2

    asyncio.run(process_reboot_vm_operation(db, operation, adapter))
    assert operation.status == "succeeded"
    assert operation.phase == "complete"
    assert vm.status == "running"


def test_reboot_recovers_when_shutdown_already_happened() -> None:
    vm, operation, adapter, db = make_operation("vm.reboot")
    adapter.shutdown_vm = AsyncMock(return_value=None)
    adapter.start_vm = AsyncMock(return_value=None)

    asyncio.run(process_reboot_vm_operation(db, operation, adapter))
    assert operation.phase == "start"
    assert operation.status == "pending"
    assert vm.status == "stopped"

    asyncio.run(process_reboot_vm_operation(db, operation, adapter))
    assert operation.status == "succeeded"
    assert vm.status == "running"


def test_delete_keeps_history_and_finishes_after_provider_task() -> None:
    vm, operation, adapter, db = make_operation("vm.delete")

    asyncio.run(process_delete_vm_operation(db, operation, adapter))
    assert operation.status == "processing"
    assert operation.provider_task_id is not None
    assert vm.status == "deleting"

    asyncio.run(process_delete_vm_operation(db, operation, adapter))
    assert operation.status == "succeeded"
    assert operation.provider_task_id is None
    assert vm.status == "deleted"


def test_delete_retries_when_provider_has_a_lock() -> None:
    vm, operation, adapter, db = make_operation("vm.delete")

    adapter.delete_vm = AsyncMock(side_effect=[
        ProviderDeleteResult(state="in_progress"),
        ProviderDeleteResult(state="succeeded"),
    ])

    asyncio.run(process_delete_vm_operation(db, operation, adapter))
    assert operation.status == "pending"
    assert vm.status == "deleting"

    asyncio.run(process_delete_vm_operation(db, operation, adapter))
    assert operation.status == "succeeded"
    assert vm.status == "deleted"


def test_failed_delete_keeps_quota_reserved() -> None:
    vm, operation, adapter, db = make_operation("vm.delete")
    asyncio.run(process_delete_vm_operation(db, operation, adapter))
    adapter.get_task_status = AsyncMock(return_value=ProviderTaskStatus(
        status="failed", error_code="proxmox_task_failed",
    ))

    asyncio.run(process_delete_vm_operation(db, operation, adapter))

    assert operation.status == "failed"
    assert operation.last_error_code == "proxmox_task_failed"
    assert vm.status == "deleting"


def make_http_adapter(client: AsyncMock) -> HttpProxmoxAdapter:
    return HttpProxmoxAdapter(
        client,
        target_node="pve01",
        pool="npd-portal",
        template_node="pve01",
        template_vmid=9000,
        template_image_id="almalinux-9",
        storage="local-zfs",
        cloud_init_user="cloud-user",
        ipconfig0="ip=dhcp",
        nameserver="1.1.1.1",
        search_domain="example.test",
    )


def test_http_delete_checks_ownership_before_calling_provider() -> None:
    client = AsyncMock()
    client.find_vm_resource.return_value = {
        "type": "qemu", "name": "someone-else", "pool": "npd-portal", "node": "pve01",
    }
    adapter = make_http_adapter(client)

    with pytest.raises(ProviderResourceConflictError):
        asyncio.run(adapter.delete_vm(uuid4(), node="pve01", vmid=101))

    client.delete_vm.assert_not_awaited()


@pytest.mark.parametrize("lock", [None, "backup"])
def test_http_delete_only_submits_for_unlocked_stopped_vm(lock: str | None) -> None:
    client = AsyncMock()
    vm_id = uuid4()
    client.find_vm_resource.return_value = {
        "type": "qemu", "name": f"npd-{vm_id}",
        "pool": "npd-portal", "node": "pve01", "lock": lock,
    }
    client.get_vm_current_status.return_value = {"vmid": 101, "status": "stopped"}
    client.delete_vm.return_value = "UPID:test"
    adapter = make_http_adapter(client)

    result = asyncio.run(adapter.delete_vm(vm_id, node="pve01", vmid=101))

    if lock is None:
        assert result.state == "submitted"
        assert result.task is not None
        assert result.task.task_id == "UPID:test"
        client.delete_vm.assert_awaited_once_with(node="pve01", vmid=101)
    else:
        assert result.state == "in_progress"
        client.delete_vm.assert_not_awaited()


def test_http_delete_refuses_running_vm() -> None:
    client = AsyncMock()
    vm_id = uuid4()
    client.find_vm_resource.return_value = {
        "type": "qemu", "name": f"npd-{vm_id}",
        "pool": "npd-portal", "node": "pve01",
    }
    client.get_vm_current_status.return_value = {"vmid": 101, "status": "running"}
    adapter = make_http_adapter(client)

    with pytest.raises(RuntimeError, match="must be stopped"):
        asyncio.run(adapter.delete_vm(vm_id, node="pve01", vmid=101))

    client.delete_vm.assert_not_awaited()


def test_http_delete_recovers_when_vm_is_already_absent() -> None:
    client = AsyncMock()
    client.find_vm_resource.return_value = None
    adapter = make_http_adapter(client)

    result = asyncio.run(adapter.delete_vm(uuid4(), node="pve01", vmid=101))

    assert result.state == "succeeded"
    client.delete_vm.assert_not_awaited()


def test_http_start_checks_owned_vm_state_once() -> None:
    client = AsyncMock()
    vm_id = uuid4()
    client.find_vm_resource.return_value = {
        "type": "qemu", "name": f"npd-{vm_id}",
        "pool": "npd-portal", "node": "pve01",
    }
    client.get_vm_current_status.return_value = {"vmid": 101, "status": "stopped"}
    client.start_vm.return_value = "UPID:start"
    adapter = make_http_adapter(client)

    task = asyncio.run(adapter.start_vm(vm_id, node="pve01", vmid=101))

    assert task is not None and task.task_id == "UPID:start"
    client.find_vm_resource.assert_awaited_once_with(101)
    client.get_vm_current_status.assert_awaited_once_with(node="pve01", vmid=101)
    client.start_vm.assert_awaited_once_with(node="pve01", vmid=101)


def test_http_power_state_reports_missing_vm_without_status_request() -> None:
    client = AsyncMock()
    client.find_vm_resource.return_value = None
    adapter = make_http_adapter(client)

    state = asyncio.run(adapter.get_vm_power_state(uuid4(), node="pve01", vmid=101))

    assert state.status == "missing"
    client.get_vm_current_status.assert_not_awaited()


def test_http_power_state_reports_lock_on_owned_vm() -> None:
    client = AsyncMock()
    vm_id = uuid4()
    client.find_vm_resource.return_value = {
        "type": "qemu", "name": f"npd-{vm_id}",
        "pool": "npd-portal", "node": "pve01", "lock": "clone",
    }
    client.get_vm_current_status.return_value = {"vmid": 101, "status": "stopped"}
    adapter = make_http_adapter(client)

    state = asyncio.run(adapter.get_vm_power_state(vm_id, node="pve01", vmid=101))

    assert state.status == "stopped"
    assert state.locked is True


def test_http_power_state_checks_lock_in_current_status_too() -> None:
    client = AsyncMock()
    vm_id = uuid4()
    client.find_vm_resource.return_value = {
        "type": "qemu", "name": f"npd-{vm_id}",
        "pool": "npd-portal", "node": "pve01",
    }
    client.get_vm_current_status.return_value = {
        "vmid": 101, "status": "stopped", "lock": "clone",
    }
    adapter = make_http_adapter(client)

    state = asyncio.run(adapter.get_vm_power_state(vm_id, node="pve01", vmid=101))

    assert state.locked is True


def test_all_lifecycle_routes_are_registered() -> None:
    paths = {route.path for route in router.routes}
    for action in ("start", "shutdown", "stop", "reboot", "delete"):
        assert f"/compute/vms/{{vm_id}}/{action}" in paths
