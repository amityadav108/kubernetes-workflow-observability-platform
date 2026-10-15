
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

RUN mkdir -p /app/worker && chown appuser:appuser /app/worker

COPY --chown=appuser:appuser run_job.py /app/worker/run_job.py

USER 10001:10001

CMD ["python", "/app/worker/run_job.py"]
