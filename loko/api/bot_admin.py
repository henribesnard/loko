"""LOKO Bot — Admin API endpoints.

Prefix: /api/bot
Covers: CRUD bots, intentions, templates, training, evaluation, playground.
"""

from __future__ import annotations

import asyncio
import logging
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

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/bot",
    tags=["bot-admin"],
    dependencies=[Depends(require_admin)],
)

# ---------------------------------------------------------------------------
# Training state (in-memory, per bot)
# ---------------------------------------------------------------------------

_TRAINING_STATE: dict[str, dict[str, Any]] = {}


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

    from loko.bot.classifier.model_store import model_exists
    if not model_exists(bot_id, "level1"):
        errors.append("Le classifieur L1 n'est pas entraine. Lancez l'entrainement d'abord.")

    if errors:
        raise HTTPException(400, {"errors": errors})

    updated = config.model_copy(update={"status": "published"})
    save_bot_config(updated)

    # Invalidate cached orchestrator so runtime picks up new status
    from loko.api.bot_public import invalidate_orchestrator
    invalidate_orchestrator(bot_id)

    return {"status": "published", "bot_id": bot_id}


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

    if bot_id in _TRAINING_STATE and _TRAINING_STATE[bot_id].get("status") == "running":
        raise HTTPException(409, "Training already in progress")

    _TRAINING_STATE[bot_id] = {"status": "running", "step": "queued", "result": None}

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
    except Exception as exc:
        logger.exception("Training failed for bot %s", bot_id)
        _TRAINING_STATE[bot_id]["status"] = "failed"
        _TRAINING_STATE[bot_id]["error"] = str(exc)
