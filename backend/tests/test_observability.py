from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

import pytest

from app import observability
from app.agents.evidence import UnsupportedEvidenceTypeError
from app.services.analysis_service import analyze_demo_evidence, analyze_evidence_bytes


@dataclass
class FakeSpan:
    name: str
    attributes: dict[str, str | int | float | bool] = field(default_factory=dict)
    exceptions: list[Exception] = field(default_factory=list)
    status: Any = None

    def is_recording(self) -> bool:
        return True

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        self.attributes[key] = value

    def record_exception(self, exception: Exception) -> None:
        self.exceptions.append(exception)

    def set_status(self, status: Any) -> None:
        self.status = status


class FakeSpanContext(AbstractContextManager[FakeSpan]):
    def __init__(self, span: FakeSpan) -> None:
        self.span = span

    def __enter__(self) -> FakeSpan:
        return self.span

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False


class FakeTracer:
    def __init__(self) -> None:
        self.spans: list[FakeSpan] = []

    def start_as_current_span(self, name: str) -> FakeSpanContext:
        span = FakeSpan(name=name)
        self.spans.append(span)
        return FakeSpanContext(span)


def _install_fake_tracer(monkeypatch: pytest.MonkeyPatch) -> FakeTracer:
    fake_tracer = FakeTracer()
    monkeypatch.setattr(
        observability.trace,
        "get_tracer",
        lambda _: fake_tracer,
    )
    return fake_tracer


def test_analysis_pipeline_emits_expected_span_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_tracer = _install_fake_tracer(monkeypatch)

    response = analyze_demo_evidence()

    assert response.summary.total_controls == 7
    assert [span.name for span in fake_tracer.spans] == [
        "analysis.request",
        "evidence_agent.extract",
        "compliance_agent.map",
        "control.FT-IAM-01.evaluate",
        "control.FT-IAM-02.evaluate",
        "control.FT-DPDP-01.evaluate",
        "control.FT-DPDP-02.evaluate",
        "control.FT-VAPT-01.evaluate",
        "control.FT-LOG-01.evaluate",
        "control.FT-IR-01.evaluate",
        "llm_enrichment.run",
        "risk_agent.score",
        "auditor_agent.questions",
        "report_agent.assemble",
    ]


def test_analysis_pipeline_span_attributes_are_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_tracer = _install_fake_tracer(monkeypatch)

    analyze_demo_evidence()

    spans_by_name = {span.name: span for span in fake_tracer.spans}
    request_attributes = spans_by_name["analysis.request"].attributes
    assert request_attributes["request_id"] == "demo-golden"
    assert request_attributes["uploaded_filename"] == "rakshak-demo-evidence.zip"
    assert request_attributes["artifact_count"] == 8
    assert request_attributes["chunk_count"] == 66
    assert request_attributes["gap_count"] == 6

    mfa_attributes = spans_by_name["control.FT-IAM-01.evaluate"].attributes
    assert mfa_attributes == {
        "request_id": "demo-golden",
        "control_id": "FT-IAM-01",
        "chunk_count": 4,
    }

    all_attributes = " ".join(str(span.attributes) for span in fake_tracer.spans)
    assert "dev_priya" not in all_attributes
    assert "CUST-3088" not in all_attributes
    assert "fin-admin@fintech.co.in" not in all_attributes


def test_analysis_pipeline_records_safe_error_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_tracer = _install_fake_tracer(monkeypatch)

    with pytest.raises(UnsupportedEvidenceTypeError):
        analyze_evidence_bytes(
            filename="README.md",
            content=b"# unsupported",
            request_id="bad-request",
        )

    spans_by_name = {span.name: span for span in fake_tracer.spans}
    assert spans_by_name["analysis.request"].attributes["error_type"] == (
        "UnsupportedEvidenceTypeError"
    )
    assert spans_by_name["evidence_agent.extract"].attributes["error_type"] == (
        "UnsupportedEvidenceTypeError"
    )
    assert spans_by_name["analysis.request"].exceptions
    assert spans_by_name["evidence_agent.extract"].exceptions
