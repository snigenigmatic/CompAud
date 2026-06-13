from fastapi import APIRouter

from app.config import get_settings
from app.models.system import HealthResponse


router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="getHealth",
    summary="Get backend health",
)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="rakshak-ai-backend",
        environment=settings.app_env,
        phoenix_enabled=settings.phoenix_enabled,
        phoenix_project_name=settings.phoenix_project_name,
        openai_enabled=settings.openai_enabled,
        openai_model=settings.openai_model,
    )
