from .base import *  # noqa: F403

SECRET_KEY = "test-only-not-for-production"
DEBUG = False
ALLOWED_HOSTS = ["testserver"]
LOCAL_AUTH_ENABLED = True
OIDC_ENABLED = True
OIDC_PROVIDER_NAME = "Google"
OIDC_PROVIDER_SLUG = "google"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
