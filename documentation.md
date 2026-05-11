# Observability Stack — A Beginner's Guide

This document explains the five tools that make up the observability stack in this repo:
**OpenTelemetry**, **Jaeger**, **Prometheus**, **Loki**, and **Grafana**.

For each one you'll find: what it is, what problem it solves, how this repo uses it, and
what data flows through it. Read it top-to-bottom the first time — each section builds
on the previous one.

---

## 0. The three signals (the mental model)

Everything in this stack exists to answer one of three questions about a running system:

| Question | Signal | Stored in |
|---|---|---|
| "Is the system healthy? What are the trends?" | **Metrics** | Prometheus |
| "Why was this specific request slow / broken?" | **Traces** | Jaeger |
| "What did the code actually say happened?" | **Logs** | Loki |

The signals are complementary, not competing. Metrics are tiny numbers (good for forever-storage
and alerts), traces are detailed request-by-request records (sampled, good for debugging one
slow request), logs are messy text (good when you need to read what the code thought it was
doing).

The big trick that makes them more than the sum of their parts is **correlation**: every log
line carries the `trace_id` of the request it ran inside, so you can pivot:

> metric spike → click an exemplar trace → see the slow span → click its logs → read the error

---

## 1. OpenTelemetry (OTel)

### What it is

**OpenTelemetry is a vendor-neutral standard for producing and shipping telemetry.** It is *not*
a storage backend. It defines:

- An **API** that your application code calls (`tracer.start_as_current_span`, `meter.create_counter`, …).
- An **SDK** that implements the API and produces data in a standard format.
- A **wire protocol** called **OTLP** (OpenTelemetry Protocol) for shipping that data over the network.
- A **Collector** — a separate process that receives OTLP and forwards it to backends.

If you've ever used a vendor-specific agent (New Relic, DataDog, AppDynamics) the contrast is:
those lock you into one backend. With OTel the app code is the same regardless of where the
data ends up — swap Jaeger for Tempo, swap Prometheus for Mimir, and the app doesn't change.

### How this repo uses it

OTel wiring lives in `backend/observability.py`. At app startup it:

1. **Builds a `Resource`** — metadata attached to every signal: `service.name=todo-backend`,
   `service.version=0.1.0`, `deployment.environment=local`. The `service.name` is the join
   key across the three signals; keep it identical or correlation breaks.
2. **Configures three providers** — `TracerProvider`, `MeterProvider`, `LoggerProvider` —
   each with an OTLP exporter pointed at the collector at `otel-collector:4317`.
3. **Auto-instruments** Flask, SQLAlchemy, psycopg2, and stdlib `logging`. These monkey-patch
   already-imported libraries so every request becomes a span, every SQL query becomes a
   child span, and every log line gets the active trace_id embedded in it — all without
   touching handler code.
4. **Returns a `Meter`** so `backend/metrics.py` can register custom domain instruments
   (`todo.operations`, `todo.title_length`).

### What "metrics" means in OTel

OTel defines several instrument types. The two used in this repo are:

| Instrument | Purpose | Example here |
|---|---|---|
| **Counter** | Monotonic count of events. Only goes up. | `todo.operations` — incremented on every CRUD action. |
| **Histogram** | Distribution of values (with auto-bucketing for percentiles). | `todo.title_length` — record one sample per created todo, query `p50` / `p95` later. |

(Other instruments OTel supports but this repo doesn't use: `UpDownCounter` for things that
go up and down like queue depth, `Gauge` for instantaneous measurements, `Observable*` for
values that are easier to read on demand than push.)

The auto-instrumentation also emits standard HTTP metrics for free:
- `http.server.duration` — histogram of request durations (this is what powers all the
  P95 latency and RPS panels in Grafana).
- `http.server.active_requests` — UpDownCounter of concurrently in-flight requests.

### Manual instrumentation in this repo

One **manual span** lives at `backend/routes.py:55` inside the `create_todo` handler:

```python
with tracer.start_as_current_span("create_todo.business_logic") as span:
    ...
    span.set_attribute("todo.id", todo.id)
    span.set_attribute("todo.title_length", len(todo.title))
    span.set_attribute("todo.has_due_date", todo.due_date is not None)
```

It nests inside the HTTP span the auto-instrumentation creates. The attributes are
searchable in Jaeger (e.g. filter by `todo.has_due_date=true`).

### Versioning gotcha

OpenTelemetry Python packages move in lockstep: `opentelemetry-api`/`-sdk` `1.x` paired with
`opentelemetry-instrumentation-*` `0.{x+21}b0`. Bumping one without the others fails at
import time. See `backend/requirements.txt` for the pinned set (currently `1.29.0` + `0.50b0`).

---

## 2. The OpenTelemetry Collector

### What it is

