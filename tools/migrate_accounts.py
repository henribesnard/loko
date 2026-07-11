#!/usr/bin/env python3
"""T1 — Idempotent migration: assign account_id to all bots.

Creates the 'Wezon interne' account if needed, and attaches all bots
that don't have an account_id to it.

Usage:
    python tools/migrate_accounts.py [--data-dir DATA_DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate bots to account_id schema v2")
    parser.add_argument("--data-dir", default="data", help="Path to data directory")
    args = parser.parse_args()

    os.environ.setdefault("LOKO_DATA_DIR", args.data_dir)

    from loko.bot.config_store import load_bot_config, _get_internal_account_id

    internal_id = _get_internal_account_id()
    print(f"Internal account ID: {internal_id}")

    bots_dir = Path(args.data_dir) / "bots"
    if not bots_dir.is_dir():
        print("No bots directory found. Nothing to migrate.")
        return

    migrated = 0
    already_ok = 0

    for bot_dir in sorted(bots_dir.iterdir()):
        config_path = bot_dir / "config.json"
        if not config_path.is_file():
            continue

        data = json.loads(config_path.read_text(encoding="utf-8"))
        bot_id = data.get("bot_id", bot_dir.name)

        if data.get("account_id") and data.get("schema_version", 1) >= 2:
            already_ok += 1
            print(f"  OK: {bot_id} (account_id={data['account_id']})")
        else:
            # Trigger lazy migration by loading
            config = load_bot_config(bot_id)
            if config:
                migrated += 1
                print(f"  MIGRATED: {bot_id} → account_id={config.account_id}")
            else:
                print(f"  ERROR: {bot_id} — could not load config")

    print(f"\nReport: {migrated} migrated, {already_ok} already OK")
    print(f"Total bots: {migrated + already_ok}")


if __name__ == "__main__":
    main()
