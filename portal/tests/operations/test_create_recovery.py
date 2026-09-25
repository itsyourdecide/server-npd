import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.operations.models import Operation
from app.proxmox.fake import FakeProxmoxAdapter
from app.ssh_keys.models import SshPublicKey
from app.virtual_machines.models import VirtualMachine
import app.workers.operation_worker as worker


def make_create_state():
    adapter = FakeProxmoxAdapter()
    user_id = uuid4()
    ssh_key = SshPublicKey(
        id=uuid4(),
        owner_user_id=user_id,
        public_key="ssh-ed25519 AAAA test",
    )
    vm = VirtualMachine(
        id=uuid4(),
        owner_user_id=user_id,
        status="pending",
        requested_vcpus=2,
        requested_memory_mb=4096,
        requested_storage_gb=30,
        image_id="test-image",
        ssh_public_key_id=ssh_key.id,
    )
    operation = Operation(
        id=uuid4(),
        virtual_machine_id=vm.id,
        operation_type="vm.create",
        status="pending",
        phase="clone",
        provider_task_id=None,
        attempts=0,
    )

    class TestSession:
        transaction_open = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def begin(self):
            class Transaction:
                async def __aenter__(self):
                    TestSession.transaction_open = True
                    self.operation_before = operation.__dict__.copy()
                    self.vm_before = vm.__dict__.copy()

                async def __aexit__(self, exc_type, exc, traceback):
                    if exc_type is not None:
                        operation.__dict__.clear()
                        operation.__dict__.update(self.operation_before)
                        vm.__dict__.clear()
                        vm.__dict__.update(self.vm_before)
                    TestSession.transaction_open = False
                    return False

            return Transaction()

        async def scalar(self, statement):
            return operation

        async def get(self, model, key, **kwargs):
            return {
                Operation: operation,
                VirtualMachine: vm,
                SshPublicKey: ssh_key,
            }[model]

        async def flush(self):
            pass

    return vm, operation, adapter, TestSession


def test_create_worker_completes_all_phases(monkeypatch) -> None:
    vm, operation, adapter, session_factory = make_create_state()
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    for name in ("clone_vm", "configure_vm", "resize_vm_disk", "start_vm"):
        original = getattr(adapter, name)

        async def checked(*args, _original=original, **kwargs):
            assert session_factory.transaction_open is False
            return await _original(*args, **kwargs)

        setattr(adapter, name, checked)

    for _ in range(12):
        if operation.status == "succeeded":
            break
        assert asyncio.run(worker.run_once(adapter)) is True

    assert operation.status == "succeeded"
    assert operation.phase == "complete"
    assert vm.status == "running"
    assert operation.attempts == 4
    assert vm.provider_vmid in adapter.created_vms


def test_create_recovers_clone_when_provider_accepted_but_response_was_lost(monkeypatch) -> None:
    vm, operation, adapter, session_factory = make_create_state()
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    assert asyncio.run(worker.run_once(adapter)) is True  # Сохранили размещение.

    original_clone = adapter.clone_vm

    async def accepted_then_timeout(*args, **kwargs):
        await original_clone(*args, **kwargs)
        raise TimeoutError("clone response was lost")

    adapter.clone_vm = AsyncMock(side_effect=accepted_then_timeout)
    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "processing"
    assert operation.phase == "reconcile_create_clone"
    assert operation.provider_task_id is None
    assert adapter.clone_vm.await_count == 1

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "pending"
    assert operation.phase == "configure"
    assert adapter.clone_vm.await_count == 1
    assert vm.provider_vmid in adapter.created_vms


def test_create_does_not_clone_again_after_dispatch_marker_without_response(monkeypatch) -> None:
    vm, operation, adapter, session_factory = make_create_state()
    vm.provider_node = "fake-node"
    vm.provider_vmid = adapter._vmid_for_vm_id(vm.id)
    operation.status = "processing"
    operation.phase = "dispatch_create_clone"
    adapter.clone_vm = AsyncMock(side_effect=AssertionError("duplicate clone"))
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "processing"
    assert operation.phase == "reconcile_create_clone"
    assert operation.last_error_code == "provider_outcome_unknown"
    adapter.clone_vm.assert_not_awaited()


def test_create_task_poll_timeout_preserves_saved_task(monkeypatch) -> None:
    vm, operation, adapter, session_factory = make_create_state()
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    assert asyncio.run(worker.run_once(adapter)) is True  # Placement.
    assert asyncio.run(worker.run_once(adapter)) is True  # Clone отправлен.
    task_id = operation.provider_task_id
    original_poll = adapter.get_task_status
    adapter.get_task_status = AsyncMock(side_effect=TimeoutError("status unavailable"))

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.phase == "poll_backoff_create_clone"
    assert operation.provider_task_id == task_id

    adapter.get_task_status = original_poll
    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "pending"
    assert operation.phase == "configure"
    assert operation.provider_task_id is None


@pytest.mark.parametrize("phase", ["configure", "resize"])
def test_create_does_not_resubmit_ambiguous_configuration(monkeypatch, phase) -> None:
    vm, operation, adapter, session_factory = make_create_state()
    vm.provider_node = "fake-node"
    vm.provider_vmid = adapter._vmid_for_vm_id(vm.id)
    adapter._power_states[vm.provider_vmid] = "stopped"
    operation.phase = phase
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    command_name = "configure_vm" if phase == "configure" else "resize_vm_disk"
    original_command = getattr(adapter, command_name)

    async def accepted_then_timeout(*args, **kwargs):
        await original_command(*args, **kwargs)
        raise TimeoutError("response was lost")

    lost_response = AsyncMock(side_effect=accepted_then_timeout)
    setattr(adapter, command_name, lost_response)

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "processing"
    assert operation.phase == f"reconcile_create_{phase}"

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "processing"
    assert operation.phase == f"needs_review_create_{phase}"
    assert operation.last_error_code == "provider_outcome_unknown"
    assert lost_response.await_count == 1


def test_create_recovers_initial_start_without_resubmitting(monkeypatch) -> None:
    vm, operation, adapter, session_factory = make_create_state()
    vm.provider_node = "fake-node"
    vm.provider_vmid = adapter._vmid_for_vm_id(vm.id)
    adapter._power_states[vm.provider_vmid] = "stopped"
    operation.phase = "start"
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    original_start = adapter.start_vm

    async def accepted_then_timeout(*args, **kwargs):
        await original_start(*args, **kwargs)
        raise TimeoutError("start response was lost")

    adapter.start_vm = AsyncMock(side_effect=accepted_then_timeout)
    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.phase == "reconcile_create_start"

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "succeeded"
    assert operation.phase == "complete"
    assert vm.status == "running"
    assert adapter.start_vm.await_count == 1
