"""HTTP endpoints for the todo API.

Handlers are thin: validate the request with a Pydantic schema, delegate
the actual work to `services`, record domain metrics, and return JSON.
All business logic lives in `services.py`; all observability instruments
live in `metrics.py`.
"""

import json
import logging

from flask import Blueprint, abort, jsonify, request
from opentelemetry import trace
from pydantic import ValidationError

import services
from metrics import record_op, record_title_length
from schemas import TodoCreate, TodoUpdate

api = Blueprint("api", __name__, url_prefix="/api")

tracer = trace.get_tracer(__name__)
log = logging.getLogger(__name__)


def _validation_error_response(exc: ValidationError):
    # Pydantic's .json() handles non-serializable values inside `ctx`
    # (e.g. the raw ValueError raised by a model_validator); plain
    # exc.errors() + jsonify would crash on those.
    details = json.loads(exc.json(include_url=False))
    return jsonify({"error": "validation failed", "details": details}), 400


@api.get("/health")
def health():
    return {"status": "ok"}


@api.get("/todos")
def list_todos():
    todos = services.list_todos()
    record_op("list")
    return jsonify([t.to_dict() for t in todos])


@api.post("/todos")
def create_todo():
    # Manual span: even though the request is already wrapped in an HTTP
    # span by FlaskInstrumentor, a nested span around the business logic
    # gives a clean visual block in Jaeger named
    # "create_todo.business_logic" — and we can attach domain attributes
    # (title length, has-due-date, etc.) without polluting the parent
    # span's tags. This is the typical pattern for marking out
    # interesting chunks of work.
    with tracer.start_as_current_span("create_todo.business_logic") as span:
        try:
            payload = TodoCreate.model_validate(request.get_json(force=True, silent=True) or {})
        except ValidationError as exc:
            span.set_attribute("validation.failed", True)
            record_op("create", "error")
            log.warning("create rejected: %s", exc.errors())
            return _validation_error_response(exc)

        todo = services.create_todo(payload.model_dump())

        # Attributes on the span are how you make traces searchable: in
        # Jaeger you can later filter "all create spans where
        # todo.has_due_date=true" by tag.
        span.set_attribute("todo.id", todo.id)
        span.set_attribute("todo.title_length", len(todo.title))
        span.set_attribute("todo.has_due_date", todo.due_date is not None)

        record_title_length(len(todo.title))
        record_op("create")
        log.info("todo created id=%s title=%r", todo.id, todo.title)
        return jsonify(todo.to_dict()), 201


@api.put("/todos/<int:todo_id>")
def update_todo(todo_id):
    todo = services.get_todo(todo_id)
    if todo is None:
        record_op("update", "error")
        abort(404)

    try:
        payload = TodoUpdate.model_validate(request.get_json(force=True, silent=True) or {})
    except ValidationError as exc:
        record_op("update", "error")
        log.warning("update rejected: %s", exc.errors())
        return _validation_error_response(exc)

    services.update_todo(todo, payload.model_dump(exclude_unset=True))
    record_op("update")
    log.info("todo updated id=%s", todo_id)
    return jsonify(todo.to_dict())


@api.post("/todos/<int:todo_id>/complete")
def complete_todo(todo_id):
    # Toggles the checkbox state. Keeps the generic PUT free for edits and
    # gives us a single-purpose hook for the completion metric — we only
    # increment `complete` on the false→true transition, so un-checking
    # doesn't count as a completion.
    todo = services.get_todo(todo_id)
    if todo is None:
        record_op("complete", "error")
        abort(404)
    was_completed = todo.completed
    services.update_todo(todo, {"completed": not was_completed})
    if not was_completed:
        record_op("complete")
    log.info("todo completion toggled id=%s completed=%s", todo_id, todo.completed)
    return jsonify(todo.to_dict())


@api.delete("/todos/<int:todo_id>")
def delete_todo(todo_id):
    todo = services.get_todo(todo_id)
    if todo is None:
        record_op("delete", "error")
        abort(404)
    services.delete_todo(todo)
    record_op("delete")
    log.info("todo deleted id=%s", todo_id)
    return "", 204
