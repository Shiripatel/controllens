"""Sign-off workflow and segregation of duties."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import audit
from .models import Control, SignOff, ReviewNote, User, STATUSES
from .security import ROLE_RANK


def active_signoffs(db: Session, control_id: int, stage: str | None = None):
    q = db.query(SignOff).filter_by(control_id=control_id, revoked=False)
    if stage:
        q = q.filter_by(stage=stage)
    return q.order_by(SignOff.id).all()


def _set_status(c: Control, status: str):
    c.status = status
    c.row_version += 1


def mark_in_progress(db: Session, c: Control, stage: str, user: User):
    if stage == "dni" and c.status == "not_started":
        _set_status(c, "dni_in_progress")
    elif stage == "toe" and c.status == "dni_reviewed":
        _set_status(c, "toe_in_progress")


def invalidate(db: Session, c: Control, stage: str, user: User, reason: str):
    """Something changed that the sign-offs relied on: revoke them and roll back status."""
    stages = ["dni", "toe"] if stage == "dni" else ["toe"]
    revoked = 0
    for s in active_signoffs(db, c.id):
        if s.stage in stages:
            s.revoked = True
            revoked += 1
    if revoked:
        if stage == "dni" and STATUSES.index(c.status) > STATUSES.index("dni_in_progress"):
            _set_status(c, "dni_in_progress")
        elif stage == "toe" and STATUSES.index(c.status) > STATUSES.index("toe_in_progress"):
            _set_status(c, "toe_in_progress")
        audit.log(db, user, "signoff.revoked", "control", c.id, {"stage": stage, "reason": reason,
                  "count": revoked}, engagement_id=c.engagement_id, control_id=c.id)
    return revoked


def sign(db: Session, c: Control, stage: str, kind: str, user: User, comment: str) -> SignOff:
    if user.role == "viewer":
        raise HTTPException(403, "Viewers cannot sign off")
    conclusion = c.dni_conclusion if stage == "dni" else c.toe_conclusion
    if kind == "prepare":
        need = "dni_in_progress" if stage == "dni" else "toe_in_progress"
        if c.status != need:
            raise HTTPException(409, f"Control must be in '{need}' to prepare {stage.upper()} (now '{c.status}')")
        if not conclusion:
            raise HTTPException(409, f"Confirm the {stage.upper()} conclusion before signing as preparer")
        if c.preparer_id and c.preparer_id != user.id and ROLE_RANK[user.role] < ROLE_RANK["manager"]:
            raise HTTPException(403, "Only the assigned preparer (or a manager) can prepare this control")
        new_status = f"{stage}_prepared"
    elif kind == "review":
        if c.status != f"{stage}_prepared":
            raise HTTPException(409, f"{stage.upper()} must be prepared before review (now '{c.status}')")
        if ROLE_RANK[user.role] < ROLE_RANK["reviewer"]:
            raise HTTPException(403, "Reviewer role or higher is required to review")
        preparers = {s.user_id for s in active_signoffs(db, c.id, stage) if s.kind == "prepare"}
        if user.id in preparers:
            raise HTTPException(403, "Segregation of duties: you prepared this work and cannot review it")
        open_notes = db.query(ReviewNote).filter_by(control_id=c.id, stage=stage).filter(
            ReviewNote.status != "closed").count()
        if open_notes:
            raise HTTPException(409, f"{open_notes} review note(s) for {stage.upper()} are not closed")
        new_status = f"{stage}_reviewed"
    else:
        raise HTTPException(422, "kind must be prepare or review")

    so = SignOff(control_id=c.id, stage=stage, kind=kind, user_id=user.id, comment=comment)
    db.add(so)
    _set_status(c, new_status)
    audit.log(db, user, f"signoff.{kind}", "control", c.id, {"stage": stage, "comment": comment,
              "new_status": new_status}, engagement_id=c.engagement_id, control_id=c.id)
    return so
