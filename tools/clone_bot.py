#!/usr/bin/env python3
"""Clone a bot for disposable testing (W3.2 - protocol v2.1).

Usage:
    python tools/clone_bot.py <source_bot_id> <clone_name_suffix>

Example:
    python tools/clone_bot.py a39327f2-9f4a-45ce-b7ee-064bd570f186 v2-4-disposable

Creates a full copy of the bot directory including:
- config.json (with new bot_id and name suffix)
- classifier_l1/ (trained model files)
- classifier_l2/ dictionaries (if present)
- sessions.db (empty - fresh start for V2-4/V2-5)
- Any other bot artifacts

Use case (protocol v2.1):
  1. Train campaign bot to V2-1 (frozen checkpoint)
  2. Clone bot for V2-4/V2-5: clone_bot.py {bot_id} v2-disposable
  3. Run V2-4/V2-5 on the disposable bot (add examples, retrain, measure)
  4. Run V3-0 through V3-6 on the ORIGINAL bot (frozen at V2-1)
  5. Delete disposable bot after campaign

This prevents V2-5 training contamination from affecting V3 measurements.
"""

import shutil
import sys
import uuid
from pathlib import Path

# Adjust path to import loko modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loko.bot.config_store import load_bot_config, save_bot_config
from loko.bot.session_store import get_bot_dir


def clone_bot(source_bot_id: str, name_suffix: str) -> str:
    """Clone a bot to a new bot_id with name suffix.

    Args:
        source_bot_id: UUID of the source bot
        name_suffix: Suffix to append to cloned bot name (e.g., "v2-disposable")

    Returns:
        The new bot_id (UUID string)

    Raises:
        ValueError: If source bot not found or name_suffix invalid
    """
    # Load source bot config
    source_config = load_bot_config(source_bot_id)
    if not source_config:
        raise ValueError(f"Source bot not found: {source_bot_id}")

    source_dir = get_bot_dir(source_bot_id, create=False)
    if not source_dir.exists():
        raise ValueError(f"Source bot directory not found: {source_dir}")

    # Generate new bot_id and create clone config
    clone_bot_id = str(uuid.uuid4())
    clone_config = source_config.model_copy(deep=True)
    clone_config.bot_id = clone_bot_id
    clone_config.name = f"{source_config.name} [{name_suffix}]"
    clone_config.status = "draft"  # Clones start as draft, not published

    # Create clone directory
    clone_dir = get_bot_dir(clone_bot_id, create=True)

    print("Cloning bot...")
    print(f"  Source: {source_bot_id}")
    print(f"  Source name: {source_config.name}")
    print(f"  Clone: {clone_bot_id}")
    print(f"  Clone name: {clone_config.name}")
    print(f"  Source dir: {source_dir}")
    print(f"  Clone dir: {clone_dir}")

    # Copy all files and directories except config.json and sessions.db
    # (config.json will be written with new values, sessions.db starts fresh)
    copied_items = []
    for item in source_dir.iterdir():
        if item.name == "config.json":
            continue  # Will write new config
        if item.name == "sessions.db":
            continue  # Start with empty session history

        dest = clone_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
            copied_items.append(f"{item.name}/ (directory)")
        else:
            shutil.copy2(item, dest)
            copied_items.append(item.name)

    # Save clone config
    save_bot_config(clone_config)

    print(f"\nCloned {len(copied_items)} items:")
    for item in sorted(copied_items):
        print(f"  - {item}")

    print("\nClone created successfully!")
    print(f"Bot ID: {clone_bot_id}")
    print("\nNext steps (protocol v2.1):")
    print(
        f"  1. Run V2-4 on this clone: loko-eval --bot-dir {clone_dir} --mode confusion"
    )
    print(f"  2. Add examples via API: POST /api/bot/{clone_bot_id}/examples")
    print(f"  3. Retrain clone: POST /api/bot/{clone_bot_id}/train")
    print("  4. Run V2-5 comparison on this clone")
    print(f"  5. Run V3 on ORIGINAL bot (frozen at V2-1): {source_bot_id}")
    print(f"  6. Delete clone after campaign: rm -rf {clone_dir}")

    return clone_bot_id


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        print("\nError: Expected 2 arguments", file=sys.stderr)
        sys.exit(1)

    source_bot_id = sys.argv[1]
    name_suffix = sys.argv[2]

    try:
        clone_bot_id = clone_bot(source_bot_id, name_suffix)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
