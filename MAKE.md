# Makefile Guide

The Makefile provides a compact local Kubernetes workflow for the Python app and
the independently deployable LGTM observability stack. `make deploy` always enables
OpenTelemetry for the app and deploys both Helm charts.

## Prerequisites

For deployment, install Docker, `k3d`, `kubectl`, Helm, Python 3, and Make. Tests and
chart validation do not require a Kubernetes cluster.

## Main targets

- `make test` - run application tests with pytest.
- `make validate` - run tests, lint both charts, and render both charts.
- `make deploy` - build the app image, prepare k3d, and deploy LGTM and the app with telemetry enabled.
- `make simulate-traffic` - send normal, delayed, and deliberate 503 requests for the dashboard.
- `make grafana` - port-forward Grafana to `localhost:3000`.
- `make status` - show app and observability pods, services, and PVCs.
- `make uninstall` - uninstall both releases and delete chart-owned observability PVCs.
- `make k3d-delete` - delete the local k3d cluster.

Build, tool-check, chart-validation, and cluster-creation targets are internal
dependencies and are omitted from `make help`.

## Common workflow

```bash
make validate
make deploy
make grafana
make simulate-traffic
```

Open [http://localhost:3000](http://localhost:3000) and sign in with the local
default credentials `admin` / `admin`. Add `127.0.0.1 python-app.local` to
`/etc/hosts` if needed. Traffic simulation requires the deployed application and
Gateway route to be reachable; it sends a normal request, a 500 ms delayed request,
and a deliberate 503 request per cycle. The simulated error log and server span share
a trace ID, and the dashboard includes the corresponding failure logs.

Synthetic endpoints are enabled by `helm/python-app/values-local-dev.yaml` and are
disabled by the chart's default values.

## Configuration

Common Make variables can be overridden on the command line:

- `IMAGE_REPO` (`python-app`), `IMAGE_TAG` (`latest`)
- `K3D_CLUSTER` (`demo`), `K3D_PORT` (`8081:80`)
- `APP_RELEASE` (`python-app`), `NAMESPACE` (`default`)
- `OBS_RELEASE` (`lgtm`), `OBS_NAMESPACE` (`observability`)
- `APP_HOST` (`python-app.local`), `APP_URL` (`http://python-app.local:8081`)
- `SIMULATE_REQUESTS` (`5` cycles), `GRAFANA_PORT` (`3000`)

For example:

```bash
make deploy OBS_RELEASE=lgtm-dev OBS_NAMESPACE=observability-dev
make grafana OBS_NAMESPACE=observability-dev GRAFANA_PORT=3300
make simulate-traffic SIMULATE_REQUESTS=10 APP_URL=http://python-app.local:8081
```

Each Helm chart is also independently deployable with `helm upgrade --install`.
The app chart's default values disable telemetry; set `telemetry.enabled=true` and
configure `telemetry.endpoint` when deploying it separately alongside a Collector.

The stack is intended for local development: single-replica components use
persistent volumes from the default StorageClass unless chart values override it.
If the cluster has no dynamic default provisioner, configure storage classes in
the chart values. Grafana and the backends are ClusterIP-only, with local-only
default credentials; set `grafana.adminPassword` before using a shared cluster.

## Teardown

`make uninstall` removes both Helm releases and any remaining named observability
PVCs. To remove the entire local Kubernetes environment as well, run:

```bash
make k3d-delete
```
