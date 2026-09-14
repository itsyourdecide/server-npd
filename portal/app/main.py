from fastapi import FastAPI

from app.system.router import router

app = FastAPI(
    title="portal",
    version="0.1.0",
)

app.include_router(router)
