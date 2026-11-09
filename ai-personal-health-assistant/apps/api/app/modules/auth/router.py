from datetime import timedelta
from functools import lru_cache
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.core.security import hasher, password_valid, hash_token, csrf_for, fingerprint
from app.models import User, CredentialSession, LoginAttempt, utcnow
from app.schemas import Register, Login
from app.shared.dependencies import get_db, get_current_user, check_origin

router = APIRouter(prefix="/auth", tags=["auth"])


def public_user(user):
    return {"id": user.id, "email": user.email, "role": user.role}


@lru_cache(maxsize=1)
def dummy_hash():
    return hasher.hash(secrets.token_urlsafe(32))


def rate_limit(db, request, email):
    ip = request.client.host if request.client else "unknown"
    # Do not trust forwarded IP headers unless a trusted reverse proxy sanitizes them.
    keys = [(fingerprint("email:" + email), 10), (fingerprint("ip:" + ip), 50)]
    cutoff = utcnow() - timedelta(minutes=15)
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < utcnow() - timedelta(days=1)))
    for key, limit in keys:
        count = db.scalar(select(func.count()).select_from(LoginAttempt).where(
            LoginAttempt.fingerprint == key, LoginAttempt.created_at >= cutoff))
        if count >= limit:
            raise HTTPException(429, "Too many attempts. Try again later", headers={"Retry-After": "900"})
    for key, _ in keys:
        db.add(LoginAttempt(fingerprint=key))
    db.commit()  # Persist attempts even if credentials fail.


@router.post("/register", status_code=201)
def register(body: Register, request: Request, db=Depends(get_db)):
    check_origin(request)
    email = str(body.email).lower()
    rate_limit(db, request, email)
    user = User(email=email, password_hash=hasher.hash(body.password), role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email is already registered")
    return public_user(user)


@router.post("/login")
def login(body: Login, request: Request, response: Response, db=Depends(get_db)):
    check_origin(request)
    email = str(body.email).lower()
    rate_limit(db, request, email)
    user = db.scalar(select(User).where(User.email == email))
    if not password_valid(user.password_hash if user else dummy_hash(), body.password) or not user:
        raise HTTPException(401, "Invalid email or password")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(body.password)
    db.execute(delete(CredentialSession).where(CredentialSession.expires_at <= utcnow()))
    token = secrets.token_urlsafe(32)
    expires = utcnow() + timedelta(hours=settings.session_hours)
    db.add(CredentialSession(user_id=user.id, token_hash=hash_token(token), expires_at=expires))
    db.commit()
    if body.client == "web":
        response.set_cookie("health_session", token, httponly=True, secure=settings.environment != "development",
                            samesite="strict", max_age=settings.session_hours * 3600, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"user": public_user(user), "access_token": token if body.client == "mobile" else None,
            "csrf_token": csrf_for(token) if body.client == "web" else None, "expires_at": expires.isoformat()}


@router.get("/session")
def session(request: Request, user=Depends(get_current_user)):
    return {"user": public_user(user), "csrf_token": csrf_for(request.state.auth_token),
            "expires_at": request.state.auth_session.expires_at.isoformat()}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user=Depends(get_current_user), db=Depends(get_db)):
    db.delete(request.state.auth_session)
    db.commit()
    response.delete_cookie("health_session", path="/", secure=settings.environment != "development", httponly=True, samesite="strict")
