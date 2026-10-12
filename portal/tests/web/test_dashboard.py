from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.identity.csrf import make_csrf_token
from app.identity.services import get_or_create_user
from app.identity.sessions import create_application_session
from app.operations.models import Operation
from app.ssh_keys.schemas import SshPublicKeyCreate
from app.ssh_keys.services import import_ssh_public_key
from app.virtual_machines.models import VirtualMachine

SSH_PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILXD5hvkNQhVB+lAbP50cAdixrOMIAMwW8O55MxYqqMn"
)


async def _committed_user_with_session(db):
    """User и session, закоммиченные в БД: приложение читает своими сессиями."""
    user = await get_or_create_user(
        db=db, issuer="issuer", subject="subject", email="email@example.com"
    )
    token = create_application_session(db, user_id=user.id)
    await db.commit()
    return user, token


async def _seed_vm(db, user_id, *, status):
    vm = VirtualMachine(
        owner_user_id=user_id,
        status=status,
        requested_vcpus=1,
        requested_memory_mb=512,
        requested_storage_gb=10,
        image_id="almalinux-9",
    )
    db.add(vm)
    await db.flush()
    return vm


async def _rows():
    """Свежее чтение мимо identity map тестовой сессии."""
    async with SessionLocal() as fresh:
        vms = list(await fresh.scalars(select(VirtualMachine)))
        operations = list(await fresh.scalars(select(Operation)))
        return vms, operations


@pytest.mark.asyncio
async def test_public_page_and_styles_are_served(client) -> None:
    page = await client.get("/")
    styles = await client.get("/static/portal.css")

    assert page.status_code == 200
    assert "Войти через Keycloak" in page.text
    assert styles.status_code == 200
    assert "text/css" in styles.headers["content-type"]


@pytest.mark.asyncio
async def test_dashboard_requires_authentication(client) -> None:
    response = await client.get("/dashboard")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_vm_form_creates_vm_and_redirects(db, client) -> None:
    user, token = await _committed_user_with_session(db)
    key = await import_ssh_public_key(
        db,
        user_id=user.id,
        request_model=SshPublicKeyCreate(name="laptop", public_key=SSH_PUBLIC_KEY),
    )
    await db.commit()
    client.cookies.set("npd_session", token)
    idempotency_key = str(uuid4())

    response = await client.post("/dashboard/vms", data={
        "csrf_token": make_csrf_token(token),
        "idempotency_key": idempotency_key,
        "requested_vcpus": "2",
        "requested_memory_mb": "4096",
        "requested_storage_gb": "30",
        "image_id": "almalinux-9",
        "ssh_public_key_id": str(key.id),
    })

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard#vms"

    vms, operations = await _rows()
    assert len(vms) == 1
    assert vms[0].status == "pending"
    assert len(operations) == 1
    assert operations[0].operation_type == "vm.create"
    assert operations[0].phase == "clone"
    assert operations[0].idempotency_key == idempotency_key


@pytest.mark.asyncio
async def test_dashboard_vm_form_rejects_invalid_csrf(db, client) -> None:
    user, token = await _committed_user_with_session(db)
    client.cookies.set("npd_session", token)

    response = await client.post("/dashboard/vms", data={
        "csrf_token": "wrong",
        "idempotency_key": str(uuid4()),
        "requested_vcpus": "2",
        "requested_memory_mb": "4096",
        "requested_storage_gb": "30",
        "image_id": "almalinux-9",
        "ssh_public_key_id": str(uuid4()),
    })

    assert response.status_code == 403

    vms, operations = await _rows()
    assert vms == []
    assert operations == []


@pytest.mark.asyncio
async def test_dashboard_vm_form_rejects_invalid_fields(db, client) -> None:
    user, token = await _committed_user_with_session(db)
    client.cookies.set("npd_session", token)

    response = await client.post("/dashboard/vms", data={
        "csrf_token": make_csrf_token(token),
        "idempotency_key": str(uuid4()),
        "requested_vcpus": "0",
        "requested_memory_mb": "4096",
        "requested_storage_gb": "30",
        "image_id": "almalinux-9",
        "ssh_public_key_id": str(uuid4()),
    })

    assert response.status_code == 422

    vms, operations = await _rows()
    assert vms == []
    assert operations == []


@pytest.mark.asyncio
async def test_dashboard_vm_form_maps_service_conflict_to_409(db, client) -> None:
    user, token = await _committed_user_with_session(db)
    key = await import_ssh_public_key(
        db,
        user_id=user.id,
        request_model=SshPublicKeyCreate(name="laptop", public_key=SSH_PUBLIC_KEY),
    )
    await db.commit()
    client.cookies.set("npd_session", token)

    # Сервис отвергает образ; форма проходит валидацию, конфликт доходит
    # до сервисного уровня и отображается как 409.
    response = await client.post("/dashboard/vms", data={
        "csrf_token": make_csrf_token(token),
        "idempotency_key": str(uuid4()),
        "requested_vcpus": "2",
        "requested_memory_mb": "4096",
        "requested_storage_gb": "30",
        "image_id": "fedora-40",
        "ssh_public_key_id": str(key.id),
    })

    assert response.status_code == 409
    assert "image is not allowed" in response.text

    vms, operations = await _rows()
    assert vms == []
    assert operations == []


