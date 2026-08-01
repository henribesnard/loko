"""LOKO — Account management API.

Router prefix: /api/account
Handles: profile (A.1), security (A.2), team/roles (A.3), plan/usage (A.4), RGPD (A.5).

Separate public routes for invitation acceptance: /api/invitations
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from loko.api.role_middleware import require_account_role
from loko.api.session_middleware import require_session
from loko.db.accounts import (
    accept_invitation,
    count_owners,
    create_invitation,
    create_membership,
    create_session,
    create_user,
    delete_membership,
    delete_user_and_account,
    get_account,
    get_invitation_by_id,
    get_invitation_by_token,
    get_membership,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    list_invitations,
    list_memberships,
    list_user_sessions,
    refresh_invitation_token,
    revoke_all_sessions_except,
    revoke_invitation,
    revoke_specific_session,
    update_membership_role,
    update_user,
    verify_password,
    create_email_token,
    mark_token_used,
    validate_email_token,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/account", tags=["account"])
invitations_router = APIRouter(prefix="/api/invitations", tags=["invitations"])


# ---------------------------------------------------------------------------
# Rate limiting helpers (in-memory)
# ---------------------------------------------------------------------------

_INVITE_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_MAX_INVITE_RATE = 10
_INVITE_WINDOW = 3600  # 1h

_RESEND_VERIFY_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_MAX_RESEND_VERIFY = 1
_RESEND_VERIFY_WINDOW = 300  # 5 min


def _check_invite_rate(account_id: str) -> None:
    now = time.time()
    attempts = _INVITE_ATTEMPTS[account_id]
    _INVITE_ATTEMPTS[account_id] = [t for t in attempts if now - t < _INVITE_WINDOW]
    if len(_INVITE_ATTEMPTS[account_id]) >= _MAX_INVITE_RATE:
        raise HTTPException(429, "Trop d'invitations envoyees. Reessayez plus tard.")


def _record_invite(account_id: str) -> None:
    _INVITE_ATTEMPTS[account_id].append(time.time())


def _check_resend_verify_rate(user_id: str) -> None:
    now = time.time()
    attempts = _RESEND_VERIFY_ATTEMPTS[user_id]
    _RESEND_VERIFY_ATTEMPTS[user_id] = [t for t in attempts if now - t < _RESEND_VERIFY_WINDOW]
    if len(_RESEND_VERIFY_ATTEMPTS[user_id]) >= _MAX_RESEND_VERIFY:
        raise HTTPException(429, "Veuillez patienter quelques minutes avant de renvoyer.")


def _record_resend_verify(user_id: str) -> None:
    _RESEND_VERIFY_ATTEMPTS[user_id].append(time.time())


# ---------------------------------------------------------------------------
# Password validation (reuse from user_auth)
# ---------------------------------------------------------------------------

PW_MIN_CHARS = 12


def _validate_password(password: str) -> list[str]:
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
# Request schemas (extra="forbid" on all — AC-12)
# ---------------------------------------------------------------------------

class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = None
    language: Literal["fr", "en"] | None = None
    timezone: str | None = Field(default=None, max_length=64)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str
    new_password: str = Field(..., min_length=12)


class InviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emails: list[str] = Field(..., min_length=1, max_length=10)
    role: Literal["editor", "viewer"]


class UpdateRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["owner", "editor", "viewer"]


class AcceptInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    password: str | None = Field(default=None, min_length=12)
    display_name: str = Field(default="", max_length=100)


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str
    confirm: Literal["SUPPRIMER"]


# ===================================================================
# A.1 — Profile
# ===================================================================


@router.get("/profile")
async def get_profile(request: Request, _auth=Depends(require_session)) -> dict[str, Any]:
    """Get current user profile."""
    user = get_user_by_id(request.state.user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable.")
    account = get_account(request.state.account_id)
    membership = get_membership(request.state.account_id, request.state.user_id)
    return {
        "display_name": user.get("display_name", ""),
        "email": user["email"],
        "email_verified_at": user.get("email_verified_at"),
        "language": user.get("language", "fr"),
        "timezone": user.get("timezone", "Europe/Paris"),
        "created_at": user.get("created_at"),
        "role": membership["role"] if membership else user.get("role", "owner"),
        "org_name": account["org_name"] if account else "",
    }


@router.patch("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    request: Request,
    _auth=Depends(require_session),
) -> dict[str, str]:
    """Update profile fields (name, language, timezone)."""
    updates: dict[str, Any] = {}
    if req.display_name is not None:
        updates["display_name"] = req.display_name.strip()[:100]
    if req.language is not None:
        updates["language"] = req.language
    if req.timezone is not None:
        updates["timezone"] = req.timezone
    if not updates:
        raise HTTPException(400, "Aucun champ a modifier.")
    update_user(request.state.user_id, **updates)
    return {"status": "ok"}


@router.post("/profile/resend-verification")
async def resend_verification(request: Request, _auth=Depends(require_session)) -> dict[str, str]:
    """Resend email verification (rate-limited: 1/5min)."""
    user = get_user_by_id(request.state.user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable.")
    if user.get("email_verified_at"):
        return {"status": "ok", "message": "Email deja verifie."}
    _check_resend_verify_rate(request.state.user_id)
    _record_resend_verify(request.state.user_id)
    token = create_email_token(request.state.user_id, "verify")
    from loko.email import send_verification_email
    send_verification_email(user["email"], token)
    return {"status": "ok", "message": "Email de verification envoye."}


# ===================================================================
# A.2 — Security
# ===================================================================


@router.post("/password")
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    _auth=Depends(require_session),
) -> dict[str, str]:
    """Change password; invalidates all other sessions (AC-6)."""
    user = get_user_by_id(request.state.user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable.")
    if not verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(400, "Mot de passe actuel incorrect.")
    pw_errors = _validate_password(req.new_password)
    if pw_errors:
        raise HTTPException(400, " ".join(pw_errors))
    new_hash = hash_password(req.new_password)
    update_user(user["id"], password_hash=new_hash)
    # AC-6: revoke all other sessions, keep current
    session_id = request.cookies.get("loko_session", "")
    revoke_all_sessions_except(user["id"], session_id)
    return {"status": "ok", "message": "Mot de passe modifie."}


@router.get("/sessions")
async def list_sessions(request: Request, _auth=Depends(require_session)) -> list[dict[str, Any]]:
    """List active sessions for current user."""
    current_session_id = request.cookies.get("loko_session", "")
    sessions = list_user_sessions(request.state.user_id)
    result = []
    for s in sessions:
        result.append({
            "id": s["id"],
            "created_at": s["created_at"],
            "user_agent": s.get("user_agent", ""),
            "ip_address": s.get("ip_address", ""),
            "is_current": s["id"] == current_session_id,
        })
    return result


@router.delete("/sessions/{session_id}")
async def revoke_session_endpoint(
    session_id: str,
    request: Request,
    _auth=Depends(require_session),
) -> dict[str, str]:
    """Revoke a specific session."""
    current_session_id = request.cookies.get("loko_session", "")
    if session_id == current_session_id:
        raise HTTPException(400, "Impossible de revoquer la session courante.")
    ok = revoke_specific_session(session_id, request.state.user_id)
    if not ok:
        raise HTTPException(404, "Session introuvable.")
    return {"status": "ok"}


@router.delete("/sessions")
async def revoke_other_sessions(
    request: Request,
    _auth=Depends(require_session),
    others: bool = Query(default=False),
) -> dict[str, Any]:
    """Revoke all sessions except current."""
    if not others:
        raise HTTPException(400, "Parametre others=true requis.")
    current_session_id = request.cookies.get("loko_session", "")
    count = revoke_all_sessions_except(request.state.user_id, current_session_id)
    return {"status": "ok", "revoked": count}


# ===================================================================
# A.3 — Team & Roles
# ===================================================================


@router.get("/team")
async def list_team(
    request: Request,
    _auth=Depends(require_account_role("viewer")),
) -> dict[str, Any]:
    """List team members and pending invitations."""
    members = list_memberships(request.state.account_id)
    invites = list_invitations(request.state.account_id)
    return {"members": members, "invitations": invites}


@router.post("/team/invite")
async def invite_members(
    req: InviteRequest,
    request: Request,
    _auth=Depends(require_account_role("owner")),
) -> dict[str, Any]:
    """Send invitations (Owner only). Rate-limited."""
    _check_invite_rate(request.state.account_id)
    account = get_account(request.state.account_id)
    org_name = account["org_name"] if account else "LOKO"
    inviter_email = request.state.user_email
    results = []
    for raw_email in req.emails:
        email = raw_email.strip().lower()
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            results.append({"email": email, "status": "invalid_email"})
            continue
        # Check if already a member
        existing_user = get_user_by_email(email)
        if existing_user:
            existing_membership = get_membership(request.state.account_id, existing_user["id"])
            if existing_membership:
                results.append({"email": email, "status": "already_member"})
                continue
        inv_id, raw_token = create_invitation(
            request.state.account_id, email, req.role, request.state.user_id,
        )
        _record_invite(request.state.account_id)
        # Send email
        from loko.email import send_invitation_email
        sent = send_invitation_email(email, raw_token, org_name, inviter_email, req.role)
        results.append({"email": email, "status": "invited", "email_sent": sent})
    return {"results": results}


@router.delete("/team/invite/{invitation_id}")
async def cancel_invitation(
    invitation_id: str,
    request: Request,
    _auth=Depends(require_account_role("owner")),
) -> dict[str, str]:
    """Revoke a pending invitation (Owner only)."""
    ok = revoke_invitation(invitation_id, request.state.account_id)
    if not ok:
        raise HTTPException(404, "Invitation introuvable ou deja acceptee.")
    return {"status": "ok"}


@router.post("/team/invite/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: str,
    request: Request,
    _auth=Depends(require_account_role("owner")),
) -> dict[str, str]:
    """Resend an invitation email with a fresh token (Owner only, rate-limited)."""
    _check_invite_rate(request.state.account_id)
    raw_token = refresh_invitation_token(invitation_id, request.state.account_id)
    if not raw_token:
        raise HTTPException(404, "Invitation introuvable ou deja acceptee/revoquee.")
    inv = get_invitation_by_id(invitation_id, request.state.account_id)
    if not inv:
        raise HTTPException(404, "Invitation introuvable.")
    account = get_account(request.state.account_id)
    org_name = account["org_name"] if account else "LOKO"
    from loko.email import send_invitation_email
    send_invitation_email(inv["email"], raw_token, org_name, request.state.user_email, inv["role"])
    _record_invite(request.state.account_id)
    return {"status": "ok", "message": "Invitation renvoyee."}


@router.patch("/team/{user_id}/role")
async def update_member_role(
    user_id: str,
    req: UpdateRoleRequest,
    request: Request,
    _auth=Depends(require_account_role("owner")),
) -> dict[str, str]:
    """Change a member's role (Owner only). AC-3: last owner guard."""
    membership = get_membership(request.state.account_id, user_id)
    if not membership:
        raise HTTPException(404, "Membre introuvable.")
    # AC-3: cannot demote the last owner
    if membership["role"] == "owner" and req.role != "owner":
        if count_owners(request.state.account_id) <= 1:
            raise HTTPException(
                403, "Impossible de modifier le role du seul proprietaire du compte."
            )
    update_membership_role(request.state.account_id, user_id, req.role)
    return {"status": "ok"}


