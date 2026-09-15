from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: SecretStr

    oidc_state_secret: SecretStr

    oidc_cookie_secure: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
