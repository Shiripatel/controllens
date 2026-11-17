"""Tamper-evident audit trail (hash chain)."""
import hashlib
import json
from datetime import timezone

from sqlalchemy.orm import Session

from .models import AuditLog, User, now

GENESIS = "0" * 64


def _ts(dt) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _digest(prev_hash, at, user_id, action, entity, entity_id, details) -> str:
    payload = json.dumps(
        [prev_hash, _ts(at), user_id, action, entity, str(entity_id), details],
        sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def log(db: Session, user: User | None, action: str, entity: str, entity_id="",
        details: dict | None = None, engagement_id: int | None = None,
        control_id: int | None = None) -> AuditLog:
    """Add an audit row to the current transaction. Caller commits."""
    details = json.loads(json.dumps(details or {}, default=str))
    q = db.query(AuditLog).order_by(AuditLog.id.desc())
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update()
    last = q.first()
    prev = last.hash if last else GENESIS
    at = now()
    uid = user.id if user else None
    row = AuditLog(
        at=at, user_id=uid, user_email=user.email if user else "system",
        action=action, entity=entity, entity_id=str(entity_id),
        engagement_id=engagement_id, control_id=control_id, details=details,
        prev_hash=prev, hash=_digest(prev, at, uid, action, entity, entity_id, details))
    db.add(row)
    db.flush()
    return row


def verify_chain(db: Session) -> dict:
    prev = GENESIS
    count = 0
    for row in db.query(AuditLog).order_by(AuditLog.id).yield_per(500):
        expected = _digest(prev, row.at, row.user_id, row.action, row.entity,
                           row.entity_id, row.details)
        if row.prev_hash != prev or row.hash != expected:
            return {"valid": False, "checked": count, "broken_at_id": row.id}
        prev = row.hash
        count += 1
    return {"valid": True, "checked": count, "broken_at_id": None}