@router.delete("/team/{user_id}")
async def remove_member(
    user_id: str,
    request: Request,
    _auth=Depends(require_account_role("owner")),
) -> dict[str, str]:
    """Remove a team member (Owner only, or self-removal except last Owner)."""
    membership = get_membership(request.state.account_id, user_id)
    if not membership:
        raise HTTPException(404, "Membre introuvable.")
    # Allow self-removal for non-owners
    is_self = user_id == request.state.user_id
    if not is_self and request.state.user_role != "owner":
        raise HTTPException(403, "Seul un proprietaire peut retirer un membre.")
    # AC-3: cannot remove the last owner
    if membership["role"] == "owner" and count_owners(request.state.account_id) <= 1:
        raise HTTPException(403, "Impossible de retirer le seul proprietaire du compte.")
    delete_membership(request.state.account_id, user_id)
    return {"status": "ok"}


# ===================================================================
# A.3 — Invitation acceptance (public routes, no auth)
# ===================================================================


@invitations_router.get("/{token}")
async def get_invitation_info(token: str) -> dict[str, Any]:
    """Public: get invitation details for acceptance screen. Anti-enumeration."""
    inv = get_invitation_by_token(token)
    if not inv:
        # Anti-enumeration: uniform response
        raise HTTPException(404, "Invitation introuvable ou expiree.")
    return {
        "email": inv["email"],
        "role": inv["role"],
        "org_name": inv.get("org_name", ""),
        "expires_at": inv["expires_at"],
    }


