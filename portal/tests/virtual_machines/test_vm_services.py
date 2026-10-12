from uuid import uuid4

import pytest
from sqlalchemy import select

from app.identity.services import get_or_create_user
from app.operations.models import Operation
from app.ssh_keys.schemas import SshPublicKeyCreate
from app.ssh_keys.services import import_ssh_public_key
from app.virtual_machines.models import VirtualMachine
from app.virtual_machines.schemas import VirtualMachineCreate
from app.virtual_machines.services import create_vm, enqueue_vm_operation

import app.virtual_machines.services as vm_services

SSH_PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILXD5hvkNQhVB+lAbP50cAdixrOMIAMwW8O55MxYqqMn"
)
SSH_PUBLIC_KEY_OTHER = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKHwwmyu2wPsv6A0Xj5zAaaIUahf92nM8bhUh9pEDII4"
)


def _vm_request(ssh_key_id, *, vcpus=1, memory_mb=512, storage_gb=10):
    return VirtualMachineCreate(
        requested_vcpus=vcpus,
        requested_memory_mb=memory_mb,
        requested_storage_gb=storage_gb,
        image_id="almalinux-9",
        ssh_public_key_id=ssh_key_id,
    )


async def _import_key(db, user, name="laptop"):
    return await import_ssh_public_key(
        db,
        user_id=user.id,
        request_model=SshPublicKeyCreate(name=name, public_key=SSH_PUBLIC_KEY),
    )


async def _seed_vm(db, user_id, *, status="stopped", ssh_key_id=None):
    vm = VirtualMachine(
        owner_user_id=user_id,
        status=status,
        requested_vcpus=1,
        requested_memory_mb=512,
        requested_storage_gb=10,
        image_id="almalinux-9",
        ssh_public_key_id=ssh_key_id,
    )
    db.add(vm)
    await db.flush()
    return vm


# --- Квоты -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_vm_within_quota_creates_pending_vm_and_operation(db, user) -> None:
    key = await _import_key(db, user)

    vm = await create_vm(
        db,
        user_id=user.id,
        request_model=_vm_request(key.id),
        idempotency_key=str(uuid4()),
    )

    assert vm.status == "pending"

    vms = list(await db.scalars(select(VirtualMachine)))
    assert len(vms) == 1

    operation = await db.scalar(select(Operation))
    assert operation.operation_type == "vm.create"
    assert operation.status == "pending"
    assert operation.phase == "clone"
    assert operation.virtual_machine_id == vm.id


@pytest.mark.asyncio
async def test_create_vm_over_vms_limit_is_rejected(db, user) -> None:
    key = await _import_key(db, user)

    await create_vm(
        db,
        user_id=user.id,
        request_model=_vm_request(key.id),
        idempotency_key=str(uuid4()),
    )

    with pytest.raises(ValueError, match="VM limit exceeded"):
        await create_vm(
            db,
            user_id=user.id,
            request_model=_vm_request(key.id),
            idempotency_key=str(uuid4()),
        )

    vms = list(await db.scalars(select(VirtualMachine)))
    assert len(vms) == 1


@pytest.mark.asyncio
async def test_create_vm_rejects_unknown_image(db, user) -> None:
    key = await _import_key(db, user)
    request = _vm_request(key.id)
    request = request.model_copy(update={"image_id": "fedora-40"})

    with pytest.raises(ValueError, match="image is not allowed"):
        await create_vm(
            db,
            user_id=user.id,
            request_model=request,
            idempotency_key=str(uuid4()),
        )


@pytest.mark.asyncio
async def test_create_vm_rejects_storage_below_image_minimum(db, user) -> None:
    key = await _import_key(db, user)

    with pytest.raises(ValueError, match="storage must be at least"):
        await create_vm(
            db,
            user_id=user.id,
            request_model=_vm_request(key.id, storage_gb=5),
            idempotency_key=str(uuid4()),
        )


@pytest.mark.asyncio
async def test_create_vm_rejects_foreign_ssh_key(db, user) -> None:
    other = await get_or_create_user(
        db=db, issuer="issuer", subject="other-subject", email="other@example.com"
    )
    foreign_key = await _import_key(db, other, name="foreign")

    with pytest.raises(ValueError, match="does not belong to user"):
        await create_vm(
            db,
            user_id=user.id,
            request_model=_vm_request(foreign_key.id),
            idempotency_key=str(uuid4()),
        )


@pytest.mark.asyncio
async def test_create_vm_with_suspended_quota_is_forbidden(db, user) -> None:
    from app.compute.models import UserQuota

    key = await _import_key(db, user)
    quota = await db.get(UserQuota, user.id)
    quota.status = "suspended"
    await db.flush()

    with pytest.raises(PermissionError, match="suspended"):
        await create_vm(
            db,
            user_id=user.id,
            request_model=_vm_request(key.id),
            idempotency_key=str(uuid4()),
        )


# --- Идемпотентные повторы --------------------------------------------------


@pytest.mark.asyncio
async def test_create_vm_replay_returns_existing_vm(db, user) -> None:
    key = await _import_key(db, user)
    idempotency_key = str(uuid4())

    first = await create_vm(
        db, user_id=user.id, request_model=_vm_request(key.id),
        idempotency_key=idempotency_key,
    )
    second = await create_vm(
        db, user_id=user.id, request_model=_vm_request(key.id),
        idempotency_key=idempotency_key,
    )

    assert second.id == first.id

    vms = list(await db.scalars(select(VirtualMachine)))
    operations = list(await db.scalars(select(Operation)))
    assert len(vms) == 1
    assert len(operations) == 1


