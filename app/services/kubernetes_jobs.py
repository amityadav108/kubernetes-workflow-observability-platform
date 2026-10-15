
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


NAMESPACE = os.getenv("KUBERNETES_NAMESPACE", "ml-platform")
WORKER_IMAGE = os.getenv("WORKER_IMAGE", "workflow-worker:0.1.3")


def get_batch_api() -> client.BatchV1Api:
    """Create a Kubernetes client using the pod's service account."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        # Allows local development when a kubeconfig is available.
        config.load_kube_config()

    return client.BatchV1Api()


def create_job(
    task_type: str,
    parameters: dict,
) -> dict:
    """Create a Kubernetes Job that runs the worker container."""
    job_id = str(uuid4())
    job_name = f"ml-{job_id}"
    submitted_at = datetime.now(timezone.utc).isoformat()

    job_body = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name=job_name,
            labels={
                "app": "ml-worker",
                "managed-by": "workflow-api",
                "job-id": job_id,
            },
            annotations={
                "task-type": task_type,
                "parameters-json": json.dumps(parameters),
                "submitted-at": submitted_at,
            },
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "ml-worker",
                        "managed-by": "workflow-api",
                        "job-id": job_id,
                    }
                ),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            name="worker",
                            image=WORKER_IMAGE,
                            image_pull_policy="Never",
                            command=["python", "/app/worker/run_job.py"],
                            env=[
                                client.V1EnvVar(
                                    name="JOB_ID",
                                    value=job_id,
                                ),
                                client.V1EnvVar(
                                    name="TASK_TYPE",
                                    value=task_type,
                                ),
                                client.V1EnvVar(
                                    name="PARAMETERS_JSON",
                                    value=json.dumps(parameters),
                                ),
                            ],
                        )
                    ],
                ),
            ),
        ),
    )

    api = get_batch_api()
    api.create_namespaced_job(
        namespace=NAMESPACE,
        body=job_body,
    )

    return {
        "job_id": job_id,
        "kubernetes_job_name": job_name,
        "task_type": task_type,
        "parameters": parameters,
        "status": "queued",
        "submitted_at": submitted_at,
        "finished_at": None,
        "result": None,
        "error": None,
    }


def _serialize_job(job: client.V1Job) -> dict:
    """Convert Kubernetes Job metadata and status into an API response."""
    metadata = job.metadata
    annotations = metadata.annotations or {}
    status_obj = job.status
    status_obj = status_obj or client.V1JobStatus()

    if status_obj.succeeded:
        status = "succeeded"
    elif status_obj.failed:
        status = "failed"
    elif status_obj.active:
        status = "running"
    else:
        status = "queued"

    error = None
    for condition in status_obj.conditions or []:
        if condition.type == "Failed" and condition.status == "True":
            error = condition.message or condition.reason or "Job failed"
            status = "failed"
            break

    finished_at = None
    for condition in status_obj.conditions or []:
        if condition.type in {"Complete", "Failed"} and condition.status == "True":
            finished_at = (
                condition.last_transition_time.isoformat()
                if condition.last_transition_time
                else None
            )

    return {
        "job_id": (metadata.labels or {}).get("job-id", metadata.name),
        "kubernetes_job_name": metadata.name,
        "task_type": annotations.get("task-type", "unknown"),
        "parameters": json.loads(
            annotations.get("parameters-json", "{}")
        ),
        "status": status,
        "submitted_at": annotations.get("submitted-at"),
        "finished_at": finished_at,
        "result": (
            {"message": "Worker completed successfully"}
            if status == "succeeded"
            else None
        ),
        "error": error,
    }


def get_job(job_id: str) -> dict:
    api = get_batch_api()

    try:
        job = api.read_namespaced_job(
            name=f"ml-{job_id}",
            namespace=NAMESPACE,
        )
    except ApiException as exc:
        if exc.status == 404:
            raise KeyError(job_id) from exc
        raise

    return _serialize_job(job)


def list_jobs() -> list[dict]:
    api = get_batch_api()
    response = api.list_namespaced_job(
        namespace=NAMESPACE,
        label_selector="managed-by=workflow-api",
    )
    return [_serialize_job(job) for job in response.items]
