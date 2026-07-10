"""Q3 — Transactional email service (stub).

Currently logs emails instead of sending them. To enable real sending,
set LOKO_SMTP_HOST, LOKO_SMTP_PORT, LOKO_SMTP_USER, LOKO_SMTP_PASS,
LOKO_SMTP_FROM in environment.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _get_smtp_config() -> dict[str, str] | None:
    """Return SMTP config from environment, or None if not configured."""
    host = os.environ.get("LOKO_SMTP_HOST")
    if not host:
        return None
    return {
        "host": host,
        "port": os.environ.get("LOKO_SMTP_PORT", "587"),
        "user": os.environ.get("LOKO_SMTP_USER", ""),
        "password": os.environ.get("LOKO_SMTP_PASS", ""),
        "from_addr": os.environ.get("LOKO_SMTP_FROM", "noreply@loko.ai"),
    }


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email. Returns True on success.

    In development (no SMTP config), logs the email content instead.
    """
    config = _get_smtp_config()
    if not config:
        logger.info("Email (stub) to=%s subject=%s", to, subject)
        logger.debug("Email body:\n%s", body)
        return True

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = config["from_addr"]
        msg["To"] = to

        with smtplib.SMTP(config["host"], int(config["port"])) as server:
            server.starttls()
            if config["user"]:
                server.login(config["user"], config["password"])
            server.send_message(msg)

        logger.info("Email sent to=%s subject=%s", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to=%s", to)
        return False


def send_verification_email(to: str, token: str) -> bool:
    """Send email verification link."""
    base_url = os.environ.get("LOKO_BASE_URL", "http://localhost:1420")
    link = f"{base_url}/verify?token={token}"
    body = (
        f"Bienvenue sur LOKO !\n\n"
        f"Cliquez sur le lien suivant pour verifier votre adresse email :\n"
        f"{link}\n\n"
        f"Ce lien expire dans 24 heures.\n\n"
        f"L'equipe LOKO"
    )
    return send_email(to, "Verifiez votre adresse email — LOKO", body)


def send_password_reset_email(to: str, token: str) -> bool:
    """Send password reset link."""
    base_url = os.environ.get("LOKO_BASE_URL", "http://localhost:1420")
    link = f"{base_url}/reset?token={token}"
    body = (
        f"Vous avez demande une reinitialisation de mot de passe.\n\n"
        f"Cliquez sur le lien suivant :\n"
        f"{link}\n\n"
        f"Ce lien expire dans 24 heures.\n"
        f"Si vous n'avez pas fait cette demande, ignorez cet email.\n\n"
        f"L'equipe LOKO"
    )
    return send_email(to, "Reinitialisation de mot de passe — LOKO", body)
