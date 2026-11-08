# `python-app` Helm Chart

This folder contains a Helm chart used to deploy the sample Python application to Kubernetes.

## What is a Helm chart?

A Helm chart is a package of Kubernetes manifests plus templates and default values.
It helps you:

- install an application with one command,
- configure it with values instead of editing YAML by hand,
- upgrade or roll back releases consistently.

## What a chart has

A typical Helm chart includes:

- `Chart.yaml`: chart metadata (name, version, description, app version).
- `values.yaml`: default configuration values used by templates.
- `values-local-dev.yaml`: stack specific overrides for local development environment.
- `templates/`: Kubernetes manifest templates rendered by Helm.
- `.helmignore`: files that should not be included when chart is packaged.

## Chart versioning

Helm chart versions are managed in `Chart.yaml`:

- `version`: chart package version (bump this for any chart/template/values change).
- `appVersion`: application version the chart deploys (bump this when the app image/release changes).

Use semantic versioning for `version` (for example: `0.1.0` -> `0.1.1` for fixes, `0.2.0` for backward-compatible features, `1.0.0` for breaking changes).


## What this chart contains

- `templates/deployment.yaml`: deploys the application Pod(s).
- `templates/service.yaml`: exposes Pods internally via a Service.
- `templates/gateway.yaml`: creates Gateway API `Gateway` resource, when enabled.
- `templates/httproute.yaml`: creates Gateway API `HTTPRoute` resource, when enabled.
- `templates/_helpers.tpl`: shared template helpers for names/labels.
- `templates/NOTES.txt`: post-install usage notes shown by Helm.

## How this chart is configured

Main values in `values.yaml`:

- `image.repository`, `image.tag`, `image.pullPolicy` for the container image details
- `replicaCount` for the number of replicas
- `service.port`, `service.targetPort`, `service.type` for the Service configuration
- `gateway.*` and `httpRoute.*` for Gateway API routing
- `telemetry.enabled`, `telemetry.serviceName`, `telemetry.endpoint`, and `telemetry.traceSampleRatio` for optional OpenTelemetry export (OTLP/gRPC)
- `simulation.enabled` to expose local-only slow and deliberate 503 routes for dashboard demonstrations (disabled by default)
- `probes.readiness.*` and `probes.liveness.*` for liveness and readiness probes
- `resources`, `nodeSelector`, `tolerations`, `affinity` for pod scheduling and resource management

Values in `values-local-dev.yaml`:

We are overriding the following in there
- number of replicas
- enabling the Gateway API resource
- enabling HTTPRoute resource
- enabling OpenTelemetry export to the local observability collector (the app remains available if the collector is unreachable)
- enabling synthetic latency and failure routes so the observability dashboard can display varied metrics and correlated failure logs

## Run the application in k3d

From the repository root, use `make deploy` to deploy the app and observability charts
together with OTLP telemetry enabled:

```sh
make deploy
```

`make simulate-traffic` sends normal, slow, and deliberate 503 requests to populate
the dashboard.

`make validate` tests the app, lints both charts, and renders both charts. `make
uninstall` removes both chart releases and the observability chart's PVCs. The app
chart can still be managed independently with Helm commands when needed.
