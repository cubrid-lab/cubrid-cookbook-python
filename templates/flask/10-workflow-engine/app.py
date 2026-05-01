from __future__ import annotations

import os
from datetime import datetime
from typing import Any, cast

from flask import Flask, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

try:
    from .database import db
    from .models import (
        WorkflowDefinition,
        WorkflowRun,
        WorkflowStepDefinition,
        WorkflowStepRun,
    )
except ImportError:
    from database import db  # pyright: ignore[reportImplicitRelativeImport]
    from models import (  # pyright: ignore[reportImplicitRelativeImport]
        WorkflowDefinition,
        WorkflowRun,
        WorkflowStepDefinition,
        WorkflowStepRun,
    )


def _json_payload() -> dict[str, object]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return {}


def _serialize_predecessors(predecessor_keys: list[str]) -> str:
    return ",".join(predecessor_keys)


def _parse_predecessors(predecessor_keys_text: str) -> list[str]:
    if not predecessor_keys_text:
        return []
    return [part for part in predecessor_keys_text.split(",") if part]


def validate_dag(steps: list[dict[str, object]]) -> None:
    graph: dict[str, set[str]] = {}
    for step in steps:
        predecessor_keys = cast(list[str], step.get("predecessor_keys", []))
        graph[str(step["step_key"])] = set(predecessor_keys)
    for _, preds in graph.items():
        for pred in preds:
            if pred not in graph:
                raise ValueError(f"Unknown predecessor: {pred}")

    in_degree = {key: len(preds) for key, preds in graph.items()}
    queue = [key for key, degree in in_degree.items() if degree == 0]
    visited = 0

    while queue:
        node = queue.pop(0)
        visited += 1
        for key, preds in graph.items():
            if node in preds:
                in_degree[key] -= 1
                if in_degree[key] == 0:
                    queue.append(key)

    if visited != len(graph):
        raise ValueError("Cycle detected in workflow DAG")


def _step_defs_by_workflow(workflow_id: int) -> dict[str, WorkflowStepDefinition]:
    step_defs = (
        db.session.execute(
            select(WorkflowStepDefinition)
            .where(WorkflowStepDefinition.workflow_id == workflow_id)
            .order_by(WorkflowStepDefinition.sort_order.asc(), WorkflowStepDefinition.id.asc())
        )
        .scalars()
        .all()
    )
    return {step_def.step_key: step_def for step_def in step_defs}


def _step_runs_by_run(run_id: int) -> dict[str, WorkflowStepRun]:
    step_runs = (
        db.session.execute(
            select(WorkflowStepRun)
            .where(WorkflowStepRun.run_id == run_id)
            .order_by(WorkflowStepRun.id.asc())
        )
        .scalars()
        .all()
    )
    return {step_run.step_key: step_run for step_run in step_runs}


def _is_done_state(state: str) -> bool:
    return state in {"completed", "skipped"}


def _reevaluate_successors(workflow_run: WorkflowRun) -> None:
    step_defs = _step_defs_by_workflow(workflow_run.workflow_id)
    step_runs = _step_runs_by_run(workflow_run.id)
    changed = True

    while changed:
        changed = False
        for step_key, step_def in step_defs.items():
            step_run = step_runs[step_key]
            if step_run.state != "pending":
                continue

            predecessors = _parse_predecessors(step_def.predecessor_keys_text)
            if not all(_is_done_state(step_runs[pred].state) for pred in predecessors):
                continue

            next_state = "ready" if step_def.step_kind == "auto" else "waiting_approval"
            updated = (
                db.session.query(WorkflowStepRun)
                .filter(
                    WorkflowStepRun.id == step_run.id,
                    WorkflowStepRun.state == "pending",
                    WorkflowStepRun.version == step_run.version,
                )
                .update(
                    {
                        "state": next_state,
                        "version": WorkflowStepRun.version + 1,
                    }
                )
            )
            if updated == 1:
                refreshed = db.session.get(WorkflowStepRun, step_run.id)
                if refreshed is not None:
                    step_runs[step_key] = refreshed
                changed = True


