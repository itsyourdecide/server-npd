from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    virtual_machine_id: UUID
    operation_type: str
    status: str
    phase: str | None
    created_at: datetime
    updated_at: datetime
    last_error_code: str | None
    
