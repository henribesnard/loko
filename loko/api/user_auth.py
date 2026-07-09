"""LOKO — User authentication API.

Router prefix: /api/auth
Handles: signup, login, logout, email verification, password reset, me.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from loko.db.accounts import (
    create_account,
    create_email_token,
    create_session,
    create_user,
    get_account,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    mark_token_used,
    revoke_all_sessions,
    revoke_session,
    update_user,
    validate_email_token,
    validate_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per IP)
# ---------------------------------------------------------------------------

_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 900  # 15 min


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if too many login attempts."""
    now = time.time()
    attempts = _LOGIN_ATTEMPTS[ip]
    # Purge old entries
    _LOGIN_ATTEMPTS[ip] = [t for t in attempts if now - t < _LOGIN_WINDOW_SECONDS]
    if len(_LOGIN_ATTEMPTS[ip]) >= _MAX_LOGIN_ATTEMPTS:
        raise HTTPException(429, "Trop de tentatives. Reessayez dans quelques minutes.")


def _record_attempt(ip: str) -> None:
    _LOGIN_ATTEMPTS[ip].append(time.time())


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

_COOKIE_NAME = "loko_session"
_COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=_COOKIE_NAME, path="/")


def _get_session_id(request: Request) -> str | None:
    return request.cookies.get(_COOKIE_NAME)


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

PW_MIN_CHARS = 8


def _validate_password(password: str) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors = []
    if len(password) < PW_MIN_CHARS:
        errors.append(f"Le mot de passe doit contenir au moins {PW_MIN_CHARS} caracteres.")
    if not re.search(r"[A-Z]", password):
        errors.append("Le mot de passe doit contenir au moins une majuscule.")
    if not re.search(r"[0-9]", password):
        errors.append("Le mot de passe doit contenir au moins un chiffre.")
    return errors


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    org_name: str = Field(..., min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: str
    password: str


class ResetRequestModel(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/signup", status_code=201)
async def signup(req: SignupRequest) -> dict[str, Any]:
    """Create a new account and user."""
    email = req.email.strip().lower()

    # Validate email format
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise HTTPException(400, "Adresse email invalide.")

    # Validate password
    pw_errors = _validate_password(req.password)
    if pw_errors:
        raise HTTPException(400, " ".join(pw_errors))

    # Check existing user
    existing = get_user_by_email(email)
    if existing:
        raise HTTPException(409, "Un compte existe deja avec cet email.")

    # Create account + user
    account = create_account(req.org_name.strip())
    user = create_user(account["id"], email, req.password)

    # Create verification token
    token = create_email_token(user["id"], "verify")
    logger.info("Signup: user=%s account=%s verify_token created", user["id"], account["id"])

    # TODO: send verification email (lot 4)
    # For now, log the token for manual verification
    logger.info("Verify token for %s: %s", email, token)

    return {
        "status": "created",
        "user_id": user["id"],
        "account_id": account["id"],
        "email": email,
        "message": "Compte cree. Verifiez votre email.",
    }


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    """Authenticate and create a session."""
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)

    email = req.email.strip().lower()
    user = get_user_by_email(email)

    if not user:
        _record_attempt(ip)
        raise HTTPException(401, "Email ou mot de passe incorrect.")

    from loko.db.accounts import verify_password
    if not verify_password(req.password, user["password_hash"]):
        _record_attempt(ip)
        raise HTTPException(401, "Email ou mot de passe incorrect.")

    # Create session
    session_id = create_session(user["id"])
    _set_session_cookie(response, session_id)

    # Update last_login_at
    update_user(user["id"], last_login_at=datetime.now(timezone.utc).isoformat())

    account = get_account(user["account_id"])

    return {
        "status": "ok",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "email_verified": user.get("email_verified_at") is not None,
        },
        "account": {
            "id": user["account_id"],
            "org_name": account["org_name"] if account else "",
            "plan": account["plan"] if account else "trial",
        },
    }


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """Revoke session and clear cookie."""
    session_id = _get_session_id(request)
    if session_id:
        revoke_session(session_id)
    _clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/me")
async def me(request: Request) -> dict[str, Any]:
    """Return current user info from session cookie."""
    session_id = _get_session_id(request)
    if not session_id:
        raise HTTPException(401, "Non authentifie.")

    session = validate_session(session_id)
    if not session:
        raise HTTPException(401, "Session invalide ou expiree.")

    return {
        "user": {
            "id": session["user_id"],
            "email": session["email"],
            "role": session["role"],
            "email_verified": session.get("email_verified_at") is not None,
        },
        "account": {
            "id": session["account_id"],
            "org_name": session["org_name"],
            "plan": session["plan"],
        },
    }


@router.post("/verify-email")
async def verify_email(token: str) -> dict[str, str]:
    """Verify email address using token."""
    data = validate_email_token(token, "verify")
    if not data:
        raise HTTPException(400, "Lien de verification invalide ou expire.")

    mark_token_used(data["id"])
    update_user(data["user_id"], email_verified_at=datetime.now(timezone.utc).isoformat())

    return {"status": "ok", "message": "Email verifie."}


@router.post("/request-reset")
async def request_reset(req: ResetRequestModel) -> dict[str, str]:
    """Request a password reset. Anti-enumeration: always returns same response."""
    email = req.email.strip().lower()
    user = get_user_by_email(email)

    if user:
        token = create_email_token(user["id"], "reset")
        logger.info("Reset token for %s: %s", email, token)
        # TODO: send reset email (lot 4)

    # Always same response (anti-enumeration)
    return {"status": "ok", "message": "Si un compte existe avec cet email, un lien de reinitialisation a ete envoye."}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest) -> dict[str, str]:
    """Reset password using token."""
    pw_errors = _validate_password(req.password)
    if pw_errors:
        raise HTTPException(400, " ".join(pw_errors))

    data = validate_email_token(req.token, "reset")
    if not data:
        raise HTTPException(400, "Lien de reinitialisation invalide ou expire.")

    mark_token_used(data["id"])
    new_hash = hash_password(req.password)
    update_user(data["user_id"], password_hash=new_hash)
    revoke_all_sessions(data["user_id"])

    return {"status": "ok", "message": "Mot de passe reinitialise. Reconnectez-vous."}


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, request: Request) -> dict[str, str]:
    """Change password (requires active session)."""
    session_id = _get_session_id(request)
    if not session_id:
        raise HTTPException(401, "Non authentifie.")

    session = validate_session(session_id)
    if not session:
        raise HTTPException(401, "Session invalide.")

    user = get_user_by_id(session["user_id"])
    if not user:
        raise HTTPException(401, "Utilisateur introuvable.")

    from loko.db.accounts import verify_password
    if not verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(400, "Mot de passe actuel incorrect.")

    pw_errors = _validate_password(req.new_password)
    if pw_errors:
        raise HTTPException(400, " ".join(pw_errors))

    new_hash = hash_password(req.new_password)
    update_user(user["id"], password_hash=new_hash)

    # Revoke all other sessions
    revoke_all_sessions(user["id"])

    return {"status": "ok", "message": "Mot de passe modifie."}
