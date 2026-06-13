from fastapi.testclient import TestClient

from app.main import app


def test_openapi_has_stable_operation_ids_for_sdk_generation() -> None:
    client = TestClient(app)

    spec = client.get("/openapi.json").json()

    assert spec["paths"]["/health"]["get"]["operationId"] == "getHealth"
    assert spec["paths"]["/controls"]["get"]["operationId"] == "getControls"
    assert spec["paths"]["/demo/golden"]["get"]["operationId"] == "getDemoGolden"
    assert spec["paths"]["/demo/golden/stream"]["get"]["operationId"] == "streamDemoGolden"
    assert spec["paths"]["/analyze"]["post"]["operationId"] == "analyzeEvidence"
    assert spec["paths"]["/analyze/stream"]["post"]["operationId"] == "streamAnalyzeEvidence"


def test_openapi_documents_analysis_upload_contract() -> None:
    client = TestClient(app)

    spec = client.get("/openapi.json").json()
    analyze = spec["paths"]["/analyze"]["post"]

    assert analyze["tags"] == ["analysis"]
    assert analyze["summary"] == "Analyze uploaded compliance evidence"
    assert "multipart/form-data" in analyze["requestBody"]["content"]
    assert analyze["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AnalysisResponse"
    }
    assert analyze["responses"]["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert analyze["responses"]["415"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_openapi_includes_frontend_response_schemas() -> None:
    client = TestClient(app)

    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]

    assert "AnalysisResponse" in schemas
    assert "ControlReportResult" in schemas
    assert "ErrorResponse" in schemas
    assert schemas["ErrorResponse"]["additionalProperties"] is False
    assert schemas["ErrorResponse"]["required"] == ["error"]
