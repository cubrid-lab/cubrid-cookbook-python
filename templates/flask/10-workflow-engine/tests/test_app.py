from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def client(tmp_path):
    from app import create_app  # pyright: ignore[reportImplicitRelativeImport]

    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/test.db",
            "TESTING": True,
        }
    )
    with app.test_client() as c:
        yield c


def _create_workflow(client, steps):
    response = client.post(
        "/workflows",
        json={
            "workflow_key": "wf-order",
            "name": "Order workflow",
            "steps": steps,
        },
    )
    assert response.status_code == 201
    return response.get_json()


def _create_run(client, run_key="run-1"):
    response = client.post("/workflow-runs", json={"run_key": run_key, "workflow_key": "wf-order"})
    assert response.status_code == 201
    return response.get_json()


def _step_map(run_payload):
    return {step["step_key"]: step for step in run_payload["step_runs"]}


def test_create_workflow_dag_valid(client):
    _create_workflow(
        client,
        [
            {
                "step_key": "start",
                "name": "Start",
                "predecessor_keys": [],
                "step_kind": "auto",
                "max_retries": 1,
                "sort_order": 1,
            },
            {
                "step_key": "review",
                "name": "Review",
                "predecessor_keys": ["start"],
                "step_kind": "manual",
                "max_retries": 0,
                "sort_order": 2,
            },
        ],
    )
    run = _create_run(client)
    steps = _step_map(run)
    assert steps["start"]["state"] == "ready"
    assert steps["review"]["state"] == "pending"


def test_cycle_detection_400(client):
    response = client.post(
        "/workflows",
        json={
            "workflow_key": "wf-cycle",
            "name": "Cyclic workflow",
            "steps": [
                {"step_key": "A", "name": "A", "predecessor_keys": ["C"]},
                {"step_key": "B", "name": "B", "predecessor_keys": ["A"]},
                {"step_key": "C", "name": "C", "predecessor_keys": ["B"]},
            ],
        },
    )
    assert response.status_code == 400
    assert "Cycle detected" in response.get_json()["error"]


def test_tick_completes_auto_steps(client):
    _create_workflow(
        client,
        [
            {"step_key": "A", "name": "A", "predecessor_keys": [], "step_kind": "auto"},
            {"step_key": "B", "name": "B", "predecessor_keys": ["A"], "step_kind": "auto"},
        ],
    )
    _create_run(client)

    tick1 = client.post("/workflow-runs/run-1/tick", json={})
    assert tick1.status_code == 200
    steps1 = _step_map(tick1.get_json())
    assert steps1["A"]["state"] == "completed"
    assert steps1["B"]["state"] == "ready"

    tick2 = client.post("/workflow-runs/run-1/tick", json={})
    steps2 = _step_map(tick2.get_json())
    assert steps2["B"]["state"] == "completed"
    assert tick2.get_json()["state"] == "completed"


def test_manual_step_waiting_approval(client):
    _create_workflow(
        client,
        [
            {"step_key": "A", "name": "A", "predecessor_keys": [], "step_kind": "auto"},
            {
                "step_key": "M",
                "name": "Manual",
                "predecessor_keys": ["A"],
                "step_kind": "manual",
            },
        ],
    )
    _create_run(client)

    tick = client.post("/workflow-runs/run-1/tick", json={})
    steps = _step_map(tick.get_json())
    assert steps["M"]["state"] == "waiting_approval"


def test_approve_unblocks_successor(client):
    _create_workflow(
        client,
        [
            {"step_key": "A", "name": "A", "predecessor_keys": [], "step_kind": "auto"},
            {
                "step_key": "M",
                "name": "Manual",
                "predecessor_keys": ["A"],
                "step_kind": "manual",
            },
            {
                "step_key": "B",
                "name": "B",
                "predecessor_keys": ["M"],
                "step_kind": "auto",
            },
        ],
    )
    _create_run(client)
    tick = client.post("/workflow-runs/run-1/tick", json={})
    steps = _step_map(tick.get_json())

    approve = client.post(f"/workflow-step-runs/{steps['M']['id']}/approve")
    assert approve.status_code == 200

    run = client.get("/workflow-runs/run-1")
    run_steps = _step_map(run.get_json())
    assert run_steps["B"]["state"] == "ready"


def test_retry_within_budget(client):
    _create_workflow(
        client,
        [
            {
                "step_key": "A",
                "name": "A",
                "predecessor_keys": [],
                "step_kind": "auto",
                "max_retries": 2,
            }
        ],
    )
    _create_run(client)

    tick = client.post(
        "/workflow-runs/run-1/tick",
        json={"forced_outcomes": {"A": "fail"}},
    )
    steps = _step_map(tick.get_json())
    assert steps["A"]["state"] == "failed"

    retry = client.post(f"/workflow-step-runs/{steps['A']['id']}/retry")
    assert retry.status_code == 200
    assert retry.get_json()["state"] == "ready"


def test_skip_allows_downstream(client):
    _create_workflow(
        client,
        [
            {"step_key": "A", "name": "A", "predecessor_keys": [], "step_kind": "auto"},
            {
                "step_key": "M",
                "name": "Manual",
                "predecessor_keys": ["A"],
                "step_kind": "manual",
            },
            {
                "step_key": "B",
                "name": "B",
                "predecessor_keys": ["M"],
                "step_kind": "auto",
            },
        ],
    )
    _create_run(client)
    tick = client.post("/workflow-runs/run-1/tick", json={})
    steps = _step_map(tick.get_json())

    skip = client.post(f"/workflow-step-runs/{steps['M']['id']}/skip")
    assert skip.status_code == 200

    run = client.get("/workflow-runs/run-1")
    run_steps = _step_map(run.get_json())
    assert run_steps["B"]["state"] == "ready"
