"""
backend/auth.py — Google Sign-In verification, session management, and the
admins.conf allowlist for VidLife.

Sessions are in-memory only (same pattern as tasks.py's _active_runs) — the
simplest option for a single local/small-scale backend process. Sessions are
lost on restart; users just sign in again, which is an acceptable tradeoff
for how this app runs today.

See docs/authentication.md for the full design/rationale.
"""

import secrets
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent.parent
ADMINS_FILE = BASE_DIR / "admins.conf"

SESSION_COOKIE_NAME = "vidlife_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days


# ─────────────────────────────────────────────────────────────
# admins.conf
# ─────────────────────────────────────────────────────────────

def _parse_admins() -> set[str]:
    if not ADMINS_FILE.exists():
        return set()
    admins: set[str] = set()
    for line in ADMINS_FILE.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            admins.add(line.lower())
    return admins


def is_admin(email: str) -> bool:
    return email.lower() in _parse_admins()


def user_id_from_email(email: str) -> str:
    """Everything before '@', used as-is — no further normalization."""
    return email.split("@", 1)[0]


# ─────────────────────────────────────────────────────────────
# Sessions (in-memory)
# ─────────────────────────────────────────────────────────────

_sessions: dict[str, dict] = {}
_sessions_lock = threading.Lock()


def create_session(email: str) -> str:
    session_id = secrets.token_urlsafe(32)
    with _sessions_lock:
        _sessions[session_id] = {"email": email, "user_id": user_id_from_email(email)}
    return session_id


def destroy_session(session_id: Optional[str]) -> None:
    if not session_id:
        return
    with _sessions_lock:
        _sessions.pop(session_id, None)


def _get_session(session_id: Optional[str]) -> Optional[dict]:
    if not session_id:
        return None
    with _sessions_lock:
        return _sessions.get(session_id)


# ─────────────────────────────────────────────────────────────
# Current-user dependency
# ─────────────────────────────────────────────────────────────

class CurrentUser(BaseModel):
    email: str
    user_id: str
    is_admin: bool


def _current_user_from_email(email: str) -> CurrentUser:
    return CurrentUser(email=email, user_id=user_id_from_email(email), is_admin=is_admin(email))


def get_current_user(vidlife_session: Optional[str] = Cookie(default=None)) -> CurrentUser:
    session = _get_session(vidlife_session)
    if not session:
        raise HTTPException(status_code=401, detail="Not signed in")
    return _current_user_from_email(session["email"])


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def resolve_owner(current_user: CurrentUser, owner_param: Optional[str]) -> str:
    """Admins may act on behalf of another user via the `owner` query param;
    everyone else is always scoped to their own workspace regardless of what
    they pass — `owner_param` is never trusted as an override for non-admins."""
    if current_user.is_admin and owner_param:
        return owner_param
    return current_user.user_id


# ─────────────────────────────────────────────────────────────
# Google ID token verification
# ─────────────────────────────────────────────────────────────

def _google_client_id() -> str:
    # Lazy import to avoid a circular import with settings.py (which depends
    # on this module for its own admin gate) — mirrors tasks.py's _cfg().
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import settings as _settings
    return _settings.load().get("GOOGLE_CLIENT_ID", "")


def verify_google_id_token(credential: str) -> dict:
    """Verify a Google ID token's signature, audience, and issuer. Raises on
    any failure (bad signature, wrong/missing audience, expired, ...)."""
    client_id = _google_client_id()
    if not client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID is not configured")
    try:
        return google_id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Google credential: {exc}")


# ─────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────

router = APIRouter(tags=["auth"])


class GoogleSignInRequest(BaseModel):
    credential: str


@router.post("/auth/google")
def google_sign_in(body: GoogleSignInRequest, response: Response) -> CurrentUser:
    claims = verify_google_id_token(body.credential)

    if not claims.get("email_verified"):
        raise HTTPException(status_code=403, detail="Google account email is not verified")

    email = claims.get("email", "")
    if not email.lower().endswith("@gmail.com"):
        raise HTTPException(status_code=403, detail="Only @gmail.com accounts are supported")

    session_id = create_session(email)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        samesite="lax",
        secure=False,  # dev over plain http://localhost; set True behind https in prod
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
    )
    return _current_user_from_email(email)


@router.get("/auth/me")
def auth_me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return current_user


@router.post("/auth/logout")
def auth_logout(response: Response, vidlife_session: Optional[str] = Cookie(default=None)) -> dict:
    destroy_session(vidlife_session)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"message": "Signed out"}