@invitations_router.post("/accept")
async def accept_invite(
    req: AcceptInviteRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    """Accept an invitation. Creates user if needed, adds membership."""
    inv = get_invitation_by_token(req.token)
    if not inv:
        raise HTTPException(400, "Invitation invalide ou expiree.")

    email = inv["email"]
    existing_user = get_user_by_email(email)

    if existing_user:
        # User already exists — check they're not already a member
        existing_membership = get_membership(inv["account_id"], existing_user["id"])
        if existing_membership:
            raise HTTPException(400, "Vous etes deja membre de ce compte.")
        # Add membership
        create_membership(inv["account_id"], existing_user["id"], inv["role"])
        user_id = existing_user["id"]
    else:
        # New user — password required
        if not req.password:
            raise HTTPException(400, "Mot de passe requis pour creer un compte.")
        pw_errors = _validate_password(req.password)
        if pw_errors:
            raise HTTPException(400, " ".join(pw_errors))
        user = create_user(inv["account_id"], email, req.password)
        user_id = user["id"]
        if req.display_name:
            update_user(user_id, display_name=req.display_name.strip()[:100])
        # Override the default 'owner' role from create_user with the invited role
        update_user(user_id, role=inv["role"])
        # Create membership with invited role
        create_membership(inv["account_id"], user_id, inv["role"])
        # Auto-verify email (they clicked the invitation link)
        update_user(user_id, email_verified_at=datetime.now(timezone.utc).isoformat())

    # Mark invitation as accepted (one-time — AC-5)
    accept_invitation(inv["id"])

    # Create session and set cookie
    ua = request.headers.get("user-agent", "")
    ip = request.client.host if request.client else ""
    session_id = create_session(user_id, user_agent=ua, ip_address=ip)
    response.set_cookie(
        key="loko_session",
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/",
    )
    from loko.api.csrf import set_csrf_cookie
    set_csrf_cookie(response)

    return {"status": "ok", "account_id": inv["account_id"], "role": inv["role"]}


# ===================================================================
# A.4 — Plan & Quotas
# ===================================================================


@router.get("/usage")
async def get_usage(request: Request, _auth=Depends(require_session)) -> dict[str, Any]:
    """Get current plan and quota usage."""
    from loko.api.quotas import get_effective_quotas
    from loko.bot.config_store import list_bots

    account = get_account(request.state.account_id)
    quotas = get_effective_quotas(request.state.account_id)
    bots = list_bots(account_id=request.state.account_id)

    return {
        "plan": account["plan"] if account else "trial",
        "quotas": {
            "bots": {
                "used": len(bots),
                "limit": quotas.get("max_bots", 1),
            },
            "intents_per_bot": {
                "limit": quotas.get("max_intents_per_bot", 5),
            },
            "documents": {
                "limit": quotas.get("max_documents", 20),
            },
        },
    }


@router.get("/billing/history")
async def get_billing_history(
    request: Request, _auth=Depends(require_session)
) -> list[Any]:
    """Billing history — placeholder (returns empty)."""
    return []


# ===================================================================
# A.5 — RGPD
# ===================================================================


@router.post("/export")
async def export_data(request: Request, _auth=Depends(require_session)) -> dict[str, Any]:
    """RGPD export: all personal data for the current account."""
    user = get_user_by_id(request.state.user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable.")
    account = get_account(request.state.account_id)
    from loko.bot.config_store import list_bots
    bots = list_bots(account_id=request.state.account_id)
    members = list_memberships(request.state.account_id)
    invites = list_invitations(request.state.account_id)

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name", ""),
            "language": user.get("language", "fr"),
            "timezone": user.get("timezone", "Europe/Paris"),
            "created_at": user.get("created_at"),
            "last_login_at": user.get("last_login_at"),
            "email_verified_at": user.get("email_verified_at"),
        },
        "account": {
            "id": request.state.account_id,
            "org_name": account["org_name"] if account else "",
            "plan": account["plan"] if account else "",
            "created_at": account.get("created_at") if account else "",
        },
        "memberships": members,
        "invitations": invites,
        "bots": bots,
    }
    return export