@pytest.mark.asyncio
async def test_dashboard_start_vm_enqueues_operation_and_redirects(db, client) -> None:
    user, token = await _committed_user_with_session(db)
    vm = await _seed_vm(db, user.id, status="stopped")
    await db.commit()
    client.cookies.set("npd_session", token)
    idempotency_key = str(uuid4())

    response = await client.post(
        f"/dashboard/vms/{vm.id}/start",
        data={
            "csrf_token": make_csrf_token(token),
            "idempotency_key": idempotency_key,
        },
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard#vms"

    vms, operations = await _rows()
    assert len(operations) == 1
    assert operations[0].operation_type == "vm.start"
    assert operations[0].status == "pending"
    assert operations[0].virtual_machine_id == vm.id


@pytest.mark.asyncio
async def test_dashboard_start_vm_rejects_invalid_csrf(db, client) -> None:
    user, token = await _committed_user_with_session(db)
    vm = await _seed_vm(db, user.id, status="stopped")
    await db.commit()
    client.cookies.set("npd_session", token)

    response = await client.post(
        f"/dashboard/vms/{vm.id}/start",
        data={
            "csrf_token": "wrong",
            "idempotency_key": str(uuid4()),
        },
    )

    assert response.status_code == 403

    _, operations = await _rows()
    assert operations == []


@pytest.mark.asyncio
async def test_dashboard_start_vm_rejects_invalid_idempotency_key(db, client) -> None:
    user, token = await _committed_user_with_session(db)
    vm = await _seed_vm(db, user.id, status="stopped")
    await db.commit()
    client.cookies.set("npd_session", token)

    response = await client.post(
        f"/dashboard/vms/{vm.id}/start",
        data={
            "csrf_token": make_csrf_token(token),
            "idempotency_key": "not-a-uuid",
        },
    )

    assert response.status_code == 422

    _, operations = await _rows()
    assert operations == []


@pytest.mark.asyncio
async def test_dashboard_start_missing_vm_maps_to_404(db, client) -> None:
    user, token = await _committed_user_with_session(db)
    client.cookies.set("npd_session", token)

    response = await client.post(
        f"/dashboard/vms/{uuid4()}/start",
        data={
            "csrf_token": make_csrf_token(token),
            "idempotency_key": str(uuid4()),
        },
    )

    assert response.status_code == 404

    _, operations = await _rows()
    assert operations == []


@pytest.mark.asyncio
async def test_dashboard_shows_own_resources_and_escapes_names(db, client) -> None:
    user, token = await _committed_user_with_session(db)
    other = await get_or_create_user(
        db=db, issuer="issuer", subject="other-subject", email="other@example.com"
    )

    dangerous_name = "<script>alert(1)</script>"
    key = await import_ssh_public_key(
        db,
        user_id=user.id,
        request_model=SshPublicKeyCreate(
            name=dangerous_name, public_key=SSH_PUBLIC_KEY
        ),
    )

    running_vm = await _seed_vm(db, user.id, status="running")
    stopped_vm = await _seed_vm(db, user.id, status="stopped")
    other_users_vm = await _seed_vm(db, other.id, status="stopped")

    db.add(Operation(
        virtual_machine_id=running_vm.id,
        operation_type="vm.create",
        status="succeeded",
        phase="complete",
        idempotency_key=str(uuid4()),
    ))
    await db.commit()
    client.cookies.set("npd_session", token)

    response = await client.get("/dashboard")

    assert response.status_code == 200
    assert "starter" in response.text
    assert "almalinux-9" in response.text
    assert key.fingerprint in response.text
    assert "vm.create" in response.text

    # Имена экранируются, а не попадают в HTML как есть.
    assert dangerous_name not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text

    # Формы содержат CSRF и idempotency.
    assert 'action="/dashboard/vms"' in response.text
    assert 'name="csrf_token"' in response.text
    assert 'name="idempotency_key"' in response.text
    assert 'name="ssh_public_key_id"' in response.text
    assert str(key.id) in response.text

    # Кнопка запуска только у остановленной VM.
    assert f'action="/dashboard/vms/{stopped_vm.id}/start"' in response.text
    assert f'action="/dashboard/vms/{running_vm.id}/start"' not in response.text

    # Видны только собственные ресурсы.
    assert str(other_users_vm.id) not in response.text
