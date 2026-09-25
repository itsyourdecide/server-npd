from uuid import UUID

from app.proxmox.contracts import (
    CreateVmRequest,
    ProviderPlacement,
    ProviderTask,
    ProviderTaskStatus,
    ProviderDeleteResult,
    ProviderVmState,
)
from app.proxmox.contracts import ProviderCloneResult


class FakeProxmoxAdapter:
    def __init__(
        self,
        node: str = "fake-node",
    ) -> None:
        self._node = node

        self.created_vms: dict[int, CreateVmRequest] = {}
        self._task_statuses: dict[str, ProviderTaskStatus] = {}
        self._deleted_vmids: set[int] = set()
        self._power_states: dict[int, str] = {}

    @staticmethod
    def _vmid_for_vm_id(
        vm_id: UUID,
    ) -> int:
        return 100_000 + (vm_id.int % 899_900_000)


    async def choose_clone_target(
        self,
        request: CreateVmRequest,
    ) -> ProviderPlacement:
        return ProviderPlacement(
            node=self._node,
            vmid=self._vmid_for_vm_id(request.vm_id),
        )

    async def clone_vm(
        self,
        request: CreateVmRequest,
        *,
        node: str,
        vmid: int,
    ) -> ProviderCloneResult:
        if node != self._node:
            raise RuntimeError("fake provider node does not match")

        if vmid != self._vmid_for_vm_id(request.vm_id):
            raise RuntimeError("fake provider VMID does not match")

        task = ProviderTask(
            task_id=f"fake:clone:{request.vm_id}",
            vmid=vmid,
            node=node,
        )

        self.created_vms[vmid] = request
        self._power_states[vmid] = "stopped"
        self._task_statuses[task.task_id] = ProviderTaskStatus(
            status="succeeded",
        )

        return ProviderCloneResult(
            state="submitted",
            task=task,
        )

    async def get_task_status(
        self,
        task: ProviderTask,
    ) -> ProviderTaskStatus:
        status = self._task_statuses.get(task.task_id)

        if status is not None:
            return status

        parts = task.task_id.split(":")
        
        if len(parts) != 3:
            raise RuntimeError("invalid fake provider task id")

        prefix, operation_type, raw_vm_id = parts

        if prefix != "fake" or operation_type not in {
            "clone",
            "resize",
            "start",
            "shutdown",
            "stop",
            "delete",
        }:
            raise RuntimeError("invalid fake provider task id")

        try:
            vm_id = UUID(raw_vm_id)
        except ValueError as exc:
            raise RuntimeError(
                "invalid fake provider task id"
            ) from exc

        expected_vmid = self._vmid_for_vm_id(vm_id)

        if task.vmid != expected_vmid:
            raise RuntimeError("fake provider VMID does not match task")

        if task.node != self._node:
            raise RuntimeError("fake provider node does not match task")

        return ProviderTaskStatus(
            status="succeeded",
        )

    async def configure_vm(
        self,
        request: CreateVmRequest,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        if node != self._node:
            raise RuntimeError("fake provider node does not match")

        if vmid != self._vmid_for_vm_id(request.vm_id):
            raise RuntimeError("fake provider VMID does not match")

        return None


    async def resize_vm_disk(
        self,
        request: CreateVmRequest,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask:
        if node != self._node:
            raise RuntimeError("fake provider node does not match")

        if vmid != self._vmid_for_vm_id(request.vm_id):
            raise RuntimeError("fake provider VMID does not match")

        task = ProviderTask(
            task_id=f"fake:resize:{request.vm_id}",
            vmid=vmid,
            node=node,
        )
        self._task_statuses[task.task_id] = ProviderTaskStatus(status="succeeded")
        return task


    async def start_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask:
        if node != self._node:
            raise RuntimeError("fake provider node does not match")

        if vmid != self._vmid_for_vm_id(portal_vm_id):
            raise RuntimeError("fake provider VMID does not match")

        task = ProviderTask(
            task_id=f"fake:start:{portal_vm_id}",
            vmid=vmid,
            node=node,
        )
        self._task_statuses[task.task_id] = ProviderTaskStatus(status="succeeded")
        self._power_states[vmid] = "running"
        return task


    async def shutdown_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        if node != self._node:
            raise RuntimeError("fake provider node does not match")

        if vmid != self._vmid_for_vm_id(portal_vm_id):
            raise RuntimeError("fake provider VMID does not match")

        task = ProviderTask(
            task_id=f"fake:shutdown:{portal_vm_id}",
            vmid=vmid,
            node=node,
        )
        self._task_statuses[task.task_id] = ProviderTaskStatus(status="succeeded")
        self._power_states[vmid] = "stopped"
        return task


    async def stop_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        if node != self._node:
            raise RuntimeError("fake provider node does not match")

        if vmid != self._vmid_for_vm_id(portal_vm_id):
            raise RuntimeError("fake provider VMID does not match")

        task = ProviderTask(
            task_id=f"fake:stop:{portal_vm_id}",
            vmid=vmid,
            node=node,
        )
        self._task_statuses[task.task_id] = ProviderTaskStatus(status="succeeded")
        self._power_states[vmid] = "stopped"
        return task

    async def get_vm_power_state(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderVmState:
        if node != self._node:
            raise RuntimeError("fake provider node does not match")

        if vmid != self._vmid_for_vm_id(portal_vm_id):
            raise RuntimeError("fake provider VMID does not match")

        if vmid in self._deleted_vmids:
            return ProviderVmState(status="missing")

        if vmid not in self.created_vms and vmid not in self._power_states:
            return ProviderVmState(status="missing")

        return ProviderVmState(status=self._power_states.get(vmid, "stopped"))

    async def delete_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderDeleteResult:
        if node != self._node:
            raise RuntimeError("fake provider node does not match")

        if vmid != self._vmid_for_vm_id(portal_vm_id):
            raise RuntimeError("fake provider VMID does not match")

        if vmid in self._deleted_vmids:
            return ProviderDeleteResult(state="succeeded")

        task = ProviderTask(
            task_id=f"fake:delete:{portal_vm_id}",
            vmid=vmid,
            node=node,
        )
        self._task_statuses[task.task_id] = ProviderTaskStatus(status="succeeded")
        self._deleted_vmids.add(vmid)
        self.created_vms.pop(vmid, None)
        self._power_states.pop(vmid, None)

        return ProviderDeleteResult(state="submitted", task=task)