@router.delete("")
async def delete_account(
    req: DeleteAccountRequest,
    request: Request,
    response: Response,
    _auth=Depends(require_session),
) -> dict[str, str]:
    """RGPD: permanently delete account and all data (AC-7).

    Requires password re-verification and confirm='SUPPRIMER'.
    """
    user = get_user_by_id(request.state.user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable.")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(400, "Mot de passe incorrect.")

    # Must be owner
    membership = get_membership(request.state.account_id, request.state.user_id)
    if not membership or membership["role"] != "owner":
        raise HTTPException(403, "Seul un proprietaire peut supprimer le compte.")

    account_id = request.state.account_id

    # Delete all bots
    from loko.bot.config_store import delete_bot, list_bots
    bots = list_bots(account_id=account_id)
    for bot in bots:
        try:
            delete_bot(bot["bot_id"])
        except Exception:
            logger.warning("Failed to delete bot %s during account purge", bot["bot_id"])

    # Purge analytics events for this tenant (AC-7 coordination with OBS)
    # Delete rollups BEFORE events (the sub-query needs events to exist)
    try:
        from loko.analytics.db import get_analytics_db
        adb = get_analytics_db()
        if adb:
            adb.execute(
                "DELETE FROM daily_rollups WHERE bot_id IN "
                "(SELECT DISTINCT bot_id FROM events WHERE account_id = ?)",
                (account_id,),
            )
            adb.execute("DELETE FROM events WHERE account_id = ?", (account_id,))
            adb.commit()
    except Exception:
        logger.warning("Failed to purge analytics for account %s", account_id, exc_info=True)

    # Delete user, memberships, invitations, sessions, email_tokens, account
    delete_user_and_account(request.state.user_id, account_id)

    # Clear session cookie
    response.delete_cookie(key="loko_session", path="/")
    logger.info("Account deleted (RGPD): user=%s account=%s", request.state.user_id, account_id)

    return {"status": "deleted", "message": "Compte et donnees supprimes definitivement."}
