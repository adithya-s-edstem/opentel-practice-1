# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

This is a **guided learning project** for the OpenTelemetry stack (Jaeger / Prometheus / Loki / Grafana), built around a tiny todo app. The README.md is written as a tutorial — when changing observability code, preserve the heavy explanatory comments in `backend/observability.py`, `backend/routes.py` (the manual span block), `backend/metrics.py`, and `observability/otel-collector-config.yaml`; they are the actual teaching surface, not vestigial noise.

## Run / dev commands

The canonical way to run everything is Docker Compose — there is no host-side venv/npm install setup.

```bash
docker compose up --build              # full stack (app + 5 observability services)
docker compose --profile load up -d loadgen   # opt-in synthetic traffic (~2 RPS, 5% errors)
docker compose down -v                 # full reset (drops postgres/prom/loki/grafana volumes)
docker compose logs -f otel-collector  # see telemetry batches arriving (debug exporter prints counts)
docker compose restart backend         # pick up backend code changes (volume-mounted, but Flask doesn't auto-reload OTel init)
```

UIs: app `:5173`, backend `:5000`, **Grafana `:3000`** (anon admin, no login), Jaeger `:16686`, Prometheus `:9090`.

There is no test suite, no linter config, and no CI in this repo.

## Architecture: signal flow is the spine

Every change in this repo eventually has to answer "does this preserve the three-signal pipeline?". The data flow:

```
backend (Flask + OTel SDK)  ──OTLP/gRPC:4317──▶  otel-collector  ──▶ jaeger (traces)
                                                                 ──▶ prometheus (scraped at :8889)
                                                                 ──▶ loki (OTLP/HTTP :3100/otlp)
                                                                              ▲
                                                                              │ datasources
                                                                          grafana
```

The collector (`observability/otel-collector-config.yaml`) is the **single fan-out point** — if you swap any backend (e.g. Tempo for Jaeger), it's the only file that should need to change. Apps only know "OTLP → collector".

Key invariant: `service.name = "todo-backend"` must be identical across all three signals for cross-signal correlation (logs↔traces, exemplars) to work. It's set in `backend/observability.py` (`SERVICE_NAME`) and is the join key Grafana uses.

## Backend (Flask) — module layout and instrumentation pattern

The backend is split into one-concern-per-file modules under `backend/`. None of these are packages — `WORKDIR=/app` in the Dockerfile means they import each other as top-level modules (`from extensions import db`).

| File              | Owns                                                                          |
|-------------------|-------------------------------------------------------------------------------|
| `app.py`          | `create_app()` factory + boot order. Nothing else.                            |
| `extensions.py`   | `db = SQLAlchemy()` singleton (avoids circular import on `app`).              |
| `models.py`       | `Todo` ORM model, SQLAlchemy 2.0 `Mapped` / `mapped_column` style.            |
| `schemas.py`      | Pydantic v2 `TodoCreate` / `TodoUpdate` for request validation.               |
| `services.py`     | Data-access functions (`list_todos`, `create_todo`, …). 2.0-style `select`.   |
| `routes.py`       | Blueprint `api` (`/api/...`). Thin handlers: validate → service → respond.    |
| `metrics.py`      | Custom OTel instruments + `record_op` / `record_title_length` helpers.        |
| `observability.py`| OTel SDK wiring (traces, metrics, logs). The teaching surface — don't slim.   |

**Boot order matters.** In `create_app()`: `db.init_app(app)` first, then `import models` so they register on `db.metadata`, then `db.create_all()` (with retry loop for cold-start), **then** `setup_observability(app)` (auto-instrumentation monkey-patches already-imported libraries — Flask, SQLAlchemy, psycopg2, stdlib `logging`), **then** `init_metrics(meter)` to register custom instruments on the meter the OTel setup returns, then `app.register_blueprint(api)`.

**Where things go.** Validation → `schemas.py` (Pydantic). DB → `services.py`. HTTP shape, status codes, span attributes, `record_op` calls → `routes.py`. The manual `create_todo.business_logic` span lives in the POST handler and wraps validation + service call + attribute setting — keep it where it is; the HTTP/SQL spans around it come free from auto-instrumentation, don't add manual spans that duplicate them.

**Custom-metrics gotchas.** Register instruments in `metrics.py::init_metrics()`. The collector's Prometheus exporter appends `unit` as a suffix to the exported metric name — `unit="characters"` on a histogram named `todo.title_length` produces `todo_title_length_characters_bucket` in PromQL. Use `unit="1"` or `""` for no suffix. Dots in attribute keys become underscores in Prometheus labels.

**Log↔trace correlation.** The `LoggingInstrumentor` rewrites stdlib `logging`'s format to embed `trace_id=… span_id=…`. Grafana's Loki datasource picks that up via a `derivedFields` regex in `observability/grafana/provisioning/datasources/datasources.yaml` to render clickable "View trace" links. Don't reconfigure logging without checking that regex.

## Frontend

React + Vite + Tailwind v4 + **RTK Query** (not plain Redux thunks). All API access lives in `frontend/src/store/todosApi.js` via `createApi` — `useGetTodosQuery`, `useAddTodoMutation`, etc. Tag-based cache invalidation (`{ type: "Todo", id: "LIST" }`) is how mutations refresh the list; preserve the tag pattern when adding endpoints.

Vite proxies `/api` → `http://backend:5000` (configurable via `VITE_API_PROXY`), so the frontend talks to the backend over the relative path `/api/...`. The frontend is **not currently OTel-instrumented**; the OTel collector's HTTP receiver on `:4318` is exposed for that future addition.

`utils/groupByDate.js` + `components/GroupedTodos.jsx` implement due-date bucketing (Overdue / Today / Tomorrow / This Week / …). Week starts Monday.

## Loadgen

`loadgen/loadgen.py` is a deliberately **un-instrumented** Python client — it stays "outside" so traces show the backend as the trace root, not a continuation. It sits behind the `load` Compose profile so it doesn't start by default. The 5% intentional error rate (empty-title POSTs returning 400) is the source of the error traces the README's tour relies on.

## Versioning gotcha

OpenTelemetry Python packages must move in lockstep: `opentelemetry-api`/`-sdk` `1.x` paired with `opentelemetry-instrumentation-*` `0.{x+21}b0` (currently `1.29.0` + `0.50b0`). Bumping one without the others will explode at import time. See `backend/requirements.txt` for the pinned set.
