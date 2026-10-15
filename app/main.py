
from typing import Literal

from fastapi import FastAPI, HTTPException
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

from app.services import kubernetes_jobs


app = FastAPI(
    title="Kubernetes Workflow Automation Platform",
    description="API for submitting and tracking ML workloads.",
    version="0.2.0",
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


class JobRequest(BaseModel):
    task_type: Literal["training", "inference"]
    parameters: dict[str, str | int | float | bool] = Field(
        default_factory=dict
    )


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/jobs", status_code=202)
def submit_job(request: JobRequest) -> dict:
    try:
        job = kubernetes_jobs.create_job(
            task_type=request.task_type,
            parameters=request.parameters,
        )
    except ApiException as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Kubernetes could not create the Job: {exc.reason}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to Kubernetes: {exc}",
        ) from exc

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "status_url": f"/jobs/{job['job_id']}",
    }


@app.get("/jobs")
def list_jobs() -> dict:
    try:
        return {"jobs": kubernetes_jobs.list_jobs()}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not list Kubernetes Jobs: {exc}",
        ) from exc


@app.get("/jobs/{job_id}")
def read_job(job_id: str) -> dict:
    try:
        return kubernetes_jobs.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not read Kubernetes Job: {exc}",
        ) from exc
