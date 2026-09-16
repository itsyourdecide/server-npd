from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComputePlan(Base):
    __tablename__ = "compute_plans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50))
    max_vms: Mapped[int] = mapped_column()
    max_running_vms: Mapped[int] = mapped_column()
    max_total_vcpus: Mapped[int] = mapped_column()
    max_total_memory_mb: Mapped[int] = mapped_column()
    max_total_storage_gb: Mapped[int] = mapped_column()
    max_shared_storage_gb: Mapped[int] = mapped_column()
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "code",
            name="uq_compute_plans_code",
        ),
        CheckConstraint(
            "max_vms >= 0",
            name="ck_compute_plans_max_vms_non_negative",
        ),
        CheckConstraint(
            "max_running_vms >= 0",
            name="ck_compute_plans_max_running_vms_non_negative",
        ),
        CheckConstraint(
            "max_running_vms <= max_vms",
            name="ck_compute_plans_running_vms_limit",
        ),
        CheckConstraint(
            "max_total_vcpus >= 0",
            name="ck_compute_plans_vcpus_non_negative",
        ),
        CheckConstraint(
            "max_total_memory_mb >= 0",
            name="ck_compute_plans_memory_non_negative",
        ),
        CheckConstraint(
            "max_total_storage_gb >= 0",
            name="ck_compute_plans_storage_non_negative",
        ),
        CheckConstraint(
            "max_shared_storage_gb >= 0",
            name="ck_compute_plans_shared_storage_non_negative",
        ),
    )

class UserQuota(Base):
    __tablename__ = "user_quota"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    compute_plan_id: Mapped[UUID] = mapped_column(ForeignKey("compute_plans.id"), index=True)
    status: Mapped[str] = mapped_column(server_default="active", default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_user_status",
        ),
    )

