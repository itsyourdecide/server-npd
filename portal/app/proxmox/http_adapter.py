from typing import Any
from uuid import UUID

from app.proxmox.client import ProxmoxClient
from app.proxmox.contracts import (
    CreateVmRequest,
    ProviderCloneResult,
    ProviderDeleteResult,
    ProviderPlacement,
    ProviderTask,
    ProviderTaskStatus,
    ProviderVmState,
)
from app.proxmox.errors import ProviderResourceConflictError


class HttpProxmoxAdapter:
    def __init__(
        self,
        client: ProxmoxClient,
        *,
        target_node: str,
        pool: str,
        template_node: str,
        template_vmid: int,
        template_image_id: str,
        storage: str,
        cloud_init_user: str,
        ipconfig0: str,
        nameserver: str,
        search_domain: str,
    ) -> None:
        self._client = client
        self._target_node = target_node
        self._pool = pool
        self._template_node = template_node
        self._template_vmid = template_vmid
        self._template_image_id = template_image_id
        self._storage = storage
        self._cloud_init_user = cloud_init_user
        self._ipconfig0 = ipconfig0
        self._nameserver = nameserver
        self._search_domain = search_domain

    @staticmethod
    def _vm_name(vm_id: UUID) -> str:
        return f"npd-{vm_id}"

    async def choose_clone_target(
        self,
        request: CreateVmRequest,
    ) -> ProviderPlacement:
        vmid = await self._client.get_next_vmid()

        return ProviderPlacement(
            node=self._target_node,
            vmid=vmid,
        )

    async def _find_owned_vm_resource(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> dict[str, Any] | None:
        resource = await self._client.find_vm_resource(vmid)

        if resource is None:
            return None

        expected_name = self._vm_name(portal_vm_id)

        if resource.get("type") != "qemu":
            raise ProviderResourceConflictError(f"VMID {vmid} belongs to a non-QEMU resource")

        if resource.get("name") != expected_name:
            raise ProviderResourceConflictError(f"VMID {vmid} has unexpected name")

        if resource.get("pool") != self._pool:
            raise ProviderResourceConflictError(f"VMID {vmid} belongs to another pool")

        if resource.get("node") != node:
            raise ProviderResourceConflictError(f"VMID {vmid} belongs to another node")

        return resource


    async def clone_vm(
        self,
        request: CreateVmRequest,
        *,
        node: str,
        vmid: int,
    ) -> ProviderCloneResult:
        if node != self._target_node:
            raise ValueError("unexpected Proxmox target node")

        if request.image_id != self._template_image_id:
            raise ValueError(f"unsupported VM image: {request.image_id}")

        resource = await self._find_owned_vm_resource(
            request.vm_id,
            node=node,
            vmid=vmid,
        )

        if resource is not None:
            lock = resource.get("lock")

            if lock == "clone":
                return ProviderCloneResult(
                    state="in_progress",
                )

            if lock is not None:
                raise ProviderResourceConflictError(f"VMID {vmid} has unexpected lock: {lock}")

            return ProviderCloneResult(state="succeeded")

        upid = await self._client.clone_vm(
            source_node=self._template_node,
            target_node=node,
            template_vmid=self._template_vmid,
            new_vmid=vmid,
            name=self._vm_name(request.vm_id),
            storage=self._storage,
            pool=self._pool,
        )

        task = ProviderTask(
            task_id=upid,
            node=node,
            vmid=vmid,
        )

        return ProviderCloneResult(
            state="submitted",
            task=task,
        )

    async def get_task_status(
        self,
        task: ProviderTask,
    ) -> ProviderTaskStatus:
        data = await self._client.get_task_status(
            node=task.node,
            upid=task.task_id,
        )

        response_upid = data.get("upid")

        if response_upid != task.task_id:
            raise RuntimeError("Proxmox returned status for another task")

        status = data.get("status")

        if status == "running":
            return ProviderTaskStatus(
                status="running",
            )

        if status != "stopped":
            raise RuntimeError(f"unknown Proxmox task status: {status}")

        exit_status = data.get("exitstatus")

        if not isinstance(exit_status, str):
            raise RuntimeError("finished Proxmox task has no exit status")

        if exit_status == "OK":
            return ProviderTaskStatus(
                status="succeeded",
            )

        return ProviderTaskStatus(
            status="failed",
            error_code="proxmox_task_failed",
        )


    async def configure_vm(
        self,
        request: CreateVmRequest,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        if node != self._target_node:
            raise ValueError("unexpected Proxmox target node")

        resource = await self._find_owned_vm_resource(
            request.vm_id,
            node=node,
            vmid=vmid,
        )

        if resource is None:
            raise RuntimeError(f"VMID {vmid} is missing before configuration")

        lock = resource.get("lock")

        if lock is not None:
            raise RuntimeError(f"VMID {vmid} is locked before configuration: {lock}")

        tags = f"npd-portal;npd-{request.vm_id}"

        upid = await self._client.configure_vm(
            node=node,
            vmid=vmid,
            vcpus=request.vcpus,
            memory_mb=request.memory_mb,
            cloud_init_user=self._cloud_init_user,
            ipconfig0=self._ipconfig0,
            nameserver=self._nameserver,
            search_domain=self._search_domain,
            ssh_public_key=request.ssh_public_key,
            tags=tags,
        )

        if upid is None:
            return None

        return ProviderTask(
            task_id=upid,
            node=node,
            vmid=vmid,
        )


    async def resize_vm_disk(
        self,
        request: CreateVmRequest,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        if node != self._target_node:
            raise ValueError("unexpected Proxmox target node")

        resource = await self._find_owned_vm_resource(
            request.vm_id,
            node=node,
            vmid=vmid,
        )

        if resource is None:
            raise RuntimeError(f"VMID {vmid} is missing before disk resize")

        lock = resource.get("lock")

        if lock is not None:
            raise RuntimeError(f"VMID {vmid} is locked before disk resize: {lock}")

        vm_status = await self._client.get_vm_current_status(
            node=node,
            vmid=vmid,
        )

        current_size_bytes = vm_status.get("maxdisk")

        if (
            not isinstance(current_size_bytes, int)
            or isinstance(current_size_bytes, bool)
            or current_size_bytes <= 0
        ):
            raise RuntimeError(f"VMID {vmid} has invalid disk size")

        requested_size_bytes = request.storage_gb * 1024**3

        if current_size_bytes > requested_size_bytes:
            raise RuntimeError(f"VMID {vmid} disk is larger than requested")

        if current_size_bytes == requested_size_bytes:
            return None

        upid = await self._client.resize_vm_disk(
            node=node,
            vmid=vmid,
            disk="scsi0",
            size_gb=request.storage_gb,
        )

        return ProviderTask(
            task_id=upid,
            node=node,
            vmid=vmid,
        )

    async def start_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        state = await self.get_vm_power_state(
            portal_vm_id,
            node=node,
            vmid=vmid,
        )

        if state.locked:
            raise RuntimeError(f"VMID {vmid} is locked before start")

        if state.status == "running":
            return None

        if state.status != "stopped":
            raise RuntimeError(
                f"VMID {vmid} has unexpected status before start: "
                f"{state.status}"
            )

        upid = await self._client.start_vm(
            node=node,
            vmid=vmid,
        )

        return ProviderTask(
            task_id=upid,
            node=node,
            vmid=vmid,
        )


    async def _get_owned_vm_status(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> str:
        resource = await self._find_owned_vm_resource(
            portal_vm_id,
            node=node,
            vmid=vmid,
        )

        if resource is None:
            raise RuntimeError(f"VMID {vmid} is missing")

        lock = resource.get("lock")

        if lock is not None:
            raise RuntimeError(
                f"VMID {vmid} is locked: {lock}"
            )

        vm_status = await self._client.get_vm_current_status(
            node=node,
            vmid=vmid,
        )

        current_status = vm_status.get("status")

        if current_status not in {"running", "stopped"}:
            raise RuntimeError(
                f"VMID {vmid} has unexpected status: {current_status}"
            )

        return current_status

    async def get_vm_power_state(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderVmState:
        if node != self._target_node:
            raise ValueError("unexpected Proxmox target node")

        resource = await self._find_owned_vm_resource(
            portal_vm_id,
            node=node,
            vmid=vmid,
        )

        if resource is None:
            return ProviderVmState(status="missing")

        vm_status = await self._client.get_vm_current_status(
            node=node,
            vmid=vmid,
        )
        current_status = vm_status.get("status")

        if current_status not in {"running", "stopped"}:
            raise RuntimeError(f"VMID {vmid} has unexpected status: {current_status}")

        return ProviderVmState(
            status=current_status,
            locked=(
                resource.get("lock") is not None
                or vm_status.get("lock") is not None
            ),
        )

    async def shutdown_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        current_status = await self._get_owned_vm_status(
            portal_vm_id,
            node=node,
            vmid=vmid,
        )

        if current_status == "stopped":
            return None

        upid = await self._client.shutdown_vm(
            node=node,
            vmid=vmid,
        )

        return ProviderTask(
            task_id=upid,
            node=node,
            vmid=vmid,
        )

    async def stop_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        current_status = await self._get_owned_vm_status(
            portal_vm_id,
            node=node,
            vmid=vmid,
        )

        if current_status == "stopped":
            return None

        upid = await self._client.stop_vm(
            node=node,
            vmid=vmid,
        )

        return ProviderTask(
            task_id=upid,
            node=node,
            vmid=vmid,
        )

    async def delete_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderDeleteResult:
        if node != self._target_node:
            raise ValueError("unexpected Proxmox target node")

        resource = await self._find_owned_vm_resource(
            portal_vm_id,
            node=node,
            vmid=vmid,
        )

        if resource is None:
            # Повторный проход после успешного удаления: удалять уже нечего.
            return ProviderDeleteResult(state="succeeded")

        if resource.get("lock") is not None:
            # Proxmox ещё занят этой VM. Не отправляем второй DELETE вслепую.
            return ProviderDeleteResult(state="in_progress")

        vm_status = await self._client.get_vm_current_status(
            node=node,
            vmid=vmid,
        )

        if vm_status.get("status") != "stopped":
            raise RuntimeError(f"VMID {vmid} must be stopped before delete")

        upid = await self._client.delete_vm(
            node=node,
            vmid=vmid,
        )

        return ProviderDeleteResult(
            state="submitted",
            task=ProviderTask(
                task_id=upid,
                node=node,
                vmid=vmid,
            ),
        )
