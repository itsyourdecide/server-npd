from authlib.integrations.starlette_client import OAuth

from app.core.config import settings

oauth = OAuth()

oauth.register(
    name="keycloak",
    client_id=settings.oidc_client_id,
    client_secret=settings.oidc_client_secret.get_secret_value(),
    server_metadata_url=(
        f"{settings.oidc_issuer}/.well-known/openid-configuration"
    ),
    client_kwargs={"scope": "openid profile email"},
)
