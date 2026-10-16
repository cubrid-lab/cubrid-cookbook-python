from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

app = import_module("app").app
session_scope = import_module("database").session_scope
models = import_module("models")
EmailLog = models.EmailLog
Job = models.Job

logger = logging.getLogger(__name__)


def _start_job(task_name: str) -> int:
    with session_scope() as session:
        job = Job(task_name=task_name, status="STARTED")
        session.add(job)
        session.flush()
        return job.id


def _finish_job(job_id: int, status: str, payload: dict[str, Any]) -> None:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = status
        job.result = json.dumps(payload)
        job.completed_at = datetime.now(timezone.utc)


def _end_attempt(job_id: int, status: str, payload: dict[str, Any]) -> None:
    """Record how a failed attempt ended; never let that replace the task's own error.

    If the status store is unavailable too, the Job stays STARTED and the
    failure is only logged: nothing can be recorded then.
    """
    try:
        _finish_job(job_id, status, payload)
    except Exception:
        logger.exception("could not record job %s as %s", job_id, status)


@app.task(bind=True, max_retries=3, default_retry_delay=2, name="tasks.send_notification")
def send_notification(
    self,
    recipient: str,
    subject: str,
    message: str,
    simulate_transient_error: bool = False,
) -> dict[str, Any]:
    # Each invocation, including every retry, records its own Job: one row per
    # attempt. An attempt that will be retried ends as RETRY, the last one as
    # FAILED or SUCCESS.
    job_id = _start_job("send_notification")

    try:
        if simulate_transient_error and self.request.retries < 1:
            raise RuntimeError("Simulated transient email provider error")

        with session_scope() as session:
            email_log = EmailLog(
                recipient=recipient,
                subject=subject,
                message=message,
                status="SENT",
            )
            session.add(email_log)
    except Exception as exc:
        failure = {"error": str(exc), "recipient": recipient, "retries": self.request.retries}
        if self.request.retries >= self.max_retries:
            _end_attempt(job_id, "FAILED", failure)
            raise
        _end_attempt(job_id, "RETRY", failure)
        raise self.retry(exc=exc)

    result: dict[str, object] = {
        "recipient": recipient,
        "subject": subject,
        "status": "SENT",
    }
    # Outside the try: the email is already logged, so failing to record the
    # Job must not retry the task and log it again.
    _finish_job(job_id, "SUCCESS", result)
    return result


@app.task(name="tasks.batch_email")
def batch_email(recipients: list[str], subject: str, message: str) -> dict[str, object]:
    job_id = _start_job("batch_email")

    try:
        with session_scope() as session:
            for recipient in recipients:
                session.add(
                    EmailLog(
                        recipient=recipient,
                        subject=subject,
                        message=message,
                        status="QUEUED",
                    )
                )
    except Exception as exc:
        _end_attempt(job_id, "FAILED", {"error": str(exc), "subject": subject})
        raise

    result: dict[str, object] = {
        "queued": len(recipients),
        "subject": subject,
    }
    _finish_job(job_id, "SUCCESS", {"queued": len(recipients), "subject": subject})
    return result
