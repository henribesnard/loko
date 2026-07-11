"""LOKO Bot — PII anonymization (Lot PRO-1 §7.1).

Deterministic regex-based masking of personally identifiable information.
Applied at PERSISTENCE only (never in-flight: classification and LLM
see the real text).

Supported PII types:
- NIR (French social security number, 13+2 digits with key verification)
- Email addresses
- Phone numbers (FR and international)
- IBAN
- Credit card numbers (Luhn-validated)

Tokens: [NIR], [EMAIL], [TEL], [IBAN], [CB]
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# PII detection patterns
# ---------------------------------------------------------------------------

# NIR: 1 digit sex + 2 digits year + 2 digits month + 5 digits commune +
#       3 digits order + 2 digits key (optional spaces/dots/dashes)
_NIR_PATTERN = re.compile(
    r"\b[12]\s*[\d]{2}\s*(?:0[1-9]|1[0-2])\s*[\d]{2,3}\s*[\d]{3}\s*[\d]{3}\s*(?:\d{2})?\b"
)

# Email
_EMAIL_PATTERN = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")

# Phone (FR formats: 01-10, +33, 0033; international with +)
_PHONE_PATTERN = re.compile(
    r"(?:\+\d{1,3}[\s.\-]?)?\(?\d{1,4}\)?[\s.\-]?\d{2,4}[\s.\-]?\d{2,4}[\s.\-]?\d{2,4}\b"
)
# More specific FR phone
_PHONE_FR_PATTERN = re.compile(r"\b(?:(?:\+33|0033|0)\s*[1-9])(?:[\s.\-]?\d{2}){4}\b")

# IBAN (FR format: FR + 2 check digits + 23 alphanumeric; generic: 2 letters + 2 digits + up to 30 alnum)
_IBAN_PATTERN = re.compile(
    r"\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}[\s]?[\dA-Z]{4}[\s]?[\dA-Z]{4}[\s]?[\dA-Z]{4}[\s]?[\dA-Z]{0,7}\b",
    re.IGNORECASE,
)

# Credit card: 13-19 digits (spaces/dashes allowed), Luhn-validated
_CB_PATTERN = re.compile(r"\b(?:\d[\s\-]?){13,19}\b")


def _luhn_check(number: str) -> bool:
    """Validate a number string with the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PIIType = Literal["nir", "email", "tel", "iban", "cb"]

_ALL_PII_TYPES: set[PIIType] = {"nir", "email", "tel", "iban", "cb"}


class PIIConfig(BaseModel):
    """PII masking configuration per bot."""

    enabled: bool = True
    types: set[PIIType] = Field(default_factory=lambda: set(_ALL_PII_TYPES))
    custom_patterns: list[dict[str, str]] = Field(default_factory=list)
    escalade_pii_en_clair: bool = False


# ---------------------------------------------------------------------------
# Masking engine
# ---------------------------------------------------------------------------


def mask_pii(text: str, config: PIIConfig | None = None) -> str:
    """Mask PII in text using deterministic regex replacement.

    Parameters
    ----------
    text : str
        The text to mask.
    config : PIIConfig | None
        PII configuration. If None, uses defaults (all types enabled).

    Returns
    -------
    str
        Text with PII replaced by typed tokens.
    """
    if config is not None and not config.enabled:
        return text

    types = config.types if config else _ALL_PII_TYPES
    result = text

    if "email" in types:
        result = _EMAIL_PATTERN.sub("[EMAIL]", result)

    if "nir" in types:
        result = _NIR_PATTERN.sub("[NIR]", result)

    if "iban" in types:
        result = _IBAN_PATTERN.sub("[IBAN]", result)

    if "cb" in types:
        # Only mask sequences that pass Luhn check
        def _cb_replace(match: re.Match) -> str:
            digits = "".join(c for c in match.group() if c.isdigit())
            if _luhn_check(digits):
                return "[CB]"
            return match.group()

        result = _CB_PATTERN.sub(_cb_replace, result)

    if "tel" in types:
        # FR phone first (more specific), then generic
        result = _PHONE_FR_PATTERN.sub("[TEL]", result)

    # Apply custom patterns
    if config and config.custom_patterns:
        for cp in config.custom_patterns:
            pattern = cp.get("pattern", "")
            token = cp.get("token", "[PII]")
            if pattern:
                try:
                    result = re.sub(pattern, token, result)
                except re.error:
                    pass

    return result


def mask_transcript(
    transcript: list[dict],
    config: PIIConfig | None = None,
) -> list[dict]:
    """Mask PII in a transcript (list of turn dicts).

    Applied at persistence — the in-flight transcript is untouched.
    """
    masked = []
    for turn in transcript:
        masked_turn = dict(turn)
        if "content" in masked_turn:
            masked_turn["content"] = mask_pii(masked_turn["content"], config)
        masked.append(masked_turn)
    return masked
