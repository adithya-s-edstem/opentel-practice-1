"""
OpenTelemetry wiring for the todo backend.

================================================================================
Big picture (read this first if you're new to OpenTelemetry)
================================================================================

OpenTelemetry (OTel) standardizes how applications emit three "signals":

  - TRACES  : nested records of operations. A trace for "POST /api/todos"
              contains spans for the HTTP handler, the SQL INSERT, etc.
              Lets you see exactly where time is going inside a request.

  - METRICS : numeric measurements aggregated over time. "Requests per
              second", "p95 latency", "todos created" — these are metrics.
              Cheap to store, perfect for dashboards and alerts.

  - LOGS    : text events with structured attributes. The new thing OTel
              adds is automatic correlation: every log line carries the
              trace id + span id of whatever was happening when it ran.

This module configures one "provider" for each signal, all of which export
OTLP to the OpenTelemetry Collector (see ../observability/otel-collector-
config.yaml). The collector fans the signals out to Jaeger / Prometheus /
Loki, which Grafana then visualizes.

App code only ever depends on the OTel API (opentelemetry.trace, .metrics,
._logs). The SDK + exporters are an implementation detail that this file
owns; if you ever swap backends, this is the only file that changes.

================================================================================
"""

import logging
import os

# The OTel API surface — what app code touches.
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider

# OTLP exporters: one per signal type, each speaking gRPC to the collector.
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Auto-instrumentations: each one monkey-patches a library so calls into it
# automatically produce spans/metrics. No app code changes required.
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# SDK pieces — the concrete implementations behind the API.
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


# `service.name` is the single most important attribute in OTel. It appears
# as the service in Jaeger, becomes a `service_name` label on every metric
# in Prometheus, and becomes a Loki stream label. Keep it identical across
# signals so cross-signal correlation works.
SERVICE_NAME = "todo-backend"
SERVICE_VERSION = "0.1.0"

# Where to send everything. The OTel SDK also reads OTEL_EXPORTER_OTLP_ENDPOINT
# automatically; we still pass it explicitly so the path is obvious to readers.
OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")


def setup_observability(app):
    """Configure OTel for the Flask app and return a meter for custom metrics.

    Call this exactly once, after `create_app()` has built `app` and
    initialized SQLAlchemy. The order matters: instrumentation patches the
    libraries you've already imported, so the imports have to happen first.
    """

    # A Resource is metadata about THIS process. Every span, metric, and log
    # produced by this app will carry these attributes. Think of it as the
    # "from" address on the envelope.
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": SERVICE_VERSION,
            "deployment.environment": os.environ.get("OTEL_ENV", "local"),
        }
    )

    _setup_traces(resource)
    _setup_metrics(resource)
    _setup_logs(resource)
    _install_auto_instrumentation(app)

    # Return a Meter so the caller can create custom instruments. A Meter
    # is the metric equivalent of a Tracer; you ask it for Counters,
    # Histograms, etc.
    return metrics.get_meter(SERVICE_NAME, SERVICE_VERSION)


# -----------------------------------------------------------------------------
# Traces
# -----------------------------------------------------------------------------
def _setup_traces(resource: Resource) -> None:
    """Build a TracerProvider that batches spans and pushes them via OTLP."""
    provider = TracerProvider(resource=resource)

    # BatchSpanProcessor accumulates spans in memory and ships them in
    # batches. Without batching every span = one network round-trip, which
    # ruins performance. The default settings (512 spans or 5s, whichever
    # first) are sensible.
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
    )

    # set_tracer_provider installs `provider` as the global default. After
    # this, `trace.get_tracer(__name__)` anywhere in the codebase returns a
    # tracer backed by our config.
    trace.set_tracer_provider(provider)


# -----------------------------------------------------------------------------
# Metrics
# -----------------------------------------------------------------------------
def _setup_metrics(resource: Resource) -> None:
    """Build a MeterProvider that periodically exports metrics over OTLP."""
    # PeriodicExportingMetricReader vs BatchSpanProcessor: metrics are
    # aggregated, not individually shipped. The reader takes a snapshot of
    # the current counter/histogram state every export_interval_millis and
    # sends it. 5s is a good balance between freshness and load.
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True),
        export_interval_millis=5_000,
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)


# -----------------------------------------------------------------------------
# Logs
# -----------------------------------------------------------------------------
def _setup_logs(resource: Resource) -> None:
    """Bridge Python's stdlib `logging` module into the OTel logs pipeline.

    Two things happen here:
      1. We build a LoggerProvider that exports OTel LogRecords over OTLP.
      2. We attach a LoggingHandler to the root logger so anything written
         via the standard `logging` API turns into an OTel LogRecord — and
         therefore automatically gets the active trace_id/span_id attached.
    """
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True))
    )
    set_logger_provider(provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


# -----------------------------------------------------------------------------
# Auto-instrumentation
# -----------------------------------------------------------------------------
def _install_auto_instrumentation(app) -> None:
    """Monkey-patch Flask / SQLAlchemy / psycopg2 / logging to emit OTel data.

    "Auto" means: you don't write any tracing code in your handlers. The
    instrumentation wraps the framework so each request, each query, each
    log line is already observable. Custom spans are still useful when you
    want to mark out a chunk of business logic, but the boring stuff is free.
    """
    # Flask: produces one span per request, with attributes for the method,
    # route template, status code, etc. Also produces HTTP metrics:
    # `http.server.duration` (histogram) and `http.server.active_requests`.
    FlaskInstrumentor().instrument_app(app)

    # SQLAlchemy: every ORM query becomes a child span. enable_commenter
    # adds a SQL comment like /* traceparent='...' */ on each statement,
    # which shows up in Postgres logs — neat trick for correlating DB-side
    # slow query logs with app traces.
    SQLAlchemyInstrumentor().instrument(enable_commenter=True, commenter_options={})

    # psycopg2: the layer below SQLAlchemy. Instrumenting it as well gives
    # you spans even for raw psycopg2 use (we don't have any, but it's free
    # insurance and shows up in the connection setup phase).
    Psycopg2Instrumentor().instrument(enable_commenter=True, commenter_options={})

    # logging: rewrites the default log format to include trace context.
    # After this every log line looks like:
    #   2026-05-11 14:30:00 [INFO] [trace_id=abc123 span_id=def456] todo created id=7
    # The `trace_id=...` substring is what the Grafana Loki datasource picks
    # up via its derivedFields regex (see datasources.yaml) to turn it into
    # a clickable link to Jaeger.
    LoggingInstrumentor().instrument(set_logging_format=True)
