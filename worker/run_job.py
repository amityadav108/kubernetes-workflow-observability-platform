
import os
import json
import time
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    job_id = os.environ["JOB_ID"]
    task_type = os.environ["TASK_TYPE"]
    params = json.loads(os.getenv("PARAMETERS_JSON", "{}"))

    logger.info("Started %s: %s", job_id, task_type)
    logger.info("Parameters: %s", params)

    # Controlled failure for reliability testing only.
    if params.get("simulate_failure") is True:
        logger.error("Simulated worker failure for job %s", job_id)
        sys.exit(1)

    time.sleep(3)
    logger.info("Job completed: %s", job_id)


if __name__ == "__main__":
    main()
