from fastapi import FastAPI

from app.system.router import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="portal",
        version="0.1.0",
    )

    app.include_router(router)
    return app


app = create_app()
