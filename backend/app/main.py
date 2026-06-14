import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.controllers.system_controller import router as system_router
from app.errors import ApiError, api_error_handler
from app.observability import configure_phoenix_tracing, shutdown_observability

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_phoenix_tracing(settings)
    try:
        yield
    finally:
        shutdown_observability()


app = FastAPI(
    title="CompAud Backend",
    version="0.1.0",
    description="Compliance readiness analysis backend for CompAud.",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "system",
            "description": "Backend health and runtime configuration.",
        },
        {
            "name": "ps3",
            "description": "Automated compliance evidence collection & audit (PS3).",
        },
    ],
)
app.add_exception_handler(ApiError, api_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.controllers.ps3_controller import router as ps3_router

app.include_router(system_router)
app.include_router(ps3_router)
