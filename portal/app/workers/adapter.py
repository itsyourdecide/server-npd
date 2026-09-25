from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.proxmox.client import ProxmoxClient
from app.proxmox.contracts import ProxmoxAdapter
from app.proxmox.fake import FakeProxmoxAdapter
from app.proxmox.http_adapter import HttpProxmoxAdapter
from app.workers.config import OperationWorkerSettings, WorkerModeSettings


@asynccontextmanager
async def create_worker_adapter() -> AsyncIterator[ProxmoxAdapter]:
    mode = WorkerModeSettings().worker_adapter

    if mode == "fake":
        # Для локальной разработки токен и сертификат Proxmox не нужны.
        yield FakeProxmoxAdapter()
        return

    # Полная проверка PROXMOX_* выполняется только в реальном режиме.
    settings = OperationWorkerSettings()
    client = ProxmoxClient(
        api_url=settings.proxmox_api_url,
        token_id=settings.proxmox_token_id,
        token_secret=settings.proxmox_token_secret.get_secret_value(),
        ca_file=str(settings.proxmox_ca_file),
        timeout_seconds=settings.proxmox_timeout_seconds,
    )

    try:
        adapter = HttpProxmoxAdapter(
            client,
            target_node=settings.proxmox_target_node,
            pool=settings.proxmox_pool,
            template_node=settings.proxmox_template_node,
            template_vmid=settings.proxmox_template_vmid,
            template_image_id=settings.proxmox_template_image_id,
            storage=settings.proxmox_storage,
            cloud_init_user=settings.proxmox_cloud_init_user,
            ipconfig0=settings.proxmox_ipconfig0,
            nameserver=settings.proxmox_nameserver,
            search_domain=settings.proxmox_search_domain,
        )
        yield adapter
    finally:
        await client.aclose()
