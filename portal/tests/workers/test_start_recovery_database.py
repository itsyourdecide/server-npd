from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.db.session import SessionLocal
from app.operations.models import Operation
from app.proxmox.fake import FakeProxmoxAdapter
from app.virtual_machines.models import VirtualMachine
from app.workers.operation_worker import RECONCILE_DELAY, run_once


async def _seed_pending_start(db, user_id):
    """Закоммиченные VM и операция — worker читает их своими сессиями."""
    adapter = FakeProxmoxAdapter()
    vm = VirtualMachine(
        owner_user_id=user_id,
        status="stopped",
        requested_vcpus=1,
        requested_memory_mb=512,
        requested_storage_gb=10,
        image_id="almalinux-9",
    )
    db.add(vm)
    await db.flush()

    vm.provider_node = adapter._node
    vm.provider_vmid = FakeProxmoxAdapter._vmid_for_vm_id(vm.id)

    operation = Operation(
        virtual_machine_id=vm.id,
        operation_type="vm.start",
        status="pending",
        phase=None,
        idempotency_key=str(uuid4()),
    )
    db.add(operation)
    await db.commit()
    return vm.id, operation.id


async def _rows(vm_id, operation_id):
    """Свежее чтение состояния мимо identity map тестовой сессии."""
    async with SessionLocal() as fresh:
        vm = await fresh.get(VirtualMachine, vm_id)
        operation = await fresh.get(Operation, operation_id)
        return vm, operation


@pytest.mark.asyncio
async def test_worker_completes_start_against_real_database(db, user) -> None:
    vm_id, operation_id = await _seed_pending_start(db, user.id)
    adapter = FakeProxmoxAdapter()

    # Первый проход: маркер dispatching зафиксирован ДО вызова провайдера,
    # затем UPID задачи сохранён в операции.
    assert await run_once(adapter) is True

    vm, operation = await _rows(vm_id, operation_id)
    assert operation.status == "processing"
    assert operation.phase == "await_task"
    assert operation.provider_task_id is not None
    assert vm.status == "stopped"

    # Второй проход: poll статуса задачи, успех.
    assert await run_once(adapter) is True

    vm, operation = await _rows(vm_id, operation_id)
    assert operation.status == "succeeded"
    assert operation.phase == "complete"
    assert operation.provider_task_id is None
    assert operation.last_error_code is None
    assert vm.status == "running"


@pytest.mark.asyncio
async def test_worker_reconciles_start_after_submit_outcome_unknown(db, user) -> None:
    vm_id, operation_id = await _seed_pending_start(db, user.id)
    adapter = FakeProxmoxAdapter()

    # Proxmox принял команду, но ответ потерялся: сначала реальный start,
    # затем обрыв связи.
    original_start = adapter.start_vm
    submissions = {"count": 0}

    async def accept_then_timeout(*args, **kwargs):
        submissions["count"] += 1
        await original_start(*args, **kwargs)
        raise TimeoutError("response was lost")

    adapter.start_vm = accept_then_timeout

    assert await run_once(adapter) is True

    vm, operation = await _rows(vm_id, operation_id)
    assert operation.status == "processing"
    assert operation.phase == "reconcile"
    assert operation.provider_task_id is None
    assert operation.last_error_code == "provider_submit_unknown"
    assert vm.status == "stopped"
    assert submissions["count"] == 1

    # RECONCILE_DELAY ещё не истёк: worker не должен трогать операцию
    # и тем более повторять отправку.
    assert await run_once(adapter) is False
    assert submissions["count"] == 1

    # Время детально не ждём: операция «осталась с прошлого прохода».
    await db.execute(
        update(Operation)
        .where(Operation.id == operation_id)
        .values(updated_at=datetime.now(UTC) - RECONCILE_DELAY - timedelta(seconds=1))
    )
    await db.commit()

    assert await run_once(adapter) is True

    vm, operation = await _rows(vm_id, operation_id)
    assert operation.status == "succeeded"
    assert operation.phase == "complete"
    assert vm.status == "running"
    # Reconcile только читает состояние и не отправляет start повторно.
    assert submissions["count"] == 1
