"""LOKO Bot — Conversational guardrails (Lot GF §4).

Three-layer defense:
1. Deterministic pre-filter (regex rules, < 1ms) — this module
2. Classification hors_perimetre (SetFit, existing)
3. Prompt hardening + output validation (generation.py)

The pre-filter runs BEFORE classification. No LLM call, no retrieval.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Regex engine with timeout support (falls back to stdlib re if unavailable)
try:
    import regex as _regex_mod

    def _match_with_timeout(
        pattern: re.Pattern, text: str, timeout_ms: int = 10
    ) -> bool:
        """Match with timeout protection against ReDoS."""
        try:
            return bool(
                _regex_mod.search(
                    pattern.pattern,
                    text,
                    flags=pattern.flags | _regex_mod.IGNORECASE,
                    timeout=timeout_ms / 1000.0,
                )
            )
        except _regex_mod.error:
            return False
        except TimeoutError:
            logger.critical(
                "Guardrail regex timeout (ReDoS?): pattern=%s", pattern.pattern[:80]
            )
            return False
except ImportError:

    def _match_with_timeout(
        pattern: re.Pattern, text: str, timeout_ms: int = 10
    ) -> bool:
        """Fallback: match without timeout (stdlib re)."""
        return bool(pattern.search(text))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class GuardrailRule(BaseModel):
    """A single guardrail rule."""

    id: str
    category: Literal[
        "dangereux",
        "donnees_tiers",
        "injection",
        "juridique_medical",
        "custom",
    ]
    pattern: str
    action: Literal["refuser", "refuser_et_compter", "escalader"]
    enabled: bool = True
    is_system: bool = False  # system rules cannot be deleted


class GuardrailsConfig(BaseModel):
    """Guardrail configuration per bot."""

    enabled: bool = True
    rules: list[GuardrailRule] = Field(default_factory=list)
    max_infractions: int = Field(default=2, ge=1, le=5)
    action_apres_max: Literal["fin_ferme", "escalade"] = "fin_ferme"
    seuil_rejet_fort: float = Field(default=0.85, ge=0.0, le=1.0)
    block_low_grounding: bool = False


class GuardrailResult(BaseModel):
    """Result of a guardrail check."""

    blocked: bool = False
    rule_id: str | None = None
    category: str | None = None
    action: str | None = None


# ---------------------------------------------------------------------------
# Default ruleset (system rules — non-suppressible)
# ---------------------------------------------------------------------------

_DEFAULT_RULES: list[dict[str, Any]] = [
    # Injection attempts
    {
        "id": "sys_injection_ignore",
        "category": "injection",
        "pattern": r"(?i)(ignore[sz]?\s+(tes|vos|les|toutes?\s+les?)\s+(instructions?|consignes?|regles?))",
        "action": "refuser_et_compter",
        "is_system": True,
    },
    {
        "id": "sys_injection_repeat_prompt",
        "category": "injection",
        "pattern": r"(?i)(repete[sz]?\s+(ton|votre|le)\s+(prompt|system|instructions?))",
        "action": "refuser_et_compter",
        "is_system": True,
    },
    {
        "id": "sys_injection_dev_mode",
        "category": "injection",
        "pattern": r"(?i)(mode\s+(dev|developpeur|developer|debug|test|admin|root|jailbreak|dan))",
        "action": "refuser_et_compter",
        "is_system": True,
    },
    {
        "id": "sys_injection_pretend",
        "category": "injection",
        "pattern": r"(?i)(fais\s+semblant|pretend|act\s+as\s+if|imagine\s+que\s+tu\s+es|tu\s+es\s+maintenant)",
        "action": "refuser_et_compter",
        "is_system": True,
    },
    {
        "id": "sys_injection_reveal",
        "category": "injection",
        "pattern": r"(?i)(montre|affiche|revele|donne|show|reveal|display)\s+.{0,20}(prompt|system|instructions?|config|cle|key|secret|token)",
        "action": "refuser_et_compter",
        "is_system": True,
    },
    # Dangerous content
    {
        "id": "sys_danger_weapons",
        "category": "dangereux",
        "pattern": r"(?i)(fabriquer?\s+(une?\s+)?(bombe|explosif|arme)|comment\s+(faire|construire|fabriquer)\s+(une?\s+)?(bombe|arme|explosif))",
        "action": "refuser_et_compter",
        "is_system": True,
    },
    {
        "id": "sys_danger_selfharm",
        "category": "dangereux",
        "pattern": r"(?i)(comment\s+(se\s+)?suicider|methodes?\s+(de\s+)?suicide|facon\s+de\s+mourir)",
        "action": "refuser_et_compter",
        "is_system": True,
    },
    # Third-party data requests
    {
        "id": "sys_tiers_address",
        "category": "donnees_tiers",
        "pattern": r"(?i)(donne|trouve|cherche|dis)\s*(-|\s)*(moi\s+)?(l['e]?\s*)?(adresse|numero|telephone|email|mail|coordonnees)\s+.{0,20}(de|du|d['e])\s+",
        "action": "refuser_et_compter",
        "is_system": True,
    },
]


def default_ruleset() -> list[GuardrailRule]:
    """Return the default system rules."""
    return [GuardrailRule(**r) for r in _DEFAULT_RULES]


# ---------------------------------------------------------------------------
# Pre-filter engine
# ---------------------------------------------------------------------------


class GuardrailEngine:
    """Deterministic pre-filter engine.

    Compiles regex patterns and matches against user messages.
    Latency target: < 1ms.
    """

    def __init__(self, config: GuardrailsConfig) -> None:
        self.config = config
        self._compiled: list[tuple[GuardrailRule, re.Pattern]] = []
        self._compile_rules()

    def _compile_rules(self) -> None:
        """Compile enabled rules. Invalid regex → disabled + log CRITICAL."""
        self._compiled = []
        for rule in self.config.rules:
            if not rule.enabled:
                continue
            try:
                pattern = re.compile(rule.pattern, re.IGNORECASE)
                self._compiled.append((rule, pattern))
            except re.error as exc:
                logger.critical(
                    "Invalid guardrail regex (rule %s): %s — disabling",
                    rule.id,
                    exc,
                )

    def check(self, text: str) -> GuardrailResult:
        """Check a user message against all enabled rules.

        Returns GuardrailResult with blocked=True if a rule matched.
        The response never reveals WHICH rule matched (no oracle).
        """
        if not self.config.enabled:
            return GuardrailResult()

        normalized = text.strip()
        if not normalized:
            return GuardrailResult()

        for rule, pattern in self._compiled:
            if _match_with_timeout(pattern, normalized):
                logger.info(
                    "Guardrail rule %s (%s) matched — action=%s",
                    rule.id,
                    rule.category,
                    rule.action,
                )
                return GuardrailResult(
                    blocked=True,
                    rule_id=rule.id,
                    category=rule.category,
                    action=rule.action,
                )

        return GuardrailResult()


# ---------------------------------------------------------------------------
# Output validation (post-generation, Lot GF §4.4)
# ---------------------------------------------------------------------------

# Patterns for leak detection (always blocking)
_LEAK_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI-style keys
    re.compile(r"loko_[a-zA-Z0-9_]{10,}"),  # LOKO API keys
    re.compile(r"Bearer\s+[a-zA-Z0-9._\-]{20,}"),  # Bearer tokens
    re.compile(r"(/app/|/root/|C:\\Users\\)[^\s]+\.py"),  # Disk paths
    re.compile(r"Traceback \(most recent call last\)"),  # Stack traces
    re.compile(r"File \"[^\"]+\", line \d+"),  # Python stack frames
]


def check_response_leaks(response: str) -> str | None:
    """Scan a generated response for forbidden patterns.

    Returns the leak type if found, None if clean.
    Always blocking — no config flag (GF §4.4).
    """
    for pattern in _LEAK_PATTERNS:
        if pattern.search(response):
            return pattern.pattern[:40]
    return None


# V1: Streaming-level leak detection — sliding window for per-token checking
# The longest leak pattern needs ~60 chars to match; we keep a window of 200
# to cover token boundaries safely.
_LEAK_WINDOW_SIZE = 200


def check_response_leaks_streaming(accumulated: str) -> str | None:
    """Check for leaks in the tail of an accumulating response (V1).

    Only scans the last _LEAK_WINDOW_SIZE characters for efficiency.
    Returns the leak type if found, None if clean.
    """
    tail = accumulated[-_LEAK_WINDOW_SIZE:] if len(accumulated) > _LEAK_WINDOW_SIZE else accumulated
    for pattern in _LEAK_PATTERNS:
        if pattern.search(tail):
            return pattern.pattern[:40]
    return None


def check_grounding(
    response: str,
    chunks: list[Any],
    refusal_phrase: str = "",
    min_ngram: int = 8,
) -> bool:
    """Check if the response is grounded in the provided chunks.

    Returns True if grounded (contains refusal phrase or shares
    n-grams with chunks), False if low grounding.

    V1: marking only (block_low_grounding=False by default).
    """
    if refusal_phrase and refusal_phrase in response:
        return True

    # Normalize for n-gram comparison
    def _normalize(text: str) -> list[str]:
        return text.lower().split()

    response_words = _normalize(response)
    if len(response_words) < min_ngram:
        return True  # too short to check

    for chunk in chunks:
        chunk_text = chunk.text if hasattr(chunk, "text") else str(chunk)
        chunk_words = _normalize(chunk_text)
        if len(chunk_words) < min_ngram:
            continue

        # Check for shared n-grams
        chunk_ngrams = set()
        for i in range(len(chunk_words) - min_ngram + 1):
            chunk_ngrams.add(tuple(chunk_words[i : i + min_ngram]))

        for i in range(len(response_words) - min_ngram + 1):
            ngram = tuple(response_words[i : i + min_ngram])
            if ngram in chunk_ngrams:
                return True

    return False
