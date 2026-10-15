
from threading import Lock
from datetime import datetime

from prometheus_client import Counter, Gauge, Histogram

jobs_submitted_total = Counter(
    "workflow_jobs_submitted_total",
    "Total jobs successfully submitted to Kubernetes.",
    ["task_type"],
)

jobs_finished_total = Counter(
    "workflow_jobs_finished_total",
    "Total jobs by final status.",
    ["task_type", "status"],
)

job_duration_seconds = Histogram(
    "workflow_job_duration_seconds",
    "Elapsed time from submission to job completion in seconds.",
    ["task_type"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
)

jobs_currently_running = Gauge(
    "workflow_jobs_currently_running",
    "Number of currently running workflow jobs.",
    ["task_type"],
)

_state_lock = Lock()
_job_states: dict[str, str] = {}


def record_submission(job_id: str, task_type: str) -> None:
    """Record a successful submission once per process."""
    with _state_lock:
        if job_id in _job_states:
            return

        _job_states[job_id] = "queued"
        jobs_submitted_total.labels(task_type=task_type).inc()


def record_status(
    job_id: str,
    task_type: str,
    status: str,
    submitted_at: str | None,
    finished_at: str | None,
) -> None:
    """Record observed job state transitions without repeated counts."""
    with _state_lock:
        previous = _job_states.get(job_id)

        if previous is None:
            # The API may have restarted or may be observing an older job.
            # Track the observed state without inventing a submission event.
            _job_states[job_id] = status
            if status == "running":
                jobs_currently_running.labels(task_type=task_type).inc()
            elif status in {"succeeded", "failed"}:
                jobs_finished_total.labels(
                    task_type=task_type,
                    status=status,
                ).inc()
            return

        if previous == status:
            return

        if previous == "running":
            jobs_currently_running.labels(task_type=task_type).dec()

        if status == "running":
            jobs_currently_running.labels(task_type=task_type).inc()

        if status in {"succeeded", "failed"}:
            jobs_finished_total.labels(
                task_type=task_type,
                status=status,
            ).inc()

            if submitted_at and finished_at:
                try:
                    start = datetime.fromisoformat(submitted_at)
                    end = datetime.fromisoformat(finished_at)
                    duration = (end - start).total_seconds()
                    if duration >= 0:
                        job_duration_seconds.labels(
                            task_type=task_type
                        ).observe(duration)
                except (TypeError, ValueError):
                    pass

        _job_states[job_id] = status
