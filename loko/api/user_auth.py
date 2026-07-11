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
from pydantic import BaseModel, Field

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

_AUTH_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_MAX_AUTH_ATTEMPTS = 5
_AUTH_WINDOW_SECONDS = 900  # 15 min

# S5: separate buckets for signup/reset
_SIGNUP_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_MAX_SIGNUP_ATTEMPTS = 3
_SIGNUP_WINDOW_SECONDS = 3600  # 1 hour


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if too many login attempts."""
    now = time.time()
    attempts = _AUTH_ATTEMPTS[ip]
    _AUTH_ATTEMPTS[ip] = [t for t in attempts if now - t < _AUTH_WINDOW_SECONDS]
    if len(_AUTH_ATTEMPTS[ip]) >= _MAX_AUTH_ATTEMPTS:
        raise HTTPException(429, "Trop de tentatives. Reessayez dans quelques minutes.")


def _record_attempt(ip: str) -> None:
    _AUTH_ATTEMPTS[ip].append(time.time())


def _check_signup_rate(ip: str) -> None:
    """S5: Raise 429 if too many signup attempts."""
    now = time.time()
    attempts = _SIGNUP_ATTEMPTS[ip]
    _SIGNUP_ATTEMPTS[ip] = [t for t in attempts if now - t < _SIGNUP_WINDOW_SECONDS]
    if len(_SIGNUP_ATTEMPTS[ip]) >= _MAX_SIGNUP_ATTEMPTS:
        raise HTTPException(429, "Trop de tentatives de creation de compte.")


def _record_signup(ip: str) -> None:
    _SIGNUP_ATTEMPTS[ip].append(time.time())


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

PW_MIN_CHARS = 12  # S3: raised from 8


def _validate_password(password: str) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors = []
    if len(password) < PW_MIN_CHARS:
        errors.append(f"Le mot de passe doit contenir au moins {PW_MIN_CHARS} caracteres.")
    if not re.search(r"[A-Z]", password):
        errors.append("Le mot de passe doit contenir au moins une majuscule.")
    if not re.search(r"[0-9]", password):
        errors.append("Le mot de passe doit contenir au moins un chiffre.")
    if not re.search(r"[^a-zA-Z0-9]", password):
        errors.append("Le mot de passe doit contenir au moins un caractere special.")
    return errors


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

_CURRENT_TERMS_VERSION = "2026-07-09-v1"


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=12)
    org_name: str = Field(..., min_length=1, max_length=100)
    accept_terms: bool = False  # Q4: must be True


class LoginRequest(BaseModel):
    email: str
    password: str


class ResetRequestModel(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=12)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=12)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/signup", status_code=201)
async def signup(req: SignupRequest, request: Request) -> dict[str, Any]:
    """Create a new account and user."""
    # Q4: terms acceptance required
    if not req.accept_terms:
        raise HTTPException(400, "Vous devez accepter les conditions d'utilisation.")

    ip = request.client.host if request.client else "unknown"
    _check_signup_rate(ip)
    _record_signup(ip)

    email = req.email.strip().lower()

    # Validate email format
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise HTTPException(400, "Adresse email invalide.")

    # Validate password
    pw_errors = _validate_password(req.password)
    if pw_errors:
        raise HTTPException(400, " ".join(pw_errors))

    # S4: anti-enumeration — same response whether email exists or not
    existing = get_user_by_email(email)
    if existing:
        logger.info("Signup attempt with existing email (anti-enumeration)")
        # Return same status code and shape as success
        return {
            "status": "created",
            "message": "Compte cree. Verifiez votre email.",
        }

    # Create account + user
    account = create_account(req.org_name.strip())
    user = create_user(account["id"], email, req.password)

    # Create verification token and send email
    token = create_email_token(user["id"], "verify")
    logger.info("Signup: user=%s account=%s verify_token created", user["id"], account["id"])

    # Q3: send verification email (stub if SMTP not configured)
    from loko.email import send_verification_email
    send_verification_email(email, token)

    import os
    result: dict[str, Any] = {
        "status": "created",
        "message": "Compte cree. Verifiez votre email.",
    }
    # S1: debug mode only — never in production
    from loko.config.env import get_env
    if os.environ.get("LOKO_AUTH_DEBUG_TOKENS") == "on" and get_env("ENV") != "production":
        result["_debug_verify_token"] = token
        result["user_id"] = user["id"]
        result["account_id"] = account["id"]

    return result


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

    # T4: check account not suspended before creating session
    account = get_account(user["account_id"])
    if account and account.get("status") == "suspended":
        raise HTTPException(403, "Compte suspendu. Contactez le support.")

    # ACC-4: email verification is mandatory before any session is issued
    if user.get("email_verified_at") is None:
        raise HTTPException(
            status_code=403,
            detail="Email non verifie. Verifiez votre boite mail ou demandez un nouveau lien.",
        )

    # Create session
    session_id = create_session(user["id"])
    _set_session_cookie(response, session_id)

    # S6: set CSRF cookie on login
    from loko.api.csrf import set_csrf_cookie
    set_csrf_cookie(response)

    # Update last_login_at
    update_user(user["id"], last_login_at=datetime.now(timezone.utc).isoformat())

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


@router.get("/csrf-token")
async def get_csrf_token(response: Response) -> dict[str, str]:
    """S6: Issue/refresh CSRF token (double-submit cookie)."""
    from loko.api.csrf import set_csrf_cookie
    token = set_csrf_cookie(response)
    return {"csrf_token": token}


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


class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest) -> dict[str, str]:
    """S2: Verify email address using token (in body, not query)."""
    data = validate_email_token(req.token, "verify")
    if not data:
        raise HTTPException(400, "Lien de verification invalide ou expire.")

    mark_token_used(data["id"])
    update_user(data["user_id"], email_verified_at=datetime.now(timezone.utc).isoformat())

    return {"status": "ok", "message": "Email verifie."}


class ResendVerificationRequest(BaseModel):
    email: str


@router.post("/resend-verification")
async def resend_verification(req: ResendVerificationRequest, request: Request) -> dict[str, str]:
    """ACC-4: resend verification email. Anti-enumeration: always same response."""
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)

    email = req.email.strip().lower()
    user = get_user_by_email(email)

    if user and user.get("email_verified_at") is None:
        token = create_email_token(user["id"], "verify")
        logger.info("Resend verification: user=%s verify_token created", user["id"])
        from loko.email import send_verification_email
        send_verification_email(email, token)

    # Anti-enumeration: identical response whether user exists, is verified, or not
    return {"status": "ok", "message": "Si un compte non verifie existe avec cet email, un nouveau lien a ete envoye."}


@router.post("/request-reset")
async def request_reset(req: ResetRequestModel, request: Request) -> dict[str, str]:
    """Request a password reset. Anti-enumeration: always returns same response."""
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)

    email = req.email.strip().lower()
    user = get_user_by_email(email)

    if user:
        token = create_email_token(user["id"], "reset")
        logger.info("Password reset requested for user=%s", user["id"])
        # Q3: send reset email (stub if SMTP not configured)
        from loko.email import send_password_reset_email
        send_password_reset_email(email, token)

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


# ---------------------------------------------------------------------------
# Q2: GDPR — data export and account deletion
# ---------------------------------------------------------------------------

@router.get("/export")
async def export_my_data(request: Request) -> dict[str, Any]:
    """Q2/GDPR: export all personal data for the current user."""
    session_id = _get_session_id(request)
    if not session_id:
        raise HTTPException(401, "Non authentifie.")

    session = validate_session(session_id)
    if not session:
        raise HTTPException(401, "Session invalide.")

    user = get_user_by_id(session["user_id"])
    if not user:
        raise HTTPException(404, "Utilisateur introuvable.")

    account = get_account(session["account_id"])

    # Collect bot data
    from loko.bot.config_store import list_bots
    bots = list_bots(account_id=session["account_id"])

    export = {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "created_at": user.get("created_at"),
            "last_login_at": user.get("last_login_at"),
            "email_verified_at": user.get("email_verified_at"),
        },
        "account": {
            "id": session["account_id"],
            "org_name": account["org_name"] if account else "",
            "plan": account["plan"] if account else "",
            "created_at": account.get("created_at") if account else "",
        },
        "bots": bots,
    }
    return export


class DeleteAccountRequest(BaseModel):
    confirm: str = Field(..., description="Must be 'SUPPRIMER' to confirm")


@router.post("/delete-account")
async def delete_my_account(
    req: DeleteAccountRequest, request: Request, response: Response,
) -> dict[str, str]:
    """Q2/GDPR: permanently delete account and all associated data."""
    if req.confirm != "SUPPRIMER":
        raise HTTPException(400, "Confirmation requise: envoyez confirm='SUPPRIMER'")

    session_id = _get_session_id(request)
    if not session_id:
        raise HTTPException(401, "Non authentifie.")

    session = validate_session(session_id)
    if not session:
        raise HTTPException(401, "Session invalide.")

    from loko.db.accounts import delete_user_and_account
    from loko.bot.config_store import delete_bot, list_bots

    # Delete all bots belonging to this account
    bots = list_bots(account_id=session["account_id"])
    for bot in bots:
        delete_bot(bot["bot_id"])

    # Delete user and account
    delete_user_and_account(session["user_id"], session["account_id"])

    _clear_session_cookie(response)
    logger.info("Account deleted: user=%s account=%s", session["user_id"], session["account_id"])

    return {"status": "deleted", "message": "Compte et donnees supprimes."}
