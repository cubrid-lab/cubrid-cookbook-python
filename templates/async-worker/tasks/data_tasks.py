from __future__ import annotations

import json
import logging
from importlib import import_module
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select

app = import_module("app").app
session_scope = import_module("database").session_scope
models = import_module("models")
Job = models.Job
Report = models.Report
SalesRecord = models.SalesRecord

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


def _fail_job(job_id: int, exc: BaseException) -> None:
    """Record a failed attempt; never let that replace the task's own error.

    If the status store is unavailable too, the Job stays STARTED and the
    failure is only logged: nothing can be recorded then.
    """
    try:
        _finish_job(job_id, "FAILED", {"error": str(exc)})
    except Exception:
        logger.exception("could not record job %s as FAILED", job_id)


@app.task(name="tasks.aggregate_sales")
def aggregate_sales(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    # Invalid dates fail before any Job is recorded.
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    job_id = _start_job("aggregate_sales")

    try:
        with session_scope() as session:
            stmt = select(
                func.count(SalesRecord.id), func.coalesce(func.sum(SalesRecord.amount), 0)
            )
            if start_dt is not None:
                stmt = stmt.where(SalesRecord.created_at >= start_dt)
            if end_dt is not None:
                stmt = stmt.where(SalesRecord.created_at <= end_dt)

            total_orders, total_amount = session.execute(stmt).one()
            payload = {
                "start_date": start_date,
                "end_date": end_date,
                "total_orders": int(total_orders or 0),
                "total_amount": float(total_amount or Decimal("0")),
            }

            report = Report(
                report_name="sales-aggregation",
                content=json.dumps(payload),
            )
            session.add(report)
    except Exception as exc:
        _fail_job(job_id, exc)
        raise

    _finish_job(job_id, "SUCCESS", payload)
    return payload


@app.task(name="tasks.generate_report")
def generate_report(
    aggregation: dict[str, Any], report_name: str = "sales-report"
) -> dict[str, Any]:
    job_id = _start_job("generate_report")
    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aggregation": aggregation,
    }

    try:
        with session_scope() as session:
            report = Report(report_name=report_name, content=json.dumps(report_payload))
            session.add(report)
            session.flush()
            result = {
                "report_id": report.id,
                "report_name": report_name,
            }
    except Exception as exc:
        _fail_job(job_id, exc)
        raise

    _finish_job(job_id, "SUCCESS", result)
    return result


@app.task(name="tasks.cleanup_old_records")
def cleanup_old_records(days: int = 30) -> dict[str, int]:
    """Delete completed Jobs and Reports older than ``days`` days.

    ``days`` must be a whole number of days, 0 or more; ``0`` removes every
    completed Job and Report created before now. The period is checked before
    any Job is recorded or the database is touched: a negative value would move
    the cutoff into the future and delete recent records.
    """
    if isinstance(days, bool) or not isinstance(days, int):
        raise TypeError(f"days must be an int, not {type(days).__name__}")
    if days < 0:
        raise ValueError(f"days must be 0 or more, got {days}")
    try:
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
    except OverflowError as exc:
        raise ValueError(f"days={days} is too large to compute a cutoff date") from exc
    job_id = _start_job("cleanup_old_records")

    try:
        with session_scope() as session:
            old_jobs = (
                session.execute(
                    select(Job.id)
                    .where(Job.completed_at.is_not(None))
                    .where(Job.completed_at < threshold)
                )
                .scalars()
                .all()
            )
            old_reports = (
                session.execute(select(Report.id).where(Report.created_at < threshold))
                .scalars()
                .all()
            )

            deleted_jobs = len(old_jobs)
            deleted_reports = len(old_reports)

            if old_jobs:
                session.execute(delete(Job).where(Job.id.in_(old_jobs)))
            if old_reports:
                session.execute(delete(Report).where(Report.id.in_(old_reports)))
    except Exception as exc:
        _fail_job(job_id, exc)
        raise

    result = {
        "deleted_jobs": int(deleted_jobs or 0),
        "deleted_reports": int(deleted_reports or 0),
    }
    _finish_job(
        job_id,
        "SUCCESS",
        {
            "deleted_jobs": result["deleted_jobs"],
            "deleted_reports": result["deleted_reports"],
        },
    )
    return result
