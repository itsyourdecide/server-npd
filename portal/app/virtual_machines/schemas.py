from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


#отдельный класс что бы передавать браузеру только то что мы хотим
class VirtualMachineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True) #разрешает Pydantic читать данные из атрибутов SQLAlchemy-объекта

    id: UUID
    status: str
    requested_vcpus: int
    requested_memory_mb: int
    requested_storage_gb: int
    image_id: str
    ssh_public_key_id: UUID | None
    created_at: datetime
    updated_at: datetime

#класс для создания виртуалок
class VirtualMachineCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid", #защита от вась
        str_strip_whitespace=True,
    )

    requested_vcpus: int = Field(gt=0)
    requested_memory_mb: int = Field(gt=0)
    requested_storage_gb: int = Field(gt=0)
    image_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    ssh_public_key_id: UUID