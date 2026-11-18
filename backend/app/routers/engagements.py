import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from .. import audit, serializers as S
from ..db import get_db
from ..library import LIBRARY, LIBRARY_BY_REF, DOMAINS, FREQUENCIES
from ..models import (Evidence, EvidenceRequest, SignOff, Engagement, EngagementMember, System, Control, User, Exception_, ReviewNote,
                      STATUSES)
from ..security import current_user, require_role, check_engagement_access

router = APIRouter(tags=["engagements"])


def get_engagement(db, eid, user, write=False) -> Engagement:
    e = db.get(Engagement, eid)
    if not e:
        raise HTTPException(404, "Engagement not found")
    check_engagement_access(db, user, e, write)
    return e


@router.get("/library")
def library(_: User = Depends(current_user)):
    return {"domains": DOMAINS, "frequencies": FREQUENCIES, "controls": LIBRARY}


def _stats(db, e: Engagement):
    controls = db.query(Control).filter_by(engagement_id=e.id).all()
    by_status = {s: 0 for s in STATUSES}
    by_domain = {d: 0 for d in DOMAINS}
    for c in controls:
        by_status[c.status] = by_status.get(c.status, 0) + 1
        by_domain[c.domain] = by_domain.get(c.domain, 0) + 1
    ids = [c.id for c in controls] or [-1]
    reqs = {"open": 0, "received": 0, "closed": 0}
    for (st,) in db.query(EvidenceRequest.status).filter(EvidenceRequest.control_id.in_(ids)):
        reqs[st] = reqs.get(st, 0) + 1
    lead = db.get(User, e.created_by)
    return {
        "requests": reqs, "lead": lead.name if lead else "",
        "controls": len(controls), "by_status": by_status, "by_domain": by_domain,
        "complete": by_status.get("operating_reviewed", 0),
        "open_exceptions": db.query(Exception_).filter(Exception_.control_id.in_(ids),
                                                       Exception_.status == "open").count(),
        "open_notes": db.query(ReviewNote).filter(ReviewNote.control_id.in_(ids),
                                                  ReviewNote.status != "closed").count(),
        "deficient": sum(1 for c in controls if (c.operating_conclusion or {}).get("operating") == "not_operating_effectively"
                         or (c.design_conclusion or {}).get("design") == "not_effective"),
    }


@router.get("/engagements")
def list_engagements(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Engagement)
    if user.role not in ("admin", "manager"):
        q = q.join(EngagementMember).filter(EngagementMember.user_id == user.id)
    return [S.engagement(e, _stats(db, e)) for e in q.order_by(Engagement.created_at.desc())]


class EngagementIn(BaseModel):
    name: str
    client: str
    engagement_type: str = "SOX ITGC"
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def _period(self):
        if self.period_end < self.period_start:
            raise ValueError("Period end must be after period start")
        return self


@router.post("/engagements", status_code=201)
def create_engagement(body: EngagementIn, db: Session = Depends(get_db),
                      user: User = Depends(require_role("manager"))):
    e = Engagement(**body.model_dump(), created_by=user.id)
    db.add(e)
    db.flush()
    db.add(EngagementMember(engagement_id=e.id, user_id=user.id))
    audit.log(db, user, "engagement.created", "engagement", e.id, body.model_dump(), engagement_id=e.id)
    db.commit()
    return S.engagement(e, _stats(db, e))


