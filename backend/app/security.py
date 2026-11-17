from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User, EngagementMember, Engagement

settings = get_settings()
bearer = HTTPBearer(auto_error=False)

ROLE_RANK = {"viewer": 0, "preparer": 1, "reviewer": 2, "manager": 3, "admin": 4}


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def validate_password_strength(pw: str):
    problems = []
    if len(pw) < 10:
        problems.append("at least 10 characters")
    if not any(c.isupper() for c in pw):
        problems.append("an upper-case letter")
    if not any(c.islower() for c in pw):
        problems.append("a lower-case letter")
    if not any(c.isdigit() for c in pw):
        problems.append("a number")
    if problems:
        raise HTTPException(422, "Password needs " + ", ".join(problems))


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        data = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid")
    user = db.get(User, int(data["sub"]))
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not active")
    return user


def require_role(min_role: str):
    def dep(user: User = Depends(current_user)) -> User:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[min_role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {min_role} role or higher")
        return user
    return dep


def check_engagement_access(db: Session, user: User, engagement: Engagement, write: bool = False):
    """Admins and managers see everything; others must be engagement members."""
    if user.role in ("admin", "manager"):
        pass
    else:
        is_member = db.query(EngagementMember).filter_by(
            engagement_id=engagement.id, user_id=user.id).first()
        if not is_member:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not on this engagement")
    if write:
        if user.role == "viewer":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewers cannot make changes")
        if engagement.status != "active":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Engagement is {engagement.status}; changes are blocked")