The Collector is a single process that accepts telemetry from many sources, optionally
transforms it, and exports it to one or more backends. It's the **fan-out point**: apps push
to one address, the collector decides where each signal type ends up.

Without a collector, every app would need to know the URL and protocol of every backend
(Jaeger's gRPC endpoint, Prometheus's remote-write URL, Loki's HTTP API, etc.). With it,
apps speak OTLP to one address and you can change backends by editing one config file.

### How this repo uses it

`observability/otel-collector-config.yaml` has three sections:

```yaml
receivers:    # how telemetry comes IN
  otlp:       # accepts OTLP/gRPC on :4317 and OTLP/HTTP on :4318

processors:   # what we do to telemetry in flight
  batch:      # group spans/metrics/logs before exporting (perf)
  resource:   # tag everything with deployment.environment=local

exporters:    # where telemetry goes OUT
  otlp/jaeger:   # traces → jaeger:4317
  prometheus:    # metrics → exposed at :8889 for Prometheus to SCRAPE
  otlphttp/loki: # logs → loki:3100/otlp
  debug:         # also print batch counts to collector stdout
```

The `service.pipelines` section is the data-flow graph: one pipeline per signal type, each
wiring receivers → processors → exporters.

### Notice the asymmetry

- **Traces and logs are pushed** out of the collector to their backends.
- **Metrics are pulled**: the collector exposes a `/metrics` endpoint on port 8889, and
  Prometheus scrapes it on a schedule. This is the Prometheus way and it's why this is
  the only signal where the collector exposes a port for the backend to call *in*.

### What the collector itself measures

It also exposes its *own* internal metrics on port 8888 (scraped by Prometheus too): spans
received, spans dropped, exporter queue length, etc. Useful for catching pipeline problems
("the collector is dropping spans") before they bite you in dashboards.

---

## 3. Jaeger — distributed tracing

### What it is

**Jaeger is a tracing backend.** It receives spans, stores them, and provides a UI to search
and visualize traces. Originally built at Uber, now a CNCF graduated project.

### Key vocabulary

| Term | Meaning |
|---|---|
| **Trace** | A tree of spans representing one logical operation (e.g. one HTTP request). Identified by a `trace_id`. |
| **Span** | One unit of work inside a trace. Has a name, start/end time, attributes, status, and a parent span (unless it's the root). |
| **Attribute** | A key=value tag on a span. Searchable in the UI. |
| **Service** | The thing that emitted the span — populated from `service.name`. |

### What data Jaeger sees in this repo

Each HTTP request to the backend produces a trace like this:

```
todo-backend   POST /api/todos               ███████░░░░░  90ms   ← FlaskInstrumentor (auto)
todo-backend     create_todo.business_logic    █████░░░░░  60ms   ← manual span in routes.py
todo-backend       INSERT todos                   ███░░░░  30ms   ← SQLAlchemyInstrumentor (auto)
```

Attributes you'll find on these spans:

- On the HTTP span: `http.method`, `http.route`, `http.status_code`, `http.url`, etc.
  (set by the Flask instrumentation).
- On `create_todo.business_logic`: `todo.id`, `todo.title_length`, `todo.has_due_date`
  (set manually in `routes.py`).
- On SQL spans: the SQL statement, the DB name, etc.

### Typical Jaeger workflows

1. **"Why was this slow?"** — search by service + operation, sort by duration descending,
   click the slowest, see which span is fat.
2. **"Show me the failures"** — filter by tag `http.status_code=400` (or `error=true`).
3. **"Show me a specific user's request"** — if you tag spans with `user.id`, filter by it.

UI is at `http://localhost:16686`.

---

## 4. Prometheus — metrics

### What it is

**Prometheus is a time-series database optimized for metrics.** Each metric is a stream of
numeric samples over time, identified by a name and a set of `key=value` labels. PromQL is
its query language.

It's **pull-based**: on a schedule (every 10s in this repo) it makes HTTP GET requests to
each configured target's `/metrics` endpoint, parses the result, and stores it.

### Key vocabulary

| Term | Meaning |
|---|---|
| **Time series** | One specific combination of `metric_name{labels}` over time. `http_server_duration_milliseconds_count{http_route="/api/todos", http_method="POST"}` is one series. |
| **Counter** | Cumulative count, only goes up. Query with `rate()` to get a per-second rate. |
| **Gauge** | Instantaneous value. Goes up or down. |
| **Histogram** | Pre-bucketed distribution. Comes with `_bucket`, `_count`, `_sum` sibling series. Query with `histogram_quantile()` for percentiles. |
| **Label** | A key=value tag on a series. Crucial for slicing data ("by route", "by status"). |

### How this repo uses it

`observability/prometheus.yml` configures three scrape jobs:

| Job | Target | Source of data |
|---|---|---|
| `otel-collector-apps` | `otel-collector:8889` | Our app's metrics (the OTel collector's Prometheus exporter). |
| `otel-collector-internal` | `otel-collector:8888` | The collector's own health metrics. |
| `prometheus` | `localhost:9090` | Prometheus self-monitoring. |

Notice the app never exposes a `/metrics` endpoint directly — it pushes OTLP to the
collector, which exposes the Prometheus-format `/metrics` page on its behalf.

### What metrics are actually available

**Auto-emitted by the Flask/SQLAlchemy instrumentation:**

| Metric | Type | Use |
|---|---|---|
| `http_server_duration_milliseconds_count` | Counter | Total requests served (used for RPS via `rate()`). |
| `http_server_duration_milliseconds_bucket` | Histogram bucket | Latency distribution (used for `histogram_quantile()`). |
| `http_server_duration_milliseconds_sum` | Counter | Total ms spent serving requests. |
| `http_server_active_requests` | UpDownCounter | Currently in-flight requests. |

Labels include `http_method`, `http_route`, `http_status_code`, `service_name`.

**Custom (defined in `backend/metrics.py`):**

| Metric | Type | Labels | Use |
|---|---|---|---|
| `todo_operations_total` | Counter | `operation` (create/list/update/complete/delete), `status` (ok/error) | Business-level counts of what the app actually did. |
| `todo_title_length_characters_bucket` | Histogram bucket | (none beyond service_name) | Distribution of created-todo title lengths. |

**Important suffix gotcha:** the OTel→Prometheus exporter appends the instrument's **unit**
as a suffix. A histogram named `todo.title_length` with `unit="characters"` becomes
`todo_title_length_characters_bucket` in PromQL. Dots in attribute keys also become
underscores in Prometheus labels.

### Example PromQL

```promql
# Request rate per route and method
sum by (http_route, http_method) (
  rate(http_server_duration_milliseconds_count{service_name="todo-backend"}[1m])
)

# P95 latency overall
histogram_quantile(0.95,
  sum by (le) (rate(http_server_duration_milliseconds_bucket{service_name="todo-backend"}[1m]))
)

# Successful creates per second
sum(rate(todo_operations_total{operation="create", status="ok"}[1m]))
```

UI is at `http://localhost:9090` (raw PromQL playground).

---

## 5. Loki — logs

### What it is

**Loki is a log database, designed to be cheap.** Its trick is: don't index the log content,
only index a small set of labels (`service_name`, `level`, etc.). When you query, Loki picks
the matching log streams by label, then *grep*s the actual log text on the fly. This is much
cheaper than Elasticsearch-style full-text indexing, at the cost of slower content queries.

Query language is **LogQL** — modeled on PromQL but for logs.

### How this repo uses it

The backend writes via the standard Python `logging` module. The OTel `LoggingInstrumentor`:

1. Rewrites the log format to include `trace_id=...` and `span_id=...` substrings.
2. Routes the log records through OTel's logs pipeline, which exports them via OTLP to the
   collector, which forwards them to Loki at `http://loki:3100/otlp`.

A log line looks roughly like:

```
2026-05-11 14:30:00 [INFO] [trace_id=abc123 span_id=def456] todo created id=7
```

Loki stores log streams keyed by labels lifted from the OTel resource — `service_name`,
`deployment_environment`, etc.

### Example LogQL

```logql
{service_name="todo-backend"}                          # tail everything
{service_name="todo-backend"} |= "WARNING"             # substring match
{service_name="todo-backend"} |~ "todo .* id=\\d+"     # regex match
{service_name="todo-backend"} != "health"              # exclude
```

The pattern is **stream selector first (`{...}`, cheap, indexed), then line filters
(`|=`, `|~`, `!=`, decoded on the fly)**.

### The killer feature: clickable trace IDs

The Grafana Loki datasource is configured (`observability/grafana/provisioning/datasources/datasources.yaml`)
with a `derivedFields` regex that matches `trace_id=([a-f0-9]+)` in any log line and turns
it into a clickable link to Jaeger. This is the **logs → traces pivot** and it's the entire
reason for setting up `LoggingInstrumentor` the way we did. Don't reconfigure logging without
checking that regex still matches.

UI: best accessed through Grafana's **Explore** view, datasource = Loki. Raw HTTP API is
also exposed on `:3100`.

---

## 6. Grafana — visualization

### What it is

**Grafana is the unified UI.** It doesn't store anything itself — it queries Prometheus,
Loki, and Jaeger and renders the results. Dashboards are JSON files; panels run queries in
PromQL, LogQL, or Jaeger's search API depending on which datasource the panel targets.

### How this repo uses it

Configuration is **auto-provisioned** — Grafana reads `observability/grafana/provisioning/`
at startup and wires up datasources and dashboards without anybody clicking through the UI.

**Datasources** (`provisioning/datasources/datasources.yaml`):

- `Prometheus` (uid: `prometheus`) — at `http://prometheus:9090`. Configured with
  `exemplarTraceIdDestinations` so metric points can deep-link to traces.
- `Loki` (uid: `loki`) — at `http://loki:3100`. Configured with the `derivedFields` regex
  that makes `trace_id=...` clickable.
- `Jaeger` (uid: `jaeger`) — at `http://jaeger:16686`. Configured with `tracesToLogsV2` and
  `tracesToMetrics` so from any span you can pivot to its logs or its surrounding metrics.

**Dashboards** (`observability/grafana/dashboards/todo-overview.json`):

A single "Todo App — Overview" dashboard with these panels:

| Panel | Datasource | What it shows |
|---|---|---|
| HTTP request rate | Prometheus | Overall RPS (`rate()` of `http_server_duration_milliseconds_count`). |
| P95 latency | Prometheus | Overall p95 via `histogram_quantile`. |
| Todos created | Prometheus | Cumulative `todo_operations_total{operation="create", status="ok"}`. |
| Todos completed | Prometheus | Cumulative `todo_operations_total{operation="complete", status="ok"}`. |
| Failed operations | Prometheus | Cumulative `todo_operations_total{status="error"}`. |
| Request rate by route | Prometheus | Stacked timeseries by `http_route`, `http_method`. |
| P95 latency by route | Prometheus | One line per route. |
| Todo operations by type | Prometheus | Custom-metric timeseries by `operation` label. |
| Title length distribution (p50/p95) | Prometheus | `histogram_quantile` over `todo_title_length_characters_bucket`. |
| Backend logs | Loki | Live tail of `{service_name="todo-backend"}`. |

The bottom logs panel is where the magic happens: any line with `trace_id=...` becomes a
clickable "View trace" link that jumps to Jaeger.

UI: `http://localhost:3000`. Auth is disabled for local dev (`GF_AUTH_ANONYMOUS_ENABLED=true`).

---

## 7. How it all fits together

```
            ┌──────────────────────────┐
            │  backend (Flask + OTel)  │
            │  app.py, routes.py, …    │
            └──────────────┬───────────┘
                           │ OTLP/gRPC (traces, metrics, logs)
                           ▼
              ┌─────────────────────────┐
              │   otel-collector        │
              │   (receivers/processors/│
              │    exporters)           │
              └──┬──────────┬─────────┬─┘
   traces (push)│   metrics │  logs (push)
                │  (pulled  │
                │  via :8889)│
                ▼           ▼         ▼
            ┌───────┐  ┌──────────┐  ┌──────┐
            │Jaeger │  │Prometheus│  │ Loki │
            └───┬───┘  └─────┬────┘  └───┬──┘
                │            │           │
                └────────────┼───────────┘
                             │ (datasources)
                             ▼
                       ┌──────────┐
                       │ Grafana  │ ← you, in a browser
                       └──────────┘
```

The single most important detail in this diagram: **the collector is the only thing your
app talks to.** Every storage backend is replaceable without changing app code.

The second-most-important detail: **`service.name=todo-backend` is identical on all three
signals.** That's the join key Grafana uses to wire metrics ↔ traces ↔ logs.

---

## 8. Quick reference — which tool answers which question

| Question | Where to look | Query |
|---|---|---|
| "What's my error rate right now?" | Grafana / Prometheus | `sum(rate(todo_operations_total{status="error"}[5m]))` |
| "What's my p95 latency?" | Grafana / Prometheus | `histogram_quantile(0.95, sum by (le) (rate(http_server_duration_milliseconds_bucket[5m])))` |
| "Which route is slow?" | Grafana | "P95 latency by route" panel |
| "Why is *this* request slow?" | Jaeger | Find the trace, look at the waterfall, find the fat span. |
| "What did the code log around that error?" | Loki (or Jaeger → Logs for this span) | `{service_name="todo-backend"} \|= "ERROR"` |
| "Did the user behavior shift?" | Grafana | "Todo operations by type" panel — watch the mix. |
| "Is my collector dropping spans?" | Prometheus | `otelcol_exporter_send_failed_spans_total` |

---

## 9. Where to dig deeper

- `backend/observability.py` — OTel SDK wiring, line-by-line commented.
- `backend/metrics.py` — Custom instrument registration.
- `backend/routes.py` (the `create_todo` handler) — the only manual span in the codebase.
- `observability/otel-collector-config.yaml` — the routing brain.
- `observability/grafana/provisioning/datasources/datasources.yaml` — the cross-signal
  correlation links (Loki `derivedFields`, Jaeger `tracesToLogs`/`tracesToMetrics`).
- `README.md` § 3 "A guided tour" — a hands-on walkthrough of clicking around all three UIs.
