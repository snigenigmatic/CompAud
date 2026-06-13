import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.controllers.analysis_controller import router as analysis_router
from app.controllers.controls_controller import router as controls_router
from app.controllers.system_controller import router as system_router
from app.errors import ApiError, api_error_handler
from app.knowledge.graph import close_driver, init_driver
from app.observability import configure_phoenix_tracing, shutdown_observability

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_phoenix_tracing(settings)
    if settings.neo4j_uri:
        try:
            init_driver(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        except Exception:
            logger.warning("Neo4j connection failed — running without knowledge graph", exc_info=True)
    try:
        yield
    finally:
        close_driver()
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
            "name": "controls",
            "description": "Compliance control catalog endpoints.",
        },
        {
            "name": "analysis",
            "description": "Evidence analysis endpoints.",
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

from app.controllers.knowledge_controller import router as knowledge_router
from app.controllers.ps3_controller import router as ps3_router

app.include_router(system_router)
app.include_router(controls_router)
app.include_router(analysis_router)
app.include_router(knowledge_router)
app.include_router(ps3_router)
