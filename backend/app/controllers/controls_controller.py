from fastapi import APIRouter

from app.models.controls import ControlCatalogResponse
from app.services.control_catalog_service import (
    CONTROL_REQUIREMENTS_SOURCE,
    load_control_requirements,
)


router = APIRouter(tags=["controls"])


@router.get(
    "/controls",
    response_model=ControlCatalogResponse,
    operation_id="getControls",
    summary="Get compliance control catalog",
)
def controls() -> ControlCatalogResponse:
    control_requirements = load_control_requirements()
    return ControlCatalogResponse(
        source=CONTROL_REQUIREMENTS_SOURCE,
        count=len(control_requirements),
        controls=control_requirements,
    )
