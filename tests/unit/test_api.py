
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@patch("app.main.kubernetes_jobs.create_job")
def test_submit_job(mock_create_job):
    mock_create_job.return_value = {
        "job_id": "test-job-123",
        "status": "queued",
    }

    response = client.post(
        "/jobs",
        json={
            "task_type": "training",
            "parameters": {"epochs": 3},
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "job_id": "test-job-123",
        "status": "queued",
        "status_url": "/jobs/test-job-123",
    }

    mock_create_job.assert_called_once_with(
        task_type="training",
        parameters={"epochs": 3},
    )


@patch("app.main.kubernetes_jobs.get_job")
def test_get_existing_job(mock_get_job):
    mock_get_job.return_value = {
        "job_id": "test-job-456",
        "kubernetes_job_name": "ml-test-job-456",
        "task_type": "inference",
        "parameters": {},
        "status": "succeeded",
        "submitted_at": "2026-10-15T10:00:00+00:00",
        "finished_at": "2026-10-15T10:00:03+00:00",
        "result": {"message": "Worker completed successfully"},
        "error": None,
    }

    response = client.get("/jobs/test-job-456")

    assert response.status_code == 200
    assert response.json()["job_id"] == "test-job-456"
    assert response.json()["task_type"] == "inference"
    assert response.json()["status"] == "succeeded"

    mock_get_job.assert_called_once_with("test-job-456")


@patch("app.main.kubernetes_jobs.get_job")
def test_unknown_job_returns_404(mock_get_job):
    mock_get_job.side_effect = KeyError("nonexistent-job")

    response = client.get("/jobs/nonexistent-job")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


@patch("app.main.kubernetes_jobs.list_jobs")
def test_list_jobs(mock_list_jobs):
    mock_list_jobs.return_value = [
        {
            "job_id": "test-job-789",
            "status": "running",
        }
    ]

    response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json()["jobs"] == [
        {
            "job_id": "test-job-789",
            "status": "running",
        }
    ]


def test_invalid_task_type_returns_422():
    response = client.post(
        "/jobs",
        json={"task_type": "unknown", "parameters": {}},
    )

    assert response.status_code == 422


def test_metrics_endpoint():
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text
