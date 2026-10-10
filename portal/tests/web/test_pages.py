import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx2

from app.compute.models import ComputePlan, UserQuota
from app.db.session import get_db
from app.identity.csrf import make_csrf_token
from app.identity.dependencies import get_current_user
from app.main import create_app
from app.virtual_machines.schemas import VirtualMachineCreate
import app.web.router as web_router


def test_public_page_and_styles_are_served() -> None:
    app = create_app()

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            page = await client.get("/")
            styles = await client.get("/static/portal.css")
            assert page.status_code == 200
            assert "Войти через Keycloak" in page.text
            assert styles.status_code == 200
            assert "text/css" in styles.headers["content-type"]

    asyncio.run(check())


def test_dashboard_vm_form_creates_vm_and_redirects(monkeypatch) -> None:
    app = create_app()
    user_id = uuid4()
    ssh_key_id = uuid4()
    idempotency_key = uuid4()
    session_token = "test-session"
    db = Mock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    create_vm = AsyncMock()
    monkeypatch.setattr(web_router, "create_vm", create_vm)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    app.dependency_overrides[get_db] = lambda: db

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("npd_session", session_token)
            response = await client.post("/dashboard/vms", data={
                "csrf_token": make_csrf_token(session_token),
                "idempotency_key": str(idempotency_key),
                "requested_vcpus": "2",
                "requested_memory_mb": "4096",
                "requested_storage_gb": "30",
                "image_id": "almalinux-9",
                "ssh_public_key_id": str(ssh_key_id),
            })

            assert response.status_code == 303
            assert response.headers["location"] == "/dashboard#vms"
            create_vm.assert_awaited_once()
            args, kwargs = create_vm.call_args
            assert args == (db,)
            assert kwargs["user_id"] == user_id
            assert kwargs["idempotency_key"] == str(idempotency_key)
            assert isinstance(kwargs["request_model"], VirtualMachineCreate)
            assert kwargs["request_model"].ssh_public_key_id == ssh_key_id
            assert kwargs["request_model"].requested_vcpus == 2
            db.commit.assert_awaited_once_with()
            db.rollback.assert_not_awaited()

    asyncio.run(check())


def test_dashboard_vm_form_rejects_invalid_csrf(monkeypatch) -> None:
    app = create_app()
    db = Mock()
    db.commit = AsyncMock()
    create_vm = AsyncMock()
    monkeypatch.setattr(web_router, "create_vm", create_vm)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: db

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("npd_session", "test-session")
            response = await client.post("/dashboard/vms", data={"csrf_token": "wrong"})
            assert response.status_code == 403
            create_vm.assert_not_awaited()
            db.commit.assert_not_awaited()

    asyncio.run(check())


def test_dashboard_vm_form_rejects_invalid_fields(monkeypatch) -> None:
    app = create_app()
    session_token = "test-session"
    db = Mock()
    db.commit = AsyncMock()
    create_vm = AsyncMock()
    monkeypatch.setattr(web_router, "create_vm", create_vm)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: db

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("npd_session", session_token)
            response = await client.post("/dashboard/vms", data={
                "csrf_token": make_csrf_token(session_token),
                "idempotency_key": str(uuid4()),
                "requested_vcpus": "0",
                "requested_memory_mb": "4096",
                "requested_storage_gb": "30",
                "image_id": "almalinux-9",
                "ssh_public_key_id": str(uuid4()),
            })
            assert response.status_code == 422
            create_vm.assert_not_awaited()
            db.commit.assert_not_awaited()

    asyncio.run(check())


def test_dashboard_vm_form_rolls_back_service_error(monkeypatch) -> None:
    app = create_app()
    session_token = "test-session"
    db = Mock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    create_vm = AsyncMock(side_effect=ValueError("image is not allowed"))
    monkeypatch.setattr(web_router, "create_vm", create_vm)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: db

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("npd_session", session_token)
            response = await client.post("/dashboard/vms", data={
                "csrf_token": make_csrf_token(session_token),
                "idempotency_key": str(uuid4()),
                "requested_vcpus": "2",
                "requested_memory_mb": "4096",
                "requested_storage_gb": "30",
                "image_id": "almalinux-9",
                "ssh_public_key_id": str(uuid4()),
            })
            assert response.status_code == 409
            db.rollback.assert_awaited_once_with()
            db.commit.assert_not_awaited()

    asyncio.run(check())


def test_dashboard_start_vm_enqueues_operation_and_redirects(monkeypatch) -> None:
    app = create_app()
    user_id = uuid4()
    vm_id = uuid4()
    idempotency_key = uuid4()
    session_token = "test-session"
    db = Mock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    enqueue = AsyncMock()
    monkeypatch.setattr(web_router, "enqueue_vm_operation", enqueue)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    app.dependency_overrides[get_db] = lambda: db

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("npd_session", session_token)
            response = await client.post(f"/dashboard/vms/{vm_id}/start", data={
                "csrf_token": make_csrf_token(session_token),
                "idempotency_key": str(idempotency_key),
            })
            assert response.status_code == 303
            assert response.headers["location"] == "/dashboard#vms"
            enqueue.assert_awaited_once_with(
                db=db,
                user_id=user_id,
                vm_id=vm_id,
                operation_type="vm.start",
                idempotency_key=str(idempotency_key),
            )
            db.commit.assert_awaited_once_with()
            db.rollback.assert_not_awaited()

    asyncio.run(check())


