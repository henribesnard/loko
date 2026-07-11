"""LOKO Bot — Escalation provider interface and implementations (Lot PRO-4 §7.4).

The escalation contract is frozen (spec §8). Providers:
- MockEscalationProvider: for testing (C7, moved to loko.testing.mocks)
- WebhookEscalationProvider: POST payload to webhook_url with HMAC signature
- EmailEscalationProvider: send transcript via SMTP

Real providers degrade gracefully: on failure, the template is rendered
with a fallback wait time and the error is traced + counted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Literal, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field

from loko.bot.models import EscalationPayload, EscalationResult

logger = logging.getLogger(__name__)


@runtime_checkable
class EscalationProvider(Protocol):
    """Interface for escalation providers."""

    async def escalate(self, payload: EscalationPayload) -> EscalationResult:
        """Send the escalation payload and return the result."""
        ...


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class EscalationConfig(BaseModel):
    """Escalation configuration per bot."""

    provider: Literal["mock", "webhook", "email"] = "mock"
    webhook_url: str = ""
    webhook_secret_ref: str = ""  # ref in secret store for HMAC signing
    email_to: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password_ref: str = ""
    temps_attente_defaut_min: int = Field(default=5, ge=1, le=60)


# ---------------------------------------------------------------------------
# Webhook provider
# ---------------------------------------------------------------------------


class WebhookEscalationProvider:
    """POST escalation payload to a webhook URL with HMAC signature.

    Signature: X-Loko-Signature: sha256=HMAC(body, secret)
    Timeout: 5s, 1 retry with 2s backoff.
    Degradation: on failure, returns fallback wait time.
    """

    def __init__(
        self,
        webhook_url: str,
        signing_secret: str = "",
        fallback_wait: int = 5,
    ) -> None:
        self.webhook_url = webhook_url
        self.signing_secret = signing_secret
        self.fallback_wait = fallback_wait

    async def escalate(self, payload: EscalationPayload) -> EscalationResult:
        body = json.dumps(
            payload.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }

        # HMAC signature
        if self.signing_secret:
            sig = hmac.new(
                self.signing_secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Loko-Signature"] = f"sha256={sig}"

        timeout = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)

        for attempt in range(2):  # 1 retry
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        self.webhook_url,
                        content=body,
                        headers=headers,
                    )

                if response.status_code < 300:
                    try:
                        data = response.json()
                        wait = data.get("temps_attente_estime_min", self.fallback_wait)
                        return EscalationResult(temps_attente_estime_min=int(wait))
                    except (json.JSONDecodeError, ValueError):
                        return EscalationResult(
                            temps_attente_estime_min=self.fallback_wait
                        )

                logger.warning(
                    "Webhook escalation returned %d (attempt %d)",
                    response.status_code,
                    attempt + 1,
                )

            except Exception as exc:
                logger.warning(
                    "Webhook escalation failed (attempt %d): %s",
                    attempt + 1,
                    exc,
                )

            # Backoff before retry
            if attempt == 0:
                import asyncio

                await asyncio.sleep(2.0)

        # All attempts failed — graceful degradation
        logger.error(
            "Webhook escalation failed after 2 attempts, using fallback wait=%d",
            self.fallback_wait,
        )
        return EscalationResult(temps_attente_estime_min=self.fallback_wait)


# ---------------------------------------------------------------------------
# Email provider
# ---------------------------------------------------------------------------


class EmailEscalationProvider:
    """Send escalation via SMTP email.

    The transcript is included as plain text.
    Wait time is always the configured fallback (no synchronous response).
    """

    def __init__(
        self,
        email_to: str,
        smtp_host: str = "localhost",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        fallback_wait: int = 5,
    ) -> None:
        self.email_to = email_to
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.fallback_wait = fallback_wait

    async def escalate(self, payload: EscalationPayload) -> EscalationResult:
        import smtplib
        from email.mime.text import MIMEText

        # Build email body
        transcript_text = "\n".join(
            f"[{t.get('role', '?')}] {t.get('content', '')}" for t in payload.transcript
        )

        body = (
            f"Escalade LOKO\n"
            f"Session: {payload.conversation_id}\n"
            f"Intention: {payload.intention or 'N/A'}\n"
            f"Sous-motif: {payload.sous_motif or 'N/A'}\n"
            f"Motif: {payload.motif_escalade.value}\n"
            f"Date: {payload.horodatage}\n\n"
            f"--- Transcript ---\n{transcript_text}"
        )

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[LOKO] Escalade — {payload.motif_escalade.value}"
        msg["From"] = self.smtp_user or "loko@localhost"
        msg["To"] = self.email_to

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                if self.smtp_user and self.smtp_password:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            logger.info("Escalation email sent to %s", self.email_to)
        except Exception as exc:
            logger.error("Email escalation failed: %s", exc)

        return EscalationResult(temps_attente_estime_min=self.fallback_wait)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_escalation_provider(
    config: EscalationConfig,
    secret_store: Any = None,
) -> EscalationProvider:
    """Build an escalation provider from config.

    Parameters
    ----------
    config : EscalationConfig
        Escalation configuration.
    secret_store : SecretStore | None
        Secret store for resolving webhook signing secret / SMTP password.
    """
    if config.provider == "webhook":
        signing_secret = ""
        if config.webhook_secret_ref and secret_store:
            try:
                signing_secret = secret_store.get(config.webhook_secret_ref)
            except (KeyError, RuntimeError):
                logger.warning("Could not resolve webhook signing secret")

        return WebhookEscalationProvider(
            webhook_url=config.webhook_url,
            signing_secret=signing_secret,
            fallback_wait=config.temps_attente_defaut_min,
        )

    if config.provider == "email":
        smtp_password = ""
        if config.smtp_password_ref and secret_store:
            try:
                smtp_password = secret_store.get(config.smtp_password_ref)
            except (KeyError, RuntimeError):
                logger.warning("Could not resolve SMTP password")

        return EmailEscalationProvider(
            email_to=config.email_to,
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_password=smtp_password,
            fallback_wait=config.temps_attente_defaut_min,
        )

    # Mock — import from testing module
    from loko.testing.mocks import MockEscalationProvider

    return MockEscalationProvider()
