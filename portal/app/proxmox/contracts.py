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
    ssh_public_key: str

@dataclass(frozen=True, slots=True)
class ProviderTask:
    task_id: str
    vmid: int
    node: str

@dataclass(frozen=True, slots=True)
class ProviderCloneResult:
    state: Literal["submitted", "in_progress", "succeeded"]
    task: ProviderTask | None = None

@dataclass(frozen=True, slots=True)
class ProviderDeleteResult:
    state: Literal["submitted", "in_progress", "succeeded"]
    task: ProviderTask | None = None

@dataclass(frozen=True, slots=True)
class ProviderTaskStatus:
    status: Literal["running", "succeeded", "failed"]
    error_code: str | None = None

@dataclass(frozen=True, slots=True)
class ProviderVmState:
    status: Literal["running", "stopped", "missing"]
    locked: bool = False

@dataclass(frozen=True, slots=True)
class ProviderPlacement:
    node: str
    vmid: int

class ProxmoxAdapter(Protocol):

    async def get_vm_power_state(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderVmState:
        ...

    async def choose_clone_target(
        self,
        request: CreateVmRequest,
    ) -> ProviderPlacement:
        ...

    async def get_task_status(
        self,
        task: ProviderTask,
    ) -> ProviderTaskStatus:
        ...
    
    async def clone_vm(
        self,
        request: CreateVmRequest,
        *,
        node: str,
        vmid: int,
    ) -> ProviderCloneResult:
        ...

    async def configure_vm(
        self,
        request: CreateVmRequest,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        ...

    async def resize_vm_disk(
        self,
        request: CreateVmRequest,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        ...

    async def start_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        ...

    async def shutdown_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        ...

    async def stop_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderTask | None:
        ...

    async def delete_vm(
        self,
        portal_vm_id: UUID,
        *,
        node: str,
        vmid: int,
    ) -> ProviderDeleteResult:
        ...
