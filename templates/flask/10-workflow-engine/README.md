# 10 Workflow Engine (DAG)

Standalone Flask recipe that models workflow definitions and workflow runs with DAG-based execution.

Run: `python run.py`
Test: `python3 -m pytest tests/ -v`

## Endpoints

- `POST /workflows`
- `GET /workflows/<workflow_key>`
- `POST /workflow-runs`
- `GET /workflow-runs/<run_key>`
- `POST /workflow-runs/<run_key>/tick`
- `POST /workflow-step-runs/<id>/approve`
- `POST /workflow-step-runs/<id>/retry`
- `POST /workflow-step-runs/<id>/skip`
