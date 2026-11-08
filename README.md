# Python App + Docker + Helm (k3d)

This repository contains a simple Flask application, a minimal Dockerfile, and a parameterized Helm chart that can deploy the app to a local `k3d` Kubernetes cluster with Gateway API routing.

## Project layout

| Path | Description |
|------|-------------|
| `app/main.py` | Flask app with `/`, `/healthz/live`, and `/healthz/ready` endpoints. Sets up JSON request logging via `before_request` / `after_request` hooks. |
| `app/logging_config.py` | Configures Flask JSON stdout logging and JSON-formatted OTLP log records with trace context. |
| `app/telemetry.py` | Optional OpenTelemetry SDK setup for request metrics, server spans, and correlated OTLP logs from propagated Python loggers. |
| `helm/python-app/` | Parameterized Helm chart for deploying the app to Kubernetes. |
| `helm/observability/` | Independent local-development Helm chart for Grafana, Loki, Tempo, Mimir, and the OpenTelemetry Collector. |
| `helm/python-app/Chart.yaml` | Chart metadata (name, version, appVersion). |
| `helm/python-app/values.yaml` | Default chart values (image, replicas, service, gateway, resources, etc.). |
| `helm/python-app/values-local-dev.yaml` | Stack specific overrides for local development environment. |
| `helm/python-app/templates/` | Kubernetes manifest templates rendered by Helm. |
| `helm/python-app/templates/deployment.yaml` | Kubernetes Deployment manifest. |
| `helm/python-app/templates/service.yaml` | Kubernetes Service manifest. |
| `helm/python-app/templates/gateway.yaml` | Gateway manifest for Gateway API routing. |
| `helm/python-app/templates/httproute.yaml` | HTTPRoute manifest for Gateway API routing. |
| `helm/python-app/templates/_helpers.tpl` | Named template helpers (labels, selectors, chart name, etc.). |
| `helm/python-app/templates/NOTES.txt` | Post-install usage message printed by Helm. |
| `helm/python-app/README-HELM.md` | Helm chart-specific usage notes. |
| `helm/observability/README-HELM.md` | LGTM Helm chart-specific usage notes. |
| `tests/test_app.py` | Pytest coverage for endpoints, telemetry, and synthetic failure scenarios. |
| `Dockerfile` | Minimal runtime image using `python:3.12-alpine`. Runs as a non-root user on port `8080`. |
| `Makefile` | Convenience targets for build, test, and deploy workflows. |
| `requirements.txt` | Python dependencies. |
| `pytest.ini` | pytest configuration (test paths, markers, etc.). |
| `MAKE.md` | Makefile target reference, variable overrides, and usage examples. |
| `SECRETS.md` | Secrets usage guide using External Secrets Operator, and usage examples. |
| `PODIDENTITY.md` | Pod Identity usage guide for setting up IAM roles, and usage examples. |
| `README.md` | This file — project overview and usage guide. |

## App behavior

- `GET /` returns JSON with a welcome message.
- `GET /healthz/live` return `{"status":"alive"}` for liveness probes.
- `GET /healthz/ready` return `{"status":"ready"}` for readiness probes.
- With `SIMULATION_ENABLED=true`, `GET /simulate/slow` adds 500 ms latency and
  `GET /simulate/error` returns a deliberate 503 with a trace-correlated error log.

## Local development

### Prerequisites

Install Docker, Helm, k3d, and kubectl before following the Kubernetes deployment steps.

- Helm install docs: https://helm.sh/docs/intro/install/
- k3d install docs: https://k3d.io/stable/#installation

On macOS with Homebrew:

```bash
brew install helm
brew install k3d
```

Quick check:

```bash
helm version
k3d version
```

### 1) Set up and run tests

