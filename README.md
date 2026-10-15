# Kubernetes Workflow Observability Platform

A Kubernetes-native platform for submitting and tracking machine-learning workloads through a FastAPI service. Kubernetes Jobs execute worker tasks, while Prometheus and Grafana provide application monitoring and observability.

> **Project status:** The API, Kubernetes Job execution, automated tests, CI workflow, Prometheus configuration, Grafana deployment, and API alert rules have been implemented. Job-level Prometheus metrics are a work in progress and should not be considered available until they are integrated and verified.

## Overview

The platform exposes an HTTP API for submitting `training` and `inference` tasks. Each accepted request creates a Kubernetes Job that runs a worker container. The API also exposes job status endpoints and a Prometheus metrics endpoint.

### Architecture

```mermaid
flowchart TD
    Client[Client / User] --> API[FastAPI Workflow API]
    API --> K8s[Kubernetes API]
    K8s --> Job[Kubernetes Job]
    Job --> Worker[Worker Container]
    API --> Metrics[/metrics endpoint]
    Metrics --> Prom[Prometheus]
    Prom --> Grafana[Grafana]
    Prom --> Alerts[Prometheus Alert Rules]
```

## Features

- FastAPI endpoints for health checks, job submission, listing, and status lookup.
- Kubernetes Jobs for isolated worker execution.
- Supports `training` and `inference` task types.
- Job metadata includes task type, parameters, and submission timestamp.
- Prometheus instrumentation for HTTP request metrics.
- Prometheus configuration and alert rules for API availability, error rate, and latency.
- Grafana deployment for monitoring visualization.
- Unit and integration tests.
- Automated linting and test execution in CI.

## Technology stack

- Python
- FastAPI and Uvicorn
- Kubernetes Jobs and Python Kubernetes client
- Docker container images
- Prometheus and `prometheus-client`
- Grafana
- pytest and Ruff

## Repository structure

```text
.
├── app/
│   ├── main.py
│   └── services/
│       ├── kubernetes_jobs.py
│       └── job_metrics.py
├── k8s/
│   ├── api-deployment.yaml
│   ├── workflow-rbac.yaml
│   └── monitoring/
│       ├── grafana-deployment.yaml
│       ├── prometheus-alerts.yaml
│       ├── prometheus-config.yaml
│       ├── prometheus-deployment.yaml
├── worker/
│   └── Dockerfile
├── tests/
│   ├── unit/
│   └── integration/
├── requirements.txt
└── README.md
```

The exact filenames may differ if the repository changes. Inspect the `k8s/` directory before using deployment commands.

## Prerequisites

- Python 3.13 (the CI workflow uses Python 3.13)
- Docker
- `kubectl`
- Minikube or another Kubernetes cluster
- Git

For local development, a Python virtual environment is recommended.

## Local setup

From the repository root, create and activate a virtual environment in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run the API locally:

```powershell
uvicorn app.main:app --reload
```

The API should then be available at `http://localhost:8000`. Interactive API documentation is available at `/docs`.

The API's Kubernetes integration requires a working Kubernetes configuration. Outside a cluster, the application attempts to use the local kubeconfig.

## API reference

### `GET /health`

Returns a basic health status.

Example response:

```json
{
  "status": "healthy"
}
```

### `POST /jobs`

Submits a Kubernetes worker job. The endpoint returns HTTP `202 Accepted` when the request is accepted by the API and Kubernetes Job creation succeeds.

Example request:

```json
{
  "task_type": "training",
  "parameters": {
    "epochs": 3
  }
}
```

Example response:

```json
{
  "job_id": "your-job-id",
  "status": "queued",
  "status_url": "/jobs/your-job-id"
}
```

The returned `job_id` is generated for the submitted job. The example above is illustrative.

Allowed `task_type` values are `training` and `inference`. `parameters` is an optional JSON object whose values should be strings, numbers, or booleans.

### `GET /jobs`

Lists workflow jobs managed by the API.

### `GET /jobs/{job_id}`

Returns the Kubernetes-backed status and metadata for a specific job. Depending on Kubernetes state, status may be `queued`, `running`, `succeeded`, or `failed`.

### `GET /metrics`

