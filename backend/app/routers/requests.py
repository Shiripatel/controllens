"""Evidence request (PBC) list and work paper export."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit, serializers as S
from ..db import get_db
from ..models import AgentRun, Control, Evidence, EvidenceRequest, User
from ..security import current_user
from ..workpaper import render_workpaper
from .controls import get_control
from .engagements import get_engagement

router = APIRouter(tags=["requests"])


def _log(db, user, action, c, rid, details=None):
    audit.log(db, user, action, "request", rid, details or {}, engagement_id=c.engagement_id, control_id=c.id)


@router.get("/controls/{cid}/requests")
def list_requests(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_control(db, cid, user)
    return [S.request(r) for r in db.query(EvidenceRequest).filter_by(control_id=cid).order_by(EvidenceRequest.id)]


class RequestIn(BaseModel):
    title: str
    detail: str = ""
    due_date: date | None = None


@router.post("/controls/{cid}/requests", status_code=201)
def create_request(cid: int, body: RequestIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_control(db, cid, user, write=True)
    if not body.title.strip():
        raise HTTPException(422, "Title is required")
    r = EvidenceRequest(control_id=cid, title=body.title.strip()[:255], detail=body.detail,
                        due_date=body.due_date, created_by=user.id)
    db.add(r)
    db.flush()
    _log(db, user, "request.created", c, r.id, {"title": r.title})
    db.commit()
    return S.request(r)


@router.post("/controls/{cid}/requests/draft", status_code=201)
def draft_requests(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Draft the request list. Uses the Design agent's 'evidence to request' items if it has
    run; otherwise the standard evidence list for the control. Skips items already on the list."""
    c = get_control(db, cid, user, write=True)
    run = (db.query(AgentRun).filter_by(control_id=cid, agent="design", status="succeeded")
           .order_by(AgentRun.id.desc()).first())
    from_agent = ((run.result or {}).get("evaluation") or {}).get("evidence_requests") if run else None
    items = [(t, f"Raised by the Design Effectiveness agent in run #{run.id}.") for t in (from_agent or [])]
    if not items:
        sysname = f" for {c.system.name}" if c.system else ""
        period = f"{c.engagement.period_start} to {c.engagement.period_end}"
        items = [(f"{t}{sysname}", f"Standard request for {c.ref}. Period: {period}. "
                  "Please provide system-generated files where possible, showing the run date.")
                 for t in c.expected_evidence]
    existing = {r.title.lower() for r in db.query(EvidenceRequest).filter_by(control_id=cid)}
    created = []
    for title, detail in items:
        title = str(title).strip()[:255]
        if not title or title.lower() in existing:
            continue
        r = EvidenceRequest(control_id=cid, title=title, detail=detail, source="agent", created_by=user.id)
        db.add(r)
        existing.add(title.lower())
        created.append(r)
    db.flush()
    _log(db, user, "request.drafted", c, "", {"count": len(created), "from_run": run.id if from_agent else None})
    db.commit()
    return [S.request(r) for r in created]


class RequestPatch(BaseModel):
    title: str | None = None
    detail: str | None = None
    status: str | None = None
    due_date: date | None = None
    evidence_ids: list[int] | None = None


@router.patch("/requests/{rid}")
def patch_request(rid: int, body: RequestPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    r = db.get(EvidenceRequest, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    c = get_control(db, r.control_id, user, write=True)
    ch = body.model_dump(exclude_unset=True)
    if "status" in ch and ch["status"] not in ("open", "received", "closed"):
        raise HTTPException(422, "status must be open, received or closed")
    if "evidence_ids" in ch:
        ok = {e.id for e in db.query(Evidence).filter_by(control_id=c.id, deleted=False)}
        if not set(ch["evidence_ids"]) <= ok:
            raise HTTPException(422, "Evidence must belong to this control")
    for k, v in ch.items():
        setattr(r, k, v)
    _log(db, user, "request.updated", c, r.id, ch)
    db.commit()
    return S.request(r)


def _engagement_requests(db, eid):
    return (db.query(EvidenceRequest, Control).join(Control, Control.id == EvidenceRequest.control_id)
            .filter(Control.engagement_id == eid).order_by(Control.ref, EvidenceRequest.id).all())


@router.get("/engagements/{eid}/requests")
def engagement_requests(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_engagement(db, eid, user)
    return [dict(S.request(r), control_ref=c.ref, control_title=c.title) for r, c in _engagement_requests(db, eid)]


@router.get("/engagements/{eid}/requests.csv")
def engagement_requests_csv(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = get_engagement(db, eid, user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Control", "Request", "Detail", "Status", "Due", "Files received"])
    for r, c in _engagement_requests(db, eid):
        w.writerow([c.ref, r.title, r.detail, r.status, r.due_date or "", len(r.evidence_ids or [])])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{e.client}_evidence_requests.csv"'.replace(" ", "_")})


@router.get("/controls/{cid}/workpaper.html", response_class=HTMLResponse)
def workpaper(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_control(db, cid, user)
    html = render_workpaper(db, c, user)
    audit.log(db, user, "control.workpaper_exported", "control", c.id, {},
              engagement_id=c.engagement_id, control_id=c.id)
    db.commit()
    return HTMLResponse(html, headers={"Content-Disposition": f'attachment; filename="{c.ref}_workpaper.html"'})
