import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.services import kubernetes_jobs as jobs


def make_kubernetes_job(
    job_id="test-job-id",
    status=None,
    conditions=None,
):
    """Build a Kubernetes Job object for testing."""
    return client.V1Job(
        metadata=client.V1ObjectMeta(
            name=f"ml-{job_id}",
            labels={"job-id": job_id},
            annotations={
                "task-type": "training",
                "parameters-json": json.dumps({"epochs": 3}),
                "submitted-at": "2026-10-15T10:00:00+00:00",
            },
        ),
        status=client.V1JobStatus(
            active=status.get("active", 0) if status else 0,
            succeeded=status.get("succeeded", 0) if status else 0,
            failed=status.get("failed", 0) if status else 0,
            conditions=conditions or [],
        ),
    )


@patch("app.services.kubernetes_jobs.get_batch_api")
def test_create_job_submits_correct_kubernetes_job(mock_get_api):
    mock_api = MagicMock()
    mock_get_api.return_value = mock_api

    result = jobs.create_job("training", {"epochs": 3})

    mock_api.create_namespaced_job.assert_called_once()
    call_args = mock_api.create_namespaced_job.call_args.kwargs

    assert call_args["namespace"] == jobs.NAMESPACE

    body = call_args["body"]
    assert body.kind == "Job"
    assert body.api_version == "batch/v1"
    assert body.metadata.name == result["kubernetes_job_name"]
    assert body.metadata.labels["managed-by"] == "workflow-api"
    assert body.metadata.labels["job-id"] == result["job_id"]

    container = body.spec.template.spec.containers[0]
    assert container.image == jobs.WORKER_IMAGE
    assert container.image_pull_policy == "Never"
    assert container.env[0].name == "JOB_ID"
    assert container.env[0].value == result["job_id"]
    assert container.env[1].name == "TASK_TYPE"
    assert container.env[1].value == "training"
    assert json.loads(container.env[2].value) == {"epochs": 3}

    assert result["status"] == "queued"
    assert result["parameters"] == {"epochs": 3}
    assert result["finished_at"] is None
    assert result["error"] is None


@pytest.mark.parametrize(
    ("status_data", "expected_status"),
    [
        ({"succeeded": 1}, "succeeded"),
        ({"active": 1}, "running"),
        ({"failed": 1}, "failed"),
        ({}, "queued"),
    ],
)
def test_serialize_job_maps_kubernetes_status(
    status_data,
    expected_status,
):
    kubernetes_job = make_kubernetes_job(status=status_data)

    result = jobs._serialize_job(kubernetes_job)

    assert result["status"] == expected_status
    assert result["job_id"] == "test-job-id"
    assert result["task_type"] == "training"
    assert result["parameters"] == {"epochs": 3}


@patch("app.services.kubernetes_jobs.get_batch_api")
def test_get_job_returns_serialized_job(mock_get_api):
    mock_api = MagicMock()
    mock_api.read_namespaced_job.return_value = make_kubernetes_job(
        status={"succeeded": 1}
    )
    mock_get_api.return_value = mock_api

    result = jobs.get_job("test-job-id")

    mock_api.read_namespaced_job.assert_called_once_with(
        name="ml-test-job-id",
        namespace=jobs.NAMESPACE,
    )
    assert result["status"] == "succeeded"
    assert result["result"] == {
        "message": "Worker completed successfully"
    }


@patch("app.services.kubernetes_jobs.get_batch_api")
def test_get_missing_job_raises_key_error(mock_get_api):
    mock_api = MagicMock()
    mock_api.read_namespaced_job.side_effect = ApiException(
        status=404,
        reason="Not Found",
    )
    mock_get_api.return_value = mock_api

    with pytest.raises(KeyError, match="test-job-id"):
        jobs.get_job("test-job-id")


@patch("app.services.kubernetes_jobs.get_batch_api")
def test_get_job_propagates_unexpected_kubernetes_error(mock_get_api):
    mock_api = MagicMock()
    mock_api.read_namespaced_job.side_effect = ApiException(
        status=500,
        reason="Internal Server Error",
    )
    mock_get_api.return_value = mock_api

    with pytest.raises(ApiException) as error:
        jobs.get_job("test-job-id")

    assert error.value.status == 500


@patch("app.services.kubernetes_jobs.get_batch_api")
def test_list_jobs_uses_workflow_label_selector(mock_get_api):
    mock_api = MagicMock()
    mock_api.list_namespaced_job.return_value.items = [
        make_kubernetes_job(status={"succeeded": 1}),
        make_kubernetes_job(
            job_id="another-job",
            status={"active": 1},
        ),
    ]
    mock_get_api.return_value = mock_api

    result = jobs.list_jobs()

    mock_api.list_namespaced_job.assert_called_once_with(
        namespace=jobs.NAMESPACE,
        label_selector="managed-by=workflow-api",
    )
    assert len(result) == 2
    assert result[0]["status"] == "succeeded"
    assert result[1]["status"] == "running"


def test_serialize_failed_condition_includes_error_message():
    failed_condition = client.V1JobCondition(
        type="Failed",
        status="True",
        reason="BackoffLimitExceeded",
        message="Worker exited with an error",
        last_transition_time=datetime.now(timezone.utc),
    )
    kubernetes_job = make_kubernetes_job(
        status={},
        conditions=[failed_condition],
    )

    result = jobs._serialize_job(kubernetes_job)

    assert result["status"] == "failed"
    assert result["error"] == "Worker exited with an error"
    assert result["finished_at"] is not None
    assert result["result"] is None
