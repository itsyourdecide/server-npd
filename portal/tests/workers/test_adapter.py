import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.proxmox.fake import FakeProxmoxAdapter
from app.proxmox.http_adapter import HttpProxmoxAdapter
from app.workers.adapter import create_worker_adapter
from app.workers.config import OperationWorkerSettings
import app.workers.adapter as adapter_module
import app.workers.operation_worker as worker


def without_worker_config(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)  # Здесь нет локального .env.worker разработчика.
    monkeypatch.delenv("WORKER_ADAPTER", raising=False)
    for name in OperationWorkerSettings.model_fields:
        if name.startswith("proxmox_"):
            monkeypatch.delenv(name.upper(), raising=False)


def test_fake_mode_does_not_require_proxmox_secrets(monkeypatch, tmp_path) -> None:
    without_worker_config(monkeypatch, tmp_path)
    client_factory = Mock(side_effect=AssertionError("real client must not be created"))
    monkeypatch.setattr(adapter_module, "ProxmoxClient", client_factory)

    async def check():
        async with create_worker_adapter() as adapter:
            assert isinstance(adapter, FakeProxmoxAdapter)

    asyncio.run(check())
    client_factory.assert_not_called()


def test_proxmox_mode_requires_real_settings(monkeypatch, tmp_path) -> None:
    without_worker_config(monkeypatch, tmp_path)
    monkeypatch.setenv("WORKER_ADAPTER", "proxmox")
    client_factory = Mock(side_effect=AssertionError("incomplete config must not create client"))
    monkeypatch.setattr(adapter_module, "ProxmoxClient", client_factory)

    async def check():
        async with create_worker_adapter():
            pass

    with pytest.raises(ValidationError):
        asyncio.run(check())
    client_factory.assert_not_called()


def test_unknown_mode_is_rejected(monkeypatch, tmp_path) -> None:
    without_worker_config(monkeypatch, tmp_path)
    monkeypatch.setenv("WORKER_ADAPTER", "unknown")

    async def check():
        async with create_worker_adapter():
            pass

    with pytest.raises(ValidationError):
        asyncio.run(check())


def test_proxmox_mode_builds_adapter_and_closes_client(monkeypatch, tmp_path) -> None:
    without_worker_config(monkeypatch, tmp_path)
    values = {
        "WORKER_ADAPTER": "proxmox",
        "PROXMOX_API_URL": "https://pve.test:8006/api2/json",
        "PROXMOX_TOKEN_ID": "portal-worker@pve!portal",
        "PROXMOX_TOKEN_SECRET": "test-secret",
        "PROXMOX_CA_FILE": "/tmp/test-ca.pem",
        "PROXMOX_TIMEOUT_SECONDS": "10",
        "PROXMOX_TARGET_NODE": "pve02",
        "PROXMOX_POOL": "npd-portal",
        "PROXMOX_TEMPLATE_NODE": "pve01",
        "PROXMOX_TEMPLATE_VMID": "9000",
        "PROXMOX_TEMPLATE_IMAGE_ID": "almalinux-9",
        "PROXMOX_STORAGE": "local-zfs",
        "PROXMOX_CLOUD_INIT_USER": "cloud-user",
        "PROXMOX_IPCONFIG0": "ip=dhcp",
        "PROXMOX_NAMESERVER": "1.1.1.1",
        "PROXMOX_SEARCH_DOMAIN": "example.test",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    client = Mock()
    client.aclose = AsyncMock()
    client_factory = Mock(return_value=client)
    monkeypatch.setattr(adapter_module, "ProxmoxClient", client_factory)

    async def check():
        async with create_worker_adapter() as adapter:
            assert isinstance(adapter, HttpProxmoxAdapter)
            assert adapter._client is client
            assert adapter._target_node == "pve02"
            assert adapter._template_vmid == 9000

    asyncio.run(check())

    client_factory.assert_called_once_with(
        api_url=values["PROXMOX_API_URL"],
        token_id=values["PROXMOX_TOKEN_ID"],
        token_secret=values["PROXMOX_TOKEN_SECRET"],
        ca_file=values["PROXMOX_CA_FILE"],
        timeout_seconds=10,
    )
    client.aclose.assert_awaited_once()

    client.aclose.reset_mock()

    async def check_error():
        async with create_worker_adapter():
            raise RuntimeError("worker stopped")

    with pytest.raises(RuntimeError, match="worker stopped"):
        asyncio.run(check_error())
    client.aclose.assert_awaited_once()


def test_worker_main_uses_selected_adapter(monkeypatch, tmp_path) -> None:
    without_worker_config(monkeypatch, tmp_path)
    run_worker = AsyncMock()
    monkeypatch.setattr(worker, "run_worker", run_worker)

    asyncio.run(worker.main())

    run_worker.assert_awaited_once()
    assert isinstance(run_worker.await_args.args[0], FakeProxmoxAdapter)
