from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SshPublicKey(Base):
    __tablename__ = "ssh_public_keys"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    key_type: Mapped[str] = mapped_column(String(50))
    public_key: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "name",
            name="uq_ssh_public_keys_owner_name",
        ),
        UniqueConstraint(
            "fingerprint",
            name="uq_ssh_public_keys_fingerprint",
        ),
    )
