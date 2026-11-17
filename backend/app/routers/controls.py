import hashlib
import os
import random
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit, serializers as S, workflow
from ..agents import design, operating, reviewer, prompts
from ..agents.common import input_hash
from ..agents.llm import provider_name
from ..agents.runner import execute
from ..config import get_settings
from ..db import get_db
from ..extraction import extract, ALLOWED_EXT
from ..library import FREQUENCIES
from ..models import (Control, Evidence, Sample, AgentRun, ReviewNote, Exception_, SignOff, User,
                      AuditLog)
from ..sampling import determine_test_type, sample_size, parse_population, select
from ..security import current_user, check_engagement_access, ROLE_RANK

router = APIRouter(tags=["controls"])
settings = get_settings()

AGENTS = {"design": (design.run, prompts.DESIGN_VERSION), "operating": (operating.run, prompts.OE_VERSION),
          "reviewer": (reviewer.run, prompts.REVIEW_VERSION)}


def get_control(db: Session, cid: int, user: User, write=False) -> Control:
    c = db.get(Control, cid)
    if not c:
        raise HTTPException(404, "Control not found")
    check_engagement_access(db, user, c.engagement, write)
    return c


def _log(db, user, action, c: Control, details=None, entity="control", entity_id=None):
    audit.log(db, user, action, entity, entity_id or c.id, details or {},
              engagement_id=c.engagement_id, control_id=c.id)


