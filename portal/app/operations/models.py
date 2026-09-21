from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    virtual_machine_id: Mapped[UUID] = mapped_column(ForeignKey("virtual_machines.id"), index=True)
    operation_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    provider_task_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint (
            "operation_type IN ('vm.create', 'vm.start', 'vm.stop', 'vm.delete')",
            name="operation_type_list",
        ),
        CheckConstraint (
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="operations_status_list",
        ),
        CheckConstraint (
            "attempts >= 0",
            name="operations_attempts_not_negative",
        ),
        UniqueConstraint (
            "idempotency_key", 
            name="uq_operations_idempotency_key",
        ),
    )