# Todos + OpenTelemetry — A Guided Tutorial

A working todo app instrumented end-to-end with OpenTelemetry, set up as a
learning project for **Grafana**, **Jaeger**, **Prometheus**, and **Loki**.
Read it cover to cover the first time — every section builds on the previous.

- **Frontend:** React + Vite + JS, Tailwind v4, RTK Query
- **Backend:** Flask + SQLAlchemy — instrumented with OTel Python SDK
- **DB:** Postgres 16
- **Telemetry pipeline:** OpenTelemetry Collector → Jaeger / Prometheus / Loki → Grafana
- **Load:** a small Python container that drives traffic so the dashboards are never empty

---

## 1. The 60-second mental model

When you're trying to understand a running system you usually want to answer one of three questions:

| Question | Answered by | Tool here |
|---|---|---|
| "Is the system healthy right now? What are the trends?" | **Metrics** | Prometheus |
| "Why is this particular request slow / broken?" | **Traces** | Jaeger |
| "What did the app actually say happened?" | **Logs** | Loki |

These three things are the **signals** of OpenTelemetry. Each signal is best at one job:

- **Metrics** are cheap (just numbers aggregated over time) so you keep them forever and look at them all the time. *"Is anything weird?"*
- **Traces** are detailed (every span of every request) so you sample them and look at them when something's weird. *"Why this one?"*
- **Logs** are messy (free-form text) so you keep recent ones and grep through them. *"What did the code think it was doing?"*

The killer feature of OTel is **correlation**: every log line carries the trace id of the request it ran inside. So you can pivot:
*"this metric line shows a latency spike → click an exemplar trace → see the slow span → click its logs → read what blew up."*

The four tools in this stack each own one job:

- **OpenTelemetry Collector** — a single proxy that all your apps push telemetry to. It owns the "where does each signal go" decision so your apps don't have to.
- **Jaeger** — stores and visualizes traces.
- **Prometheus** — stores and queries metrics (PromQL).
- **Loki** — stores and queries logs (LogQL).
- **Grafana** — the unified UI on top of all three.

> For a deeper, tool-by-tool walkthrough of what each of these is and the problem it solves, see [`documentation.md`](./documentation.md).

Architecture:

```
                       ┌──────────────┐
  ┌─────────┐  OTLP    │   OTel       │  ──▶ Jaeger      (traces)
  │ backend │ ───────▶ │  Collector   │  ──▶ Prometheus  (metrics, pulled)
  └─────────┘          │              │  ──▶ Loki        (logs)
                       └──────────────┘                      ▲ ▲ ▲
                                                             │ │ │
                                           ┌───────────┐     │ │ │
                                           │  Grafana  │ ────┴─┴─┘
                                           └───────────┘
```

---

## 2. Boot it

```bash
docker compose up --build
```

First boot pulls images and builds the backend/frontend/loadgen — give it a couple of minutes.

| What | Where |
|---|---|
| The todo app | http://localhost:5173 |
| Backend API | http://localhost:5000/api/todos |
| **Grafana** | **http://localhost:3000** (login disabled, admin by default) |
| Jaeger UI | http://localhost:16686 |
| Prometheus | http://localhost:9090 |
| Postgres | localhost:5432 (todo/todo/todo) |

> **Tip:** if anything looks empty, give it 30s. The collector batches before exporting, Prometheus scrapes every 10s, and Grafana refreshes every 10s — so the worst case is around 25–30s of lag end to end.

### Generating traffic

By default nothing exercises the API, so dashboards will be flat until you click around in the app. To fill them automatically there's a `loadgen` service hidden behind a Compose profile:

```bash
docker compose --profile load up -d loadgen   # background, runs until stopped
docker compose stop loadgen                   # stop it when done
# or one-shot in the foreground:
docker compose run --rm loadgen
```

It posts/lists/updates/deletes todos at ~2 RPS with a 5% intentional-error rate. Tunable via `LOADGEN_RPS` and `LOADGEN_ERROR_FRACTION` in `docker-compose.yml`.

---

## 3. A guided tour

Do these in order. Each step builds intuition for one tool.

### Step 1 — open the todo app and create a few todos

http://localhost:5173

Add 3–4 todos, mark one complete, delete one. You now have traces + metrics + logs flowing for actions you actually initiated.

### Step 2 — find your trace in Jaeger

http://localhost:16686

1. In the **Service** dropdown pick `todo-backend`.
2. Click **Find Traces**.
3. Click any recent trace.

