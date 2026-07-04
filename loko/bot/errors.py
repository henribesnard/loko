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
