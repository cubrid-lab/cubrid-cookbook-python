"""Failed and retried task attempts leave a finished Job, never a STARTED one (#384).

Live CUBRID checks through the actual task implementations; each reads the
stored Jobs through a new session. Retries run through Celery's eager
``apply()``, so no Redis broker or worker is involved.
"""

from __future__ import annotations

import json
import logging
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError


def _jobs(database: ModuleType, models: ModuleType) -> list[Any]:
    with database.SessionLocal() as session:
        return list(session.execute(select(models.Job).order_by(models.Job.id)).scalars().all())


@pytest.fixture()
def no_result_backend(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep eager ``apply()`` off the app's real result backend (``db+...`` on port 33000)."""
    from celery.backends.cache import CacheBackend

    task = worker_database[3].send_notification
    # Set the private attribute: reading `task.backend` would create the real backend.
    monkeypatch.setattr(task, "_backend", CacheBackend(app=task.app, url="memory://"))


def _failing(exc: BaseException) -> Any:
    def _raise(*_args: object, **_kwargs: object) -> Any:
        raise exc

    return _raise


def test_invalid_date_fails_before_any_job_is_recorded(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    database, models, data_tasks, _email_tasks = worker_database
    with pytest.raises(ValueError):
        data_tasks.aggregate_sales.run(start_date="not-a-date")
    assert _jobs(database, models) == []


def test_workload_failure_marks_the_job_failed_and_keeps_the_error(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, models, data_tasks, _email_tasks = worker_database
    error = OperationalError("INSERT INTO cookbook_reports", {}, Exception("broker reset"))
    monkeypatch.setattr(data_tasks, "Report", _failing(error))

    with pytest.raises(OperationalError) as excinfo:
        data_tasks.aggregate_sales.run()
    assert excinfo.value is error

    (job,) = _jobs(database, models)
    assert (job.task_name, job.status) == ("aggregate_sales", "FAILED")
    assert job.completed_at is not None
    assert json.loads(job.result) == {"error": str(error)}


def test_failure_to_record_the_failure_does_not_replace_the_error(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    database, models, data_tasks, _email_tasks = worker_database
    error = RuntimeError("report storage failed")
    monkeypatch.setattr(data_tasks, "Report", _failing(error))
    monkeypatch.setattr(data_tasks, "_finish_job", _failing(RuntimeError("status store down")))

    with caplog.at_level(logging.ERROR, logger=data_tasks.__name__):
        with pytest.raises(RuntimeError) as excinfo:
            data_tasks.generate_report.run({"total_orders": 0})
    assert excinfo.value is error
    assert "could not record job" in caplog.text
    # The status store refused the update, so the Job could only stay STARTED.
    (job,) = _jobs(database, models)
    assert (job.status, job.completed_at) == ("STARTED", None)


def test_batch_email_failure_marks_the_job_failed(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, models, _data_tasks, email_tasks = worker_database
    error = RuntimeError("queue table unavailable")
    monkeypatch.setattr(email_tasks, "EmailLog", _failing(error))

    with pytest.raises(RuntimeError) as excinfo:
        email_tasks.batch_email.run(["cb384@example.com"], "cb384-subject", "body")
    assert excinfo.value is error
    (job,) = _jobs(database, models)
    assert (job.task_name, job.status) == ("batch_email", "FAILED")
    assert job.completed_at is not None


@pytest.mark.usefixtures("no_result_backend")
def test_transient_failure_then_success_leaves_no_started_attempt(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    database, models, _data_tasks, email_tasks = worker_database
    result = email_tasks.send_notification.apply(
        kwargs={
            "recipient": "cb384@example.com",
            "subject": "cb384-retry",
            "message": "retried once",
            "simulate_transient_error": True,
        }
    )
    # Eager apply() runs the retry in place and reports its result.
    assert result.state == "SUCCESS"
    assert result.result["status"] == "SENT"

    jobs = _jobs(database, models)
    assert [(job.task_name, job.status) for job in jobs] == [
        ("send_notification", "RETRY"),
        ("send_notification", "SUCCESS"),
    ]
    assert all(job.completed_at is not None for job in jobs)
    assert json.loads(jobs[0].result) == {
        "error": "Simulated transient email provider error",
        "recipient": "cb384@example.com",
        "retries": 0,
    }
    assert json.loads(jobs[1].result)["status"] == "SENT"
    with database.SessionLocal() as session:
        logs = session.execute(select(models.EmailLog)).scalars().all()
        assert [log.status for log in logs] == ["SENT"]  # sent once, by the retry


@pytest.mark.usefixtures("no_result_backend")
def test_exhausted_retries_end_every_attempt(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, models, _data_tasks, email_tasks = worker_database
    monkeypatch.setattr(email_tasks, "EmailLog", _failing(RuntimeError("provider down")))

    email_tasks.send_notification.apply(
        kwargs={"recipient": "cb384@example.com", "subject": "s", "message": "m"}
    )

    jobs = _jobs(database, models)
    max_retries = email_tasks.send_notification.max_retries
    assert [job.status for job in jobs] == ["RETRY"] * max_retries + ["FAILED"]
    assert all(job.completed_at is not None for job in jobs)
    assert [json.loads(job.result)["retries"] for job in jobs] == list(range(max_retries + 1))


def test_retry_signal_survives_a_failure_to_record_the_attempt(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, models, _data_tasks, email_tasks = worker_database
    error = RuntimeError("provider down")
    monkeypatch.setattr(email_tasks, "EmailLog", _failing(error))
    monkeypatch.setattr(email_tasks, "_finish_job", _failing(RuntimeError("status store down")))

    # Called directly, Celery's retry re-raises the task's own exception.
    with pytest.raises(RuntimeError) as excinfo:
        email_tasks.send_notification.run("cb384@example.com", "s", "m")
    assert excinfo.value is error
    (job,) = _jobs(database, models)
    assert job.status == "STARTED"
