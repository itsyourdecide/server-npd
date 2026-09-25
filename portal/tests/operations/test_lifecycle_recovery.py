import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.operations.models import Operation
from app.proxmox.fake import FakeProxmoxAdapter
from app.virtual_machines.models import VirtualMachine
import app.workers.operation_worker as worker


def make_worker_state(operation_type: str, *, phase: str | None = None):
    adapter = FakeProxmoxAdapter()
    vm_id = uuid4()
    vm_status = "stopped" if operation_type == "vm.delete" or phase == "start" else "running"
    vm = VirtualMachine(
        id=vm_id,
        status=vm_status,
        provider_node="fake-node",
        provider_vmid=adapter._vmid_for_vm_id(vm_id),
    )
    adapter._power_states[vm.provider_vmid] = vm_status
    operation = Operation(
        id=uuid4(),
        virtual_machine_id=vm_id,
        operation_type=operation_type,
        status="pending",
        phase=phase,
        provider_task_id=None,
        attempts=0,
    )

    class TestSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def begin(self):
            return self

        async def scalar(self, statement):
            return operation

        async def get(self, model, key, **kwargs):
            return vm if model is VirtualMachine else operation

    return vm, operation, adapter, TestSession


@pytest.mark.parametrize(
    ("operation_type", "target_status"),
    [("vm.shutdown", "stopped"), ("vm.stop", "stopped"), ("vm.delete", "deleted")],
)
def test_lifecycle_worker_dispatch_and_task_poll(monkeypatch, operation_type, target_status) -> None:
    vm, operation, adapter, session_factory = make_worker_state(operation_type)
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "processing"
    assert operation.provider_task_id is not None

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "succeeded"
    assert vm.status == target_status


def test_reboot_worker_keeps_shutdown_and_start_as_separate_phases(monkeypatch) -> None:
    vm, operation, adapter, session_factory = make_worker_state("vm.reboot", phase="shutdown")
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.phase == "shutdown"
    assert operation.provider_task_id is not None

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.phase == "start"
    assert operation.status == "pending"
    assert vm.status == "stopped"

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.phase == "start"
    assert operation.provider_task_id is not None

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "succeeded"
    assert vm.status == "running"


@pytest.mark.parametrize(
    ("operation_type", "command", "target_status"),
    [
        ("vm.shutdown", "shutdown_vm", "stopped"),
        ("vm.stop", "stop_vm", "stopped"),
        ("vm.delete", "delete_vm", "deleted"),
    ],
)
def test_lifecycle_reconciles_lost_response_without_resubmitting(
    monkeypatch, operation_type, command, target_status,
) -> None:
    vm, operation, adapter, session_factory = make_worker_state(operation_type)
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    original_command = getattr(adapter, command)

    async def accepted_then_timeout(*args, **kwargs):
        await original_command(*args, **kwargs)
        raise TimeoutError("response was lost")

    lost_response = AsyncMock(side_effect=accepted_then_timeout)
    setattr(adapter, command, lost_response)

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "processing"
    assert operation.phase == f"reconcile_{operation_type.removeprefix('vm.')}"
    assert operation.provider_task_id is None
    assert lost_response.await_count == 1

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "succeeded"
    assert vm.status == target_status
    assert lost_response.await_count == 1


@pytest.mark.parametrize("phase", ["shutdown", "start"])
def test_reboot_reconciles_each_phase_after_lost_response(monkeypatch, phase) -> None:
    vm, operation, adapter, session_factory = make_worker_state("vm.reboot", phase=phase)
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    original_command = getattr(adapter, f"{phase}_vm")

    async def accepted_then_timeout(*args, **kwargs):
        await original_command(*args, **kwargs)
        raise TimeoutError("response was lost")

    lost_response = AsyncMock(side_effect=accepted_then_timeout)
    setattr(adapter, f"{phase}_vm", lost_response)

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.phase == f"reconcile_reboot_{phase}"
    assert operation.provider_task_id is None

    assert asyncio.run(worker.run_once(adapter)) is True
    if phase == "shutdown":
        assert operation.status == "pending"
        assert operation.phase == "start"
        assert vm.status == "stopped"
    else:
        assert operation.status == "succeeded"
        assert vm.status == "running"
    assert lost_response.await_count == 1
