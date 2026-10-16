"""``cleanup_old_records(days)`` validates its retention period before any database work (#383).

The validation tests need no database: they fail if the task records a Job
or opens a session. The retention tests run against the live CUBRID fixture.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module
from types import ModuleType

import pytest
from sqlalchemy import select


@pytest.fixture()
def guarded_tasks(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The data-task module with every database entry point turned into a failure."""
    data_tasks = import_module("tasks.data_tasks")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("database work before the retention period was validated")

    monkeypatch.setattr(data_tasks, "_start_job", forbidden)
    monkeypatch.setattr(data_tasks, "session_scope", forbidden)
    return data_tasks


@pytest.mark.parametrize("days", [-1, -30])
def test_negative_retention_is_rejected_before_any_database_work(
    guarded_tasks: ModuleType, days: int
) -> None:
    with pytest.raises(ValueError, match="days must be 0 or more"):
        guarded_tasks.cleanup_old_records.run(days=days)


@pytest.mark.parametrize("days", [True, False, 1.5, "30", None])
def test_non_integer_retention_is_rejected_before_any_database_work(
    guarded_tasks: ModuleType, days: object
) -> None:
    with pytest.raises(TypeError, match="days must be an int"):
        guarded_tasks.cleanup_old_records.run(days=days)


@pytest.mark.parametrize("days", [10**9, 10**20])
def test_unrepresentable_retention_is_rejected_before_any_database_work(
    guarded_tasks: ModuleType, days: int
) -> None:
    with pytest.raises(ValueError, match="too large"):
        guarded_tasks.cleanup_old_records.run(days=days)


NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return NOW if tz is not None else NOW.replace(tzinfo=None)


@pytest.mark.parametrize("days", [30, 0])
def test_retention_deletes_only_completed_records_older_than_the_cutoff(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    days: int,
) -> None:
    database, models, data_tasks, _email_tasks = worker_database
    monkeypatch.setattr(data_tasks, "datetime", _FixedDatetime)
    # Stored DateTime columns are naive; the fixtures use UTC wall time.
    cutoff = (NOW - timedelta(days=days)).replace(tzinfo=None)
    second = timedelta(seconds=1)
    with database.session_scope() as session:
        session.add_all(
            [
                models.Job(task_name="cb383-old", status="SUCCESS", completed_at=cutoff - second),
                models.Job(task_name="cb383-at-cutoff", status="SUCCESS", completed_at=cutoff),
                models.Job(
                    task_name="cb383-recent", status="SUCCESS", completed_at=cutoff + second
                ),
                models.Job(task_name="cb383-running", status="STARTED", completed_at=None),
                models.Report(report_name="cb383-old", content="{}", created_at=cutoff - second),
                models.Report(report_name="cb383-at-cutoff", content="{}", created_at=cutoff),
            ]
        )

    result = data_tasks.cleanup_old_records.run(days=days)

    assert result == {"deleted_jobs": 1, "deleted_reports": 1}
    with database.SessionLocal() as session:
        jobs = {job.task_name: job for job in session.execute(select(models.Job)).scalars().all()}
        reports = session.execute(select(models.Report.report_name)).scalars().all()
    # Exactly at the cutoff is kept: only records strictly older are removed.
    assert set(jobs) == {"cb383-at-cutoff", "cb383-recent", "cb383-running", "cleanup_old_records"}
    assert jobs["cleanup_old_records"].status == "SUCCESS"
    assert reports == ["cb383-at-cutoff"]


def test_rejected_retention_leaves_the_live_tables_untouched(
    worker_database: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    database, models, data_tasks, _email_tasks = worker_database
    recent = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    with database.session_scope() as session:
        session.add(models.Job(task_name="cb383-recent", status="SUCCESS", completed_at=recent))
        session.add(models.Report(report_name="cb383-recent", content="{}", created_at=recent))

    with pytest.raises(ValueError):
        data_tasks.cleanup_old_records.run(days=-1)

    with database.SessionLocal() as session:
        assert session.execute(select(models.Job.task_name)).scalars().all() == ["cb383-recent"]
        assert session.execute(select(models.Report.report_name)).scalars().all() == [
            "cb383-recent"
        ]
