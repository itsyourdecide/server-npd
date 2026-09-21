from uuid import UUID, uuid4

from app.proxmox.contracts import CreateVmRequest, ProviderTask, ProviderTaskStatus


class FakeProxmoxAdapter:
    def __init__(
        self,
        node: str = "fake-node",
    ) -> None:
        self._node = node

        self.created_vms: dict[int, CreateVmRequest] = {}
        self._task_statuses: dict[str, ProviderTaskStatus] = {}

    @staticmethod
    def _vmid_for_vm_id(
        vm_id: UUID,
    ) -> int:
        return 100_000 + (vm_id.int % 899_900_000)

    async def create_vm(
        self,
        request: CreateVmRequest,
    ) -> ProviderTask:
        vmid = self._vmid_for_vm_id(request.vm_id)

        task = ProviderTask(
            task_id=f"fake:create:{request.vm_id}",
            vmid=vmid,
            node=self._node,
        )

        self.created_vms[vmid] = request
        self._task_statuses[task.task_id] = ProviderTaskStatus(
            status="succeeded",
        )

        return task

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

        if prefix != "fake" or operation_type != "create":
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