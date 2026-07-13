"""LOKO Bot — Admin API endpoints.

Prefix: /api/bot
Covers: CRUD bots, intentions, templates, training, evaluation, playground.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from loko.api.session_middleware import require_session_or_ops, require_tenant_or_ops
from loko.bot.config_store import (
    delete_bot,
    list_bots,
    load_bot_config,
    save_bot_config,
)
from loko.bot.models import (
    BotConfig,
    Intent,
    JourneyParams,
    KnowledgeSource,
    MessageTemplate,
    SourceType,
    TagRule,
    TemplateKey,
)
from loko.bot.session_store import get_bot_dir, get_bots_dir


def _reject_demo_mutation(config: BotConfig | None, bot_id: str) -> None:
    """Q5: demo bots are read-only — refuse any mutation."""
    if config and config.demo:
        raise HTTPException(403, f"Bot '{bot_id}' is a demo bot (read-only).")


logger = logging.getLogger(__name__)

# T2: router no longer has a global require_admin dependency.
# Each route uses require_session_or_ops or require_tenant_or_ops.
router = APIRouter(
    prefix="/api/bot",
    tags=["bot-admin"],
)

# ---------------------------------------------------------------------------
# Training state (in-memory, per bot) — L4: backed by train_state.json
# ---------------------------------------------------------------------------

_TRAINING_STATE: dict[str, dict[str, Any]] = {}

_TRAIN_STATE_FILENAME = "train_state.json"


def _train_state_path(bot_id: str) -> Path:
    """Path to the on-disk training state file for a bot."""
    return get_bot_dir(bot_id) / _TRAIN_STATE_FILENAME


def _persist_train_state(bot_id: str) -> None:
    """Write the current in-memory training state to disk."""
    state = _TRAINING_STATE.get(bot_id)
    if not state:
        return
    # Only persist status, step, error, timestamp — not the full result
    disk_state = {
        "status": state.get("status"),
        "step": state.get("step"),
        "error": state.get("error"),
        "timestamp": state.get("timestamp", datetime.now(timezone.utc).isoformat()),
    }
    try:
        path = _train_state_path(bot_id)
        path.write_text(
            json.dumps(disk_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logger.warning("Could not persist training state for bot %s", bot_id)


def _load_train_state(bot_id: str) -> dict[str, Any] | None:
    """Read training state from disk, or None if absent."""
    try:
        path = _train_state_path(bot_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def recover_interrupted_jobs() -> None:
    """L4: on server boot, requalify any 'running' job as 'failed/interrupted'.

    Scans all bot directories for train_state.json with status == 'running'
    and marks them as failed.
    """
    bots_dir = get_bots_dir()
    if not bots_dir.is_dir():
        return
    for bot_dir in bots_dir.iterdir():
        if not bot_dir.is_dir():
            continue
        state_path = bot_dir / _TRAIN_STATE_FILENAME
        if not state_path.is_file():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if state.get("status") == "running":
            bot_id = bot_dir.name
            logger.warning(
                "Bot %s had a training job in 'running' state at boot — "
                "requalifying as 'failed/interrupted'",
                bot_id,
            )
            state["status"] = "failed"
            state["error"] = "interrupted"
            state["step"] = "interrupted"
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # Also populate in-memory state
            _TRAINING_STATE[bot_id] = {
                "status": "failed",
                "step": "interrupted",
                "error": "interrupted",
                "result": None,
            }


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class BotCreateRequest(BaseModel):
    name: str
    channel: str = "both"
    language: str = "fr"
    tone_profile: str = "neutre"


class BotUpdateRequest(BaseModel):
    name: str | None = None
    channel: str | None = None
    language: str | None = None
    tone_profile: str | None = None
    intents: list[Intent] | None = None
    journey: JourneyParams | None = None
    templates: dict[TemplateKey, MessageTemplate] | None = None
    knowledge_collection: str | None = None
    confidentiality_filter: list[str] | None = None


class TrainRequest(BaseModel):
    base_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    run_evaluation: bool = True


# ---------------------------------------------------------------------------
# Bot CRUD
# ---------------------------------------------------------------------------


@router.get("/")
async def list_all_bots(
    request: Request, _auth=Depends(require_session_or_ops)
) -> list[dict[str, str]]:
    """T2: list bots filtered by tenant (ops sees all)."""
    is_ops = getattr(request.state, "is_ops", False)
    if is_ops:
        return list_bots()
    return list_bots(account_id=request.state.account_id)


@router.post("/", status_code=201)
async def create_bot(
    req: BotCreateRequest,
    request: Request,
    _auth=Depends(require_session_or_ops),
) -> dict[str, Any]:
    """T2: new bot bound to the session's account_id. Q1: quota check."""
    is_ops = getattr(request.state, "is_ops", False)
    account_id = "" if is_ops else request.state.account_id

    # Q1: check bot creation quota
    if account_id:
        from loko.api.quotas import check_bot_creation_quota

        check_bot_creation_quota(account_id)

    config = BotConfig(
        name=req.name,
        channel=req.channel,
        language=req.language,
        tone_profile=req.tone_profile,
        account_id=account_id,
    )
    save_bot_config(config)
    return config.model_dump(mode="json")


