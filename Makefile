SHELL := /bin/bash

# Docker image settings - copies what's in default values.yaml
IMAGE_REPO ?= python-app
IMAGE_TAG ?= latest
IMAGE ?= $(IMAGE_REPO):$(IMAGE_TAG)

# K3d cluster settings
# exposes the cluster's port 80 to localhost:8081
K3D_CLUSTER ?= demo
K3D_PORT ?= 8081:80

# Helm chart settings
APP_RELEASE ?= python-app
APP_CHART ?= helm/python-app
LOCAL_VALUES_FILE ?= values-local-dev.yaml
NAMESPACE ?= default
APP_HOST ?= python-app.local
TRAEFIK_VERSION ?= 42.3.1
OBS_RELEASE ?= lgtm
OBS_CHART ?= helm/observability
OBS_NAMESPACE ?= observability
GRAFANA_PORT ?= 3000
APP_URL ?= http://$(APP_HOST):8081
SIMULATE_REQUESTS ?= 5

# Python virtual environment settings
VENV ?= .venv
PIP ?= $(VENV)/bin/pip
PYTEST ?= $(VENV)/bin/pytest

.PHONY: help _venv _install test validate simulate-traffic _docker-build _check-helm _check-k3d _check-kubectl _helm-lint _helm-template _k3d-create k3d-delete deploy uninstall grafana status

help:
	@echo "Available targets:"
	@echo "  make test              - Run pytest suite"
	@echo "  make validate          - Test and validate both Helm charts"
	@echo "  make deploy            - Deploy LGTM and the app with telemetry enabled"
	@echo "  make simulate-traffic  - Generate normal, slow, and failing requests"
	@echo "  make grafana           - Port-forward Grafana to localhost:$(GRAFANA_PORT)"
	@echo "  make status            - Show app and observability resources"
	@echo "  make uninstall         - Remove both releases and observability PVCs"
	@echo "  make k3d-delete        - Delete the local k3d cluster"

# ensure required tools are installed
_check-helm:
	@command -v helm >/dev/null 2>&1 || \
		{ echo "ERROR: 'helm' not found. Install it first: https://helm.sh/docs/intro/install/"; exit 1; }

_check-k3d:
	@command -v k3d >/dev/null 2>&1 || \
		{ echo "ERROR: 'k3d' not found. Install it first: https://k3d.io/stable/#installation"; exit 1; }

_check-kubectl:
	@command -v kubectl >/dev/null 2>&1 || \
		{ echo "ERROR: 'kubectl' not found. Install it first: https://kubernetes.io/docs/tasks/tools/"; exit 1; }

# Python virtual environment and dependencies
_venv:
	@test -d "$(VENV)" || python3 -m venv "$(VENV)"

_install: _venv
	"$(PIP)" install -r requirements.txt

# Run test suite
test: _install
	"$(PYTEST)" -q

# Generate normal, delayed, and deliberate 503 requests for the cluster dashboard.
simulate-traffic: _check-kubectl
	@set -e; \
	for ((i=1; i<=$(SIMULATE_REQUESTS); i++)); do \
	  curl -fsS "$(APP_URL)/" >/dev/null; \
	  curl -fsS "$(APP_URL)/simulate/slow" >/dev/null; \
	  status=$$(curl -sS -o /dev/null -w '%{http_code}' "$(APP_URL)/simulate/error"); \
	  if [ "$$status" != "503" ]; then \
	    echo "Expected simulated failure to return 503, got $$status"; exit 1; \
	  fi; \
	  echo "cycle $$i: normal=200 slow=200 failure=$$status"; \
	done

# Build the image for import into the local k3d cluster.
_docker-build:
	docker build -t "$(IMAGE)" .

# Lint or render both repository charts together.
_helm-lint: _check-helm
	helm lint "$(APP_CHART)"
	helm lint "$(OBS_CHART)"

