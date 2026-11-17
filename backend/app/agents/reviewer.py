"""Reviewer agent: rule-based quality checks plus an AI review of the work papers.
It raises review notes; it never signs off."""
import json

from ..models import AgentRun, ReviewNote, Sample, Exception_
from ..sampling import sample_size, determine_test_type
from . import prompts
from .common import control_block, evidence_block
from .llm import call_structured
from .runner import RunContext

SCHEMA = {
    "type": "object",
    "properties": {"notes": {"type": "array", "items": {
        "type": "object",
        "properties": {"stage": {"type": "string", "enum": ["dni", "toe"]},
                       "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                       "text": {"type": "string"}},
        "required": ["stage", "severity", "text"]}},
        "overall": {"type": "string"}},
    "required": ["notes", "overall"],
}


def _latest(db, cid, agent):
    return (db.query(AgentRun).filter_by(control_id=cid, agent=agent, status="succeeded")
            .order_by(AgentRun.id.desc()).first())


def run(ctx: RunContext) -> dict:
    c, db = ctx.control, ctx.db
    dni, toe = _latest(db, c.id, "dni"), _latest(db, c.id, "toe")
    current_ids = sorted(e.id for e in ctx.evidence)

    def rules():
        notes = []
        if not dni:
            notes.append(("dni", "high", "No completed D&I agent run or work on file."))
        if dni and sorted(dni.evidence_ids or []) != current_ids:
            notes.append(("dni", "medium", f"Evidence changed since D&I run #{dni.id}; re-run or document why results still hold."))
        if dni and dni.guardrail_flags:
            notes.append(("dni", "high", f"D&I run #{dni.id} has {len(dni.guardrail_flags)} citation/guardrail flags to resolve."))
        if c.dni_conclusion is None and dni:
            notes.append(("dni", "medium", "D&I conclusion has not been confirmed by the preparer."))
        if toe:
            if sorted(toe.evidence_ids or []) != current_ids:
                notes.append(("toe", "medium", f"Evidence changed since TOE run #{toe.id}."))
            if c.toe_conclusion is None:
                notes.append(("toe", "medium", "TOE conclusion has not been confirmed by the preparer."))
            open_x = db.query(Exception_).filter_by(control_id=c.id, status="open").count()
            if open_x and (c.toe_conclusion or {}).get("operating") == "operating_effectively":
                notes.append(("toe", "high", f"{open_x} open exception(s) but the conclusion is 'operating effectively'; document why the exceptions do not change the conclusion."))
            if toe.guardrail_flags:
                notes.append(("toe", "high", f"TOE run #{toe.id} has {len(toe.guardrail_flags)} guardrail flags."))
            sample = db.query(Sample).filter_by(control_id=c.id, active=True).first()
            if determine_test_type(c.nature, c.frequency)["method"] == "random":
                if not sample:
                    notes.append(("toe", "high", "No sample on file for a sampling-based test."))
                else:
                    need, _ = sample_size(c.frequency, c.risk_rating, sample.population_size)
                    if sample.sample_size < need:
                        notes.append(("toe", "high", f"Sample size {sample.sample_size} is below methodology minimum {need}."))
                    if not sample.population_evidence_id:
                        notes.append(("toe", "medium", "Population source file not linked; completeness of population not evidenced."))
        return [{"stage": s, "severity": v, "text": t} for s, v, t in notes]

    rule_notes = ctx.step("rules", "Run quality rules", rules)

    def ai_review():
        work = {"dni_result": dni.result if dni else None, "dni_conclusion_confirmed": c.dni_conclusion,
                "toe_result": toe.result if toe else None, "toe_conclusion_confirmed": c.toe_conclusion}
        work_txt = json.dumps(work, default=str)[:40000]
        return call_structured(
            tool_name="record_review_notes", tool_description="Record review notes",
            schema=SCHEMA, system=prompts.REVIEW,
            user=f"{control_block(c)}\n\nWORK PAPERS (JSON):\n{work_txt}\n\n{evidence_block(ctx.evidence)}",
            mock=lambda: {"notes": [], "overall": "[offline mock] Only rule-based checks were run."})

    ai = ctx.step("ai_review", "Review work papers", ai_review)

    def raise_notes():
        # Avoid duplicates: skip notes whose text already exists as an open note
        existing = {n.text for n in db.query(ReviewNote).filter_by(control_id=c.id, status="open")}
        created = 0
        for n in rule_notes + ai["notes"]:
            if n["text"] in existing:
                continue
            db.add(ReviewNote(control_id=c.id, stage=n["stage"], severity=n["severity"], text=n["text"],
                              source="reviewer_agent", created_by=ctx.user.id))
            created += 1
        db.commit()
        return {"notes_created": created}

    ctx.step("notes", "Raise review notes", raise_notes)
    return {"rule_notes": rule_notes, "ai_notes": ai["notes"], "overall": ai.get("overall", "")}
