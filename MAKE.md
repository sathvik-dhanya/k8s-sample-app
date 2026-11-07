# Makefile Guide

This document contains all `Makefile`-specific instructions for this repository.

## File and purpose

- `Makefile`: automation for local app workflows, Docker image workflows, k3d cluster workflows, and Helm deploy workflows.

## Quick start

```bash
(Checkout to repository)
make help
```

## Available targets

- `make venv` - create `.venv` if it does not exist.
- `make install` - install Python dependencies from `requirements.txt`.
- `make test` - run app tests with `pytest`.
- `make run` - run the Flask app locally on `PORT=8080`.
- `make docker-build` - build local image (`python-app:local` by default).
- `make docker-run` - run the local image on `localhost:8080`.
- `make k3d-create` - create the k3d cluster if missing.
- `make k3d-import-image` - import the built image into the k3d cluster.
- `make helm-lint` - lint the Helm chart.
- `make helm-template` - render Helm templates locally.
- `make helm-deploy` - deploy/upgrade the Helm release with Gateway API settings.
- `make deploy-app` - full flow: build image -> create cluster -> import image -> lint -> deploy.
- `make status` - show `pods`, `svc`, `gateway`, and `httproute` in namespace.
- `make k3d-delete` - delete the k3d cluster.

## Most common command sets

### Local test and run (without docker)

```bash
(Checkout to repository)
make test
make run
```

### Build and run Docker image

```bash
(Checkout to repository)
make docker-build
make docker-run
```

### Deploy to k3d using Helm

```bash
(Checkout to repository)
make deploy-app
make status
```

## Configurable variables

You can override variables per command.

- `IMAGE_REPO` (default: `python-app`)
- `IMAGE_TAG` (default: `local`)
- `K3D_CLUSTER` (default: `demo`)
- `K3D_PORT` (default: `8081:80`)
- `HELM_RELEASE` (default: `python-app`)
- `HELM_CHART` (default: `helm/python-app`)
- `NAMESPACE` (default: `default`)
- `APP_HOST` (default: `python-app.local`)

Examples:

```bash
(Checkout to repository)
make docker-build IMAGE_REPO=my-python-app IMAGE_TAG=dev
make k3d-create K3D_CLUSTER=dev-cluster K3D_PORT=8082:80
make helm-deploy HELM_RELEASE=python-app-dev NAMESPACE=dev APP_HOST=python-app.dev.local
make deploy-app IMAGE_REPO=my-python-app IMAGE_TAG=dev K3D_CLUSTER=dev-cluster APP_HOST=python-app.dev.local
```

## Notes

- `make k3d-create` is idempotent; it skips creation when the cluster already exists.
- `make helm-deploy` enables Gateway API resources by default through Helm `--values $(LOCAL_VALUES_FILE)` flag.
- If name resolution does not work locally, add your host to `/etc/hosts` (for example: `127.0.0.1 python-app.local`).