Exposes Prometheus metrics, including HTTP request metrics from FastAPI instrumentation. Job-level metrics are still being integrated and must be verified before they are described as production-ready.

## Kubernetes deployment

The repository contains Kubernetes manifests for the API, RBAC, Prometheus, Grafana, and alert rules. Before applying them, check the current manifest names and ensure your cluster is running and configured:

```powershell
kubectl config current-context
kubectl get nodes
```

The application's default Kubernetes namespace is `ml-platform`, and the worker image default is `workflow-worker:0.1.3`. The API deployment manifest currently references `workflow-api:0.3.2`.

For a local Minikube setup, make sure the API and worker images are built and available to the Minikube node before creating or updating deployments. Check the image names and tags in the manifests and application configuration so they match.

Inspect the manifests before applying them. For example:

```powershell
Get-ChildItem .\k8s -Recurse -File
```

After deployment, inspect resources in the namespace:

```powershell
kubectl get deployments,services,pods -n ml-platform
kubectl get jobs -n ml-platform
```

If your manifests use a different namespace or resource name, use the values defined in those files.

## Monitoring and alerting

### Prometheus

Prometheus is configured to scrape the Workflow API's `/metrics` endpoint. The repository includes alert rules for:

- **WorkflowAPIDown** — the API target is unavailable to Prometheus.
- **WorkflowAPIHighErrorRate** — the API's HTTP 5xx error rate is elevated.
- **WorkflowAPIHighLatency** — API request latency is elevated.

Confirm the actual expressions and thresholds in `k8s/monitoring/prometheus-alerts.yaml`.

### Grafana

A Grafana Kubernetes deployment manifest is included. Configure Grafana to use the Prometheus service as a data source, then create or import dashboards appropriate to the metrics available in the running environment. Do not assume a dashboard is provisioned automatically unless provisioning files are present in the repository.

### Job-level metrics roadmap

The intended job metrics include submitted jobs, terminal outcomes, execution duration, and currently running jobs. These require lifecycle-aware integration and tests to avoid counting the same job repeatedly when its status is queried. In-memory metrics also reset when the API process restarts and are not a durable historical event store.

## Tests and code quality

Run the tests from the repository root:

```powershell
python -m pytest -v
```

Run Ruff if it is installed in your active environment:

```powershell
python -m ruff check .
```

The test suite previously passed with **17 tests** in the development environment. Rerun tests after making changes to verify the current branch.

## Troubleshooting

- **API cannot connect to Kubernetes:** Check `kubectl config current-context`, cluster status, namespace, and service-account RBAC.
- **Worker image cannot be pulled:** Ensure the image name and tag match the Job configuration and are available to the cluster. The worker uses `imagePullPolicy: Never`, so the image must already exist on the node.
- **Jobs remain queued:** Inspect the Job and Pod events:
  ```powershell
  kubectl describe job <job-name> -n ml-platform
  kubectl get pods -n ml-platform
  kubectl describe pod <pod-name> -n ml-platform
  ```
- **Worker failure:** Review the worker Pod logs:
  ```powershell
  kubectl logs <pod-name> -n ml-platform
  ```
- **Prometheus does not scrape the API:** Check the Prometheus configuration, target status, service DNS/name, and whether `/metrics` is reachable from the Prometheus Pod.
- **Metrics are missing in Grafana:** Verify the Prometheus data source and query the metric directly in Prometheus first.

## Security and production considerations

- Do not commit secrets, kubeconfig files, or credentials to the repository.
- Review RBAC permissions using least privilege.
- Apply resource requests and limits and define appropriate network and pod security policies for your environment.
- For multiple API replicas or durable business-level job analytics, use a persistent event/state source rather than relying solely on process-local metric tracking.
- Add authentication and authorization before exposing job-submission endpoints outside a trusted environment.

## Roadmap

- Complete and test lifecycle-aware job-level Prometheus metrics.
- Add or provision Grafana dashboards for API health and workflow jobs.
- Validate alert rules against the metrics actually emitted.
- Expand integration tests for running, successful, and failed workloads.
- Document and automate the full local Kubernetes deployment workflow.

## License

Add the license that applies to this repository before distributing it as an open-source project.
