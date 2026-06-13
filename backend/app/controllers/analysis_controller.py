from uuid import uuid4

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.agents.evidence import (
    EvidenceError,
    EvidenceParseError,
    UnsafeEvidenceArchiveError,
    UnsupportedEvidenceTypeError,
)
from app.errors import ApiError
from app.models.analysis import AnalysisResponse
from app.models.errors import ErrorResponse
from app.services.analysis_service import (
    analyze_demo_evidence,
    analyze_evidence_bytes,
    stream_demo_evidence,
    stream_evidence_analysis,
)


router = APIRouter(tags=["analysis"])


@router.get(
    "/demo/golden",
    response_model=AnalysisResponse,
    operation_id="getDemoGolden",
    summary="Get deterministic demo analysis",
)
def demo_golden() -> AnalysisResponse:
    return analyze_demo_evidence()


@router.get(
    "/demo/golden/stream",
    operation_id="streamDemoGolden",
    summary="Stream deterministic demo analysis progress",
)
def demo_golden_stream() -> StreamingResponse:
    return _sse_response(stream_demo_evidence())


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    operation_id="analyzeEvidence",
    summary="Analyze uploaded compliance evidence",
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Invalid evidence upload.",
        },
        415: {
            "model": ErrorResponse,
            "description": "Unsupported evidence file type.",
        },
    },
)
async def analyze(file: UploadFile = File(...)) -> AnalysisResponse:
    if not file.filename:
        raise ApiError(
            status_code=400,
            code="MISSING_FILENAME",
            message="Uploaded evidence must include a filename.",
        )

    content = await file.read()
    if not content:
        raise ApiError(
            status_code=400,
            code="EMPTY_UPLOAD",
            message="Uploaded evidence file is empty.",
        )

    try:
        return analyze_evidence_bytes(
            filename=file.filename,
            content=content,
            request_id=str(uuid4()),
        )
    except UnsupportedEvidenceTypeError as exc:
        raise ApiError(
            status_code=415,
            code="UNSUPPORTED_EVIDENCE_TYPE",
            message=str(exc),
        ) from exc
    except UnsafeEvidenceArchiveError as exc:
        raise ApiError(
            status_code=400,
            code="UNSAFE_ARCHIVE_PATH",
            message=str(exc),
        ) from exc
    except EvidenceParseError as exc:
        raise ApiError(
            status_code=400,
            code="EVIDENCE_PARSE_ERROR",
            message=str(exc),
        ) from exc
    except EvidenceError as exc:
        raise ApiError(
            status_code=400,
            code="EVIDENCE_ERROR",
            message=str(exc),
        ) from exc


@router.post(
    "/analyze/stream",
    operation_id="streamAnalyzeEvidence",
    summary="Stream uploaded compliance evidence analysis progress",
)
async def analyze_stream(file: UploadFile = File(...)) -> StreamingResponse:
    if not file.filename:
        raise ApiError(
            status_code=400,
            code="MISSING_FILENAME",
            message="Uploaded evidence must include a filename.",
        )

    content = await file.read()
    if not content:
        raise ApiError(
            status_code=400,
            code="EMPTY_UPLOAD",
            message="Uploaded evidence file is empty.",
        )

    return _sse_response(
        stream_evidence_analysis(
            filename=file.filename,
            content=content,
            request_id=str(uuid4()),
        )
    )


def _sse_response(events) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
