"""D3/C-V3 — Master key rotation CLI.

Usage:
    python -m loko.security.rotate_master_key --db-path data/loko_secrets.db
    python -m loko.security.rotate_master_key --dry-run
    python -m loko.security.rotate_master_key --new-key-file /path/to/new.key --journal rotation.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def count_secrets(db_path: str) -> int:
    """Count secrets in the store without decrypting."""
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM secrets").fetchone()
        return row[0] if row else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rotate the LOKO SecretStore master key.",
    )
    parser.add_argument(
        "--db-path",
        default=os.path.join(
            os.environ.get("LOKO_DATA_DIR", "data"), "loko_secrets.db",
        ),
        help="Path to the secrets database (default: data/loko_secrets.db)",
    )
    parser.add_argument(
        "--new-key-file",
        help="File containing the new Fernet key. If omitted, a new key is generated.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count secrets without rotating.",
    )
    parser.add_argument(
        "--journal",
        help="Path to write a JSON rotation journal.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    db_path = args.db_path
    if not Path(db_path).is_file():
        logger.error("Database not found: %s", db_path)
        return 1

    if args.dry_run:
        n = count_secrets(db_path)
        print(f"Would rotate {n} secret(s) in {db_path}")
        return 0

    from cryptography.fernet import Fernet

    from loko.security.secret_store import SecretStore

    # Resolve new key
    if args.new_key_file:
        new_key = Path(args.new_key_file).read_bytes().strip()
    else:
        new_key = Fernet.generate_key()

    # Rotate
    store = SecretStore(db_path)
    rotated = store.rotate(new_key)

    # Verify: re-instantiate with new key and check all secrets decrypt
    os.environ["LOKO_SECRET_KEY"] = new_key.decode("utf-8")
    verify_store = SecretStore(db_path)
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        refs = [r[0] for r in conn.execute("SELECT ref FROM secrets").fetchall()]

    failures = 0
    for ref in refs:
        try:
            verify_store.get(ref)
        except Exception as exc:
            logger.error("Post-rotation verification failed for %s: %s", ref, exc)
            failures += 1

    if failures:
        logger.error(
            "%d/%d secrets failed post-rotation verification", failures, len(refs),
        )
        return 1

    key_fingerprint = hashlib.sha256(new_key).hexdigest()[:8]
    print(f"Rotated {rotated} secret(s). Key fingerprint: {key_fingerprint}")
    print(f"Update the LOKO_SECRET_KEY env var to the new key before next server start.")
    print(f"New key value: {new_key.decode('utf-8')}")

    # Journal
    if args.journal:
        journal = {
            "rotated": rotated,
            "verified": len(refs) - failures,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "key_fingerprint": key_fingerprint,
            "db_path": db_path,
        }
        Path(args.journal).write_text(
            json.dumps(journal, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Journal written to {args.journal}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
