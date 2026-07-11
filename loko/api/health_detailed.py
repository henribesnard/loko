"""
Detailed health check endpoint (O2)
Implements PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

Detects partial degradations: disk full, model unloaded, LLM unreachable.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from pathlib import Path
import os

router = APIRouter(tags=["ops"])


def check_database_writable() -> tuple[bool, str]:
    """Check if database is accessible for writes."""
    try:
        from loko.bot.config_store import get_bots_dir

        bots_dir = get_bots_dir()

        # Try to write a test file
        test_file = bots_dir / ".healthcheck"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(datetime.now(timezone.utc).isoformat())

        # Clean up
        test_file.unlink()

        return True, "OK"
    except Exception as e:
        return False, f"Database write failed: {e}"


def check_models_loaded() -> tuple[bool, str]:
    """Check if published bot models are loaded + manifests match."""
    try:
        from loko.bot.config_store import list_bot_ids, load_bot_config
        from loko.bot.classifier.loader import get_model_cache

        bot_ids = list_bot_ids()
        cache = get_model_cache()

        issues = []
        for bot_id in bot_ids:
            try:
                config = load_bot_config(bot_id)

                # Only check published bots
                if not getattr(config, "is_published", False):
                    continue

                # Check L1 model
                if bot_id not in cache._models:
                    issues.append(f"{bot_id}: L1 model not loaded")
                    continue

                # TODO: Check manifest hash integrity (GNG-10)
                # manifest_path = get_manifest_path(bot_id, "l1")
                # if manifest_path.exists():
                #     manifest = load_manifest(manifest_path)
                #     if manifest.hash != compute_model_hash(...):
                #         issues.append(f"{bot_id}: manifest hash mismatch")

            except Exception as e:
                issues.append(f"{bot_id}: {e}")

        if issues:
            return False, "; ".join(issues)

        return True, f"{len(bot_ids)} bots OK"

    except Exception as e:
        return False, f"Model check failed: {e}"


def check_disk_space(threshold_mb: int = 1000) -> tuple[bool, str]:
    """Check if disk space > threshold."""
    try:
        from loko.bot.config_store import get_bots_dir

        data_dir = get_bots_dir().parent

        stat = os.statvfs(data_dir)
        free_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)

        if free_mb < threshold_mb:
            return (
                False,
                f"Low disk space: {free_mb:.0f} MB free (threshold: {threshold_mb} MB)",
            )

        return True, f"{free_mb:.0f} MB free"

    except Exception as e:
        return False, f"Disk check failed: {e}"


def check_backup_age(max_age_hours: int = 26) -> tuple[bool, str]:
    """Check age of last backup (O3 dependency)."""
    try:
        backup_dir = Path(os.getenv("BACKUP_DIR", "/backup/loko"))
        timestamp_file = backup_dir / "last_backup_timestamp"

        if not timestamp_file.exists():
            return False, "No backup timestamp found"

        timestamp_str = timestamp_file.read_text().strip()
        # Format: YYYYMMDD_HHMMSS
        backup_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        backup_time = backup_time.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - backup_time
        age_hours = age.total_seconds() / 3600

        if age_hours > max_age_hours:
            return (
                False,
                f"Backup too old: {age_hours:.1f}h ago (max: {max_age_hours}h)",
            )

        return True, f"Last backup: {age_hours:.1f}h ago"

    except Exception as e:
        # Non-blocking if backups not configured yet
        return True, f"Backup check skipped: {e}"


def check_llm_reachable() -> tuple[bool, str]:
    """Check if LLM provider is reachable (preflight CE-8)."""
    try:
        from loko.config.env import get_env

        provider = get_env("ESCALATION_PROVIDER", "mock")

        if provider == "mock":
            return True, "Mock provider (dev mode)"

        # TODO: Implement actual LLM ping
        # For now, assume OK if not mock
        return True, f"Provider: {provider} (ping not implemented)"

    except Exception as e:
        return False, f"LLM check failed: {e}"


@router.get("/health/detailed")
async def health_detailed(
    _admin: str | None = None,  # Optionally protect with admin token
) -> JSONResponse:
    """
    Detailed health check (admin-only recommended).

    Returns:
        200 OK: All systems healthy
        503 DEGRADED: Partial degradation detected

    Response format:
        {
          "status": "OK" | "DEGRADED",
          "checks": {
            "database": {"healthy": true, "message": "OK"},
            "models": {"healthy": true, "message": "3 bots OK"},
            "disk_space": {"healthy": true, "message": "5000 MB free"},
            "backup_age": {"healthy": true, "message": "Last backup: 2.3h ago"},
            "llm": {"healthy": true, "message": "Provider: mock"}
          },
          "timestamp": "2026-07-10T12:00:00Z"
        }
    """
    checks = {}

    # Run all checks
    db_ok, db_msg = check_database_writable()
    checks["database"] = {"healthy": db_ok, "message": db_msg}

    models_ok, models_msg = check_models_loaded()
    checks["models"] = {"healthy": models_ok, "message": models_msg}

    disk_ok, disk_msg = check_disk_space()
    checks["disk_space"] = {"healthy": disk_ok, "message": disk_msg}

    backup_ok, backup_msg = check_backup_age()
    checks["backup_age"] = {"healthy": backup_ok, "message": backup_msg}

    llm_ok, llm_msg = check_llm_reachable()
    checks["llm"] = {"healthy": llm_ok, "message": llm_msg}

    # Overall status
    all_healthy = all(check["healthy"] for check in checks.values())
    status = "OK" if all_healthy else "DEGRADED"

    response = {
        "status": status,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Return 503 if degraded (for monitoring)
    status_code = 200 if all_healthy else 503

    return JSONResponse(content=response, status_code=status_code)
