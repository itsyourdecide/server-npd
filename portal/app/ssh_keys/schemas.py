from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SshPublicKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    public_key: str = Field(min_length=1, max_length=8192)

class SshPublicKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_type: str
    fingerprint: str
    created_at: datetime

class SshKeyPairGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)

class GeneratedSshKeyPairRead(BaseModel):
    key: SshPublicKeyRead
    private_key: str