```bash
(Checkout to repository)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

### 2) Run the app in k3d

The app is run in the local k3d cluster rather than directly on the host or with
`docker run`. Use `make deploy` to deploy the app and LGTM stack together; telemetry
is enabled for the Makefile deployment.

## Dockerfile details

The Dockerfile is designed to stay small and simple:

- Uses `python:3.12-alpine` as the base image.
- Installs only what is in `requirements.txt`.
- Copies only the app code.
- Runs as a non-root user.
- Exposes port `8080`.

### Build the image for k3d

```bash
make deploy
```

The image is built and imported for Kubernetes deployment; the app is not run as a
standalone Docker container.

## Helm chart details

The chart is in `helm/python-app` and is parameterized through various `values.yaml` files.

Read more about this chart in `helm/python-app/README-HELM.md`.

### How to create a Helm chart (reference)

If you wanted to scaffold from scratch, this is the standard command:

```bash
helm create python-app
```

Then adjust templates and values to match your app (as done in `helm/python-app`).

### Lint and render templates

```bash
(Checkout to repository)
helm lint helm/python-app
helm template demo helm/python-app
```

## Deploy to local k3d

**Refer `MAKE.md` file for Makefile automation (target reference, variable overrides, and examples).**
**NOTE - if you have copied the makefile to your local repository to test your app, you can tweak the variables or targets in the Makefile to suit your needs.**

After you've started the k3d cluster and have deployed the Helm chart, you can access the app through the Gateway API routing.

#### Route local hostname and access the app

Add this line to `/etc/hosts`:

```text
127.0.0.1 python-app.local
```

Now access:

```bash
http://python-app.local:8081/
http://python-app.local:8081/healthz/live
http://python-app.local:8081/healthz/ready
```
**(Port `8081` is mapped to the k3d's proxy port `80`)**

#### Verify Kubernetes resources

```bash
kubectl get pods,svc,gateway,httproute
kubectl describe gateway python-app
kubectl describe httproute python-app
```

## Local observability with LGTM

The `helm/observability` chart deploys **Grafana, Loki, Tempo, Mimir, and OpenTelemetry Collectors** into the `observability` namespace. It is independent of the Python app chart. The app emits OTLP metrics, traces, and structured logs to the collector; the collector sends them to Mimir, Tempo, and Loki respectively. The collector also scrapes kubelet container CPU/memory metrics and Prometheus endpoints on metric-named or annotated pods, including Traefik and CoreDNS in the local k3d setup. Flask and propagated Python library/server loggers are exported; OTLP log bodies are JSON with each record's fields also retained as structured attributes. Grafana provisions Python application health and Kubernetes/service metrics dashboards.

The stack is intentionally simplified for a local cluster: single replicas, local filesystem-backed storage on PVCs, no authentication or tenant isolation on internal backends, and no high availability. Services are ClusterIP-only; access Grafana with port-forwarding rather than exposing it publicly. Grafana's local default login is `admin` / `admin`; set a private password for any shared cluster. PVCs use the cluster's default StorageClass unless overridden.

### Prerequisites

For the complete local k3d workflow, install Docker, `k3d`, `kubectl`, Helm, Python 3, and Make. The current Makefile provisions Traefik and Gateway API when it creates a k3d cluster. Check that the selected Kubernetes context is the intended local cluster before deploying.

```bash
docker --version
k3d version
kubectl version --client
helm version
python3 --version
```

### Deploy to k3d

Deploy both charts together with telemetry enabled:

```bash
make deploy
```

The charts remain independently deployable with `helm upgrade --install`. For example,
deploy just the app with telemetry disabled using its default chart values:
`helm upgrade --install python-app helm/python-app -n default --create-namespace`.
The Makefile deployment always enables telemetry and deploys a local collector. If the
collector later becomes unavailable, the app continues serving requests while OTLP
exporters retry asynchronously.

### Open Grafana and generate traffic

Run this in a terminal and keep it open:

```bash
make grafana
```

Open [http://localhost:3000](http://localhost:3000) and sign in with `admin` / `admin`. Add `/etc/hosts` mapping `127.0.0.1 python-app.local` if it is not already present. If both charts are deployed (or you used `make deploy`), generate normal, slow, and failing requests:

```bash
make simulate-traffic
```

Override the number of cycles if needed with `make simulate-traffic SIMULATE_REQUESTS=10`. Each cycle sends a normal request, a delayed request, and a deliberate 503. Give the collector and metric export interval a few seconds, then open **Dashboards → Application → Python Application Health**. It shows request rate, 5xx error rate, p50/p95/p99 latency, an application health gauge, application logs, recent application traces, and a dedicated panel for 503 failure logs. The synthetic 503 is a request-level failure; the app process remains healthy, so its availability gauge correctly remains healthy.

Open **Dashboards → Application → Kubernetes and Service Metrics** for container
CPU/memory across namespaces, scrape target health, Traefik request rates, and CoreDNS
query rates. The Collector scrapes cAdvisor on every node, and scrapes pod metrics
when the pod declares a port named `metrics` or has these Prometheus annotations:

```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/path: /metrics
    prometheus.io/port: "8080"