# ------------------------------------------------------------------ control
@router.get("/controls/{cid}")
def get_one(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_control(db, cid, user)
    d = S.control(c, full=True)
    d["engagement"] = {"id": c.engagement.id, "name": c.engagement.name, "client": c.engagement.client,
                       "period_start": c.engagement.period_start.isoformat(),
                       "period_end": c.engagement.period_end.isoformat(), "status": c.engagement.status}
    d["test_type"] = determine_test_type(c.nature, c.frequency)
    d["signoffs"] = [S.signoff(s) for s in db.query(SignOff).filter_by(control_id=cid).order_by(SignOff.id)]
    d["ai_provider"] = provider_name()
    return d


class ControlPatch(BaseModel):
    row_version: int
    title: str | None = None
    description: str | None = None
    objective: str | None = None
    risk: str | None = None
    frequency: str | None = None
    nature: str | None = None
    risk_rating: str | None = None
    key_control: bool | None = None
    system_id: int | None = None
    attributes: list[dict] | None = None
    design_procedures: list[str] | None = None
    operating_procedures: list[str] | None = None
    preparer_id: int | None = None
    reviewer_id: int | None = None


DESIGN_FIELDS = {"title", "description", "objective", "risk", "frequency", "nature", "attributes",
                 "design_procedures", "system_id"}


@router.patch("/controls/{cid}")
def patch(cid: int, body: ControlPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_control(db, cid, user, write=True)
    if body.row_version != c.row_version:
        raise HTTPException(409, "This control was changed by someone else. Reload and try again.")
    ch = body.model_dump(exclude_unset=True, exclude={"row_version"})
    if "frequency" in ch and ch["frequency"] not in FREQUENCIES:
        raise HTTPException(422, "Unknown frequency")
    if "attributes" in ch:
        for i, a in enumerate(ch["attributes"]):
            if not str(a.get("text", "")).strip():
                raise HTTPException(422, "Attribute text cannot be empty")
            a["id"] = a.get("id") or f"A{i+1}"
        ids = [a["id"] for a in ch["attributes"]]
        if len(set(ids)) != len(ids):
            raise HTTPException(422, "Attribute ids must be unique")
    if "system_id" in ch and ch["system_id"] is not None and ch["system_id"] not in {s.id for s in c.engagement.systems}:
        raise HTTPException(422, "System is not in this engagement")
    before = {k: getattr(c, k) for k in ch}
    for k, v in ch.items():
        setattr(c, k, v)
    c.row_version += 1
    if DESIGN_FIELDS & set(ch):
        workflow.invalidate(db, c, "design", user, "Control definition changed")
    _log(db, user, "control.updated", c, {"before": before, "after": ch})
    db.commit()
    return get_one(cid, db, user)


@router.delete("/controls/{cid}")
def delete(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_control(db, cid, user, write=True)
    if ROLE_RANK[user.role] < ROLE_RANK["manager"]:
        raise HTTPException(403, "Only managers can delete controls")
    if c.status != "not_started":
        raise HTTPException(409, "Only controls not yet started can be deleted")
    _log(db, user, "control.deleted", c, {"ref": c.ref})
    db.delete(c)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- evidence
@router.get("/controls/{cid}/evidence")
def list_evidence(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_control(db, cid, user)
    return [S.evidence(e) for e in db.query(Evidence).filter_by(control_id=cid, deleted=False).order_by(Evidence.id)]


def _safe_name(name: str) -> str:
    name = os.path.basename(name or "file")
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:200] or "file"


@router.post("/controls/{cid}/evidence", status_code=201)
async def upload(cid: int, file: UploadFile = File(...), purpose: str = Form("general"),
                 description: str = Form(""), db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    c = get_control(db, cid, user, write=True)
    if purpose not in ("design", "operating", "population", "general"):
        raise HTTPException(422, "purpose must be design, operating, population or general")
    fname = _safe_name(file.filename)
    ext = Path(fname).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"File type {ext or '(none)'} is not allowed")
    raw = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB")
    if not raw:
        raise HTTPException(422, "File is empty")
    sha = hashlib.sha256(raw).hexdigest()
    if db.query(Evidence).filter_by(control_id=cid, sha256=sha, deleted=False).first():
        raise HTTPException(409, "This exact file is already attached to this control")
    folder = Path(settings.storage_dir) / str(c.engagement_id) / str(cid)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha[:16]}_{fname}"
    path.write_bytes(raw)
    text, note = extract(raw, fname)
    e = Evidence(control_id=cid, filename=fname, content_type=file.content_type or "application/octet-stream",
                 size=len(raw), sha256=sha, storage_path=str(path), purpose=purpose,
                 description=description, extracted_text=text, extraction_note=note, uploaded_by=user.id)
    db.add(e)
    db.flush()
    workflow.invalidate(db, c, "design" if purpose in ("design", "general") else "operating", user,
                        f"Evidence E{e.id} added")
    _log(db, user, "evidence.uploaded", c, {"file": fname, "sha256": sha, "size": len(raw),
                                            "purpose": purpose}, entity="evidence", entity_id=e.id)
    db.commit()
    return S.evidence(e)


@router.get("/evidence/{evid}/download")
def download(evid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = db.get(Evidence, evid)
    if not e or e.deleted:
        raise HTTPException(404, "Evidence not found")
    c = get_control(db, e.control_id, user)
    p = Path(e.storage_path)
    if not p.exists():
        raise HTTPException(410, "Stored file is missing")
    if hashlib.sha256(p.read_bytes()).hexdigest() != e.sha256:
        _log(db, user, "evidence.integrity_failed", c, {"evidence": e.id}, entity="evidence", entity_id=e.id)
        db.commit()
        raise HTTPException(409, "File integrity check failed: stored file does not match its hash")
    _log(db, user, "evidence.downloaded", c, {"file": e.filename}, entity="evidence", entity_id=e.id)
    db.commit()
    return FileResponse(p, filename=e.filename, media_type=e.content_type)


@router.get("/evidence/{evid}/text")
def evidence_text(evid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = db.get(Evidence, evid)
    if not e or e.deleted:
        raise HTTPException(404, "Evidence not found")
    get_control(db, e.control_id, user)
    return {"id": e.id, "filename": e.filename, "text": e.extracted_text, "note": e.extraction_note}


@router.delete("/evidence/{evid}")
def delete_evidence(evid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = db.get(Evidence, evid)
    if not e or e.deleted:
        raise HTTPException(404, "Evidence not found")
    c = get_control(db, e.control_id, user, write=True)
    e.deleted = True  # record and file are kept for the audit trail
    workflow.invalidate(db, c, "design" if e.purpose in ("design", "general") else "operating", user,
                        f"Evidence E{e.id} removed")
    _log(db, user, "evidence.removed", c, {"file": e.filename, "sha256": e.sha256},
         entity="evidence", entity_id=e.id)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- sampling
@router.get("/controls/{cid}/sampling")
def sampling_info(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_control(db, cid, user)
    tt = determine_test_type(c.nature, c.frequency)
    size, basis = sample_size(c.frequency, c.risk_rating, None)
    s = db.query(Sample).filter_by(control_id=cid, active=True).order_by(Sample.id.desc()).first()
    return {"test_type": tt, "suggested_size": size, "basis": basis, "sample": S.sample(s) if s else None}


class SampleIn(BaseModel):
    population_evidence_id: int | None = None
    seed: int | None = None
    override_size: int | None = None
    override_reason: str = ""


@router.post("/controls/{cid}/sampling", status_code=201)
def make_sample(cid: int, body: SampleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_control(db, cid, user, write=True)
    tt = determine_test_type(c.nature, c.frequency)
    seed = body.seed if body.seed is not None else random.SystemRandom().randint(1, 2**31 - 1)
    if tt["method"] == "test_of_one" and body.population_evidence_id is None:
        rows = [{"instance": "Current system configuration"}]
        size, rationale, method = 1, tt["reason"], "test_of_one"
    else:
        if body.population_evidence_id is None:
            raise HTTPException(422, "Choose the population file (upload it as evidence with purpose 'population')")
        ev = db.get(Evidence, body.population_evidence_id)
        if not ev or ev.control_id != cid or ev.deleted:
            raise HTTPException(404, "Population file not found on this control")
        rows = parse_population(Path(ev.storage_path).read_bytes(), ev.filename)
        if not rows:
            raise HTTPException(422, "Population file has no rows (needs a header row and data)")
        size, rationale = sample_size(c.frequency, c.risk_rating, len(rows))
        method = "all_items" if size >= len(rows) else "random"
        if tt["method"] == "test_of_one":
            size, method, rationale = 1, "test_of_one", tt["reason"]
    if body.override_size is not None:
        if body.override_size < 1 or body.override_size > len(rows):
            raise HTTPException(422, f"Sample size must be between 1 and {len(rows)}")
        if body.override_size < size and len(body.override_reason.strip()) < 10:
            raise HTTPException(422, "Explain why the sample is smaller than the methodology size")
        if ROLE_RANK[user.role] < ROLE_RANK["reviewer"] and body.override_size < size:
            raise HTTPException(403, "Reducing sample size below methodology needs reviewer role or higher")
        rationale += f"; overridden to {body.override_size} by {user.email}: {body.override_reason}"
        size = body.override_size
        method = "random" if size < len(rows) else "all_items"
    db.query(Sample).filter_by(control_id=cid, active=True).update({"active": False})
    items = select(rows, size, seed)
    s = Sample(control_id=cid, population_evidence_id=body.population_evidence_id,
               population_size=len(rows), sample_size=len(items), method=method, seed=seed,
               rationale=rationale, items=items, created_by=user.id)
    db.add(s)
    db.flush()
    workflow.invalidate(db, c, "operating", user, "New sample selected")
    _log(db, user, "sample.created", c, {"population": len(rows), "size": len(items), "seed": seed,
                                         "method": method}, entity="sample", entity_id=s.id)
    db.commit()
    return S.sample(s)


# ------------------------------------------------------------------- agents
class RunIn(BaseModel):
    agent: str


@router.post("/controls/{cid}/runs", status_code=202)
def start_run(cid: int, body: RunIn, bg: BackgroundTasks, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    c = get_control(db, cid, user, write=True)
    if body.agent not in AGENTS:
        raise HTTPException(422, "agent must be design, operating or reviewer")
    busy = db.query(AgentRun).filter(AgentRun.control_id == cid, AgentRun.agent == body.agent,
                                     AgentRun.status.in_(("queued", "running"))).first()
    if busy:
        raise HTTPException(409, f"A {body.agent} run is already in progress (#{busy.id})")
    fn, version = AGENTS[body.agent]
    ev = db.query(Evidence).filter_by(control_id=cid, deleted=False).order_by(Evidence.id).all()
    h = input_hash(version, S.control(c, full=True), [e.sha256 for e in ev])
    run = AgentRun(control_id=cid, agent=body.agent, prompt_version=version, input_hash=h,
                   created_by=user.id, provider=provider_name())
    db.add(run)
    if body.agent in ("design", "operating"):
        workflow.mark_in_progress(db, c, body.agent, user)
    db.flush()
    _log(db, user, f"agent.{body.agent}.started", c, {"run": run.id, "prompt_version": version},
         entity="agent_run", entity_id=run.id)
    db.commit()
    bg.add_task(execute, run.id, fn)
    return S.run(run)


@router.get("/controls/{cid}/runs")
def list_runs(cid: int, agent: str | None = None, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    get_control(db, cid, user)
    q = db.query(AgentRun).filter_by(control_id=cid)
    if agent:
        q = q.filter_by(agent=agent)
    return [S.run(r, full=False) for r in q.order_by(AgentRun.id.desc()).limit(50)]


@router.get("/runs/{rid}")
def get_run(rid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    r = db.get(AgentRun, rid)
    if not r:
        raise HTTPException(404, "Run not found")
    get_control(db, r.control_id, user)
    return S.run(r)


# -------------------------------------------------------------- conclusions
class ConclusionIn(BaseModel):
    stage: str
    run_id: int | None = None
    conclusion: dict
    rationale: str = ""


@router.post("/controls/{cid}/conclusion")
def confirm_conclusion(cid: int, body: ConclusionIn, db: Session = Depends(get_db),
                       user: User = Depends(current_user)):
    """The human decision. If it differs from what the agent proposed, a reason is required."""
    c = get_control(db, cid, user, write=True)
    if body.stage not in ("design", "operating"):
        raise HTTPException(422, "stage must be design or operating")
    proposed = None
    if body.run_id:
        r = db.get(AgentRun, body.run_id)
        if not r or r.control_id != cid or r.agent != body.stage or r.status != "succeeded":
            raise HTTPException(422, "Run does not match this control and stage")
        proposed = (r.result or {}).get("proposed_conclusion")
    keys = ("design", "implementation") if body.stage == "design" else ("operating",)
    for k in keys:
        if k not in body.conclusion:
            raise HTTPException(422, f"conclusion.{k} is required")
    overridden = bool(proposed) and any(proposed.get(k) != body.conclusion.get(k) for k in keys)
    if overridden and len(body.rationale.strip()) < 15:
        raise HTTPException(422, "You changed the agent's proposed conclusion; explain why (15+ characters)")
    value = {**{k: body.conclusion[k] for k in keys}, "rationale": body.rationale, "run_id": body.run_id,
             "overrode_agent": overridden, "confirmed_by": user.email}
    if body.stage == "design":
        c.design_conclusion = value
    else:
        c.operating_conclusion = value
    c.row_version += 1
    workflow.mark_in_progress(db, c, body.stage, user)
    workflow.invalidate(db, c, body.stage, user, "Conclusion changed")
    _log(db, user, f"conclusion.{body.stage}.confirmed", c, {"value": value, "agent_proposed": proposed})
    db.commit()
    return get_one(cid, db, user)


# ----------------------------------------------------------------- signoffs
class SignIn(BaseModel):
    stage: str
    kind: str
    comment: str = ""


@router.post("/controls/{cid}/signoffs", status_code=201)
def sign(cid: int, body: SignIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_control(db, cid, user, write=True)
    if body.stage not in ("design", "operating"):
        raise HTTPException(422, "stage must be design or operating")
    workflow.sign(db, c, body.stage, body.kind, user, body.comment)
    db.commit()
    return get_one(cid, db, user)


# ------------------------------------------------------------- review notes
@router.get("/controls/{cid}/notes")
def notes(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_control(db, cid, user)
    return [S.note(n) for n in db.query(ReviewNote).filter_by(control_id=cid).order_by(ReviewNote.id.desc())]


class NoteIn(BaseModel):
    stage: str
    severity: str = "medium"
    text: str


@router.post("/controls/{cid}/notes", status_code=201)
def add_note(cid: int, body: NoteIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_control(db, cid, user, write=True)
    if body.stage not in ("design", "operating") or body.severity not in ("low", "medium", "high"):
        raise HTTPException(422, "Invalid stage or severity")
    n = ReviewNote(control_id=cid, stage=body.stage, severity=body.severity, text=body.text.strip(),
                   created_by=user.id)
    db.add(n)
    db.flush()
    _log(db, user, "note.created", c, {"text": n.text[:200], "stage": n.stage}, entity="note", entity_id=n.id)
    db.commit()
    return S.note(n)


class NotePatch(BaseModel):
    status: str | None = None  # addressed | closed | open
    response: str | None = None


@router.patch("/notes/{nid}")
def patch_note(nid: int, body: NotePatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.get(ReviewNote, nid)
    if not n:
        raise HTTPException(404, "Note not found")
    c = get_control(db, n.control_id, user, write=True)
    if body.response is not None:
        n.response = body.response
    if body.status:
        if body.status not in ("open", "addressed", "closed"):
            raise HTTPException(422, "Invalid status")
        if body.status == "closed":
            if ROLE_RANK[user.role] < ROLE_RANK["reviewer"]:
                raise HTTPException(403, "Only reviewers can close review notes")
            n.closed_by = user.id
        n.status = body.status
    _log(db, user, "note.updated", c, body.model_dump(exclude_none=True), entity="note", entity_id=n.id)
    db.commit()
    return S.note(n)


# --------------------------------------------------------------- exceptions
@router.get("/controls/{cid}/exceptions")
def exceptions(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_control(db, cid, user)
    return [S.exception(x) for x in db.query(Exception_).filter_by(control_id=cid).order_by(Exception_.id)]


class ExceptionPatch(BaseModel):
    status: str | None = None
    severity: str | None = None
    description: str | None = None


@router.patch("/exceptions/{xid}")
def patch_exception(xid: int, body: ExceptionPatch, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    x = db.get(Exception_, xid)
    if not x:
        raise HTTPException(404, "Exception not found")
    c = get_control(db, x.control_id, user, write=True)
    ch = body.model_dump(exclude_none=True)
    if ch.get("status") and ch["status"] not in ("open", "accepted", "remediated"):
        raise HTTPException(422, "Invalid status")
    if ch.get("severity") and ch["severity"] not in ("deficiency", "significant", "material"):
        raise HTTPException(422, "Invalid severity")
    for k, v in ch.items():
        setattr(x, k, v)
    workflow.invalidate(db, c, "operating", user, f"Exception {x.id} changed")
    _log(db, user, "exception.updated", c, ch, entity="exception", entity_id=x.id)
    db.commit()
    return S.exception(x)


# ----------------------------------------------------------------- activity
@router.get("/controls/{cid}/activity")
def activity(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_control(db, cid, user)
    rows = db.query(AuditLog).filter_by(control_id=cid).order_by(AuditLog.id.desc()).limit(300)
    return [S.audit_row(a) for a in rows]
