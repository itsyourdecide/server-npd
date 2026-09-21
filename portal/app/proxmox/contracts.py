from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CreateVmRequest:
    vm_id: UUID
    image_id: str
    vcpus: int
    memory_mb: int
    storage_gb: int

@dataclass(frozen=True, slots=True)
class ProviderTask:
    task_id: str
    vmid: int
    node: str

@dataclass(frozen=True, slots=True)
class ProviderTaskStatus:
    status: Literal["running", "succeeded", "failed"]
    error_code: str | None = None

class ProxmoxAdapter(Protocol):
    async def create_vm(
        self,
        request: CreateVmRequest,
    ) -> ProviderTask:
        ...

    async def get_task_status(
        self,
        task: ProviderTask,
    ) -> ProviderTaskStatus:
        ...