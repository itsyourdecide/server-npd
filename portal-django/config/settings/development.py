from .base import *  # noqa: F403

SECRET_KEY = "development-only-not-for-production"
DEBUG = True
ALLOWED_HOSTS = [
    host.strip()
    for host in env(
        "DJANGO_ALLOWED_HOSTS",
        default="127.0.0.1,localhost,10.10.40.107",
    ).split(",")
    if host.strip()
]
LOCAL_AUTH_ENABLED = True
