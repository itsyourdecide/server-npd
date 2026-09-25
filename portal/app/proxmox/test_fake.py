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
        ssh_public_key="ssh-ed25519 AAAA... test",
    )

    target = await adapter.choose_clone_target(request)

    clone_result = await adapter.clone_vm(
        request,
        node=target.node,
        vmid=target.vmid,
    )

    if clone_result.state != "submitted":
        raise RuntimeError("fake clone was not submitted")

    if clone_result.task is None:
        raise RuntimeError("submitted clone has no provider task")

    task = clone_result.task
    
    status = await adapter.get_task_status(task)

    configure_task = await adapter.configure_vm(
        request,
        node=task.node,
        vmid=task.vmid,
    )
    assert configure_task is None

    resize_task = await adapter.resize_vm_disk(
        request,
        node=task.node,
        vmid=task.vmid,
    )
    if resize_task is None:
        raise RuntimeError("fake start returned no task")

    status = await adapter.get_task_status(resize_task)
    assert status.status == "succeeded"

    start_task = await adapter.start_vm(
        request.vm_id,
        node=task.node,
        vmid=task.vmid,
    )

    if start_task is None:
        raise RuntimeError("fake start returned no task")

    status = await adapter.get_task_status(start_task)
    assert status.status == "succeeded"

    print(start_task)
    print(status)


if __name__ == "__main__":
    asyncio.run(main())
