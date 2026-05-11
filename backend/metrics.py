"""Custom OpenTelemetry instruments for the todo domain.

These complement the auto-emitted HTTP metrics from FlaskInstrumentor — they
describe what the app does in domain terms ("a todo was created") rather
than in transport terms ("a POST returned 201"). Useful when an outage
shows itself as "creates dropped to zero" before HTTP errors spike.

The instruments are module globals initialised by `init_metrics(meter)`,
which the Flask factory calls once after `setup_observability(app)`.
Callers use the small `record_*` helpers below — they're safe to call
before init (no-op), so import order doesn't matter.
"""

from typing import Optional

_ops_counter = None
_title_length = None


def init_metrics(meter) -> None:
    """Register custom instruments on the OTel meter. Call once at startup."""
    global _ops_counter, _title_length
    _ops_counter = meter.create_counter(
        name="todo.operations",
        description="Count of todo CRUD operations, labeled by operation and outcome.",
        unit="1",
    )
    _title_length = meter.create_histogram(
        name="todo.title_length",
        description="Distribution of created todo title lengths (in characters).",
        unit="characters",
    )


def record_op(operation: str, status: str = "ok") -> None:
    """Increment the operations counter with consistent labels."""
    if _ops_counter is not None:
        _ops_counter.add(1, {"operation": operation, "status": status})


def record_title_length(n: int) -> None:
    """Record a sample for the title-length histogram."""
    if _title_length is not None:
        _title_length.record(n)