@pytest.mark.asyncio
async def test_create_vm_replay_with_changed_request_is_conflict(db, user) -> None:
    key = await _import_key(db, user)
    idempotency_key = str(uuid4())

    await create_vm(
        db, user_id=user.id, request_model=_vm_request(key.id),
        idempotency_key=idempotency_key,
    )

    with pytest.raises(ValueError, match="reused with different request"):
        await create_vm(
            db, user_id=user.id,
            request_model=_vm_request(key.id, vcpus=2),
            idempotency_key=idempotency_key,
        )


# --- Lifecycle-очередь -------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_replay_returns_existing_operation(db, user) -> None:
    vm = await _seed_vm(db, user.id)
    idempotency_key = str(uuid4())

    first = await enqueue_vm_operation(
        db, user_id=user.id, vm_id=vm.id,
        operation_type="vm.start", idempotency_key=idempotency_key,
    )
    second = await enqueue_vm_operation(
        db, user_id=user.id, vm_id=vm.id,
        operation_type="vm.start", idempotency_key=idempotency_key,
    )

    assert second.id == first.id

    operations = list(await db.scalars(select(Operation)))
    assert len(operations) == 1


@pytest.mark.asyncio
async def test_enqueue_rejects_reused_key_for_different_vm(db, user) -> None:
    vm_a = await _seed_vm(db, user.id)
    vm_b = await _seed_vm(db, user.id)
    idempotency_key = str(uuid4())

    await enqueue_vm_operation(
        db, user_id=user.id, vm_id=vm_a.id,
        operation_type="vm.start", idempotency_key=idempotency_key,
    )

    with pytest.raises(ValueError, match="idempotency key already used"):
        await enqueue_vm_operation(
            db, user_id=user.id, vm_id=vm_b.id,
            operation_type="vm.start", idempotency_key=idempotency_key,
        )


@pytest.mark.asyncio
async def test_enqueue_rejects_wrong_vm_status(db, user) -> None:
    vm = await _seed_vm(db, user.id, status="running")

    with pytest.raises(ValueError, match="cannot perform vm.start"):
        await enqueue_vm_operation(
            db, user_id=user.id, vm_id=vm.id,
            operation_type="vm.start", idempotency_key=str(uuid4()),
        )


@pytest.mark.asyncio
async def test_enqueue_rejects_second_active_operation(db, user) -> None:
    vm = await _seed_vm(db, user.id)

    await enqueue_vm_operation(
        db, user_id=user.id, vm_id=vm.id,
        operation_type="vm.start", idempotency_key=str(uuid4()),
    )

    with pytest.raises(ValueError, match="already has an active operation"):
        await enqueue_vm_operation(
            db, user_id=user.id, vm_id=vm.id,
            operation_type="vm.shutdown", idempotency_key=str(uuid4()),
        )


@pytest.mark.asyncio
async def test_enqueue_rejects_foreign_vm(db, user) -> None:
    other = await get_or_create_user(
        db=db, issuer="issuer", subject="other-subject", email="other@example.com"
    )
    foreign_vm = await _seed_vm(db, other.id)

    with pytest.raises(LookupError, match="not found"):
        await enqueue_vm_operation(
            db, user_id=user.id, vm_id=foreign_vm.id,
            operation_type="vm.start", idempotency_key=str(uuid4()),
        )


# --- Детерминированная гонка create_vm ---------------------------------------


@pytest.mark.asyncio
async def test_create_vm_race_lost_by_another_user_conflicts(db, user, monkeypatch) -> None:
    other = await get_or_create_user(
        db=db, issuer="issuer", subject="other-subject", email="other@example.com"
    )
    own_key = await _import_key(db, user, name="own")
    other_key = await import_ssh_public_key(
        db,
        user_id=other.id,
        request_model=SshPublicKeyCreate(
            name="other", public_key=SSH_PUBLIC_KEY_OTHER
        ),
    )
    idempotency_key = str(uuid4())

    # «Победитель» — другой пользователь — уже закоммитил операцию с тем же
    # idempotency_key. Квоты у них разные, поэтому сериализации через
    # FOR UPDATE на квоте нет, и окно гонки реально.
    winner_vm = await _seed_vm(db, other.id, status="pending", ssh_key_id=other_key.id)
    db.add(Operation(
        virtual_machine_id=winner_vm.id,
        operation_type="vm.create",
        status="pending",
        phase="clone",
        idempotency_key=idempotency_key,
    ))
    await db.commit()

    # Первый pre-check «не видит» чужую операцию — имитация окна гонки.
    # INSERT упирается в уникальный индекс idempotency_key, rollback,
    # повторная сверка видит закоммиченную строку чужого владельца.
    real_check = vm_services._get_existing_vm_for_create_request
    calls = {"count": 0}

    async def blind_once(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return await real_check(*args, **kwargs)

    monkeypatch.setattr(
        vm_services, "_get_existing_vm_for_create_request", blind_once
    )

    # Плоское значение до act: rollback внутри сервиса экспирит объекты
    # сессии, и чтение user.id после этого потребовало бы ленивого SELECT.
    user_id = user.id

    with pytest.raises(ValueError, match="idempotency key already used"):
        await create_vm(
            db, user_id=user_id, request_model=_vm_request(own_key.id),
            idempotency_key=idempotency_key,
        )

    # Проигравший не оставил после себя ни VM, ни операции.
    own_vms = [
        vm for vm in await db.scalars(select(VirtualMachine))
        if vm.owner_user_id == user_id
    ]
    assert own_vms == []