```

Services must expose a Prometheus-compatible `/metrics` endpoint. Apps that only emit
OTLP metrics can instead send them to the Collector's OTLP endpoint.

The failure log contains the same trace ID as its server span. Select the log's trace ID to find the corresponding trace in Tempo, or use the dashboard's trace panel. The failure metric is labeled by route and HTTP status; use the timestamp and route to relate its rate to the 503 logs without adding high-cardinality trace IDs to metrics.

You can also use **Explore** directly:

- **Metrics (Mimir / Prometheus):** `sum(rate(http_server_request_count_total{service_name="python-app"}[5m]))`
- **Logs (Loki):** `{service_name="python-app"}`
- **Traces (Tempo / TraceQL):** `{ resource.service.name = "python-app" }`

Tempo's provisioned data source links traces to corresponding Loki logs when trace IDs are present. Application stdout logs are JSON and include `trace_id` and `span_id`; OTLP log records are JSON as well, and custom `extra` fields (such as `path`, `status`, and `duration_ms`) are available as parsed fields in Grafana. Use `{service_name="python-app"} | json` in Loki Explore to see them.

The Collector's log agent also runs on every Kubernetes node and ships Kubernetes container
stdout/stderr logs from `/var/log/pods` to Loki. Filter by workload using the
`service_name` label or by namespace with `k8s_namespace_name`, for example
`{k8s_namespace_name="observability"}`. JSON-formatted container messages are parsed
into fields; plain-text messages remain searchable as text but cannot be reliably
converted into structured JSON fields.

### Configuration

The observability chart's `values.yaml` configures image repositories/tags, resource requests/limits, PVC sizes and StorageClasses, and Loki/Tempo retention. For example:

```bash
helm upgrade --install lgtm helm/observability \
  --namespace observability --create-namespace \
  --set grafana.adminPassword='choose-a-local-password' \
  --set loki.persistence.size=5Gi \
  --set tempo.persistence.storageClass=local-path
```

The app chart accepts `telemetry.enabled`, `telemetry.serviceName`, `telemetry.endpoint`, and `telemetry.traceSampleRatio`. The Makefile sets the collector endpoint based on `OBS_NAMESPACE`; Helm users can set the same values directly. Telemetry is disabled by default in the app chart and enabled in `values-local-dev.yaml`.
The `simulation.enabled` app-chart value gates the synthetic slow and 503 endpoints. It is disabled in default chart values and enabled only in `values-local-dev.yaml`.

### Tests, troubleshooting, and teardown

Unit tests use in-memory metric, log, and trace exporters and do not require Kubernetes or a running LGTM stack:

```bash
make test
make validate
```

`make validate` runs pytest and lints/renders both Helm charts. For deployment debugging, inspect pods, PVCs, and component logs:

```bash
make status
kubectl logs -n observability ds/otel-collector
kubectl logs -n observability deploy/loki
kubectl logs -n observability deploy/tempo
kubectl logs -n observability deploy/mimir
```

If a PVC remains pending, check for a default StorageClass (`kubectl get storageclass`) or set each `*.persistence.storageClass` value. If Grafana has no telemetry, verify the app's `OTEL_ENABLED` and collector endpoint, wait for the export interval, and check collector logs for exporter errors. Confirm that Grafana's provisioned data sources show **Working** and that traffic has been generated within the selected dashboard time range.

Remove both releases and the observability chart's PVCs with:

```bash
make uninstall
```

The observability chart owns its four PVCs, so a direct `helm uninstall lgtm -n observability` also removes them. The Make target additionally deletes any leftover named PVCs from an interrupted uninstall.

To remove the entire local Kubernetes environment instead, use `make k3d-delete`.
