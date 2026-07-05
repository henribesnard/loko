"""LOKO Bot — Admin API endpoints.

Prefix: /api/bot
Covers: CRUD bots, intentions, templates, training, evaluation, playground.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from loko.api.auth import require_admin
from loko.bot.config_store import (
    delete_bot,
    list_bots,
    load_bot_config,
    save_bot_config,
)
from loko.bot.models import BotConfig, Intent, JourneyParams, MessageTemplate, TemplateKey
from loko.bot.session_store import get_bot_dir, get_bots_dir

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/bot",
    tags=["bot-admin"],
    dependencies=[Depends(require_admin)],
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
async def list_all_bots() -> list[dict[str, str]]:
    return list_bots()


@router.post("/", status_code=201)
async def create_bot(req: BotCreateRequest) -> dict[str, Any]:
    config = BotConfig(
        name=req.name,
        channel=req.channel,
        language=req.language,
        tone_profile=req.tone_profile,
    )
    save_bot_config(config)
    return config.model_dump(mode="json")


@router.get("/{bot_id}")
async def get_bot(bot_id: str) -> dict[str, Any]:
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")
    return config.model_dump(mode="json")


@router.put("/{bot_id}")
async def update_bot(bot_id: str, req: BotUpdateRequest) -> dict[str, Any]:
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    updates = req.model_dump(exclude_none=True)
    updated = config.model_copy(update=updates)
    save_bot_config(updated)

    # Invalidate cached orchestrator so next request picks up new config
    from loko.api.bot_public import invalidate_orchestrator
    invalidate_orchestrator(bot_id)

    return updated.model_dump(mode="json")


@router.delete("/{bot_id}")
async def delete_bot_endpoint(bot_id: str) -> dict[str, str]:
    if not delete_bot(bot_id):
        raise HTTPException(404, f"Bot {bot_id} not found")
    return {"status": "deleted", "bot_id": bot_id}


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

@router.post("/{bot_id}/publish")
async def publish_bot(bot_id: str) -> dict[str, Any]:
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

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
        raise ModelIntegrityError(bot_id, "manifest_missing",
                                  "Aucun manifeste d'integrite. Relancez l'entrainement.")

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
        raise ModelIntegrityError(bot_id, "retrain_required",
                                  "Les exemples ont change depuis le dernier entrainement.")

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
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

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
async def get_training_status(bot_id: str) -> dict[str, Any]:
    state = _TRAINING_STATE.get(bot_id)
    if not state:
        # L4: check disk for persisted state (e.g. after restart)
        disk_state = _load_train_state(bot_id)
        if disk_state:
            return {"bot_id": bot_id, **disk_state}
        return {"status": "idle", "bot_id": bot_id}
    return {"bot_id": bot_id, **state}


@router.get("/{bot_id}/evaluation")
async def get_evaluation(bot_id: str) -> dict[str, Any]:
    state = _TRAINING_STATE.get(bot_id)
    if not state or not state.get("result"):
        raise HTTPException(404, "No evaluation available. Train the bot first.")
    result = state["result"]
    evaluation = result.get("evaluation")
    if not evaluation:
        raise HTTPException(404, "Evaluation was not run during training.")
    return evaluation


@router.get("/{bot_id}/train/report")
async def get_training_report(bot_id: str) -> dict[str, Any]:
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


@router.post("/{bot_id}/documents", status_code=201)
async def ingest_document(
    bot_id: str,
    req: IngestDocumentRequest,
) -> dict[str, Any]:
    """Ingest a document into the knowledge base."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

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

    return {"doc_id": doc_id, "bot_id": bot_id}


@router.get("/{bot_id}/documents")
async def list_documents(
    bot_id: str,
    intent: str | None = None,
) -> list[dict[str, Any]]:
    """List documents in the knowledge base, optionally filtered by intent."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    from loko.bot.knowledge_store import get_knowledge_store

    store = get_knowledge_store(bot_id)
    return store.list_documents(intent=intent)


@router.delete("/{bot_id}/documents/{doc_id}")
async def delete_document(bot_id: str, doc_id: str) -> dict[str, str]:
    """Delete a document from the knowledge base."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    from loko.bot.knowledge_store import get_knowledge_store

    store = get_knowledge_store(bot_id)
    if not store.delete_document(doc_id):
        raise HTTPException(404, "Document not found")

    return {"status": "deleted", "doc_id": doc_id}


@router.patch("/{bot_id}/documents/tags")
async def update_document_tags(
    bot_id: str,
    req: UpdateTagsRequest,
) -> dict[str, Any]:
    """Bulk-update intent/sub-motif tags on documents."""
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    from loko.bot.knowledge_store import get_knowledge_store

    store = get_knowledge_store(bot_id)
    updated = store.update_tags(
        req.doc_ids,
        bot_intents=req.bot_intents,
        bot_sub_motifs=req.bot_sub_motifs,
    )

    return {"updated": updated}


@router.get("/{bot_id}/knowledge/coverage")
async def get_knowledge_coverage(bot_id: str) -> dict[str, Any]:
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
