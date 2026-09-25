import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from app.operations.models import Operation
from app.operations.services import (
    finish_start_vm_dispatch,
    prepare_start_vm_dispatch,
    process_start_vm_operation,
    reconcile_start_vm_operation,
)
from app.proxmox.fake import FakeProxmoxAdapter
from app.virtual_machines.models import VirtualMachine
import app.workers.operation_worker as worker


def make_start():
    adapter = FakeProxmoxAdapter()
    vm_id = uuid4()
    vm = VirtualMachine(
        id=vm_id,
        status="stopped",
        provider_node="fake-node",
        provider_vmid=adapter._vmid_for_vm_id(vm_id),
    )
    operation = Operation(
        id=uuid4(),
        virtual_machine_id=vm_id,
        operation_type="vm.start",
        status="pending",
        phase=None,
        provider_task_id=None,
        attempts=0,
    )
    db = AsyncMock()
    db.get.return_value = vm
    return vm, operation, adapter, db


def test_start_recovers_after_provider_accepted_but_upid_was_lost() -> None:
    vm, operation, adapter, db = make_start()

    target = asyncio.run(prepare_start_vm_dispatch(db, operation))
    assert operation.status == "processing"
    assert operation.phase == "dispatching"
    assert operation.attempts == 1

    # Proxmox принял команду; имитируем сбой до записи UPID в БД.
    asyncio.run(adapter.start_vm(vm.id, node=target.node, vmid=target.vmid))
    adapter.start_vm = AsyncMock(side_effect=AssertionError("duplicate start"))

    asyncio.run(reconcile_start_vm_operation(db, operation, adapter))

    assert operation.status == "succeeded"
    assert operation.phase == "complete"
    assert operation.provider_task_id is None
    assert vm.status == "running"
    adapter.start_vm.assert_not_awaited()


def test_start_does_not_resubmit_when_dispatch_outcome_is_unknown() -> None:
    vm, operation, adapter, db = make_start()
    asyncio.run(prepare_start_vm_dispatch(db, operation))
    adapter.start_vm = AsyncMock(side_effect=AssertionError("duplicate start"))

    asyncio.run(reconcile_start_vm_operation(db, operation, adapter))

    assert operation.status == "processing"
    assert operation.phase == "reconcile"
    assert operation.last_error_code == "provider_outcome_unknown"
    assert vm.status == "stopped"
    adapter.start_vm.assert_not_awaited()

    adapter._power_states[vm.provider_vmid] = "running"
    asyncio.run(reconcile_start_vm_operation(db, operation, adapter))
    assert operation.status == "succeeded"
    assert vm.status == "running"


def test_start_with_saved_upid_polls_provider_task() -> None:
    vm, operation, adapter, db = make_start()
    target = asyncio.run(prepare_start_vm_dispatch(db, operation))
    task = asyncio.run(adapter.start_vm(vm.id, node=target.node, vmid=target.vmid))

    asyncio.run(finish_start_vm_dispatch(db, operation, task))
    assert operation.phase == "await_task"
    assert operation.provider_task_id == task.task_id

    asyncio.run(process_start_vm_operation(db, operation, adapter))
    assert operation.status == "succeeded"
    assert operation.phase == "complete"
    assert vm.status == "running"


def test_worker_sends_start_after_database_transaction_closes(monkeypatch) -> None:
    vm, operation, adapter, _ = make_start()
    transaction_open = False

    class TestSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def begin(self):
            class Transaction:
                async def __aenter__(self):
                    nonlocal transaction_open
                    transaction_open = True

                async def __aexit__(self, exc_type, exc, traceback):
                    nonlocal transaction_open
                    transaction_open = False
                    return False

            return Transaction()

        async def scalar(self, statement):
            return operation

        async def get(self, model, key, **kwargs):
            return vm if model is VirtualMachine else operation

    original_start = adapter.start_vm

    async def checked_start(*args, **kwargs):
        assert transaction_open is False
        return await original_start(*args, **kwargs)

    adapter.start_vm = checked_start
    monkeypatch.setattr(worker, "SessionLocal", TestSession)

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "processing"
    assert operation.phase == "await_task"
    assert operation.provider_task_id is not None


def test_worker_reconciles_timeout_after_provider_accepted_start(monkeypatch) -> None:
    vm, operation, adapter, _ = make_start()

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

    original_start = adapter.start_vm

    async def accepted_then_timeout(*args, **kwargs):
        await original_start(*args, **kwargs)
        raise TimeoutError("response was lost")

    adapter.start_vm = AsyncMock(side_effect=accepted_then_timeout)
    monkeypatch.setattr(worker, "SessionLocal", TestSession)

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "processing"
    assert operation.phase == "reconcile"
    assert operation.provider_task_id is None
    assert operation.last_error_code == "provider_submit_unknown"
    assert adapter.start_vm.await_count == 1

    # Состояние Fake уже running; следующий проход только читает его.
    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "succeeded"
    assert vm.status == "running"
    assert adapter.start_vm.await_count == 1


def test_worker_keeps_start_task_after_poll_timeout(monkeypatch) -> None:
    vm, operation, adapter, db = make_start()
    target = asyncio.run(prepare_start_vm_dispatch(db, operation))
    task = asyncio.run(adapter.start_vm(vm.id, node=target.node, vmid=target.vmid))
    asyncio.run(finish_start_vm_dispatch(db, operation, task))

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

        async def flush(self):
            pass

    original_poll = adapter.get_task_status
    adapter.get_task_status = AsyncMock(side_effect=TimeoutError("status unavailable"))
    monkeypatch.setattr(worker, "SessionLocal", TestSession)

    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "processing"
    assert operation.phase == "poll_backoff"
    assert operation.provider_task_id == task.task_id
    assert operation.last_error_code == "provider_status_unavailable"

    adapter.get_task_status = original_poll
    assert asyncio.run(worker.run_once(adapter)) is True
    assert operation.status == "succeeded"
    assert vm.status == "running"
