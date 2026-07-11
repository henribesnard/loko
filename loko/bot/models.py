"""LOKO Bot — Pydantic models (source of truth).

All data structures for the bot engine: config, session, traces, actions.
"""

from __future__ import annotations

import enum
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Slug validation (path traversal prevention)
# ---------------------------------------------------------------------------

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def validate_slug(value: str, name: str = "id") -> str:
    """Validate that a value is a safe slug (no path traversal)."""
    if not SLUG_RE.match(value):
        raise ValueError(
            f"Invalid {name}: must match ^[a-z0-9][a-z0-9_-]{{0,63}}$ — got {value!r}"
        )
    return value


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BotState(str, enum.Enum):
    """States of the bot conversation FSM."""

    ACCUEIL = "accueil"
    ATTENTE_DEMANDE = "attente_demande"
    CLASSIFICATION_L1 = "classification_l1"
    CLARIFICATION_INTER = "clarification_inter"
    CLASSIFICATION_L2 = "classification_l2"
    CLARIFICATION_INTRA = "clarification_intra"
    RETRIEVAL_GENERATION = "retrieval_generation"
    ENQUETE_SATISFACTION = "enquete_satisfaction"
    AUTRE_DEMANDE = "autre_demande"
    ESCALADE = "escalade"
    FIN = "fin"
    TIMEOUT = "timeout"
    # ORC/GF: graceful wind-down and firm close
    CLOTURE_DOUCE = "cloture_douce"
    FIN_FERME = "fin_ferme"


class TemplateKey(str, enum.Enum):
    """Message template identifiers."""

    PRESENTATION = "presentation"
    CLARIFICATION_INTER = "clarification_inter"
    CLARIFICATION_INTRA = "clarification_intra"
    HORS_PERIMETRE = "hors_perimetre"
    ENQUETE_SATISFACTION = "enquete_satisfaction"
    AUTRE_DEMANDE = "autre_demande"
    FIN = "fin"
    MISE_EN_RELATION = "mise_en_relation"
    TIMEOUT = "timeout"
    # ORC: graceful wind-down
    AVANT_DERNIERE_DEMANDE = "avant_derniere_demande"
    CLOTURE_DOUCE = "cloture_douce"
    # GF: guardrail refusal and firm close
    DEMANDE_INAPPROPRIEE = "demande_inappropriee"
    FIN_FERME = "fin_ferme"
    # PRO: maintenance mode
    MAINTENANCE = "maintenance"


class EscalationMotif(str, enum.Enum):
    """Reasons for escalation."""

    INSATISFACTION = "insatisfaction"
    DEMANDE_EXPLICITE = "demande_explicite"
    HORS_PERIMETRE = "hors_perimetre"
    RETRIEVAL_INSUFFISANT = "retrieval_insuffisant"
    # ORC: loop without resolution
    BOUCLE_SANS_ISSUE = "boucle_sans_issue"
    # GF: infraction limit reached
    INFRACTIONS = "infractions"


class ToneProfile(str, enum.Enum):
    """Tone profiles for template text."""

    FORMEL = "formel"
    CHALEUREUX = "chaleureux"
    NEUTRE = "neutre"


# ---------------------------------------------------------------------------
# Intent configuration
# ---------------------------------------------------------------------------


class SubMotif(BaseModel):
    """Sub-motif (level 2 intent refinement)."""

    id: str
    label: str
    definition: str
    examples: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Sub-motif id must not be empty")
        return v.strip()

    @model_validator(mode="after")
    def check_min_examples(self) -> SubMotif:
        if len(self.examples) < 3:
            raise ValueError(
                f"Sub-motif '{self.id}' requires at least 3 examples, "
                f"got {len(self.examples)}"
            )
        return self


class Intent(BaseModel):
    """Intent (level 1 classification target)."""

    id: str
    label: str
    definition: str
    examples: list[str] = Field(default_factory=list)
    sub_motifs: list[SubMotif] = Field(default_factory=list)
    is_system: bool = False  # hors_perimetre, demande_conseiller

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Intent id must not be empty")
        return v.strip()

    @model_validator(mode="after")
    def check_min_examples(self) -> Intent:
        if not self.is_system and len(self.examples) < 8:
            raise ValueError(
                f"Intent '{self.id}' requires at least 8 examples, "
                f"got {len(self.examples)}"
            )
        return self


# ---------------------------------------------------------------------------
# Journey parameters
# ---------------------------------------------------------------------------