@router.get("/engagements/{eid}")
def get_one(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = get_engagement(db, eid, user)
    d = S.engagement(e, _stats(db, e))
    d["systems"] = [S.system(s) for s in e.systems]
    d["members"] = [S.user(m.user) for m in e.members]
    return d


class EngagementPatch(BaseModel):
    name: str | None = None
    status: str | None = None  # active | locked | archived


@router.patch("/engagements/{eid}")
def patch_engagement(eid: int, body: EngagementPatch, db: Session = Depends(get_db),
                     user: User = Depends(require_role("manager"))):
    e = get_engagement(db, eid, user)
    ch = body.model_dump(exclude_none=True)
    if "status" in ch and ch["status"] not in ("active", "locked", "archived"):
        raise HTTPException(422, "Invalid status")
    for k, v in ch.items():
        setattr(e, k, v)
    audit.log(db, user, "engagement.updated", "engagement", e.id, ch, engagement_id=e.id)
    db.commit()
    return S.engagement(e, _stats(db, e))


class MemberIn(BaseModel):
    user_id: int


@router.post("/engagements/{eid}/members", status_code=201)
def add_member(eid: int, body: MemberIn, db: Session = Depends(get_db),
               user: User = Depends(require_role("manager"))):
    e = get_engagement(db, eid, user, write=True)
    u = db.get(User, body.user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if not db.query(EngagementMember).filter_by(engagement_id=eid, user_id=u.id).first():
        db.add(EngagementMember(engagement_id=eid, user_id=u.id))
        audit.log(db, user, "engagement.member_added", "engagement", eid, {"user": u.email}, engagement_id=eid)
        db.commit()
    return [S.user(m.user) for m in e.members]


@router.delete("/engagements/{eid}/members/{uid}")
def remove_member(eid: int, uid: int, db: Session = Depends(get_db),
                  user: User = Depends(require_role("manager"))):
    get_engagement(db, eid, user, write=True)
    db.query(EngagementMember).filter_by(engagement_id=eid, user_id=uid).delete()
    audit.log(db, user, "engagement.member_removed", "engagement", eid, {"user_id": uid}, engagement_id=eid)
    db.commit()
    return {"ok": True}


class SystemIn(BaseModel):
    name: str
    layer: str = "Application"
    description: str = ""


@router.post("/engagements/{eid}/systems", status_code=201)
def add_system(eid: int, body: SystemIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_engagement(db, eid, user, write=True)
    s = System(engagement_id=eid, **body.model_dump())
    db.add(s)
    db.flush()
    audit.log(db, user, "system.created", "system", s.id, body.model_dump(), engagement_id=eid)
    db.commit()
    return S.system(s)


@router.delete("/engagements/{eid}/systems/{sid}")
def delete_system(eid: int, sid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_engagement(db, eid, user, write=True)
    s = db.get(System, sid)
    if not s or s.engagement_id != eid:
        raise HTTPException(404, "System not found")
    if db.query(Control).filter_by(system_id=sid).count():
        raise HTTPException(409, "System has controls linked to it; move or delete them first")
    db.delete(s)
    audit.log(db, user, "system.deleted", "system", sid, {"name": s.name}, engagement_id=eid)
    db.commit()
    return {"ok": True}


class AddFromLibrary(BaseModel):
    refs: list[str]
    system_ids: list[int | None] = [None]
    risk_rating: str = "Moderate"


@router.post("/engagements/{eid}/controls/from-library", status_code=201)
def add_from_library(eid: int, body: AddFromLibrary, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    e = get_engagement(db, eid, user, write=True)
    valid_sys = {s.id: s for s in e.systems}
    created = []
    for sid in body.system_ids or [None]:
        if sid is not None and sid not in valid_sys:
            raise HTTPException(422, f"System {sid} is not in this engagement")
        for ref in body.refs:
            t = LIBRARY_BY_REF.get(ref)
            if not t:
                raise HTTPException(422, f"Unknown library control {ref}")
            suffix = f"-{valid_sys[sid].name.split()[0].upper()[:8]}" if sid else ""
            c = Control(engagement_id=eid, system_id=sid, library_ref=ref, ref=ref + suffix,
                        domain=t["domain"], title=t["title"], description=t["description"],
                        objective=t["objective"], risk=t["risk"], frequency=t["frequency"],
                        nature=t["nature"], risk_rating=body.risk_rating,
                        attributes=t["attributes"], design_procedures=t["design_procedures"],
                        operating_procedures=t["operating_procedures"], expected_evidence=t["expected_evidence"])
            db.add(c)
            db.flush()
            created.append(c)
    audit.log(db, user, "control.added_from_library", "engagement", eid,
              {"refs": body.refs, "systems": body.system_ids, "count": len(created)}, engagement_id=eid)
    db.commit()
    return [S.control(c) for c in created]


class ControlIn(BaseModel):
    ref: str
    domain: str
    title: str
    description: str
    objective: str = ""
    risk: str = ""
    frequency: str
    nature: str
    risk_rating: str = "Moderate"
    system_id: int | None = None
    attributes: list[str] = []


@router.post("/engagements/{eid}/controls", status_code=201)
def create_control(eid: int, body: ControlIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_engagement(db, eid, user, write=True)
    if body.domain not in DOMAINS:
        raise HTTPException(422, "Unknown domain")
    if body.frequency not in FREQUENCIES:
        raise HTTPException(422, "Unknown frequency")
    data = body.model_dump()
    attrs = [{"id": f"A{i+1}", "text": t} for i, t in enumerate(data.pop("attributes"))]
    c = Control(engagement_id=eid, attributes=attrs, **data)
    db.add(c)
    db.flush()
    audit.log(db, user, "control.created", "control", c.id, {"ref": c.ref}, engagement_id=eid, control_id=c.id)
    db.commit()
    return S.control(c, full=True)


@router.get("/engagements/{eid}/controls")
def list_controls(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_engagement(db, eid, user)
    cs = db.query(Control).filter_by(engagement_id=eid).order_by(Control.domain, Control.ref).all()
    ids = [c.id for c in cs] or [-1]
    extra = {c.id: {"files": 0, "requests": {"open": 0, "received": 0, "closed": 0}, "signed": [],
                    "open_exceptions": 0} for c in cs}
    for (cid,) in db.query(Evidence.control_id).filter(Evidence.control_id.in_(ids), Evidence.deleted.is_(False)):
        extra[cid]["files"] += 1
    for cid, st in db.query(EvidenceRequest.control_id, EvidenceRequest.status).filter(EvidenceRequest.control_id.in_(ids)):
        extra[cid]["requests"][st] = extra[cid]["requests"].get(st, 0) + 1
    for cid, stage, kind in db.query(SignOff.control_id, SignOff.stage, SignOff.kind).filter(
            SignOff.control_id.in_(ids), SignOff.revoked.is_(False)):
        extra[cid]["signed"].append(f"{stage}:{kind}")
    for (cid,) in db.query(Exception_.control_id).filter(Exception_.control_id.in_(ids), Exception_.status == "open"):
        extra[cid]["open_exceptions"] += 1
    return [dict(S.control(c), **extra[c.id]) for c in cs]


@router.get("/engagements/{eid}/export.csv")
def export_csv(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = get_engagement(db, eid, user)
    users = {u.id: u.name for u in db.query(User)}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Ref", "Domain", "Title", "System", "Frequency", "Nature", "Risk", "Status",
                "Design conclusion", "Implementation", "Operating conclusion", "Open exceptions",
                "Preparer", "Reviewer"])
    for c in db.query(Control).filter_by(engagement_id=eid).order_by(Control.ref):
        w.writerow([c.ref, c.domain, c.title, c.system.name if c.system else "", c.frequency, c.nature,
                    c.risk_rating, c.status, (c.design_conclusion or {}).get("design", ""),
                    (c.design_conclusion or {}).get("implementation", ""),
                    (c.operating_conclusion or {}).get("operating", ""),
                    db.query(Exception_).filter_by(control_id=c.id, status="open").count(),
                    users.get(c.preparer_id, ""), users.get(c.reviewer_id, "")])
    audit.log(db, user, "engagement.exported", "engagement", eid, {"format": "csv"}, engagement_id=eid)
    db.commit()
    buf.seek(0)
    fname = f"{e.client}_{e.name}_controls.csv".replace(" ", "_")
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/me/work")
def my_work(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """What needs this user's attention, across the engagements they can open."""
    from ..security import ROLE_RANK
    q = db.query(Control).join(Engagement, Engagement.id == Control.engagement_id).filter(Engagement.status == "active")
    if user.role not in ("admin", "manager"):
        q = q.join(EngagementMember, EngagementMember.engagement_id == Engagement.id).filter(
            EngagementMember.user_id == user.id)
    controls = q.order_by(Control.engagement_id, Control.ref).all()
    by_id = {c.id: c for c in controls}
    ids = list(by_id) or [-1]

    def item(c, **extra):
        return dict(id=c.id, ref=c.ref, title=c.title, status=c.status, engagement_id=c.engagement_id,
                    engagement=f"{c.engagement.client}: {c.engagement.name}", **extra)

    prepared_by_me = {(s.control_id, s.stage) for s in db.query(SignOff).filter(
        SignOff.control_id.in_(ids), SignOff.revoked.is_(False), SignOff.kind == "prepare", SignOff.user_id == user.id)}
    to_prepare = [item(c) for c in controls if c.preparer_id == user.id and c.status in
                  ("not_started", "design_in_progress", "design_reviewed", "operating_in_progress")]
    waiting = [item(c) for c in controls if c.preparer_id == user.id and c.status in ("design_prepared", "operating_prepared")]
    to_review = []
    if ROLE_RANK[user.role] >= ROLE_RANK["reviewer"]:
        for c in controls:
            if c.status in ("design_prepared", "operating_prepared") and c.reviewer_id in (None, user.id) \
                    and (c.id, c.status.split("_")[0]) not in prepared_by_me:
                to_review.append(item(c))
    mine = {c.id for c in controls if user.id in (c.preparer_id, c.reviewer_id)}
    notes = [item(by_id[n.control_id], note=n.text, severity=n.severity, note_status=n.status)
             for n in db.query(ReviewNote).filter(ReviewNote.control_id.in_(ids), ReviewNote.status != "closed")
             .order_by(ReviewNote.id.desc()) if n.control_id in mine]
    requests = [item(by_id[r.control_id], request=r.title, due_date=r.due_date.isoformat() if r.due_date else None)
                for r in db.query(EvidenceRequest).filter(EvidenceRequest.control_id.in_(ids), EvidenceRequest.status == "open")
                .order_by(EvidenceRequest.due_date.is_(None), EvidenceRequest.due_date, EvidenceRequest.id)
                if by_id[r.control_id].preparer_id == user.id]
    return {"to_prepare": to_prepare[:100], "to_review": to_review[:100], "waiting": waiting[:100],
            "notes": notes[:50], "requests": requests[:50]}
