from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
import re

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from .. import audit, serializers as S
from ..db import get_db
from ..models import User, ROLES
from ..security import (hash_password, verify_password, create_token, current_user, require_role,
                        validate_password_strength)

router = APIRouter(tags=["auth"])
MAX_FAILED = 5
LOCK_MINUTES = 15


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == body.email.lower().strip()).first()
    nowt = datetime.now(timezone.utc)
    if u and u.locked_until:
        lu = u.locked_until if u.locked_until.tzinfo else u.locked_until.replace(tzinfo=timezone.utc)
        if lu > nowt:
            raise HTTPException(423, "Account locked after too many failed attempts. Try again later.")
    if not u or not u.active or not verify_password(body.password, u.password_hash):
        if u:
            u.failed_logins += 1
            if u.failed_logins >= MAX_FAILED:
                u.locked_until = nowt + timedelta(minutes=LOCK_MINUTES)
                u.failed_logins = 0
            audit.log(db, None, "auth.login_failed", "user", u.id, {"email": u.email})
            db.commit()
        raise HTTPException(401, "Wrong email or password")
    u.failed_logins, u.locked_until = 0, None
    audit.log(db, u, "auth.login", "user", u.id)
    db.commit()
    return {"token": create_token(u), "user": S.user(u)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return S.user(user)


class UserIn(BaseModel):
    email: str
    name: str
    role: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v.strip()):
            raise ValueError("Enter a valid email")
        return v.strip()

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        return v


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = None


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [S.user(u) for u in db.query(User).order_by(User.name)]


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), admin: User = Depends(require_role("admin"))):
    validate_password_strength(body.password)
    email = body.email.lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "A user with this email already exists")
    u = User(email=email, name=body.name, role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit.log(db, admin, "user.created", "user", u.id, {"email": email, "role": body.role})
    db.commit()
    return S.user(u)


@router.patch("/users/{uid}")
def update_user(uid: int, body: UserPatch, db: Session = Depends(get_db),
                admin: User = Depends(require_role("admin"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_none=True)
    if "role" in changes and changes["role"] not in ROLES:
        raise HTTPException(422, "Invalid role")
    if u.id == admin.id and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise HTTPException(409, "You cannot deactivate or demote yourself")
    if "password" in changes:
        validate_password_strength(changes["password"])
        u.password_hash = hash_password(changes.pop("password"))
        changes["password"] = "(changed)"
    for k, v in changes.items():
        if k != "password":
            setattr(u, k, v)
    audit.log(db, admin, "user.updated", "user", u.id, changes)
    db.commit()
    return S.user(u)
