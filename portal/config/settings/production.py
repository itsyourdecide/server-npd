from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env


def required(name):
    value = env(name, default="")
    if not value:
        raise ImproperlyConfigured(f"{name} is required")
    return value


SECRET_KEY = required("DJANGO_SECRET_KEY")

DEBUG = False

ALLOWED_HOSTS = [
    host.strip()
    for host in required("DJANGO_ALLOWED_HOSTS").split(",")
    if host.strip()
]

LOCAL_AUTH_ENABLED = False
OIDC_ENABLED = True
AUTHENTICATION_BACKENDS = [
    "apps.accounts.oidc.PortalOIDCAuthenticationBackend",
]

OIDC_OP_ISSUER = required("OIDC_OP_ISSUER")
OIDC_OP_AUTHORIZATION_ENDPOINT = required("OIDC_OP_AUTHORIZATION_ENDPOINT")
OIDC_OP_TOKEN_ENDPOINT = required("OIDC_OP_TOKEN_ENDPOINT")
OIDC_OP_USER_ENDPOINT = required("OIDC_OP_USER_ENDPOINT")
OIDC_RP_CLIENT_ID = required("OIDC_RP_CLIENT_ID")
OIDC_RP_CLIENT_SECRET = required("OIDC_RP_CLIENT_SECRET")
OIDC_RP_SIGN_ALGO = env("OIDC_RP_SIGN_ALGO", default="RS256")
OIDC_OP_JWKS_ENDPOINT = env("OIDC_OP_JWKS_ENDPOINT", default="")
if OIDC_RP_SIGN_ALGO.startswith(("RS", "ES")) and not OIDC_OP_JWKS_ENDPOINT:
    raise ImproperlyConfigured(
        "OIDC_OP_JWKS_ENDPOINT is required for asymmetric token signatures"
    )

OIDC_RP_SCOPES = "openid profile email"
OIDC_CREATE_USER = True
OIDC_USE_NONCE = True
OIDC_USE_PKCE = True
OIDC_VERIFY_JWT = True
OIDC_VERIFY_KID = True
OIDC_VERIFY_SSL = True
OIDC_ALLOW_UNSECURED_JWT = False
OIDC_STORE_ACCESS_TOKEN = False
OIDC_STORE_ID_TOKEN = False
OIDC_TIMEOUT = env.int("OIDC_TIMEOUT", default=10)
ALLOW_LOGOUT_GET_METHOD = False

LOGIN_URL = "oidc_authentication_init"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
