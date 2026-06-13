import logging
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from app.config import Settings


TRACER_NAME = "rakshak-ai-backend"
_tracer_provider_configured = False
_tracer_provider = None


def configure_phoenix_tracing(settings: Settings) -> None:
    global _tracer_provider_configured, _tracer_provider

    if _tracer_provider_configured or not settings.phoenix_enabled:
        return

    if trace.get_tracer_provider().__class__.__name__ != "ProxyTracerProvider":
        _tracer_provider_configured = True
        return

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    logging.getLogger("opentelemetry.exporter.otlp.proto.grpc.exporter").setLevel(
        logging.CRITICAL
    )

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.phoenix_project_name,
                "service.version": "0.1.0",
            }
        )
    )
    exporter = OTLPSpanExporter(
        endpoint=settings.phoenix_collector_endpoint,
        insecure=True,
        timeout=1,
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            exporter,
            schedule_delay_millis=5000,
            max_export_batch_size=128,
        )
    )
    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    _tracer_provider_configured = True


def shutdown_observability() -> None:
    if _tracer_provider is not None:
        _tracer_provider.shutdown()


@contextmanager
def start_span(
    name: str,
    attributes: dict[str, str | int | float | bool | None] | None = None,
) -> Iterator[Span]:
    tracer = trace.get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(name) as span:
        set_span_attributes(span, attributes or {})
        try:
            yield span
        except Exception as exc:
            set_span_attributes(span, {"error_type": exc.__class__.__name__})
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR))
            raise


def set_span_attributes(
    span: Span,
    attributes: dict[str, str | int | float | bool | None],
) -> None:
    if not span.is_recording():
        return

    for key, value in attributes.items():
        if value is None:
            continue
        span.set_attribute(key, value)
