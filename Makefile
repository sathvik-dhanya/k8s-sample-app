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
HELM_RELEASE ?= python-app
HELM_CHART ?= helm/python-app
LOCAL_VALUES_FILE ?= values-local-dev.yaml
NAMESPACE ?= default
APP_HOST ?= python-app.local
TRAEFIK_VERSION ?= 41.1.1

# Python virtual environment settings
VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip
PYTEST ?= $(VENV)/bin/pytest

.PHONY: help venv install test run docker-build docker-run check-helm check-k3d helm-lint helm-template k3d-create k3d-delete k3d-import-image helm-deploy deploy-app status

help:
	@echo "Available targets:"
	@echo "  make venv              - Create Python virtual environment"
	@echo "  make install           - Install Python dependencies"
	@echo "  make test              - Run pytest suite"
	@echo "  make run               - Run app locally on PORT=8080"
	@echo "  make docker-build      - Build local Docker image ($(IMAGE))"
	@echo "  make docker-run        - Run Docker image on localhost:8080"
	@echo "  make k3d-create        - Create k3d cluster if missing"
	@echo "  make k3d-import-image  - Import Docker image into k3d cluster"
	@echo "  make helm-lint         - Lint Helm chart"
	@echo "  make helm-template     - Render Helm manifests"
	@echo "  make helm-deploy       - Deploy chart to cluster"
	@echo "  make deploy-app        - Build image, import, and deploy via Helm"
	@echo "  make status            - Show pods/service/gateway/httproute"
	@echo "  make k3d-delete        - Delete k3d cluster"

# ensure required tools are installed
check-helm:
	@command -v helm >/dev/null 2>&1 || \
		{ echo "ERROR: 'helm' not found. Install it first: https://helm.sh/docs/intro/install/"; exit 1; }

check-k3d:
	@command -v k3d >/dev/null 2>&1 || \
		{ echo "ERROR: 'k3d' not found. Install it first: https://k3d.io/stable/#installation"; exit 1; }

# Python virtual environment and dependencies
venv:
	@test -d "$(VENV)" || python3 -m venv "$(VENV)"

install: venv
	"$(PIP)" install -r requirements.txt

# Run test suite
test: install
	"$(PYTEST)" -q

# Run the app locally
run: install
	PORT=8080 "$(PYTHON)" -m app.main

# Docker build and run
docker-build:
	docker build -t "$(IMAGE)" .

docker-run:
	docker run --rm -p 8080:8080 "$(IMAGE)"

# Helm chart lint/template
helm-lint: check-helm
	helm lint "$(HELM_CHART)"

helm-template: check-helm
	helm template "$(HELM_RELEASE)" "$(HELM_CHART)"

# K3d cluster management + install Traefik and Gateway API
k3d-create: check-k3d check-helm
	@if k3d cluster list | awk 'NR>1 {print $$1}' | grep -qx "$(K3D_CLUSTER)"; then \
		echo "k3d cluster '$(K3D_CLUSTER)' already exists"; \
	else \
	    echo "Creating k3d cluster '$(K3D_CLUSTER)'"; \
		k3d cluster create "$(K3D_CLUSTER)" --agents 1 -p "$(K3D_PORT)@loadbalancer" --k3s-arg "--disable=traefik@server:0"; \
		echo "Installing Gateway API"; \
		kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml; \
		helm repo add traefik https://traefik.github.io/charts; \
        helm repo update; \
        echo "Installing Traefik"; \
        helm upgrade --install traefik traefik/traefik \
          --version "$(TRAEFIK_VERSION)" \
          --set providers.kubernetesGateway.enabled=true \
          --set gateway.enabled=true \
          --set service.type=LoadBalancer \
          --skip-crds; \
	fi

# Delete k3d cluster
k3d-delete: check-k3d
	k3d cluster delete "$(K3D_CLUSTER)"

# Import Docker image into k3d cluster
k3d-import-image: check-k3d
	k3d image import "$(IMAGE)" -c "$(K3D_CLUSTER)"

# Helm deploy to k3d cluster, using $(LOCAL_VALUES_FILE) for local environment
helm-deploy: check-helm
	helm upgrade --install "$(HELM_RELEASE)" "$(HELM_CHART)" \
	  --namespace "$(NAMESPACE)" \
	  --create-namespace \
	  --values "$(HELM_CHART)/$(LOCAL_VALUES_FILE)"
	@echo
	@echo "Deployment complete."
	@echo "Add to /etc/hosts if needed: 127.0.0.1 $(APP_HOST)"
	@echo
	@echo "Wait for a few seconds for all workloads to be ready"
	@echo "Try: curl http://$(APP_HOST):8081/"
	@echo "Try: curl http://$(APP_HOST):8081/healthz/live"
	@echo "Try: curl http://$(APP_HOST):8081/healthz/ready"

# Deploy the app: build Docker image, create k3d cluster, import into k3d, and deploy via Helm
deploy-app: docker-build k3d-create k3d-import-image helm-lint helm-deploy

# Show status of pods, services, gateway, and httproute
status: check-k3d
	kubectl get pods,svc,gateway,httproute -n "$(NAMESPACE)"
