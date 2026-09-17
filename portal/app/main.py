from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.compute.router import router as compute_router
from app.core.config import settings
from app.identity.router import router as identity_router
from app.system.router import router as system_router
from app.virtual_machines.router import router as vm_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="portal",
        version="0.1.0",
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.oidc_state_secret.get_secret_value(),
        session_cookie="npd_oidc_state",
        max_age=600,
        same_site="lax",
        https_only=settings.oidc_cookie_secure,
    )

    app.include_router(identity_router)
    app.include_router(system_router)
    app.include_router(compute_router)
    app.include_router(vm_router)

    return app


app = create_app()
