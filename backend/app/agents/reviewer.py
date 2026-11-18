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
        "properties": {"stage": {"type": "string", "enum": ["design", "operating"]},
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
    design, operating = _latest(db, c.id, "design"), _latest(db, c.id, "operating")
    current_ids = sorted(e.id for e in ctx.evidence)

    def rules():
        notes = []
        if not design:
            notes.append(("design", "high", "No completed Design Effectiveness agent run or work on file."))
        if design and sorted(design.evidence_ids or []) != current_ids:
            notes.append(("design", "medium", f"Evidence changed since Design run #{design.id}; re-run or document why results still hold."))
        if design and design.guardrail_flags:
            notes.append(("design", "high", f"Design run #{design.id} has {len(design.guardrail_flags)} citation/guardrail flags to resolve."))
        if c.design_conclusion is None and design:
            notes.append(("design", "medium", "Design conclusion has not been confirmed by the preparer."))
        if operating:
            if sorted(operating.evidence_ids or []) != current_ids:
                notes.append(("operating", "medium", f"Evidence changed since Operating run #{operating.id}."))
            if c.operating_conclusion is None:
                notes.append(("operating", "medium", "Operating conclusion has not been confirmed by the preparer."))
            open_x = db.query(Exception_).filter_by(control_id=c.id, status="open").count()
            if open_x and (c.operating_conclusion or {}).get("operating") == "operating_effectively":
                notes.append(("operating", "high", f"{open_x} open exception(s) but the conclusion is 'operating effectively'; document why the exceptions do not change the conclusion."))
            if operating.guardrail_flags:
                notes.append(("operating", "high", f"Operating run #{operating.id} has {len(operating.guardrail_flags)} guardrail flags."))
            sample = db.query(Sample).filter_by(control_id=c.id, active=True).first()
            if determine_test_type(c.nature, c.frequency)["method"] == "random":
                if not sample:
                    notes.append(("operating", "high", "No sample on file for a sampling-based test."))
                else:
                    need, _ = sample_size(c.frequency, c.risk_rating, sample.population_size)
                    if sample.sample_size < need:
                        notes.append(("operating", "high", f"Sample size {sample.sample_size} is below methodology minimum {need}."))
                    if not sample.population_evidence_id:
                        notes.append(("operating", "medium", "Population source file not linked; completeness of population not evidenced."))
        return [{"stage": s, "severity": v, "text": t} for s, v, t in notes]

    rule_notes = ctx.step("rules", "Run quality rules", rules)

    def ai_review():
        work = {"design_result": design.result if design else None, "design_conclusion_confirmed": c.design_conclusion,
                "operating_result": operating.result if operating else None, "operating_conclusion_confirmed": c.operating_conclusion}
        work_txt = json.dumps(work, default=str)[:40000]
        return call_structured(
            tool_name="record_review_notes", tool_description="Record review notes",
            schema=SCHEMA, system=prompts.REVIEW,
            user=f"{control_block(c)}\n\nWORK PAPERS (JSON):\n{work_txt}\n\n{evidence_block(ctx.evidence)}",
            mock=lambda: {"notes": [], "overall": "[offline mock] Only rule-based checks were run."}, role="review")

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
