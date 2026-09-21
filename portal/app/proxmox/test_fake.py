import asyncio
from uuid import uuid4

from app.proxmox.contracts import CreateVmRequest, ProxmoxAdapter
from app.proxmox.fake import FakeProxmoxAdapter


async def main() -> None:
    adapter: ProxmoxAdapter = FakeProxmoxAdapter()

    request = CreateVmRequest(
        vm_id=uuid4(),
        image_id="almalinux-9",
        vcpus=2,
        memory_mb=4096,
        storage_gb=30,
    )

    task = await adapter.create_vm(request)
    status = await adapter.get_task_status(task)

    print(task)
    print(status)


if __name__ == "__main__":
    asyncio.run(main())