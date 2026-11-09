from datetime import timezone
import hmac
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_token, csrf_for
from app.models import CredentialSession, User, utcnow

def get_db():
    with SessionLocal() as session:
        yield session

def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def check_origin(request):
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_origins:
        raise HTTPException(403, "Origin is not allowed")

def get_current_user(request: Request, db=Depends(get_db)) -> User:
    authorization = request.headers.get("authorization", "")
    bearer = authorization.startswith("Bearer ")
    token = authorization[7:] if bearer else request.cookies.get("health_session", "")
    session = db.scalar(select(CredentialSession).where(CredentialSession.token_hash == hash_token(token))) if token else None
    if not session or aware(session.expires_at) <= utcnow():
        raise HTTPException(401, "Session expired or invalid")
    if not bearer and request.method not in ("GET", "HEAD", "OPTIONS"):
        check_origin(request)
        if not request.headers.get("origin") or not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_for(token)):
            raise HTTPException(403, "CSRF verification failed")
    request.state.auth_session = session
    request.state.auth_token = token
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "Session expired or invalid")
    return user

def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator role required")
    return user