class JourneyParams(BaseModel):
    """Configurable parameters of the conversation state machine."""

    seuil_haut: float = Field(default=0.75, ge=0.0, le=1.0)
    seuil_bas: float = Field(default=0.45, ge=0.0, le=1.0)
    seuil_ecart_clarification: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "M2: minimum gap between top1 and top2 scores to route directly. "
            "If top1 >= seuil_haut but top1 - top2 < seuil_ecart, clarify "
            "instead of routing. Default 0.0 = disabled (backward compat)."
        ),
    )
    seuil_sous_motif: float = Field(default=0.60, ge=0.0, le=1.0)
    max_clarifications: int = Field(default=1, ge=0, le=3)
    max_demandes: int = Field(default=5, ge=1, le=20)
    timeout_inactivite_s: int = Field(default=300, ge=30, le=3600)
    retrieval_min_score: float = Field(default=0.35, ge=0.0, le=1.0)
    retrieval_min_chunks: int = Field(default=1, ge=1, le=20)

    # --- ORC: fine-grained conversation control ---
    max_tours_par_demande: int = Field(
        default=3,
        ge=1,
        le=10,
        description=(
            "ORC-1: maximum user turns on the SAME intent within one demande "
            "before forced escalation. Counted when the resolved intent equals "
            "the previous demande's intent after an unsatisfied survey or a "
            "free reformulation."
        ),
    )
    max_duree_session_s: int = Field(
        default=1800,
        ge=120,
        le=14400,
        description=(
            "ORC-2: hard session duration budget (seconds). When exceeded at "
            "the next user turn, the FSM routes to CLOTURE_DOUCE."
        ),
    )
    max_tokens_llm_session: int = Field(
        default=8000,
        ge=500,
        le=100000,
        description=(
            "ORC-3: cumulative LLM output-token budget per session. When "
            "exhausted, next generation request routes to CLOTURE_DOUCE."
        ),
    )
    prevenir_avant_derniere_demande: bool = Field(
        default=True,
        description=(
            "ORC-4: when True, at demande n° (max_demandes - 1) the "
            "'autre_demande' prompt is replaced by 'avant_derniere_demande'."
        ),
    )

    @model_validator(mode="after")
    def thresholds_coherent(self) -> JourneyParams:
        if self.seuil_bas >= self.seuil_haut:
            raise ValueError(
                f"seuil_bas ({self.seuil_bas}) must be strictly less than "
                f"seuil_haut ({self.seuil_haut})"
            )
        return self


# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------

ALLOWED_TEMPLATE_VARIABLES = frozenset(
    {
        "nom_bot",
        "intentions_gerees",
        "temps_attente",
        "lien_escalade",
        "options",
        # ORC: graceful wind-down
        "resume_demandes",
    }
)


class MessageTemplate(BaseModel):
    """A single message template with FR/EN text."""

    key: TemplateKey
    text_fr: str
    text_en: str
    variables: list[str] = Field(default_factory=list)

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, v: list[str]) -> list[str]:
        unknown = set(v) - ALLOWED_TEMPLATE_VARIABLES
        if unknown:
            raise ValueError(f"Unknown template variables: {unknown}")
        return v


# ---------------------------------------------------------------------------
# Bot LLM config
# ---------------------------------------------------------------------------


class BotLLMConfig(BaseModel):
    """LLM configuration for the generation step."""

    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key_set: bool = False
    max_tokens: int = Field(default=600, ge=100, le=2000)
    temperature: float = Field(default=0.0, ge=0.0, le=0.0)
    timeout: int = Field(default=60, ge=10, le=300)

    # --- LLM lot: BYO provider per bot ---
    provider_source: Literal["platform", "custom"] = "platform"
    provider_type: Literal["openai_compat"] = "openai_compat"
    preset: (
        Literal["openai", "mistral", "deepseek", "ollama", "vllm", "autre"] | None
    ) = None
    base_url: str = ""
    api_key_ref: str = ""
    api_key_hint: str = ""


class TrainingParams(BaseModel):
    """L2: configurable training hyperparameters."""

    num_iterations: int = Field(default=5, ge=1, le=100)
    num_epochs: int = Field(default=1, ge=1, le=10)
    batch_size: int = Field(default=16, ge=4, le=128)


# ---------------------------------------------------------------------------
# Bot config (top-level)
# ---------------------------------------------------------------------------


