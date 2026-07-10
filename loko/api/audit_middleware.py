"""
Audit logging middleware and helpers for FastAPI
Implements K2 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
"""

from fastapi import Request
from functools import wraps
from typing import Optional, Any, Callable
import os

from loko.db.audit import AuditLogger


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """
    Get the global audit logger instance.

    Returns:
        AuditLogger instance
    """
    global _audit_logger
    if _audit_logger is None:
        # Default path, can be overridden by environment variable
        audit_db_path = os.getenv("LOKO_AUDIT_DB_PATH", ".loko/audit.db")
        _audit_logger = AuditLogger(audit_db_path)
    return _audit_logger


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address
    """
    # Check for X-Forwarded-For (if behind proxy like Caddy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take first IP in chain
        return forwarded.split(",")[0].strip()

    # Check for X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback to direct client
    if request.client:
        return request.client.host

    return "unknown"


def audit_log(
    action: str,
    user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
):
    """
    Decorator for auditing API endpoint calls.

    Usage:
        @app.post("/api/bot")
        @audit_log(action=AuditLogger.ACTION_BOT_CREATE)
        async def create_bot(request: Request, ...):
            ...

    Args:
        action: Action name (use AuditLogger.ACTION_* constants)
        user_id: User ID (if None, will try to extract from request state)
        resource_id: Resource ID (if None, will try to extract from function result)
        details: Additional details dict
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Execute the original function
            result = await func(*args, **kwargs)

            # Try to extract request from args
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            # Extract user_id from request state if not provided
            actual_user_id = user_id
            if actual_user_id is None and request and hasattr(request.state, "user_id"):
                actual_user_id = request.state.user_id

            # Extract resource_id from result if not provided
            actual_resource_id = resource_id
            if actual_resource_id is None and isinstance(result, dict):
                actual_resource_id = result.get("id") or result.get("bot_id")

            # Get IP address
            ip_address = get_client_ip(request) if request else None

            # Log the audit event
            logger = get_audit_logger()
            logger.log(
                action=action,
                user_id=actual_user_id,
                resource_id=actual_resource_id,
                ip_address=ip_address,
                details=details,
            )

            return result

        return wrapper

    return decorator


def audit_log_sync(
    action: str,
    user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
):
    """
    Synchronously log an audit event.

    Use this for manual audit logging within endpoint handlers.

    Args:
        action: Action name
        user_id: User ID
        resource_id: Resource ID
        ip_address: Client IP address
        details: Additional details
    """
    logger = get_audit_logger()
    logger.log(
        action=action,
        user_id=user_id,
        resource_id=resource_id,
        ip_address=ip_address,
        details=details,
    )
