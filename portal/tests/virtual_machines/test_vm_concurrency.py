import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.operations.models import Operation
from app.ssh_keys.schemas import SshPublicKeyCreate
from app.ssh_keys.services import import_ssh_public_key
from app.virtual_machines.models import VirtualMachine
from app.virtual_machines.services import create_vm, enqueue_vm_operation

SSH_PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILXD5hvkNQhVB+lAbP50cAdixrOMIAMwW8O55MxYqqMn"
)


def _vm_request(ssh_key_id):
    from app.virtual_machines.schemas import VirtualMachineCreate

    return VirtualMachineCreate(
        requested_vcpus=1,
        requested_memory_mb=512,
        requested_storage_gb=10,
        image_id="almalinux-9",
        ssh_public_key_id=ssh_key_id,
    )


async def _seed_stopped_vm(db, user_id):
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
    return vm


@pytest.mark.asyncio
async def test_concurrent_create_same_request_yields_single_vm(db, user) -> None:
    # Двойной клик по «Создать VM»: два запроса с одним idempotency_key.
    # Оба должны увидеть одну и ту же VM, а не две.
    key = await import_ssh_public_key(
        db,
        user_id=user.id,
        request_model=SshPublicKeyCreate(name="laptop", public_key=SSH_PUBLIC_KEY),
    )
    await db.commit()

    idempotency_key = str(uuid4())

    async def create_and_commit() -> str:
        async with SessionLocal() as session:
            vm = await create_vm(
                session,
                user_id=user.id,
                request_model=_vm_request(key.id),
                idempotency_key=idempotency_key,
            )
            await session.commit()
            return vm.id

    first_id, second_id = await asyncio.gather(
        create_and_commit(),
        create_and_commit(),
    )

    assert first_id == second_id

    async with SessionLocal() as fresh:
        vms = list(await fresh.scalars(select(VirtualMachine)))
        operations = list(await fresh.scalars(select(Operation)))
    assert len(vms) == 1
    assert len(operations) == 1


@pytest.mark.asyncio
async def test_concurrent_enqueue_same_key_on_different_vms(db, user) -> None:
    # Один idempotency_key на двух VM одновременно: побеждает ровно один,
    # проигравший получает конфликт, второй операции не возникает.
    vm_a = await _seed_stopped_vm(db, user.id)
    vm_b = await _seed_stopped_vm(db, user.id)
    await db.commit()

    idempotency_key = str(uuid4())

    async def enqueue(vm_id) -> str:
        async with SessionLocal() as session:
            operation = await enqueue_vm_operation(
                session,
                user_id=user.id,
                vm_id=vm_id,
                operation_type="vm.start",
                idempotency_key=idempotency_key,
            )
            await session.commit()
            return operation.id

    results = await asyncio.gather(
        enqueue(vm_a.id),
        enqueue(vm_b.id),
        return_exceptions=True,
    )

    errors = [r for r in results if isinstance(r, Exception)]
    winners = [r for r in results if not isinstance(r, Exception)]

    assert len(winners) == 1
    assert len(errors) == 1
    assert "idempotency key already used" in str(errors[0])

    async with SessionLocal() as fresh:
        operations = list(await fresh.scalars(select(Operation)))
    assert len(operations) == 1