def _set_run_completed_if_terminal(workflow_run: WorkflowRun) -> None:
    step_runs = _step_runs_by_run(workflow_run.id)
    terminal_states = {"completed", "skipped", "failed"}
    if step_runs and all(step_run.state in terminal_states for step_run in step_runs.values()):
        has_failure = any(step_run.state == "failed" for step_run in step_runs.values())
        workflow_run.state = "failed" if has_failure else "completed"
        workflow_run.completed_at = datetime.utcnow()


def _serialize_workflow(workflow: WorkflowDefinition) -> dict[str, object]:
    step_defs = (
        db.session.execute(
            select(WorkflowStepDefinition)
            .where(WorkflowStepDefinition.workflow_id == workflow.id)
            .order_by(WorkflowStepDefinition.sort_order.asc(), WorkflowStepDefinition.id.asc())
        )
        .scalars()
        .all()
    )
    return {
        "id": workflow.id,
        "workflow_key": workflow.workflow_key,
        "name": workflow.name,
        "step_count": workflow.step_count,
        "version": workflow.version,
        "steps": [
            {
                "id": step_def.id,
                "step_key": step_def.step_key,
                "name": step_def.name,
                "predecessor_keys": _parse_predecessors(step_def.predecessor_keys_text),
                "step_kind": step_def.step_kind,
                "max_retries": step_def.max_retries,
                "sort_order": step_def.sort_order,
            }
            for step_def in step_defs
        ],
    }


def _serialize_run(workflow_run: WorkflowRun) -> dict[str, object]:
    step_runs = (
        db.session.execute(
            select(WorkflowStepRun)
            .where(WorkflowStepRun.run_id == workflow_run.id)
            .order_by(WorkflowStepRun.id.asc())
        )
        .scalars()
        .all()
    )
    return {
        "id": workflow_run.id,
        "run_key": workflow_run.run_key,
        "workflow_id": workflow_run.workflow_id,
        "state": workflow_run.state,
        "version": workflow_run.version,
        "step_runs": [
            {
                "id": step_run.id,
                "step_key": step_run.step_key,
                "state": step_run.state,
                "attempt_count": step_run.attempt_count,
                "version": step_run.version,
                "last_error_text": step_run.last_error_text,
            }
            for step_run in step_runs
        ],
    }


