from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VirtualMachine(Base):
    __tablename__ = "virtual_machines"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(server_default="pending", default="pending")
    requested_vcpus: Mapped[int] = mapped_column()
    requested_memory_mb: Mapped[int] = mapped_column()
    requested_storage_gb: Mapped[int] = mapped_column()
    image_id: Mapped[str] = mapped_column()
    provider_vmid: Mapped[int | None] = mapped_column() #числовой идентификатор VM внутри Proxmox
    provider_node: Mapped[str | None] = mapped_column() #узел Proxmox, на котором сейчас находится VM
    ssh_public_key_id: Mapped[UUID | None] = mapped_column(ForeignKey("ssh_public_keys.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'pending_capacity', 'provisioning', 'running', 'stopped', 'failed', 'deleting', 'deleted')",
            name="vm_user_status",
        ),
        CheckConstraint(
            "requested_vcpus > 0",
            name="vm_requested_vcpus_positive",
        ),
        CheckConstraint(
            "requested_memory_mb > 0",
            name="vm_requested_memory_mb_positive",
        ),
        CheckConstraint(
            "requested_storage_gb > 0",
            name="vm_requested_storage_gb_positive",
        ),
        UniqueConstraint(
            "provider_vmid",
            name="vm_provider_vmid_unique"
        )
    )