You should see a waterfall like this:

```
todo-backend   POST /api/todos               ███████░░░░░  90ms
todo-backend   create_todo.business_logic      █████░░░░░  60ms
todo-backend   INSERT todos                       ███░░░░  30ms
```

Things to notice:

- **`create_todo.business_logic`** is the manual span we added in `backend/routes.py`. The HTTP and SQL spans around it are *auto-instrumented* — we wrote no tracing code for them.
- **Click any span → "Tags"** to see the metadata. `todo.id`, `todo.title_length`, `todo.has_due_date` are attributes we set on the manual span. In Jaeger's search bar at the top you can use these as filters (`todo.has_due_date=true`).

### Step 3 — try the search

Back to the trace list. In **Tags** type:

```
http.status_code=400
```

You should get hits (the loadgen intentionally creates 5% bad requests). Click one. The span will be marked red. **This is the typical debugging move**: filter by an attribute that smells bad, drill into one example, find the cause.

### Step 4 — open Prometheus and run a query

http://localhost:9090

In the query box, paste:

```promql
sum by (http_route, http_method) (rate(http_server_duration_milliseconds_count{service_name="todo-backend"}[1m]))
```

Click **Graph**. You should see one line per `(method, route)` combination, showing requests per second.

Then click **Table** and start typing — Prometheus has autocomplete. Try `todo_` and you'll see our custom metrics:

- `todo_operations_total` — counter of create/read/list/update/delete
- `todo_title_length_bucket` — histogram of title lengths

Run:

```promql
sum by (operation, status) (rate(todo_operations_total[1m]))
```

This is "business observability" — counting what the *app* does, not what HTTP does. Useful when an outage shows itself as "creates dropped to zero" before HTTP errors spike.

### Step 5 — open Grafana

http://localhost:3000

The "Todo App — Overview" dashboard is auto-loaded. Find it at **Dashboards → Todo App → Todo App — Overview**.

You're looking at the same Prometheus queries from Step 4, plus the Loki log panel at the bottom.

Try this:

1. Find a log line containing `trace_id=...` in the bottom panel.
2. Click the line to expand it. You'll see a **"View trace"** link.
3. Click it → you're in Jaeger, looking at that exact request's trace.

This is the **logs → traces pivot**. It's the payoff for setting up the `LoggingInstrumentor` in the backend — it embeds the trace id in every log line, and Grafana picks it up via a "derived field" regex (configured in `observability/grafana/provisioning/datasources/datasources.yaml`).

### Step 6 — explore Loki directly

In Grafana, sidebar → **Explore** → top dropdown → **Loki**.

Click **Label browser** → `service_name` → `todo-backend` → **Show logs**. You're now tailing the backend's logs as LogQL:

```logql
{service_name="todo-backend"}
```

Add a filter for warning-level lines:

```logql
{service_name="todo-backend"} |= "WARNING"
```

Loki's `|=` is "contains substring"; `|~` is regex; `!=` is "does not contain". The pattern is "stream selector first (cheap, indexed), then line filters (decoded on the fly)".

---

## 4. What's actually in this repo

```
todo/
├── docker-compose.yml             # All 9 services + ports + volumes
├── backend/
│   ├── app.py                     # Flask factory only — boots extensions, OTel, routes
│   ├── extensions.py              # `db` SQLAlchemy singleton
│   ├── models.py                  # Todo ORM model (SQLAlchemy 2.0 Mapped style)
│   ├── schemas.py                 # Pydantic input validation
│   ├── services.py                # Data-access functions (CRUD)
│   ├── routes.py                  # Blueprint with HTTP handlers + manual spans
│   ├── metrics.py                 # Custom OTel instruments + record_* helpers
│   ├── observability.py           # OTel SDK wiring (read this when you want details)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   └── …
│   └── …
├── loadgen/
│   ├── loadgen.py                 # generates traffic + intentional errors
│   └── Dockerfile
└── observability/
    ├── otel-collector-config.yaml # receivers/processors/exporters; the routing brain
    ├── prometheus.yml             # scrape config
    ├── loki-config.yaml           # single-binary Loki
    └── grafana/
        ├── provisioning/
        │   ├── datasources/datasources.yaml   # wires Prom/Loki/Jaeger + derived fields
        │   └── dashboards/dashboards.yaml     # tells Grafana where to find dashboards
        └── dashboards/
            └── todo-overview.json             # the overview dashboard
```

