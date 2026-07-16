"""LOKO Assistant — Pydantic models for proposals and requests."""

from __future__ import annotations

import enum
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class UseCase(str, enum.Enum):
    """Supported assistant use cases."""

    A2_EXAMPLES = "a2_examples"


class SubMode(str, enum.Enum):
    """Sub-modes for a use case."""

    GENERATE = "generate"
    DISCRIMINATE = "discriminate"
    REVIEW = "review"


class Proposal(BaseModel):
    """A single proposal returned by the assistant."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    use_case: UseCase
    sub_mode: SubMode
    intent_id: str
    content: str
    rationale: str = ""
    confidence: float = 0.0
    status: Literal["pending", "accepted", "rejected"] = "pending"


class AssistantRequest(BaseModel):
    """Request body for POST /assistant/ask."""

    use_case: UseCase
    sub_mode: SubMode
    intent_id: str
    context: dict[str, Any] = Field(default_factory=dict)


class AssistantResponse(BaseModel):
    """Response from the assistant service."""

    proposals: list[Proposal]
    usage: dict[str, int] = Field(default_factory=dict)


class AcceptItem(BaseModel):
    """A single example to accept."""

    intent_id: str
    content: str


class AcceptRequest(BaseModel):
    """Request body for POST /assistant/accept."""

    items: list[AcceptItem]