def test_dashboard_start_vm_rejects_invalid_key(monkeypatch) -> None:
    app = create_app()
    session_token = "test-session"
    db = Mock()
    db.commit = AsyncMock()
    enqueue = AsyncMock()
    monkeypatch.setattr(web_router, "enqueue_vm_operation", enqueue)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: db

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("npd_session", session_token)
            response = await client.post(f"/dashboard/vms/{uuid4()}/start", data={
                "csrf_token": make_csrf_token(session_token),
                "idempotency_key": "not-a-uuid",
            })
            assert response.status_code == 422
            enqueue.assert_not_awaited()
            db.commit.assert_not_awaited()

    asyncio.run(check())


def test_dashboard_start_vm_rejects_invalid_csrf(monkeypatch) -> None:
    app = create_app()
    db = Mock()
    db.commit = AsyncMock()
    enqueue = AsyncMock()
    monkeypatch.setattr(web_router, "enqueue_vm_operation", enqueue)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: db

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("npd_session", "test-session")
            response = await client.post(f"/dashboard/vms/{uuid4()}/start", data={
                "csrf_token": "wrong",
                "idempotency_key": str(uuid4()),
            })
            assert response.status_code == 403
            enqueue.assert_not_awaited()
            db.commit.assert_not_awaited()

    asyncio.run(check())


def test_dashboard_start_vm_rolls_back_missing_vm(monkeypatch) -> None:
    app = create_app()
    session_token = "test-session"
    db = Mock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    enqueue = AsyncMock(side_effect=LookupError("virtual machine not found"))
    monkeypatch.setattr(web_router, "enqueue_vm_operation", enqueue)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: db

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("npd_session", session_token)
            response = await client.post(f"/dashboard/vms/{uuid4()}/start", data={
                "csrf_token": make_csrf_token(session_token),
                "idempotency_key": str(uuid4()),
            })
            assert response.status_code == 404
            db.rollback.assert_awaited_once_with()
            db.commit.assert_not_awaited()

    asyncio.run(check())


def test_dashboard_requires_authentication() -> None:
    app = create_app()

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/dashboard")
            assert response.status_code == 401

    asyncio.run(check())


def test_dashboard_shows_own_resources_and_escapes_names(monkeypatch) -> None:
    app = create_app()
    user_id = uuid4()
    vm_id = uuid4()
    operation_id = uuid4()
    quota = SimpleNamespace(compute_plan_id=uuid4(), status="active")
    plan = SimpleNamespace(
        code="starter",
        max_vms=1,
        max_total_vcpus=2,
        max_total_memory_mb=4096,
        max_total_storage_gb=30,
    )
    vm = SimpleNamespace(
        id=vm_id, image_id="almalinux-9", requested_vcpus=2,
        requested_memory_mb=4096, requested_storage_gb=30, status="running",
    )
    stopped_vm = SimpleNamespace(
        id=uuid4(), image_id="almalinux-9", requested_vcpus=2,
        requested_memory_mb=4096, requested_storage_gb=30, status="stopped",
    )
    ssh_key = SimpleNamespace(
        id=uuid4(),
        name="<script>alert(1)</script>", key_type="ssh-ed25519",
        fingerprint="SHA256:test",
    )
    operation = SimpleNamespace(
        id=operation_id, virtual_machine_id=vm_id,
        operation_type="vm.create", status="succeeded", phase="complete",
    )
    db = Mock()

    async def get(model, key):
        return quota if model is UserQuota else plan if model is ComputePlan else None

    db.get = AsyncMock(side_effect=get)
    db.scalars = AsyncMock(side_effect=[
        Mock(all=lambda: [vm, stopped_vm]),
        Mock(all=lambda: [ssh_key]),
        Mock(all=lambda: [operation]),
    ])
    monkeypatch.setattr(web_router, "get_user_compute_usage", AsyncMock(return_value={
        "used_vms": 1,
        "used_vcpus": 2,
        "used_memory_mb": 4096,
        "used_storage_gb": 30,
    }))
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    app.dependency_overrides[get_db] = lambda: db

    async def check():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("npd_session", "test-session")
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "starter" in response.text
            assert "almalinux-9" in response.text
            assert "SHA256:test" in response.text
            assert "vm.create" in response.text
            assert "<script>alert(1)</script>" not in response.text
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
            assert 'action="/dashboard/vms"' in response.text
            assert 'name="csrf_token"' in response.text
            assert 'name="idempotency_key"' in response.text
            assert 'name="ssh_public_key_id"' in response.text
            assert str(ssh_key.id) in response.text
            assert f'action="/dashboard/vms/{stopped_vm.id}/start"' in response.text
            assert f'action="/dashboard/vms/{vm_id}/start"' not in response.text

    asyncio.run(check())
