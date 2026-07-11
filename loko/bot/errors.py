"""LOKO Bot — Domain exceptions.

Fail-closed error types for production safety (GNG-10, A3).
"""

from __future__ import annotations


class ComponentUnavailableError(Exception):
    """Raised when a required bot component is unavailable in production.

    Examples: classifier not trained, SetFit not installed, model
    corrupted, manifest missing.
    """

    def __init__(self, component: str, bot_id: str, reason: str) -> None:
        self.component = component
        self.bot_id = bot_id
        self.reason = reason
        super().__init__(f"{component} unavailable for bot {bot_id}: {reason}")


# K1: Machine-readable integrity error codes for publish endpoint (422).
INTEGRITY_CODES = frozenset(
    {
        "manifest_missing",
        "manifest_invalid",
        "hash_mismatch",
        "load_error",
        "smoke_failed",
        "retrain_required",
    }
)


class ModelIntegrityError(ComponentUnavailableError):
    """Raised when model integrity verification fails during publish.

    Carries a machine-readable *code* from INTEGRITY_CODES so the API
    can return 422 with a structured body.
    """

    def __init__(self, bot_id: str, code: str, detail: str) -> None:
        if code not in INTEGRITY_CODES:
            code = "verification_error"
        self.code = code
        self.detail = detail
        super().__init__("model_integrity", bot_id, detail)