def create_app(config: dict[str, object] | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "cubrid+pycubrid://dba@localhost:33000/testdb"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if config:
        app.config.update(config)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    @app.post("/workflows")
    def create_workflow():
        payload = _json_payload()
        workflow_key = str(payload.get("workflow_key", "")).strip()
        name = str(payload.get("name", "")).strip()
        steps_payload = payload.get("steps", [])

        if not workflow_key or not name:
            return jsonify({"error": "workflow_key and name are required"}), 400
        if not isinstance(steps_payload, list) or not steps_payload:
            return jsonify({"error": "steps must be a non-empty list"}), 400

        normalized_steps: list[dict[str, Any]] = []
        seen_step_keys: set[str] = set()

        for step_payload in steps_payload:
            if not isinstance(step_payload, dict):
                return jsonify({"error": "each step must be an object"}), 400

            step_key = str(step_payload.get("step_key", "")).strip()
            step_name = str(step_payload.get("name", "")).strip()
            predecessor_keys = step_payload.get("predecessor_keys", [])
            step_kind = str(step_payload.get("step_kind", "auto")).strip() or "auto"
            max_retries = int(step_payload.get("max_retries", 0))
            sort_order = int(step_payload.get("sort_order", 0))

            if not step_key or not step_name:
                return jsonify({"error": "step_key and name are required for each step"}), 400
            if step_key in seen_step_keys:
                return jsonify({"error": f"duplicate step_key: {step_key}"}), 400
            if step_kind not in {"auto", "manual"}:
                return jsonify({"error": "step_kind must be auto or manual"}), 400
            if max_retries < 0:
                return jsonify({"error": "max_retries must be >= 0"}), 400
            if not isinstance(predecessor_keys, list):
                return jsonify({"error": "predecessor_keys must be a list"}), 400

            predecessor_values = [
                str(item).strip() for item in predecessor_keys if str(item).strip()
            ]
            seen_step_keys.add(step_key)
            normalized_steps.append(
                {
                    "step_key": step_key,
                    "name": step_name,
                    "predecessor_keys": predecessor_values,
                    "step_kind": step_kind,
                    "max_retries": max_retries,
                    "sort_order": sort_order,
                }
            )

        try:
            validate_dag(normalized_steps)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        try:
            db.session.begin_nested()
            workflow = WorkflowDefinition()
            workflow.workflow_key = workflow_key
            workflow.name = name
            workflow.step_count = len(normalized_steps)
            db.session.add(workflow)
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "workflow_key already exists"}), 409

        for step in normalized_steps:
            step_def = WorkflowStepDefinition()
            step_def.workflow_id = workflow.id
            step_def.step_key = str(step["step_key"])
            step_def.name = str(step["name"])
            step_def.predecessor_keys_text = _serialize_predecessors(
                cast(list[str], step["predecessor_keys"])
            )
            step_def.step_kind = str(step["step_kind"])
            step_def.max_retries = int(cast(int, step["max_retries"]))
            step_def.sort_order = int(cast(int, step["sort_order"]))
            db.session.add(step_def)

        db.session.commit()

        return jsonify(_serialize_workflow(workflow)), 201

    @app.get("/workflows/<workflow_key>")
    def get_workflow(workflow_key: str):
        workflow = db.session.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.workflow_key == workflow_key)
        ).scalar_one_or_none()
        if workflow is None:
            return jsonify({"error": "workflow not found"}), 404
        return jsonify(_serialize_workflow(workflow))

    @app.post("/workflow-runs")
    def create_workflow_run():
        payload = _json_payload()
        run_key = str(payload.get("run_key", "")).strip()
        workflow_key = str(payload.get("workflow_key", "")).strip()
        if not run_key or not workflow_key:
            return jsonify({"error": "run_key and workflow_key are required"}), 400

        workflow = db.session.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.workflow_key == workflow_key)
        ).scalar_one_or_none()
        if workflow is None:
            return jsonify({"error": "workflow not found"}), 404

        step_defs = (
            db.session.execute(
                select(WorkflowStepDefinition)
                .where(WorkflowStepDefinition.workflow_id == workflow.id)
                .order_by(WorkflowStepDefinition.sort_order.asc(), WorkflowStepDefinition.id.asc())
            )
            .scalars()
            .all()
        )

        workflow_run = WorkflowRun()
        workflow_run.run_key = run_key
        workflow_run.workflow_id = workflow.id
        workflow_run.state = "running"
        db.session.add(workflow_run)
        db.session.flush()

        for step_def in step_defs:
            step_run = WorkflowStepRun()
            step_run.run_id = workflow_run.id
            step_run.step_key = step_def.step_key
            if _parse_predecessors(step_def.predecessor_keys_text):
                step_run.state = "pending"
            elif step_def.step_kind == "manual":
                step_run.state = "waiting_approval"
            else:
                step_run.state = "ready"
            db.session.add(step_run)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "run_key already exists"}), 409

        return jsonify(_serialize_run(workflow_run)), 201

    @app.get("/workflow-runs/<run_key>")
    def get_workflow_run(run_key: str):
        workflow_run = db.session.execute(
            select(WorkflowRun).where(WorkflowRun.run_key == run_key)
        ).scalar_one_or_none()
        if workflow_run is None:
            return jsonify({"error": "workflow run not found"}), 404
        return jsonify(_serialize_run(workflow_run))

    @app.post("/workflow-runs/<run_key>/tick")
    def tick_workflow_run(run_key: str):
        payload = _json_payload()
        forced_outcomes = payload.get("forced_outcomes", {})
        if not isinstance(forced_outcomes, dict):
            return jsonify({"error": "forced_outcomes must be an object"}), 400

        workflow_run = db.session.execute(
            select(WorkflowRun).where(WorkflowRun.run_key == run_key)
        ).scalar_one_or_none()
        if workflow_run is None:
            return jsonify({"error": "workflow run not found"}), 404

        step_defs = _step_defs_by_workflow(workflow_run.workflow_id)
        step_runs = _step_runs_by_run(workflow_run.id)

        ready_auto_runs = [
            step_runs[key]
            for key, step_def in step_defs.items()
            if step_def.step_kind == "auto" and step_runs[key].state == "ready"
        ]

        for step_run in ready_auto_runs:
            claimed = (
                db.session.query(WorkflowStepRun)
                .filter(
                    WorkflowStepRun.id == step_run.id,
                    WorkflowStepRun.state == "ready",
                    WorkflowStepRun.version == step_run.version,
                )
                .update(
                    {
                        "state": "running",
                        "version": WorkflowStepRun.version + 1,
                        "started_at": step_run.started_at or datetime.utcnow(),
                    }
                )
            )
            if claimed != 1:
                db.session.rollback()
                return jsonify({"error": f"claim conflict for step {step_run.step_key}"}), 409

            claimed_run = db.session.get(WorkflowStepRun, step_run.id)
            if claimed_run is None:
                db.session.rollback()
                return jsonify({"error": "workflow step run not found"}), 404

            outcome = str(forced_outcomes.get(claimed_run.step_key, "success"))
            if outcome not in {"success", "fail"}:
                db.session.rollback()
                return jsonify({"error": "forced outcomes must be success or fail"}), 400

            if outcome == "success":
                finalized = (
                    db.session.query(WorkflowStepRun)
                    .filter(
                        WorkflowStepRun.id == claimed_run.id,
                        WorkflowStepRun.state == "running",
                        WorkflowStepRun.version == claimed_run.version,
                    )
                    .update(
                        {
                            "state": "completed",
                            "last_error_text": None,
                            "attempt_count": claimed_run.attempt_count + 1,
                            "version": WorkflowStepRun.version + 1,
                            "finished_at": datetime.utcnow(),
                        }
                    )
                )
            else:
                finalized = (
                    db.session.query(WorkflowStepRun)
                    .filter(
                        WorkflowStepRun.id == claimed_run.id,
                        WorkflowStepRun.state == "running",
                        WorkflowStepRun.version == claimed_run.version,
                    )
                    .update(
                        {
                            "state": "failed",
                            "last_error_text": "forced failure",
                            "attempt_count": claimed_run.attempt_count + 1,
                            "version": WorkflowStepRun.version + 1,
                            "finished_at": datetime.utcnow(),
                        }
                    )
                )
            if finalized != 1:
                db.session.rollback()
                return jsonify({"error": f"finalize conflict for step {claimed_run.step_key}"}), 409

        _reevaluate_successors(workflow_run)
        _set_run_completed_if_terminal(workflow_run)
        db.session.commit()
        refreshed = db.session.get(WorkflowRun, workflow_run.id)
        if refreshed is None:
            return jsonify({"error": "workflow run not found"}), 404
        return jsonify(_serialize_run(refreshed))

    @app.post("/workflow-step-runs/<int:step_run_id>/approve")
    def approve_step_run(step_run_id: int):
        step_run = db.session.get(WorkflowStepRun, step_run_id)
        if step_run is None:
            return jsonify({"error": "workflow step run not found"}), 404
        if step_run.state != "waiting_approval":
            return jsonify({"error": "step is not waiting for approval"}), 400

        updated = (
            db.session.query(WorkflowStepRun)
            .filter(
                WorkflowStepRun.id == step_run.id,
                WorkflowStepRun.state == "waiting_approval",
                WorkflowStepRun.version == step_run.version,
            )
            .update(
                {
                    "state": "completed",
                    "version": WorkflowStepRun.version + 1,
                    "finished_at": datetime.utcnow(),
                }
            )
        )
        if updated != 1:
            db.session.rollback()
            return jsonify({"error": "approval conflict"}), 409

        workflow_run = db.session.get(WorkflowRun, step_run.run_id)
        if workflow_run is None:
            db.session.rollback()
            return jsonify({"error": "workflow run not found"}), 404
        _reevaluate_successors(workflow_run)
        _set_run_completed_if_terminal(workflow_run)
        db.session.commit()
        refreshed = db.session.get(WorkflowStepRun, step_run.id)
        if refreshed is None:
            return jsonify({"error": "workflow step run not found"}), 404
        return jsonify({"id": refreshed.id, "state": refreshed.state})

    @app.post("/workflow-step-runs/<int:step_run_id>/retry")
    def retry_step_run(step_run_id: int):
        step_run = db.session.get(WorkflowStepRun, step_run_id)
        if step_run is None:
            return jsonify({"error": "workflow step run not found"}), 404
        if step_run.state != "failed":
            return jsonify({"error": "step is not failed"}), 400

        workflow_run = db.session.get(WorkflowRun, step_run.run_id)
        if workflow_run is None:
            return jsonify({"error": "workflow run not found"}), 404
        step_defs = _step_defs_by_workflow(workflow_run.workflow_id)
        step_def = step_defs.get(step_run.step_key)
        if step_def is None:
            return jsonify({"error": "step definition not found"}), 404

        if step_run.attempt_count >= step_def.max_retries:
            return jsonify({"error": "retry budget exhausted"}), 400

        updated = (
            db.session.query(WorkflowStepRun)
            .filter(
                WorkflowStepRun.id == step_run.id,
                WorkflowStepRun.state == "failed",
                WorkflowStepRun.version == step_run.version,
            )
            .update(
                {
                    "state": "ready",
                    "version": WorkflowStepRun.version + 1,
                    "last_error_text": None,
                    "finished_at": None,
                }
            )
        )
        if updated != 1:
            db.session.rollback()
            return jsonify({"error": "retry conflict"}), 409

        db.session.commit()
        refreshed = db.session.get(WorkflowStepRun, step_run.id)
        if refreshed is None:
            return jsonify({"error": "workflow step run not found"}), 404
        return jsonify({"id": refreshed.id, "state": refreshed.state})

    @app.post("/workflow-step-runs/<int:step_run_id>/skip")
    def skip_step_run(step_run_id: int):
        step_run = db.session.get(WorkflowStepRun, step_run_id)
        if step_run is None:
            return jsonify({"error": "workflow step run not found"}), 404
        if step_run.state not in {"failed", "waiting_approval"}:
            return jsonify({"error": "step cannot be skipped in current state"}), 400

        updated = (
            db.session.query(WorkflowStepRun)
            .filter(
                WorkflowStepRun.id == step_run.id,
                WorkflowStepRun.state == step_run.state,
                WorkflowStepRun.version == step_run.version,
            )
            .update(
                {
                    "state": "skipped",
                    "version": WorkflowStepRun.version + 1,
                    "finished_at": datetime.utcnow(),
                }
            )
        )
        if updated != 1:
            db.session.rollback()
            return jsonify({"error": "skip conflict"}), 409

        workflow_run = db.session.get(WorkflowRun, step_run.run_id)
        if workflow_run is None:
            db.session.rollback()
            return jsonify({"error": "workflow run not found"}), 404

        _reevaluate_successors(workflow_run)
        _set_run_completed_if_terminal(workflow_run)
        db.session.commit()
        refreshed = db.session.get(WorkflowStepRun, step_run.id)
        if refreshed is None:
            return jsonify({"error": "workflow step run not found"}), 404
        return jsonify({"id": refreshed.id, "state": refreshed.state})

    return app