@router.get("/{bot_id}")
async def get_bot(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")
    return config.model_dump(mode="json")


@router.get("/{bot_id}/templates/defaults")
async def get_template_defaults(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Return default templates for the bot's tone profile."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    from loko.bot.templates import get_default_templates

    defaults = get_default_templates(config.tone_profile)
    return {
        "tone": config.tone_profile.value,
        "templates": {
            k.value: t.model_dump(mode="json") for k, t in defaults.items()
        },
    }


@router.put("/{bot_id}")
async def update_bot(
    bot_id: str,
    req: BotUpdateRequest,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")
    _reject_demo_mutation(config, bot_id)

    updates = req.model_dump(exclude_none=True)

    # Validate templates: reject empty text_fr or text_en
    if "templates" in updates and updates["templates"]:
        for tkey, tpl in updates["templates"].items():
            text_fr = tpl.get("text_fr", "") if isinstance(tpl, dict) else ""
            text_en = tpl.get("text_en", "") if isinstance(tpl, dict) else ""
            if not text_fr.strip() or not text_en.strip():
                raise HTTPException(
                    422,
                    f"Le template '{tkey}' a un texte vide — "
                    "supprimez-le pour revenir au défaut, ou renseignez-le.",
                )

    updated = config.model_copy(update=updates)
    save_bot_config(updated)

    # Invalidate cached orchestrator so next request picks up new config
    from loko.api.bot_public import invalidate_orchestrator

    invalidate_orchestrator(bot_id)

    return updated.model_dump(mode="json")


@router.delete("/{bot_id}")
async def delete_bot_endpoint(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, str]:
    config = load_bot_config(bot_id)
    _reject_demo_mutation(config, bot_id)
    if not delete_bot(bot_id):
        raise HTTPException(404, "Not found")
    return {"status": "deleted", "bot_id": bot_id}


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


@router.post("/{bot_id}/publish")
async def publish_bot(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    _reject_demo_mutation(config, bot_id)

    # Validation checks
    errors: list[str] = []
    intent_ids = {i.id for i in config.intents}

    if "hors_perimetre" not in intent_ids:
        errors.append("L'intention systeme 'hors_perimetre' est requise.")

    for intent in config.intents:
        if not intent.is_system and len(intent.examples) < 8:
            errors.append(
                f"L'intention '{intent.label}' n'a que {len(intent.examples)} exemples (min 8)."
            )

    # Business validation errors → 400 (before model integrity)
    if errors:
        raise HTTPException(400, {"errors": errors})

    # A4/A5: verify model integrity (manifest + hashes + smoke test)
    # Model integrity failures → 422 with machine code (K1)
    from loko.bot.classifier.manifest import manifest_exists, verify_model
    from loko.bot.errors import ModelIntegrityError

    if not manifest_exists(bot_id):
        raise ModelIntegrityError(
            bot_id,
            "manifest_missing",
            "Aucun manifeste d'integrite. Relancez l'entrainement.",
        )

    verification = verify_model(bot_id)
    if not verification.ok:
        code = verification.error_code or "verification_error"
        detail = "; ".join(verification.errors)
        raise ModelIntegrityError(bot_id, code, detail)

    # A5: check if training data changed since last training
    from loko.bot.classifier.manifest import compute_dataset_hash, read_manifest
    from loko.bot.classifier.setfit_service import prepare_l1_training_data

    texts, labels = prepare_l1_training_data(config)
    current_hash = compute_dataset_hash(texts, labels)
    manifest = read_manifest(bot_id)
    if manifest and manifest.get("dataset_hash") != current_hash:
        raise ModelIntegrityError(
            bot_id,
            "retrain_required",
            "Les exemples ont change depuis le dernier entrainement.",
        )

    # R2-c: knowledge base coverage warnings
    warnings: list[str] = []
    try:
        from loko.bot.knowledge_store import get_knowledge_store

        kb = get_knowledge_store(bot_id)
        non_system = [i for i in config.intents if not i.is_system]
        coverage = kb.get_coverage([i.id for i in non_system])

        for intent in non_system:
            if coverage.get(intent.id, 0) == 0:
                warnings.append(
                    f"Aucun document pour l'intention '{intent.label}'. "
                    f"Le bot escaladera systématiquement sur ce sujet."
                )

        if not kb.has_documents():
            warnings.append(
                "Aucun document dans la base de connaissances. "
                "Le bot ne pourra pas générer de réponses contextuelles."
            )
    except Exception:
        warnings.append("Impossible de vérifier la base de connaissances.")

    updated = config.model_copy(update={"status": "published"})
    save_bot_config(updated)

    # PRO-2: create release snapshot
    try:
        from loko.bot.versioning import get_release_store

        release_store = get_release_store()
        model_hash = ""
        if manifest:
            model_hash = manifest.get("model_hash", "")
        release = release_store.create_release(
            bot_id=bot_id,
            config_dict=updated.model_dump(mode="json"),
            model_hash=model_hash,
        )
        logger.info("Created release v%d for bot %s", release.version, bot_id)
    except Exception as exc:
        logger.warning("Could not create release snapshot: %s", exc)

    # Invalidate cached orchestrator so runtime picks up new status
    from loko.api.bot_public import invalidate_orchestrator

    invalidate_orchestrator(bot_id)

    result: dict[str, Any] = {"status": "published", "bot_id": bot_id}
    if warnings:
        result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


@router.post("/{bot_id}/train")
async def train_bot(
    bot_id: str,
    req: TrainRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    _reject_demo_mutation(config, bot_id)

    # R2-a: LOKO_ML guard — refuse training when ML is explicitly disabled
    import os

    if os.environ.get("LOKO_ML", "on").lower() == "off":
        raise HTTPException(
            503,
            "ML features are disabled (LOKO_ML=off). "
            "Set LOKO_ML=on to enable training.",
        )

    if bot_id in _TRAINING_STATE and _TRAINING_STATE[bot_id].get("status") == "running":
        raise HTTPException(409, "Training already in progress")

    # Validate intents have enough examples before starting training
    errors = []
    for intent in config.intents:
        if intent.is_system:
            continue
        n = len([e for e in intent.examples if e.strip()])
        if n < 8:
            errors.append(
                f"Intent '{intent.label or intent.id}' : {n}/8 exemples minimum"
            )
        for sm in intent.sub_motifs:
            sn = len([e for e in sm.examples if e.strip()])
            if sn < 3:
                errors.append(
                    f"Sous-motif '{sm.label or sm.id}' : {sn}/3 exemples minimum"
                )
    if errors:
        raise HTTPException(422, ". ".join(errors))

    _TRAINING_STATE[bot_id] = {
        "status": "running",
        "step": "queued",
        "result": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _persist_train_state(bot_id)

    background_tasks.add_task(
        _run_training_background,
        config,
        req.base_model,
        req.run_evaluation,
    )

    return {"status": "started", "bot_id": bot_id}


@router.get("/{bot_id}/train/status")
async def get_training_status(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    state = _TRAINING_STATE.get(bot_id)
    if not state:
        # L4: check disk for persisted state (e.g. after restart)
        disk_state = _load_train_state(bot_id)
        if disk_state:
            return {"bot_id": bot_id, **disk_state}
        return {"status": "idle", "bot_id": bot_id}
    return {"bot_id": bot_id, **state}


@router.get("/{bot_id}/evaluation")
async def get_evaluation(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    state = _TRAINING_STATE.get(bot_id)
    if not state or not state.get("result"):
        raise HTTPException(404, "No evaluation available. Train the bot first.")
    result = state["result"]
    evaluation = result.get("evaluation")
    if not evaluation:
        raise HTTPException(404, "Evaluation was not run during training.")
    return evaluation


@router.get("/{bot_id}/train/report")
async def get_training_report(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Full training report (B2): confusion matrix, F1, advice, latency, manifest."""
    state = _TRAINING_STATE.get(bot_id)
    if not state or not state.get("result"):
        raise HTTPException(404, "No training report available. Train the bot first.")

    result = state["result"]

    report: dict[str, Any] = {
        "bot_id": bot_id,
        "level1": result.get("level1", {}),
        "level2": result.get("level2", {}),
        "evaluation": result.get("evaluation"),
        "inference_latency_ms": result.get("inference_latency_ms"),
        "manifest": result.get("manifest"),
    }

    # Enrich with manifest data if available
    from loko.bot.classifier.manifest import read_manifest

    manifest = read_manifest(bot_id)
    if manifest:
        report["manifest_data"] = {
            "created_at": manifest.get("created_at"),
            "dataset_hash": manifest.get("dataset_hash"),
            "inference_latency_ms": manifest.get("inference_latency_ms"),
        }

    return report


# ---------------------------------------------------------------------------
# R2-b: Knowledge base / document management endpoints
# ---------------------------------------------------------------------------


class IngestDocumentRequest(BaseModel):
    """Request body for document ingestion."""

    content: str = Field(..., min_length=1, max_length=500_000)
    source_url: str = ""
    source_title: str = ""
    bot_intents: list[str] = Field(default_factory=list)
    bot_sub_motifs: list[str] = Field(default_factory=list)
    confidentiality: str = "public"


class UpdateTagsRequest(BaseModel):
    """Request body for bulk tag updates."""

    doc_ids: list[str] = Field(..., min_length=1)
    bot_intents: list[str] | None = None
    bot_sub_motifs: list[str] | None = None


class CrawlTagRule(BaseModel):
    """URL-pattern based tagging applied at ingestion (WEB sources)."""

    pattern: str  # glob on the URL path, e.g. "/aide/remboursements/*"
    bot_intents: list[str] = Field(default_factory=list)
    bot_sub_motifs: list[str] = Field(default_factory=list)
    confidentiality: str | None = None  # override, e.g. "confidentiel"


class CrawlFAQRequest(BaseModel):
    """Request body for FAQ web crawl + optional ingestion."""

    start_url: str = Field(..., min_length=1)
    max_depth: int = Field(default=3, ge=1, le=10)
    max_pages: int = Field(default=200, ge=1, le=5000)
    follow_iframes: bool = True
    use_playwright: bool = True
    allow_private_networks: bool = False
    min_content_length: int = Field(default=50, ge=10)
    ingest: bool = True
    document_url_patterns: list[str] = Field(default_factory=list)
    confidentiality: str = "public"
    tag_rules: list[CrawlTagRule] = Field(default_factory=list)
    default_tags: CrawlTagRule | None = None
    source_id: str | None = None


# ---------------------------------------------------------------------------
# Knowledge sources CRUD  (§5.4)
# ---------------------------------------------------------------------------


class SourceCreateRequest(BaseModel):
    """Request body for creating a knowledge source."""

    type: SourceType
    label: str = Field(..., min_length=1, max_length=200)
    start_url: str = ""
    document_url_patterns: list[str] = Field(default_factory=list)
    tag_rules: list[TagRule] = Field(default_factory=list)
    default_tags: TagRule | None = None
    bot_intents: list[str] = Field(default_factory=list)
    bot_sub_motifs: list[str] = Field(default_factory=list)
    confidentiality: str = "public"
    resync_enabled: bool = False

    model_config = {"extra": "forbid"}


class SourceUpdateRequest(BaseModel):
    """Request body for updating a knowledge source."""

    label: str | None = None
    start_url: str | None = None
    document_url_patterns: list[str] | None = None
    tag_rules: list[TagRule] | None = None
    default_tags: TagRule | None = Field(default=None)
    bot_intents: list[str] | None = None
    bot_sub_motifs: list[str] | None = None
    confidentiality: str | None = None
    resync_enabled: bool | None = None

    model_config = {"extra": "forbid"}


def _validate_source_intents(
    config: BotConfig, bot_intents: list[str], bot_sub_motifs: list[str]
) -> None:
    """Validate that intent/sub-motif ids exist in the bot config (K1)."""
    intent_ids = {i.id for i in config.intents}
    sub_motif_map: dict[str, set[str]] = {}
    for intent in config.intents:
        sub_motif_map[intent.id] = {sm.id for sm in intent.sub_motifs}

    for iid in bot_intents:
        if iid not in intent_ids:
            raise HTTPException(
                422,
                f"source_invalid: intent '{iid}' does not exist in bot config",
            )
    for smid in bot_sub_motifs:
        found = False
        for iid in bot_intents:
            if iid in sub_motif_map and smid in sub_motif_map[iid]:
                found = True
                break
        if not found:
            raise HTTPException(
                422,
                f"source_invalid: sub-motif '{smid}' is not a child of "
                f"the declared intents {bot_intents}",
            )


def _validate_tag_rules(config: BotConfig, rules: list[TagRule]) -> None:
    """Validate tag rules: check glob syntax and intent existence."""
    from fnmatch import translate

    for rule in rules:
        try:
            translate(rule.pattern)
        except Exception:
            raise HTTPException(
                422,
                f"source_invalid: invalid glob pattern '{rule.pattern}'",
            )
        _validate_source_intents(config, rule.bot_intents, rule.bot_sub_motifs)


@router.get("/{bot_id}/sources")
async def list_sources(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> list[dict[str, Any]]:
    """List all knowledge sources for a bot."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    from loko.bot.knowledge_store import get_knowledge_store

    store = get_knowledge_store(bot_id)
    result = []
    for src in config.knowledge_sources:
        doc_count = store.count_by_source(src.id)
        data = src.model_dump(mode="json")
        data["document_count"] = doc_count
        result.append(data)
    return result


@router.post("/{bot_id}/sources", status_code=201)
async def create_source(
    bot_id: str,
    req: SourceCreateRequest,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Create a new knowledge source."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    _reject_demo_mutation(config, bot_id)

    # Validate intents/sub-motifs
    _validate_source_intents(config, req.bot_intents, req.bot_sub_motifs)
    if req.tag_rules:
        _validate_tag_rules(config, req.tag_rules)
    if req.default_tags:
        _validate_source_intents(
            config, req.default_tags.bot_intents, req.default_tags.bot_sub_motifs
        )

    source = KnowledgeSource(
        type=req.type,
        label=req.label,
        start_url=req.start_url,
        document_url_patterns=req.document_url_patterns,
        tag_rules=req.tag_rules,
        default_tags=req.default_tags,
        bot_intents=req.bot_intents,
        bot_sub_motifs=req.bot_sub_motifs,
        confidentiality=req.confidentiality,
        resync_enabled=req.resync_enabled,
    )
    config.knowledge_sources.append(source)
    save_bot_config(config)
    return source.model_dump(mode="json")


@router.put("/{bot_id}/sources/{source_id}")
async def update_source(
    bot_id: str,
    source_id: str,
    req: SourceUpdateRequest,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Update an existing knowledge source."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    _reject_demo_mutation(config, bot_id)

    source = next((s for s in config.knowledge_sources if s.id == source_id), None)
    if not source:
        raise HTTPException(404, f"Source {source_id} not found")

    updates = req.model_dump(exclude_unset=True)

    # Validate if intents/sub-motifs are being changed
    new_intents = updates.get("bot_intents", source.bot_intents)
    new_sub_motifs = updates.get("bot_sub_motifs", source.bot_sub_motifs)
    _validate_source_intents(config, new_intents, new_sub_motifs)

    if "tag_rules" in updates and updates["tag_rules"]:
        rules = [
            TagRule(**r) if isinstance(r, dict) else r for r in updates["tag_rules"]
        ]
        _validate_tag_rules(config, rules)
    if "default_tags" in updates and updates["default_tags"]:
        dt = updates["default_tags"]
        if isinstance(dt, dict):
            dt = TagRule(**dt)
        _validate_source_intents(config, dt.bot_intents, dt.bot_sub_motifs)

    for key, value in updates.items():
        setattr(source, key, value)

    save_bot_config(config)
    return source.model_dump(mode="json")


@router.delete("/{bot_id}/sources/{source_id}")
async def delete_source(
    bot_id: str,
    source_id: str,
    request: Request,
    delete_documents: bool = False,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Delete a knowledge source. Optionally delete its documents."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    _reject_demo_mutation(config, bot_id)

    source = next((s for s in config.knowledge_sources if s.id == source_id), None)
    if not source:
        raise HTTPException(404, f"Source {source_id} not found")

    docs_deleted = 0
    if delete_documents:
        from loko.bot.knowledge_store import get_knowledge_store

        store = get_knowledge_store(bot_id)
        docs_deleted = store.delete_by_source(source_id)

    config.knowledge_sources = [
        s for s in config.knowledge_sources if s.id != source_id
    ]
    save_bot_config(config)

    return {
        "deleted": source_id,
        "documents_deleted": docs_deleted,
    }


@router.post("/{bot_id}/documents", status_code=201)
async def ingest_document(
    bot_id: str,
    req: IngestDocumentRequest,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Ingest a document into the knowledge base."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    _reject_demo_mutation(config, bot_id)

    # Q1: check document quota
    if config.account_id:
        from loko.api.quotas import check_document_quota

        check_document_quota(config.account_id, bot_id)

    from loko.bot.knowledge_store import get_knowledge_store

    store = get_knowledge_store(bot_id)
    doc_id = store.ingest_document(
        req.content,
        source_url=req.source_url,
        source_title=req.source_title,
        bot_intents=req.bot_intents,
        bot_sub_motifs=req.bot_sub_motifs,
        confidentiality=req.confidentiality,
    )
    if not config.knowledge_collection:
        config.knowledge_collection = bot_id
        save_bot_config(config)

    return {"doc_id": doc_id, "bot_id": bot_id}


@router.post("/{bot_id}/knowledge/crawl")
async def crawl_faq_web(
    bot_id: str,
    req: CrawlFAQRequest,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Crawl a FAQ/help-center URL and optionally ingest discovered documents."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    _reject_demo_mutation(config, bot_id)

    import re
    from urllib.parse import urlparse

    from loko.connectors.faq_web_crawler import CrawlConfig, FAQWebCrawler
    from loko.connectors.playwright_fetcher import get_page_fetcher

    parsed = urlparse(req.start_url)
    allowed_netloc = parsed.netloc
    allowed_hostname = parsed.hostname or allowed_netloc

    fetcher = get_page_fetcher(
        prefer_playwright=req.use_playwright,
        allowed_domains=[allowed_hostname],
        allow_private_networks=req.allow_private_networks,
    )
    crawler = FAQWebCrawler(
        CrawlConfig(
            start_url=req.start_url,
            max_depth=req.max_depth,
            max_pages=req.max_pages,
            allowed_domains=[allowed_netloc] if allowed_netloc else [],
            follow_iframes=req.follow_iframes,
            min_content_length=req.min_content_length,
            confidentiality=req.confidentiality,
        ),
        fetcher=fetcher,
    )
    result = crawler.crawl()

    documents = result.documents
    if req.document_url_patterns:
        patterns = [re.compile(pattern) for pattern in req.document_url_patterns]
        documents = [
            doc
            for doc in documents
            if any(pattern.search(doc.url) for pattern in patterns)
        ]

    # -- Evaluate tag_rules for each document (first match wins) ----------
    from fnmatch import fnmatch

    def _resolve_tags(
        doc_url: str,
    ) -> tuple[list[str], list[str], str, bool]:
        """Return (intents, sub_motifs, confidentiality, tagged)."""
        doc_path = urlparse(doc_url).path
        for rule in req.tag_rules:
            if fnmatch(doc_path, rule.pattern):
                return (
                    rule.bot_intents,
                    rule.bot_sub_motifs,
                    rule.confidentiality or req.confidentiality,
                    bool(rule.bot_intents),
                )
        if req.default_tags:
            return (
                req.default_tags.bot_intents,
                req.default_tags.bot_sub_motifs,
                req.default_tags.confidentiality or req.confidentiality,
                bool(req.default_tags.bot_intents),
            )
        return [], [], req.confidentiality, False

    untagged_paths: list[str] = []
    tagged_docs: list[dict[str, Any]] = []
    for doc in documents:
        intents, sub_motifs, conf, is_tagged = _resolve_tags(doc.url)
        tagged_docs.append(
            {
                "doc": doc,
                "bot_intents": intents,
                "bot_sub_motifs": sub_motifs,
                "confidentiality": conf,
                "tagged": is_tagged,
            }
        )
        if not is_tagged:
            untagged_paths.append(urlparse(doc.url).path)

    # -- Ingestion ---------------------------------------------------------
    ingested: list[dict[str, str]] = []
    if req.ingest and documents:
        from loko.bot.knowledge_store import get_knowledge_store

        store = get_knowledge_store(bot_id)
        for entry in tagged_docs:
            doc = entry["doc"]
            doc_id = store.ingest_document(
                doc.content,
                source_url=doc.url,
                source_title=doc.title,
                bot_intents=entry["bot_intents"] or None,
                bot_sub_motifs=entry["bot_sub_motifs"] or None,
                confidentiality=entry["confidentiality"],
                doc_id=doc.doc_id,
                source_id=req.source_id,
            )
            ingested.append(
                {
                    "doc_id": doc_id,
                    "url": doc.url,
                    "title": doc.title,
                }
            )
        config_changed = False
        if ingested and not config.knowledge_collection:
            config.knowledge_collection = bot_id
            config_changed = True
        # Update last_ingest on the source if source_id provided
        if req.source_id and ingested:
            from loko.bot.models import IngestSummary

            source = next(
                (s for s in config.knowledge_sources if s.id == req.source_id),
                None,
            )
            if source:
                source.last_ingest = IngestSummary(
                    at=datetime.now(timezone.utc).isoformat(),
                    discovered=len(result.documents),
                    ingested=len(ingested),
                    untagged=len(untagged_paths),
                    errors=len(result.errors),
                )
                config_changed = True
        if config_changed:
            save_bot_config(config)

    return {
        "bot_id": bot_id,
        "urls_visited": result.urls_visited,
        "urls_skipped": result.urls_skipped,
        "errors": result.errors,
        "documents_discovered": len(result.documents),
        "documents_selected": len(documents),
        "documents_ingested": len(ingested),
        "documents_untagged": len(untagged_paths),
        "untagged_paths": untagged_paths,
        "documents": [
            {
                "doc_id": entry["doc"].doc_id,
                "url": entry["doc"].url,
                "title": entry["doc"].title,
                "content_hash": entry["doc"].content_hash,
                "content_preview": entry["doc"].content[:500],
                "bot_intents": entry["bot_intents"],
                "bot_sub_motifs": entry["bot_sub_motifs"],
                "confidentiality": entry["confidentiality"],
                "tagged": entry["tagged"],
            }
            for entry in tagged_docs
        ],
        "ingested": ingested,
    }


@router.get("/{bot_id}/documents")
async def list_documents(
    bot_id: str,
    intent: str | None = None,
    request: Request = None,
    _auth=Depends(require_tenant_or_ops),
) -> list[dict[str, Any]]:
    """List documents in the knowledge base, optionally filtered by intent."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    from loko.bot.knowledge_store import get_knowledge_store

    store = get_knowledge_store(bot_id)
    return store.list_documents(intent=intent)


@router.delete("/{bot_id}/documents/{doc_id}")
async def delete_document(
    bot_id: str,
    doc_id: str,
    request: Request = None,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, str]:
    """Delete a document from the knowledge base."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    _reject_demo_mutation(config, bot_id)

    from loko.bot.knowledge_store import get_knowledge_store

    store = get_knowledge_store(bot_id)
    if not store.delete_document(doc_id):
        raise HTTPException(404, "Document not found")

    return {"status": "deleted", "doc_id": doc_id}


@router.patch("/{bot_id}/documents/tags")
async def update_document_tags(
    bot_id: str,
    req: UpdateTagsRequest,
    request: Request = None,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Bulk-update intent/sub-motif tags on documents."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    _reject_demo_mutation(config, bot_id)

    from loko.bot.knowledge_store import get_knowledge_store

    store = get_knowledge_store(bot_id)
    updated = store.update_tags(
        req.doc_ids,
        bot_intents=req.bot_intents,
        bot_sub_motifs=req.bot_sub_motifs,
    )

    return {"updated": updated}


@router.get("/{bot_id}/knowledge/coverage")
async def get_knowledge_coverage(
    bot_id: str,
    request: Request = None,
    _auth=Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Return document count per intent (for publication readiness checks)."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    from loko.bot.knowledge_store import get_knowledge_store

    store = get_knowledge_store(bot_id)
    intent_ids = [i.id for i in config.intents if not i.is_system]
    coverage = store.get_coverage(intent_ids)

    return {
        "bot_id": bot_id,
        "coverage": coverage,
        "total_documents": sum(coverage.values()),
    }


def _run_training_background(
    config: BotConfig,
    base_model: str,
    run_evaluation: bool,
) -> None:
    """Background task for training (runs in thread)."""
    from loko.bot.classifier.training import train_bot_classifiers

    bot_id = config.bot_id

    def on_progress(step: str, detail: dict[str, Any]) -> None:
        _TRAINING_STATE[bot_id]["step"] = step
        if step == "done":
            _TRAINING_STATE[bot_id]["status"] = "completed"

    try:
        result = train_bot_classifiers(
            config,
            base_model=base_model,
            run_evaluation=run_evaluation,
            on_progress=on_progress,
        )
        _TRAINING_STATE[bot_id]["result"] = result
        _TRAINING_STATE[bot_id]["status"] = "completed"
        _persist_train_state(bot_id)
    except Exception as exc:
        logger.exception("Training failed for bot %s", bot_id)
        _TRAINING_STATE[bot_id]["status"] = "failed"
        _TRAINING_STATE[bot_id]["error"] = str(exc)
        _persist_train_state(bot_id)


# ---------------------------------------------------------------------------
# LLM configuration (Lot LLM §6.4) — BYO key per bot
# ---------------------------------------------------------------------------


class LLMConfigRequest(BaseModel):
    """Request body for PUT /api/bot/{bot_id}/llm."""

    provider_source: str = "custom"
    preset: str | None = None
    base_url: str = ""
    model: str = ""
    api_key: str | None = None  # write-only, never returned


class LLMTestRequest(BaseModel):
    """Request body for POST /api/bot/{bot_id}/llm/test."""

    base_url: str
    model: str
    api_key: str


@router.put("/{bot_id}/llm")
async def update_llm_config(
    bot_id: str,
    req: LLMConfigRequest,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Update the LLM configuration for a bot (write-only key)."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")
    _reject_demo_mutation(config, bot_id)

    # Validate base_url with SSRF check
    if req.provider_source == "custom" and req.base_url:
        from loko.security.ssrf import validate_url, SSRFError

        try:
            validate_url(req.base_url)
        except SSRFError as exc:
            raise HTTPException(422, f"base_url blocked: {exc.reason}")

    # Store API key in secret store if provided
    api_key_ref = config.llm.api_key_ref
    api_key_hint = config.llm.api_key_hint
    if req.api_key:
        from loko.security.secret_store import get_secret_store

        store = get_secret_store()
        # Delete old key if exists
        if api_key_ref:
            store.delete(api_key_ref)
        api_key_ref = store.put(req.api_key)
        api_key_hint = req.api_key[-4:] if len(req.api_key) >= 4 else "****"

    # Update config
    llm = config.llm.model_copy(
        update={
            "provider_source": req.provider_source,
            "preset": req.preset,
            "base_url": req.base_url,
            "model": req.model or config.llm.model,
            "api_key_ref": api_key_ref,
            "api_key_hint": api_key_hint,
            "api_key_set": bool(api_key_ref),
        }
    )
    config = config.model_copy(update={"llm": llm})
    save_bot_config(config)

    # Invalidate orchestrator cache
    from loko.api.bot_public import invalidate_orchestrator

    invalidate_orchestrator(bot_id)

    return {
        "status": "updated",
        "provider_source": llm.provider_source,
        "base_url": llm.base_url,
        "model": llm.model,
        "api_key_hint": llm.api_key_hint,
    }


@router.get("/{bot_id}/llm")
async def get_llm_config(
    bot_id: str,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Get LLM config (without the key — only hint)."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    llm = config.llm
    return {
        "provider_source": llm.provider_source,
        "provider_type": llm.provider_type,
        "preset": llm.preset,
        "base_url": llm.base_url,
        "model": llm.model,
        "api_key_set": llm.api_key_set,
        "api_key_hint": llm.api_key_hint,
        "max_tokens": llm.max_tokens,
        "timeout": llm.timeout,
    }


# LLM-§6.6: rate limit for test endpoint (5 per minute per account)
_LLM_TEST_ATTEMPTS: dict[str, list[float]] = {}
_LLM_TEST_WINDOW = 60  # seconds
_LLM_TEST_MAX = 5


def _check_llm_test_rate(request: Request) -> None:
    """Enforce rate limit on LLM test endpoint (5/min per account)."""
    import time as _t

    account_id = getattr(request.state, "account_id", None) or (
        request.client.host if request.client else "unknown"
    )
    now = _t.time()
    attempts = _LLM_TEST_ATTEMPTS.get(account_id, [])
    _LLM_TEST_ATTEMPTS[account_id] = [t for t in attempts if now - t < _LLM_TEST_WINDOW]
    if len(_LLM_TEST_ATTEMPTS[account_id]) >= _LLM_TEST_MAX:
        raise HTTPException(429, "LLM test rate limit exceeded (5/min)")
    _LLM_TEST_ATTEMPTS[account_id].append(now)


@router.post("/{bot_id}/llm/test")
async def test_llm_connection(
    bot_id: str,
    req: LLMTestRequest,
    request: Request,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Test LLM connection with a minimal request (5 tokens, temp=0)."""
    import time

    _check_llm_test_rate(request)

    # SSRF validation
    from loko.security.ssrf import validate_url, SSRFError

    try:
        validate_url(req.base_url)
    except SSRFError as exc:
        return {"ok": False, "error_code": "ssrf_blocked", "detail": exc.reason}

    from loko.bot.llm.openai_compat import OpenAICompatProvider, LLMProviderError

    provider = OpenAICompatProvider(
        base_url=req.base_url,
        api_key=req.api_key,
        model=req.model,
    )

    t0 = time.perf_counter()
    ttfb: float | None = None

    try:
        tokens = []
        async for token in provider.stream_chat(
            messages=[{"role": "user", "content": "Say hello."}],
            model=req.model,
            temperature=0.0,
            max_tokens=5,
            timeout=15,
        ):
            if ttfb is None:
                ttfb = (time.perf_counter() - t0) * 1000
            tokens.append(token)

        total_ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": True,
            "model": req.model,
            "ttfb_ms": round(ttfb or total_ms),
            "total_ms": round(total_ms),
        }

    except LLMProviderError as exc:
        code = "timeout"
        if exc.status_code == 401:
            code = "auth_failed"
        elif exc.status_code == 404:
            code = "model_unknown"
        elif exc.status_code == 429:
            code = "rate_limited"
        elif exc.status_code >= 400:
            code = "provider_error"
        return {"ok": False, "error_code": code, "detail": str(exc)}
    except Exception as exc:
        return {"ok": False, "error_code": "unreachable", "detail": str(exc)}


# ---------------------------------------------------------------------------
# PRO-2: Versioning and rollback (§7.2)
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/releases")
async def list_releases(
    bot_id: str,
    _auth: Any = Depends(require_tenant_or_ops),
) -> list[dict[str, Any]]:
    """List all releases for a bot, newest first."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    from loko.bot.versioning import get_release_store

    store = get_release_store()
    releases = store.list_releases(bot_id)
    return [r.model_dump(mode="json") for r in releases]


@router.post("/{bot_id}/rollback/{version}")
async def rollback_release(
    bot_id: str,
    version: int,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Rollback to a previous release version."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")
    _reject_demo_mutation(config, bot_id)

    from loko.bot.versioning import get_release_store

    store = get_release_store()

    # Get release config
    release_config = store.get_release_config(bot_id, version)
    if release_config is None:
        raise HTTPException(404, f"Release v{version} not found or corrupted")

    # Check model integrity for the release
    releases = store.list_releases(bot_id)
    target_release = next((r for r in releases if r.version == version), None)
    if not target_release:
        raise HTTPException(404, f"Release v{version} not found")

    if target_release.model_hash:
        from loko.bot.classifier.manifest import read_manifest

        manifest = read_manifest(bot_id)
        if not manifest:
            raise HTTPException(
                422,
                {
                    "error": "retrain_required",
                    "detail": "Model manifest missing. Retrain before rollback.",
                },
            )
        if manifest.get("model_hash", "") != target_release.model_hash:
            raise HTTPException(
                422,
                {
                    "error": "retrain_required",
                    "detail": "Model has changed since this release. Retrain required.",
                },
            )

    # Activate the release
    if not store.activate_release(bot_id, version):
        raise HTTPException(404, f"Release v{version} not found")

    # Restore config from release
    restored = BotConfig(**release_config)
    save_bot_config(restored)

    # Invalidate orchestrator cache
    from loko.api.bot_public import invalidate_orchestrator

    invalidate_orchestrator(bot_id)

    return {
        "status": "rolled_back",
        "bot_id": bot_id,
        "version": version,
    }


# ---------------------------------------------------------------------------
# PRO-7: Maintenance mode (§7.7)
# ---------------------------------------------------------------------------


class MaintenanceRequest(BaseModel):
    enabled: bool
    message_override: str | None = None


@router.post("/{bot_id}/maintenance")
async def set_maintenance_mode(
    bot_id: str,
    req: MaintenanceRequest,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Enable or disable maintenance mode for a bot."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    from loko.bot.maintenance import set_maintenance

    state = set_maintenance(bot_id, req.enabled, req.message_override)

    return {
        "bot_id": bot_id,
        "maintenance": state["enabled"],
        "message_override": state.get("message_override") or None,
    }


@router.get("/{bot_id}/maintenance")
async def get_maintenance_mode(
    bot_id: str,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Get maintenance mode status for a bot."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    from loko.bot.maintenance import is_maintenance, get_maintenance_message

    return {
        "bot_id": bot_id,
        "maintenance": is_maintenance(bot_id),
        "message_override": get_maintenance_message(bot_id),
    }


# ---------------------------------------------------------------------------
# PRO-6: Quota management (§7.6)
# ---------------------------------------------------------------------------


class QuotaConfigRequest(BaseModel):
    sessions_mois: int = Field(default=0, ge=0)
    messages_mois: int = Field(default=0, ge=0)
    tokens_llm_mois: int = Field(default=0, ge=0)


@router.put("/{bot_id}/quotas")
async def set_quotas(
    bot_id: str,
    req: QuotaConfigRequest,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Set monthly quotas for a bot's API keys."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    import os

    quota_dir = Path(os.environ.get("LOKO_DATA_DIR", "data")) / "quota_configs"
    quota_dir.mkdir(parents=True, exist_ok=True)
    quota_path = quota_dir / f"{bot_id}.json"
    quota_path.write_text(
        json.dumps(req.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "bot_id": bot_id,
        "quotas": req.model_dump(),
    }


@router.get("/{bot_id}/quotas/usage")
async def get_quota_usage(
    bot_id: str,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Get current quota usage for all keys of a bot."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    from loko.api.api_keys import list_api_keys
    from loko.bot.quota_usage import get_quota_usage_store

    store = get_quota_usage_store()
    keys = list_api_keys(bot_id)
    usage = {}
    for key in keys:
        key_id = key["key_id"]
        usage[key_id] = {
            "label": key.get("label", ""),
            **store.get_usage(key_id),
        }

    return {
        "bot_id": bot_id,
        "usage": usage,
    }


@router.delete("/{bot_id}/llm/key")
async def delete_llm_key(
    bot_id: str,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, str]:
    """Revoke the custom LLM API key."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")
    _reject_demo_mutation(config, bot_id)

    if config.llm.api_key_ref:
        from loko.security.secret_store import get_secret_store

        get_secret_store().delete(config.llm.api_key_ref)

    llm = config.llm.model_copy(
        update={
            "api_key_ref": "",
            "api_key_hint": "",
            "api_key_set": False,
        }
    )
    config = config.model_copy(update={"llm": llm})
    save_bot_config(config)

    from loko.api.bot_public import invalidate_orchestrator

    invalidate_orchestrator(bot_id)

    return {"status": "key_revoked"}


# ---------------------------------------------------------------------------
# GF-A8: Guardrails config (§4.8)
# ---------------------------------------------------------------------------


class GuardrailsConfigRequest(BaseModel):
    enabled: bool = True
    rules: list[dict[str, Any]] = Field(default_factory=list)
    max_infractions: int = Field(default=2, ge=1, le=5)
    action_apres_max: str = "fin_ferme"
    seuil_rejet_fort: float = Field(default=0.85, ge=0.0, le=1.0)
    block_low_grounding: bool = False


@router.put("/{bot_id}/guardrails")
async def update_guardrails(
    bot_id: str,
    req: GuardrailsConfigRequest,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Update guardrails config with server-side is_system validation (GF-A8)."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")
    _reject_demo_mutation(config, bot_id)

    from loko.bot.guardrails import default_ruleset

    # GF-A8: ensure all system rules are present and unmodified
    system_rules = {r["id"]: r for r in default_ruleset()}
    submitted_system_ids = set()

    for rule in req.rules:
        rule_id = rule.get("id", "")
        if rule.get("is_system"):
            submitted_system_ids.add(rule_id)
            if rule_id not in system_rules:
                raise HTTPException(
                    422, f"Unknown system rule '{rule_id}' cannot have is_system=true"
                )

    # Check that no system rule was removed
    missing_system = set(system_rules.keys()) - submitted_system_ids
    if missing_system:
        raise HTTPException(
            422,
            f"System rules cannot be removed: {', '.join(sorted(missing_system))}",
        )

    # Persist guardrails config to bot directory
    guardrails_path = get_bot_dir(bot_id) / "guardrails.json"
    guardrails_path.write_text(
        json.dumps(req.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Invalidate orchestrator so it picks up new guardrails
    from loko.api.bot_public import invalidate_orchestrator

    invalidate_orchestrator(bot_id)

    return {"status": "updated", "bot_id": bot_id}


@router.get("/{bot_id}/guardrails")
async def get_guardrails(
    bot_id: str,
    _auth: Any = Depends(require_tenant_or_ops),
) -> dict[str, Any]:
    """Get current guardrails config for a bot."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, "Not found")

    guardrails_path = get_bot_dir(bot_id) / "guardrails.json"
    if guardrails_path.is_file():
        return json.loads(guardrails_path.read_text(encoding="utf-8"))

    # Return defaults
    from loko.bot.guardrails import default_ruleset, GuardrailsConfig, GuardrailRule

    default_config = GuardrailsConfig(
        rules=[GuardrailRule(**r) for r in default_ruleset()]
    )
    return default_config.model_dump(mode="json")
