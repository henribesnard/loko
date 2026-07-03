"""LOKO Bot — Dashboard & continuous improvement API endpoints.

Prefix: /api/bot/{bot_id}/dashboard
Covers: metrics, session replay, misclassified turns, add-to-training.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from loko.bot.config_store import load_bot_config, save_bot_config
from loko.bot.metrics import compute_metrics, get_misclassified_turns, get_session_replay
from loko.bot.session_store import get_bot_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bot", tags=["bot-dashboard"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AddTrainingExampleRequest(BaseModel):
    """Add a misclassified turn as a training example."""
    intent_id: str
    text: str
    from_production: bool = True


class RetriggerTrainRequest(BaseModel):
    """Re-trigger training after adding examples from production."""
    base_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    run_evaluation: bool = True


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@router.get("/{bot_id}/dashboard/metrics")
async def get_metrics(bot_id: str) -> dict[str, Any]:
    """Get aggregated dashboard metrics for a bot."""
    bot_dir = get_bot_dir(bot_id)
    db_path = bot_dir / "sessions.db"
    metrics = compute_metrics(db_path)
    return metrics.to_dict()


# ---------------------------------------------------------------------------
# Session replay
# ---------------------------------------------------------------------------

@router.get("/{bot_id}/dashboard/sessions")
async def list_recent_sessions(
    bot_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List recent sessions for the dashboard."""
    from loko.bot.session_store import get_session_store

    store = get_session_store(bot_id)
    return store.list_sessions(bot_id, limit=limit, offset=offset)


@router.get("/{bot_id}/dashboard/sessions/{session_id}/replay")
async def replay_session(bot_id: str, session_id: str) -> dict[str, Any]:
    """Get full session replay (transcript + traces + feedback)."""
    bot_dir = get_bot_dir(bot_id)
    db_path = bot_dir / "sessions.db"
    replay = get_session_replay(db_path, session_id)
    if not replay:
        raise HTTPException(404, f"Session {session_id} not found")
    return replay


# ---------------------------------------------------------------------------
# Misclassified turns (continuous improvement)
# ---------------------------------------------------------------------------

@router.get("/{bot_id}/dashboard/misclassified")
async def list_misclassified(
    bot_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List turns with negative feedback — candidates for re-training."""
    bot_dir = get_bot_dir(bot_id)
    db_path = bot_dir / "sessions.db"
    return get_misclassified_turns(db_path, limit=limit)


@router.post("/{bot_id}/dashboard/add-example")
async def add_training_example(
    bot_id: str,
    req: AddTrainingExampleRequest,
) -> dict[str, Any]:
    """Add a misclassified turn as a training example for an intent.

    This is the 1-click improvement flow:
    1. Agent sees misclassified turn in dashboard
    2. Clicks "add to intent X"
    3. Text is added as a training example
    4. Agent can re-trigger training
    """
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    # Find the target intent
    intent_idx = None
    for i, intent in enumerate(config.intents):
        if intent.id == req.intent_id:
            intent_idx = i
            break

    if intent_idx is None:
        raise HTTPException(404, f"Intent '{req.intent_id}' not found in bot config")

    # Check for duplicates
    if req.text in config.intents[intent_idx].examples:
        return {"status": "duplicate", "message": "Example already exists"}

    # Add the example
    config.intents[intent_idx].examples.append(req.text)

    # Save updated config
    save_bot_config(config)

    return {
        "status": "added",
        "intent_id": req.intent_id,
        "examples_count": len(config.intents[intent_idx].examples),
        "from_production": req.from_production,
    }


@router.post("/{bot_id}/dashboard/retrain")
async def retrain_from_dashboard(
    bot_id: str,
    req: RetriggerTrainRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Re-trigger training after adding production examples.

    Delegates to the existing training infrastructure in bot_admin.
    """
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    # Delegate to the admin training endpoint logic
    from loko.api.bot_admin import _TRAINING_STATE, _run_training_background

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


# ---------------------------------------------------------------------------
# Intent split suggestion
# ---------------------------------------------------------------------------

@router.get("/{bot_id}/dashboard/suggestions")
async def get_improvement_suggestions(bot_id: str) -> list[dict[str, Any]]:
    """Analyze feedback and retrieval data to suggest improvements.

    Suggestions include:
    - Intent split: when an intent has high confusion or negative feedback
    - Missing examples: when classification confidence is consistently low
    """
    config = load_bot_config(bot_id)
    if not config:
        raise HTTPException(404, f"Bot {bot_id} not found")

    bot_dir = get_bot_dir(bot_id)
    db_path = bot_dir / "sessions.db"
    metrics = compute_metrics(db_path)
    misclassified = get_misclassified_turns(db_path, limit=100)

    suggestions: list[dict[str, Any]] = []

    # Suggest split if an intent has high escalation rate
    for intent_id, selfcare_rate in metrics.selfcare_by_intent.items():
        if selfcare_rate < 0.5 and metrics.escalation_by_intent.get(intent_id, 0) >= 3:
            suggestions.append({
                "type": "intent_split",
                "intent_id": intent_id,
                "selfcare_rate": selfcare_rate,
                "escalation_count": metrics.escalation_by_intent.get(intent_id, 0),
                "message": f"L'intention '{intent_id}' a un taux de selfcare faible "
                           f"({selfcare_rate:.0%}) et {metrics.escalation_by_intent.get(intent_id, 0)} "
                           f"escalades. Envisagez de la scinder en sous-intentions plus précises.",
            })

    # Suggest more examples for intents with many misclassifications
    misclass_by_intent: dict[str, int] = {}
    for m in misclassified:
        intent = m.get("classified_intent", "")
        if intent:
            misclass_by_intent[intent] = misclass_by_intent.get(intent, 0) + 1

    for intent_id, count in misclass_by_intent.items():
        if count >= 3:
            suggestions.append({
                "type": "more_examples",
                "intent_id": intent_id,
                "misclassification_count": count,
                "message": f"L'intention '{intent_id}' a {count} retours négatifs. "
                           f"Ajoutez des exemples d'entraînement pour améliorer la classification.",
            })

    return suggestions