class BotConfig(BaseModel):
    """Full bot configuration, persisted as config.json."""

    schema_version: int = 3
    bot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    account_id: str = ""  # T1: tenant isolation — empty = legacy (migrated to internal)
    demo: bool = False  # Q5: demo bot flag
    channel: Literal["widget", "api", "both"] = "both"
    language: Literal["fr", "en", "auto"] = "fr"
    tone_profile: ToneProfile = ToneProfile.NEUTRE
    intents: list[Intent] = Field(default_factory=list)
    journey: JourneyParams = Field(default_factory=JourneyParams)
    training: TrainingParams = Field(default_factory=TrainingParams)
    templates: dict[TemplateKey, MessageTemplate] = Field(default_factory=dict)
    knowledge_collection: str = ""
    confidentiality_filter: list[str] = Field(default_factory=lambda: ["public"])
    llm: BotLLMConfig = Field(default_factory=BotLLMConfig)
    status: Literal["draft", "published"] = "draft"

    @model_validator(mode="after")
    def validate_published(self) -> BotConfig:
        if self.status == "published":
            ids = {i.id for i in self.intents}
            if "hors_perimetre" not in ids:
                raise ValueError(
                    "Published bot must have a 'hors_perimetre' system intent"
                )
        return self


# ---------------------------------------------------------------------------
# Session / Turn / Transcript
# ---------------------------------------------------------------------------


class Turn(BaseModel):
    """A single exchange in the conversation."""

    turn_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: Literal["user", "bot", "system"]
    content: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    template_key: TemplateKey | None = None
    buttons: list[str] | None = None
    button_selected: str | None = None
    intent: str | None = None
    sub_motif: str | None = None
    sources: list[dict[str, Any]] | None = None
    # INT: interrupted generation
    interrupted: bool = False
    tokens_emitted: int | None = None


class BotSession(BaseModel):
    """Live session state for a bot conversation."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bot_id: str
    state: BotState = BotState.ACCUEIL
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_activity_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    demandes_count: int = 0
    clarifications_count_current_demande: int = 0
    reformulation_count_current_demande: int = 0
    current_intent: str | None = None
    current_sub_motif: str | None = None
    pending_candidates: list[tuple[str, float]] = Field(default_factory=list)
    original_query: str | None = None
    transcript: list[Turn] = Field(default_factory=list)
    # ORC: per-demande turn counter (same intent loop detection)
    tours_demande: int = 0
    # ORC: cumulative LLM output tokens for session budget
    tokens_llm_cumul: int = 0
    # ORC: resolved intents for resume_demandes (deterministic)
    resolved_intents: list[str] = Field(default_factory=list)
    # GF: infraction counter
    infractions: int = 0


# ---------------------------------------------------------------------------
# Trace events
# ---------------------------------------------------------------------------


class TraceEvent(BaseModel):
    """Structured trace for one step of a turn."""

    turn_id: str
    step: (
        str  # classification_l1 | classification_l2 | retrieval | generation | template
    )
    detail: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    # ORC: session counters snapshot (included in deterministic replay diff)
    counters: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Escalation contract (frozen, mock V1)
# ---------------------------------------------------------------------------


class EscalationPayload(BaseModel):
    """Payload sent to the escalation provider."""

    conversation_id: str
    transcript: list[dict[str, Any]]
    intention: str | None = None
    sous_motif: str | None = None
    motif_escalade: EscalationMotif
    horodatage: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # PRO-4: deterministic structured summary (never LLM-generated)
    resume: dict[str, Any] | None = None


class EscalationResult(BaseModel):
    """Response from the escalation provider."""

    temps_attente_estime_min: int = 4


# ---------------------------------------------------------------------------
# Engine actions — typed outputs of the FSM
# ---------------------------------------------------------------------------


class EmitTemplate(BaseModel):
    """Action: render and send a template message."""

    key: TemplateKey
    variables: dict[str, str] = Field(default_factory=dict)
    buttons: list[str] | None = None


class EmitGeneration(BaseModel):
    """Action: trigger LLM generation with filtered retrieval."""

    query: str
    intent: str
    sub_motif: str | None = None


class CallEscalation(BaseModel):
    """Action: call the escalation provider."""

    motif: EscalationMotif


class CloseSession(BaseModel):
    """Action: end the conversation."""

    reason: str = "fin"


# Union type for engine actions
Action = EmitTemplate | EmitGeneration | CallEscalation | CloseSession


# ---------------------------------------------------------------------------
# Retrieval / Generation data models
# ---------------------------------------------------------------------------


class Chunk(BaseModel):
    """A chunk of text from the knowledge base, with metadata."""

    chunk_id: str = ""
    text: str
    score: float = 0.0
    source_url: str = ""
    source_title: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Result of a filtered retrieval operation."""

    chunks: list[Chunk] = Field(default_factory=list)
    success: bool = True
    scope: str = ""  # "sub_motif" | "intent" | "fallback"
    escalate: bool = False
    escalation_motif: EscalationMotif | None = None
