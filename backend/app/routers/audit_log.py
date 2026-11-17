from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import serializers as S
from ..audit import verify_chain
from ..db import get_db
from ..models import AuditLog, User
from ..security import require_role, current_user
from .engagements import get_engagement

router = APIRouter(tags=["audit"])


@router.get("/audit")
def list_audit(engagement_id: int | None = None, action: str | None = None, limit: int = 200,
               before_id: int | None = None, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    q = db.query(AuditLog)
    if engagement_id:
        get_engagement(db, engagement_id, user)
        q = q.filter_by(engagement_id=engagement_id)
    elif user.role not in ("admin", "manager"):
        return []
    if action:
        q = q.filter(AuditLog.action.like(f"{action}%"))
    if before_id:
        q = q.filter(AuditLog.id < before_id)
    return [S.audit_row(a) for a in q.order_by(AuditLog.id.desc()).limit(min(limit, 1000))]


@router.get("/audit/verify")
def verify(db: Session = Depends(get_db), _: User = Depends(require_role("manager"))):
    return verify_chain(db)