Every file in `observability/` and the OTel parts of `backend/observability.py` is heavily commented. **Reading those comments alongside this README is the actual tutorial.**

---

## 5. What to check for (a cheat sheet)

When something looks weird, walk the signals in this order. The whole point of having all three is that they answer different questions.

### Symptom: "the app feels slow"
1. **Grafana → P95 latency by route** → which route is slow?
2. **Jaeger → service=todo-backend → operation=that route, sort by duration desc** → pick a slow one.
3. In the trace, look for the longest span. Almost always it's a database query or an outbound HTTP call.
4. From that span, **"Logs for this span"** to see what the code was logging while it ran.

### Symptom: "we're getting errors"
1. **Grafana → Failed operations panel** → is the count increasing?
2. **Jaeger → search tag `error=true`** → list of error traces.
3. Open one. Find the red span. Read its `exception.message` attribute.
4. Click "Logs for this span" → see the full stack trace.

### Symptom: "something changed in user behavior"
1. **Grafana → Todo operations by type** → did the mix shift? (e.g. lots of deletes suddenly)
2. **Loki Explore** → grep for the relevant action: `{service_name="todo-backend"} |= "todo deleted"`
3. Sample a few traces from that timeframe.

### Symptom: "I have no idea, just look around"
1. **Grafana → overview dashboard**. Set the time range to "last 1h".
2. Find a graph that looks unusual (spike, dip, missing line).
3. Click on the strange spot and pick **"Explore"** → Grafana opens with that time range zoomed in.
4. Switch the datasource between Prometheus / Loki to see metrics vs. logs at that moment.

---

## 6. Use cases (when you'd want this in real life)

**Performance regressions.** You shipped a change. P95 latency on `/api/checkout` went from 80ms to 300ms. Traces tell you the new code path adds a 220ms call to an external service.

**Capacity planning.** Your dashboard shows request rate trending up 5%/week. You extrapolate when you'll hit your DB connection limit.

**Debugging a one-off bug report.** A user says "I clicked Save and nothing happened at 14:32 UTC". You search Jaeger for traces near that timestamp from that user (if you tag spans with `user.id`). One has a 500. The trace shows a NULL exception in `serialize_todo`. Done in 90 seconds, no local repro needed.

**Production canary analysis.** You deploy 5% of traffic to a new version. Grafana shows a panel comparing error rate `version=v2` vs. `version=v1`. v2 is 10× worse. Auto-rollback.

**Cost attribution.** You instrument outbound calls. Metrics show one feature is making 50% of your third-party API calls. You optimize that one feature.

---

## 7. The OpenTelemetry concepts (in 5 minutes)

These show up in the code; here's what each means.

| Concept | What it is |
|---|---|
| **Signal** | A category of telemetry: traces, metrics, or logs. |
| **Resource** | Metadata about THIS process (service.name, version, env). Every signal carries it. |
| **Trace** | A tree of spans for one logical operation, identified by `trace_id`. |
| **Span** | One unit of work in a trace (an HTTP handler, a SQL query). Has start/end time, attributes, status, parent. |
| **Attribute** | A key=value tag on a span / metric / log. Use these for filtering later. |
| **Instrumentation** | Code that emits telemetry. *Auto* instrumentation = library does it for you. *Manual* = you call `tracer.start_as_current_span(...)`. |
| **Exporter** | The thing that sends signals over the wire. Ours is OTLP/gRPC from the backend to the collector. |
| **OTLP** | OpenTelemetry's wire protocol. Most backends accept it directly now. |
| **Collector** | Optional intermediary. Lets you change backends without redeploying apps. |
| **Propagation** | Passing the trace context between services via a header (W3C `traceparent`). Without this, each service has its own disconnected traces. |
| **Sampling** | Choosing which traces to keep. Local dev: 100%. Production: usually a few %. |

---

## 8. Common things you'll want to do

### Add a custom metric in the backend

Add the instrument registration to `backend/metrics.py` (next to `_ops_counter` / `_title_length`) and expose a small `record_…` helper:

```python
# in metrics.py
_cache_hits = None

def init_metrics(meter):
    global _cache_hits, ...
    _cache_hits = meter.create_counter("cache.hits", description="Cache lookups that hit")

def record_cache_hit(region):
    if _cache_hits is not None:
        _cache_hits.add(1, {"region": region})
```

Then call `record_cache_hit("eu")` from inside a handler in `backend/routes.py`. Restart the backend container (`docker compose restart backend`). Within a minute you'll see `cache_hits_total` in Prometheus autocomplete.