_helm-template: _check-helm
	helm template "$(APP_RELEASE)" "$(APP_CHART)"
	helm template "$(OBS_RELEASE)" "$(OBS_CHART)" --namespace "$(OBS_NAMESPACE)"

validate: test _helm-lint
	$(MAKE) _helm-template >/dev/null

# K3d cluster management + install Traefik and Gateway API
_k3d-create: _check-k3d _check-helm _check-kubectl
	@if k3d cluster list | awk 'NR>1 {print $$1}' | grep -qx "$(K3D_CLUSTER)"; then \
		echo "k3d cluster '$(K3D_CLUSTER)' already exists"; \
	else \
	    echo "Creating k3d cluster '$(K3D_CLUSTER)'"; \
		k3d cluster create "$(K3D_CLUSTER)" --agents 1 -p "$(K3D_PORT)@loadbalancer" --k3s-arg "--disable=traefik@server:0"; \
		echo "Installing Gateway API"; \
		kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml; \
	fi
	helm repo add traefik https://traefik.github.io/charts --force-update
	helm repo update
	helm upgrade --install traefik traefik/traefik \
	  --version "$(TRAEFIK_VERSION)" \
	  --set providers.kubernetesGateway.enabled=true \
	  --set gateway.enabled=true \
	  --set service.spec.type=LoadBalancer \
	  --set metrics.prometheus.addRoutersLabels=true \
	  --set metrics.prometheus.addServicesLabels=true \
	  --set-string 'deployment.podAnnotations.prometheus\.io/scrape=true' \
	  --set-string 'deployment.podAnnotations.prometheus\.io/path=/metrics' \
	  --set-string 'deployment.podAnnotations.prometheus\.io/port=9100' \
	  --skip-crds

# Delete k3d cluster
k3d-delete: _check-k3d
	k3d cluster delete "$(K3D_CLUSTER)"

# Deploy both charts together, installing the Collector before the app.
deploy: _docker-build _k3d-create _helm-lint _check-kubectl
	helm upgrade --install "$(OBS_RELEASE)" "$(OBS_CHART)" \
	  --namespace "$(OBS_NAMESPACE)" \
	  --create-namespace
	k3d image import "$(IMAGE)" -c "$(K3D_CLUSTER)"
	helm upgrade --install "$(APP_RELEASE)" "$(APP_CHART)" \
	  --namespace "$(NAMESPACE)" \
	  --create-namespace \
	  --values "$(APP_CHART)/$(LOCAL_VALUES_FILE)" \
	  --set-string telemetry.endpoint="otel-collector.$(OBS_NAMESPACE).svc.cluster.local:4317"
	kubectl rollout restart deployment --namespace "$(NAMESPACE)" \
	  --selector "app.kubernetes.io/instance=$(APP_RELEASE)"
	kubectl rollout status deployment --namespace "$(NAMESPACE)" \
	  --selector "app.kubernetes.io/instance=$(APP_RELEASE)" --timeout=120s

# Remove both releases and delete the observability storage claims.
uninstall: _check-helm _check-kubectl
	helm uninstall "$(APP_RELEASE)" --namespace "$(NAMESPACE)" --ignore-not-found
	helm uninstall "$(OBS_RELEASE)" --namespace "$(OBS_NAMESPACE)" --ignore-not-found
	@if kubectl get namespace "$(OBS_NAMESPACE)" >/dev/null 2>&1; then \
	  kubectl delete pvc grafana-data loki-data tempo-data mimir-data \
	    --namespace "$(OBS_NAMESPACE)" --ignore-not-found; \
	fi

grafana: _check-kubectl
	kubectl port-forward -n "$(OBS_NAMESPACE)" svc/grafana "$(GRAFANA_PORT):3000"

# Show resources for both namespaces.
status: _check-kubectl
	kubectl get pods,svc,gateway,httproute -n "$(NAMESPACE)"
	kubectl get pods,svc,pvc -n "$(OBS_NAMESPACE)"
