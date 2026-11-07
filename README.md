# Python App + Docker + Helm (k3d)

This repository contains a simple Flask application, a minimal Dockerfile, and a parameterized Helm chart that can deploy the app to a local `k3d` Kubernetes cluster with Gateway API routing.

## Project layout

| Path | Description |
|------|-------------|
| `app/main.py` | Flask app with `/`, `/healthz/live`, and `/healthz/ready` endpoints. Sets up JSON request logging via `before_request` / `after_request` hooks. |
| `app/logging_config.py` | Configures the Flask app logger to emit structured JSON logs to stdout via `python-json-logger`. Exposes `configure_json_logging(app_logger)` which replaces default handlers with a JSON `StreamHandler` and sets the log level to `INFO`. |
| `helm/python-app/` | Parameterized Helm chart for deploying the app to Kubernetes. |
| `helm/python-app/Chart.yaml` | Chart metadata (name, version, appVersion). |
| `helm/python-app/values.yaml` | Default chart values (image, replicas, service, gateway, resources, etc.). |
| `helm/python-app/values-staging.yaml` | Stack specific overrides for staging environment for example. |
| `helm/python-app/values-local-dev.yaml` | Stack specific overrides for local development environment. |
| `helm/python-app/templates/` | Kubernetes manifest templates rendered by Helm. |
| `helm/python-app/templates/deployment.yaml` | Kubernetes Deployment manifest. |
| `helm/python-app/templates/service.yaml` | Kubernetes Service manifest. |
| `helm/python-app/templates/gateway.yaml` | Gateway manifest for Gateway API routing. |
| `helm/python-app/templates/httproute.yaml` | HTTPRoute manifest for Gateway API routing. |
| `helm/python-app/templates/_helpers.tpl` | Named template helpers (labels, selectors, chart name, etc.). |
| `helm/python-app/templates/NOTES.txt` | Post-install usage message printed by Helm. |
| `helm/python-app/README-HELM.md` | Helm chart-specific usage notes. |
| `tests/test_app.py` | Basic pytest endpoint tests. |
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

## Local development

### Prerequisites

Install `helm` and `k3d` before following the Kubernetes deployment steps.

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

### 2) Run the app locally (without Docker)

```bash
export PORT=8080
python -m app.main
```

Then open
- `http://localhost:8080/`
- `http://localhost:8080/healthz/live`
- `http://localhost:8080/healthz/ready`

## Dockerfile details

The Dockerfile is designed to stay small and simple:

- Uses `python:3.12-alpine` as the base image.
- Installs only what is in `requirements.txt`.
- Copies only the app code.
- Runs as a non-root user.
- Exposes port `8080`.

### Build and run the Docker image locally

```bash
(Checkout to repository)
docker build -t python-app:local .
docker run --rm -p 8080:8080 python-app:local
```

Test it:

```bash
curl http://localhost:8080/
curl http://localhost:8080/healthz/live
curl http://localhost:8080/healthz/ready
```

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
