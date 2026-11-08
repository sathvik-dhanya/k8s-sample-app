# `observability` Helm Chart

This folder contains a Helm chart for the local Grafana, Loki, Tempo, Mimir, and
OpenTelemetry Collector stack. It is deployed independently from the `python-app`
chart.

## What this chart contains

- `Chart.yaml`: chart metadata and chart version.
- `values.yaml`: default images, persistence settings, and resource requests/limits.
- `dashboards/app-health.json`: provisioned Python application health dashboard.
- `dashboards/k8s-service-metrics.json`: provisioned Kubernetes and service metrics
  dashboard.
- `templates/grafana-config.yaml`: Grafana data sources and dashboard provisioning.
- `templates/grafana.yaml`: Grafana Deployment, Service, and persistent volume claim.
- `templates/loki-config.yaml` and `templates/loki.yaml`: Loki configuration and workload.
- `templates/tempo-config.yaml` and `templates/tempo.yaml`: Tempo configuration and workload.
- `templates/mimir-config.yaml` and `templates/mimir.yaml`: Mimir configuration and workload.
- `templates/otel-collector-config.yaml` and `templates/otel-collector.yaml`: single
  OTLP gateway plus Prometheus discovery and Kubernetes cAdvisor scraping.
- `templates/otel-log-agent-config.yaml` and `templates/otel-log-agent.yaml`:
  Kubernetes container-log receiver, metadata RBAC, and per-node Collector DaemonSet.
- `templates/_helpers.tpl`: shared template helpers for names and labels.

## How this chart is configured

Main values in `values.yaml`:

- `grafana.image.*`, `loki.image.*`, `tempo.image.*`, `mimir.image.*`, and
  `otelCollector.image.*` select the component images and versions.
- Each component's `resources` configures its Kubernetes CPU and memory requests/limits.
- `grafana.persistence.*`, `loki.persistence.*`, `tempo.persistence.*`, and
  `mimir.persistence.*` configure persistent storage, including volume size and
  optional `storageClass`.
- `loki.retentionPeriod` and `tempo.retentionPeriod` configure local data retention.
- `grafana.adminUser` and `grafana.adminPassword` configure Grafana's local admin login.

The chart defaults are intentionally suitable for local development: single-replica,
filesystem-backed components, internal ClusterIP services, and disabled Grafana
authentication beyond its local admin account. Do not expose these services publicly
or reuse the default credentials in a shared or production environment.

## Telemetry flow

The log Collector runs as a DaemonSet to read stdout/stderr log files for containers
on every cluster node. Its read-only `/var/log/pods` host mount and read-only
Kubernetes permissions for pods, namespaces, and workload controllers let it attach
namespace, workload, pod, and container context. It sends these logs, along with app
OTLP logs, to Loki. Kubernetes logs are filterable by
`service_name` (derived from the workload name when no `service.name` is set) and
`k8s_namespace_name`. To see JSON-formatted messages and their keys, use a query such
as `{service_name="python-app"} | json`; JSON keys are also attached as log attributes.
Plain-text messages remain plain text because arbitrary text cannot be reliably
converted into meaningful JSON fields.

The single-replica OTLP gateway accepts OTLP gRPC on port `4317` and OTLP HTTP on port
`4318`. Keeping this gateway separate from the per-node agents avoids load-balancing
one app's metric series across several remote-write exporters, which can create
out-of-order samples in Mimir. It scrapes kubelet cAdvisor metrics from every node
for container CPU and memory, plus Prometheus endpoints on pods that expose a port
named `metrics` or have the `prometheus.io/scrape: "true"` annotation. This picks up
CoreDNS and Traefik in the local k3d setup, and supports other workloads that expose
a Prometheus endpoint. A pod may opt in with `prometheus.io/scrape: "true"` and
optionally set `prometheus.io/path` and `prometheus.io/port`; it must expose a
container port for discovery. Metrics are exported with the Prometheus-compatible
`prometheusremotewrite` exporter to Mimir at `http://mimir:9009/api/v1/push`.
Grafana is provisioned with Mimir, Loki, and Tempo data sources and the Python
Application Health and Kubernetes and Service Metrics dashboards.
Python logger records are sent as JSON OTLP log bodies, while their custom fields
remain structured attributes. The dashboard applies LogQL's `| json` stage to expose
the JSON keys as fields in Grafana; the app logger and other propagated Python loggers
share this path. Only the log agents run with root privileges because common container
runtimes restrict pod log file reads to root; the host logs mount is read-only.

The Python app chart can be deployed separately. To send its telemetry to this
Collector, enable telemetry in the app chart and set its OTLP endpoint to
`otel-collector.<observability-namespace>.svc.cluster.local:4317`.
The app chart's local-development values also enable the `/simulate/slow` and
`/simulate/error` routes for producing latency metrics and trace-correlated 503 logs.

## Lint and render the chart

From the repository root:

```sh
helm lint helm/observability
helm template lgtm helm/observability --namespace observability
```

Or use the repository Make targets:

Use `make validate` to run the app tests and lint/render both charts.

## Install or upgrade the stack

The stack can be installed independently of the Python app:

```sh
helm upgrade --install lgtm helm/observability \
  --namespace observability \
  --create-namespace
```

To deploy both charts in the local development setup, run:

```sh
make deploy
```

The Makefile's combined deploy and uninstall targets use configurable release and
namespace variables. This chart remains independently deployable with the Helm
command above.

## Access Grafana

Forward Grafana's in-cluster service to localhost:

```sh
make grafana
```

Open <http://localhost:3000> and sign in with the configured `grafana.adminUser`
and `grafana.adminPassword` (defaults: `admin` / `admin`). The provisioned data sources
are named Mimir, Loki, and Tempo. Find **Python Application Health** and
**Kubernetes and Service Metrics** in the **Application** folder. The latter shows
container CPU and memory across namespaces, scrape target health, Traefik request
rates, and CoreDNS query rates.

After deploying the app and stack with `make deploy`, use `make simulate-traffic` to
generate normal, slow, and deliberate 503 requests. The dashboard's failure-log panel
shows the simulated error event and its trace ID; its request metrics are available
from Mimir.

The **Kubernetes and Service Metrics** dashboard shows cAdvisor CPU/memory metrics
for pods across namespaces, scrape health, Traefik requests, and CoreDNS query rates.
Other applications can add a named `metrics` container port or the Prometheus scrape
annotations described in the Collector configuration section to appear there.

## Check status and remove the stack

Show component pods, services, and persistent volume claims:

```sh
make status
```

To uninstall the Helm release and delete its persistent volume claims:

```sh
make uninstall
```

Deleting the claims permanently removes the locally stored Grafana, Loki, Tempo, and
Mimir data. The combined Make target also removes the Python app release.
