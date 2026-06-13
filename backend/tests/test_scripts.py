import json
import sys

from app.scripts import openapi


def test_openapi_script_exports_spec(
    monkeypatch,
    tmp_path,
) -> None:
    output_path = tmp_path / "openapi.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["rakshak-openapi", "--output", str(output_path)],
    )

    openapi.main()

    spec = json.loads(output_path.read_text(encoding="utf-8"))
    assert spec["paths"]["/analyze"]["post"]["operationId"] == "analyzeEvidence"
    assert "AnalysisResponse" in spec["components"]["schemas"]
