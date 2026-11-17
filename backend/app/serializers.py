from .models import (User, Engagement, System, Control, Evidence, Sample, AgentRun, ReviewNote,
                     Exception_, SignOff, AuditLog)


def user(u: User):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.active}


def system(s: System):
    return {"id": s.id, "name": s.name, "layer": s.layer, "description": s.description}


def engagement(e: Engagement, stats: dict | None = None):
    d = {"id": e.id, "name": e.name, "client": e.client, "engagement_type": e.engagement_type,
         "period_start": e.period_start.isoformat(), "period_end": e.period_end.isoformat(),
         "status": e.status, "created_at": e.created_at.isoformat()}
    if stats is not None:
        d["stats"] = stats
    return d


def control(c: Control, full=False):
    d = {"id": c.id, "engagement_id": c.engagement_id, "ref": c.ref, "domain": c.domain,
         "title": c.title, "frequency": c.frequency, "nature": c.nature,
         "risk_rating": c.risk_rating, "key_control": c.key_control, "status": c.status,
         "system": system(c.system) if c.system else None, "preparer_id": c.preparer_id,
         "reviewer_id": c.reviewer_id, "row_version": c.row_version,
         "design_conclusion": c.design_conclusion, "operating_conclusion": c.operating_conclusion,
         "updated_at": c.updated_at.isoformat() if c.updated_at else None}
    if full:
        d.update(description=c.description, objective=c.objective, risk=c.risk,
                 attributes=c.attributes, design_procedures=c.design_procedures,
                 operating_procedures=c.operating_procedures, expected_evidence=c.expected_evidence,
                 library_ref=c.library_ref, system_id=c.system_id)
    return d


def evidence(e: Evidence):
    return {"id": e.id, "label": f"E{e.id}", "filename": e.filename, "content_type": e.content_type,
            "size": e.size, "sha256": e.sha256, "purpose": e.purpose, "description": e.description,
            "extraction_note": e.extraction_note, "readable": bool(e.extracted_text),
            "uploaded_by": e.uploaded_by, "uploaded_at": e.uploaded_at.isoformat()}


def sample(s: Sample):
    return {"id": s.id, "population_evidence_id": s.population_evidence_id,
            "population_size": s.population_size, "sample_size": s.sample_size, "method": s.method,
            "seed": s.seed, "rationale": s.rationale, "items": s.items, "active": s.active,
            "created_by": s.created_by, "created_at": s.created_at.isoformat()}


def run(r: AgentRun, full=True):
    d = {"id": r.id, "agent": r.agent, "status": r.status, "provider": r.provider, "model": r.model,
         "prompt_version": r.prompt_version, "input_hash": r.input_hash,
         "evidence_ids": r.evidence_ids, "input_tokens": r.input_tokens,
         "output_tokens": r.output_tokens, "error": r.error, "created_by": r.created_by,
         "created_at": r.created_at.isoformat(),
         "finished_at": r.finished_at.isoformat() if r.finished_at else None,
         "flags": len(r.guardrail_flags or [])}
    if full:
        d.update(steps=r.steps, result=r.result, guardrail_flags=r.guardrail_flags)
    return d


def note(n: ReviewNote):
    return {"id": n.id, "stage": n.stage, "severity": n.severity, "text": n.text, "source": n.source,
            "status": n.status, "response": n.response, "created_by": n.created_by,
            "created_at": n.created_at.isoformat(), "closed_by": n.closed_by}


def exception(x: Exception_):
    return {"id": x.id, "sample_item": x.sample_item, "attribute_id": x.attribute_id,
            "description": x.description, "severity": x.severity, "status": x.status,
            "source": x.source, "created_at": x.created_at.isoformat()}


def signoff(s: SignOff):
    return {"id": s.id, "stage": s.stage, "kind": s.kind, "user": user(s.user), "comment": s.comment,
            "at": s.at.isoformat(), "revoked": s.revoked}


def audit_row(a: AuditLog):
    return {"id": a.id, "at": a.at.isoformat(), "user_email": a.user_email, "action": a.action,
            "entity": a.entity, "entity_id": a.entity_id, "engagement_id": a.engagement_id,
            "control_id": a.control_id, "details": a.details, "hash": a.hash}
