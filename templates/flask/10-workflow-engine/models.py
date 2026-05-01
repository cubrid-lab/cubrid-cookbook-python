from datetime import datetime

try:
    from .database import db
except ImportError:
    from database import db  # pyright: ignore[reportImplicitRelativeImport]


class WorkflowDefinition(db.Model):
    __tablename__ = "workflow_definitions"

    id = db.Column(db.Integer, primary_key=True)
    workflow_key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    step_count = db.Column(db.Integer, nullable=False, default=0)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class WorkflowStepDefinition(db.Model):
    __tablename__ = "workflow_step_definitions"
    __table_args__ = (db.UniqueConstraint("workflow_id", "step_key", name="uq_wsd_workflow_step"),)

    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(
        db.Integer, db.ForeignKey("workflow_definitions.id"), nullable=False, index=True
    )
    step_key = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    predecessor_keys_text = db.Column(db.Text, nullable=False, default="")
    step_kind = db.Column(db.String(32), nullable=False, default="auto")
    max_retries = db.Column(db.Integer, nullable=False, default=0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class WorkflowRun(db.Model):
    __tablename__ = "workflow_runs"

    id = db.Column(db.Integer, primary_key=True)
    run_key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    workflow_id = db.Column(
        db.Integer, db.ForeignKey("workflow_definitions.id"), nullable=False, index=True
    )
    state = db.Column(db.String(32), nullable=False, default="running", index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    last_error_text = db.Column(db.Text, nullable=True)


class WorkflowStepRun(db.Model):
    __tablename__ = "workflow_step_runs"
    __table_args__ = (db.UniqueConstraint("run_id", "step_key", name="uq_wsr_run_step"),)

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("workflow_runs.id"), nullable=False, index=True)
    step_key = db.Column(db.String(64), nullable=False)
    state = db.Column(db.String(32), nullable=False, default="pending", index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    version = db.Column(db.Integer, nullable=False, default=1)
    last_error_text = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
