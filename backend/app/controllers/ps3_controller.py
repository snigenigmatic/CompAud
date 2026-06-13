from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse

from app.agents.ps3_pdf import render_report_pdf
from app.errors import ApiError
from app.models.ps3 import PS3ReportResponse, RequirementCatalogResponse
from app.services.ps3_requirement_service import REQUIREMENTS_SOURCE, load_requirements
from app.services.ps3_service import run_ps3_analysis, stream_ps3_analysis

router = APIRouter(prefix="/ps3", tags=["ps3"])


@router.get(
    "/requirements",
    response_model=RequirementCatalogResponse,
    operation_id="getPs3Requirements",
    summary="Get parsed policy requirements",
)
def ps3_requirements() -> RequirementCatalogResponse:
    requirements = load_requirements()
    return RequirementCatalogResponse(
        source=REQUIREMENTS_SOURCE,
        count=len(requirements),
        requirements=requirements,
    )


@router.get(
    "/requirements/{requirement_id}",
    response_model=RequirementCatalogResponse,
    operation_id="getPs3Requirement",
    summary="Get a single parsed requirement by minted id",
)
def ps3_requirement(requirement_id: str) -> RequirementCatalogResponse:
    matches = [req for req in load_requirements() if req.id == requirement_id]
    if not matches:
        raise ApiError(
            status_code=404,
            code="REQUIREMENT_NOT_FOUND",
            message=f"No requirement with id '{requirement_id}'.",
        )
    return RequirementCatalogResponse(
        source=REQUIREMENTS_SOURCE,
        count=len(matches),
        requirements=matches,
    )


@router.post(
    "/analyze",
    response_model=PS3ReportResponse,
    operation_id="analyzePs3",
    summary="Run the full PS3 compliance analysis (collect -> link -> evaluate -> report)",
)
def ps3_analyze() -> PS3ReportResponse:
    return run_ps3_analysis()


@router.get(
    "/analyze/stream",
    operation_id="streamPs3Analyze",
    summary="Stream PS3 compliance analysis progress (SSE)",
)
def ps3_analyze_stream() -> StreamingResponse:
    return StreamingResponse(
        stream_ps3_analysis(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/report.pdf",
    operation_id="getPs3ReportPdf",
    summary="Download the PS3 audit report as PDF",
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF report"}},
)
def ps3_report_pdf() -> Response:
    report = run_ps3_analysis()
    pdf_bytes = render_report_pdf(report)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="compliance_audit_report.pdf"'},
    )
