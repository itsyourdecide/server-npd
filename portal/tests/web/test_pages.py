import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx2

from app.compute.models import ComputePlan, UserQuota
from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.main import create_app
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
    ssh_key = SimpleNamespace(
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
        Mock(all=lambda: [vm]),
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
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "starter" in response.text
            assert "almalinux-9" in response.text
            assert "SHA256:test" in response.text
            assert "vm.create" in response.text
            assert "<script>alert(1)</script>" not in response.text
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text

    asyncio.run(check())