### Add a manual span

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("expensive_thing") as span:
    span.set_attribute("input.size", len(data))
    result = do_the_thing(data)
    span.set_attribute("result.kind", result.kind)
```

### Add a new dashboard

Drop a JSON file into `observability/grafana/dashboards/`. The dashboards provider provisioner picks it up within 10s (no restart). Or use the UI: click **Dashboards → New** and once you're happy, export JSON and save it there.

### Bump log volume / sample rate

- Backend log level: edit `backend/observability.py` (search for `logging.INFO`).
- Trace sampling: the SDK defaults to "always on" (100%). To sample, set `OTEL_TRACES_SAMPLER=traceidratio` and `OTEL_TRACES_SAMPLER_ARG=0.1` in docker-compose's backend env.

### See what the collector is actually receiving

```bash
docker compose logs -f otel-collector
```

The `debug` exporter in the collector config prints batch counts to stdout. Switch its verbosity from `basic` to `detailed` in `observability/otel-collector-config.yaml` to see actual span/metric contents.

---

## 9. Troubleshooting

| Symptom | Most likely cause |
|---|---|
| Grafana dashboard panels say "No data" | First 30s after boot — collector hasn't flushed yet. Wait, then refresh. |
| Metric panel works but logs panel is empty | Loki started before its schema directory was writable. `docker compose restart loki`. |
| Backend won't start | Check `docker compose logs backend` for an OTel import error. Most likely the OTel package versions in `requirements.txt` drifted apart. They MUST all be on the same minor (`opentelemetry-api`/`sdk` 1.x and instrumentation 0.5x where x matches). |
| You added a metric but it never appears in Prometheus | The first export happens 5s after creation (`export_interval_millis`). Then Prometheus scrapes 10s later. Wait 20s. If still missing, `curl http://localhost:8889/metrics` and grep for it — that's the collector's output. If it's there, the issue is Prometheus; if it's not, the issue is your code or the SDK. |
| Custom metric appears but with wrong labels | OTel metric attributes become Prometheus labels. Dots become underscores: `todo.operation` → `todo_operation`. |
| Custom metric has an unexpected suffix in Prometheus | The OTel collector's Prometheus exporter appends the metric's **unit** as a suffix. A metric named `todo.title_length` with `unit="characters"` is exposed as `todo_title_length_characters` (so the histogram series become `todo_title_length_characters_bucket`, `_count`, `_sum`). Pass `unit=""` or `unit="1"` if you want no suffix, or include the unit when querying. |
| `trace_id=` links in Grafana don't open the trace | Grafana Loki datasource's `derivedFields` regex didn't match. Check that the log line actually contains `trace_id=` — the LoggingInstrumentor sets this format, but if you've reconfigured logging it might be different. |

---

## 10. Reset everything

```bash
docker compose down -v   # -v drops volumes (postgres data, prom/loki/grafana state)
docker compose up --build
```

This is the cleanest way to start over. There are no migrations — `db.create_all()` rebuilds the schema on a fresh volume.

---

## 11. Next learning steps

When the basics feel solid, try:

1. **Span events**. `span.add_event("cache_miss", {"key": k})`. They show up as little markers on the span in Jaeger.
2. **Sampling**. Set `OTEL_TRACES_SAMPLER=parentbased_traceidratio` with arg `0.1` and watch the trace volume drop.
3. **Alerting**. Add a Prometheus alert rule for `histogram_quantile(0.95, ...) > 1` and wire Alertmanager into the compose file.
4. **Tempo instead of Jaeger**. Tempo is Grafana's traces backend; it supports TraceQL (much more powerful than Jaeger's filter UI) and span metrics generation. Swap the `otlp/jaeger` exporter for `otlp/tempo` in the collector config.
5. **Real distributed tracing**. Add a second backend service (recommendations, search, anything) and have the todo backend `requests.get()` it. The trace will span all three services.

---

## Original API reference

| Method | Path                | Body                                                        |
|--------|---------------------|-------------------------------------------------------------|
| GET    | `/api/health`       | —                                                           |
| GET    | `/api/todos`        | —                                                           |
| POST   | `/api/todos`        | `{ title, description?, due_date? (ISO), completed? }`      |
| PUT    | `/api/todos/:id`    | any subset of the fields above                              |
| DELETE | `/api/todos/:id`    | —                                                           |

`due_date` accepts ISO 8601 (e.g. `2026-05-11T14:30:00Z`) or `null`.
