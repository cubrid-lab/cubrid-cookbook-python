"""Live CUBRID checks for worker tasks without a Redis broker or Celery worker."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from types import ModuleType

import pytest
from sqlalchemy import select


def test_sales_aggregation_and_report_persist_job_results(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, models, data_tasks, _email_tasks = worker_database
    with database.session_scope() as session:
        session.add(
            models.SalesRecord(
                product_name="cb129-test-product", quantity=2, amount=Decimal("123.45")
            )
        )

    finish_job = data_tasks._finish_job
    started_states: list[str] = []

    def observe_before_finish(job_id: int, status: str, payload: dict[str, object]) -> None:
        with database.SessionLocal() as session:
            started = session.get(models.Job, job_id)
            assert started is not None
            started_states.append(started.status)
            assert started.result is None
        finish_job(job_id, status, payload)

    monkeypatch.setattr(data_tasks, "_finish_job", observe_before_finish)
    aggregation = data_tasks.aggregate_sales.run()
    assert aggregation["total_orders"] == 1
    assert aggregation["total_amount"] == pytest.approx(123.45)
    assert started_states == ["STARTED"]

    report_result = data_tasks.generate_report.run(aggregation, report_name="cb129-test-report")
    assert report_result["report_name"] == "cb129-test-report"
    assert started_states == ["STARTED", "STARTED"]

    # Read from a new session: returning a dict is not evidence of persistence.
    with database.SessionLocal() as session:
        jobs = session.execute(select(models.Job).order_by(models.Job.id)).scalars().all()
        reports = session.execute(select(models.Report).order_by(models.Report.id)).scalars().all()
        assert [job.task_name for job in jobs] == ["aggregate_sales", "generate_report"]
        assert [job.status for job in jobs] == ["SUCCESS", "SUCCESS"]
        assert all(job.completed_at is not None for job in jobs)
        assert json.loads(jobs[0].result) == aggregation
        assert json.loads(jobs[1].result) == report_result
        assert [report.report_name for report in reports] == [
            "sales-aggregation",
            "cb129-test-report",
        ]
        assert json.loads(reports[0].content) == aggregation
        generated = json.loads(reports[1].content)
        assert generated["aggregation"] == aggregation
        assert datetime.fromisoformat(generated["generated_at"])
        assert report_result["report_id"] == reports[1].id


def test_batch_email_persists_logs_and_job_result(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    database, models, _data_tasks, email_tasks = worker_database
    result = email_tasks.batch_email.run(
        recipients=["cb129-a@example.com", "cb129-b@example.com"],
        subject="cb129-test-subject",
        message="Direct task invocation without Redis",
    )
    assert result == {"queued": 2, "subject": "cb129-test-subject"}

    with database.SessionLocal() as session:
        jobs = session.execute(select(models.Job)).scalars().all()
        logs = session.execute(select(models.EmailLog).order_by(models.EmailLog.id)).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].task_name == "batch_email"
        assert jobs[0].status == "SUCCESS"
        assert jobs[0].completed_at is not None
        assert json.loads(jobs[0].result) == result
        assert [log.recipient for log in logs] == [
            "cb129-a@example.com",
            "cb129-b@example.com",
        ]
        assert all(log.status == "QUEUED" for log in logs)
