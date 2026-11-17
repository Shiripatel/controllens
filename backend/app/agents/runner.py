"""Runs an agent as a series of recorded steps. Each step's output is saved as it
finishes, so the UI can show progress and auditors can see exactly what the agent
did and why."""
import logging
import traceback
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import AgentRun, Control, Evidence, User
from .. import audit
from .llm import LLMResult

log = logging.getLogger("controllens.agents")


class StepFailed(Exception):
    pass


class RunContext:
    def __init__(self, db: Session, run: AgentRun):
        self.db = db
        self.run = run
        self.control: Control = db.get(Control, run.control_id)
        self.user: User = db.get(User, run.created_by)
        self.evidence: list[Evidence] = (
            db.query(Evidence).filter(Evidence.control_id == run.control_id,
                                      Evidence.deleted.is_(False))
            .order_by(Evidence.id).all())
        self.flags: list[dict] = []
        self.outputs: dict = {}

    def _save_steps(self, steps):
        self.run.steps = [dict(s) for s in steps]  # new list so SQLAlchemy sees the change
        self.db.commit()

    def step(self, key: str, title: str, fn):
        steps = list(self.run.steps or [])
        entry = {"key": key, "title": title, "status": "running",
                 "started": datetime.now(timezone.utc).isoformat()}
        steps.append(entry)
        self._save_steps(steps)
        try:
            out = fn()
        except StepFailed as e:
            entry.update(status="failed", error=str(e),
                         finished=datetime.now(timezone.utc).isoformat())
            self._save_steps(steps)
            raise
        if isinstance(out, LLMResult):
            self.run.provider, self.run.model = out.provider, out.model
            self.run.input_tokens += out.input_tokens
            self.run.output_tokens += out.output_tokens
            out = out.data
        entry.update(status="done", output=out, finished=datetime.now(timezone.utc).isoformat())
        self.outputs[key] = out
        self._save_steps(steps)
        return out


def execute(run_id: int, agent_fn):
    """Entry point used by background tasks. Uses its own DB session."""
    db = SessionLocal()
    try:
        run = db.get(AgentRun, run_id)
        run.status = "running"
        db.commit()
        ctx = RunContext(db, run)
        run.evidence_ids = [e.id for e in ctx.evidence]
        try:
            result = agent_fn(ctx)
            run.result = result
            run.guardrail_flags = ctx.flags
            run.status = "succeeded"
        except StepFailed as e:
            run.status, run.error = "failed", str(e)
        except Exception as e:  # noqa: BLE001
            log.error("agent run %s crashed: %s", run_id, traceback.format_exc())
            run.status, run.error = "failed", f"{type(e).__name__}: {e}"
        run.finished_at = datetime.now(timezone.utc)
        audit.log(db, ctx.user, f"agent.{run.agent}.{run.status}", "agent_run", run.id,
                  {"model": run.model, "prompt_version": run.prompt_version,
                   "input_hash": run.input_hash, "flags": len(run.guardrail_flags or []),
                   "error": run.error[:300]},
                  engagement_id=ctx.control.engagement_id, control_id=ctx.control.id)
        db.commit()
    finally:
        db.close()
