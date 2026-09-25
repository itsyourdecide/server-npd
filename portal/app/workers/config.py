from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerModeSettings(BaseSettings):
    worker_adapter: Literal["fake", "proxmox"] = "fake"

    model_config = SettingsConfigDict(
        env_file=".env.worker",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class OperationWorkerSettings(WorkerModeSettings):
    proxmox_api_url: str
    proxmox_token_id: str
    proxmox_token_secret: SecretStr
    proxmox_ca_file: Path
    proxmox_timeout_seconds: float = Field(default=10, gt=0, lt=300)
    proxmox_target_node: str
    proxmox_pool: str
    proxmox_template_node: str
    proxmox_template_vmid: int
    proxmox_template_image_id: str
    proxmox_storage: str
    proxmox_cloud_init_user: str
    proxmox_ipconfig0: str
    proxmox_nameserver: str
    proxmox_search_domain: str
