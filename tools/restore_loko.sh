#!/bin/bash
# LOKO Restore Script
# Implements O3 restoration test from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
# Usage: ./restore_loko.sh <backup_file> [target_dir]

set -euo pipefail

# Configuration
BACKUP_FILE="${1:-}"
TARGET_DIR="${2:-/root/.loko_restored}"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    log "ERROR: $*"
    exit 1
}

# Validation
if [ -z "$BACKUP_FILE" ]; then
    error "Usage: $0 <backup_file> [target_dir]"
fi

if [ ! -f "$BACKUP_FILE" ]; then
    error "Backup file not found: $BACKUP_FILE"
fi

log "Starting LOKO restore from: $BACKUP_FILE"
log "Target directory: $TARGET_DIR"

# Create work directory
WORK_DIR=$(mktemp -d)
trap "rm -rf $WORK_DIR" EXIT

# 1. Decrypt backup
log "Decrypting backup..."
if [[ "$BACKUP_FILE" == *.age ]]; then
    if ! command -v age &> /dev/null; then
        error "age not found, cannot decrypt"
    fi
    if [ ! -f "${HOME}/.loko_backup_key_private.txt" ]; then
        error "Private key not found: ${HOME}/.loko_backup_key_private.txt"
    fi
    age -d -i "${HOME}/.loko_backup_key_private.txt" -o "${WORK_DIR}/backup.tar.gz" "$BACKUP_FILE"
    TARBALL="${WORK_DIR}/backup.tar.gz"
    log "  ✓ Decrypted with age"
elif [[ "$BACKUP_FILE" == *.gpg ]]; then
    if ! command -v gpg &> /dev/null; then
        error "gpg not found, cannot decrypt"
    fi
    gpg --decrypt --output "${WORK_DIR}/backup.tar.gz" "$BACKUP_FILE"
    TARBALL="${WORK_DIR}/backup.tar.gz"
    log "  ✓ Decrypted with gpg"
else
    # Assume unencrypted tarball
    TARBALL="$BACKUP_FILE"
    log "  ⚠ No encryption detected"
fi

# 2. Extract tarball
log "Extracting tarball..."
cd "$WORK_DIR"
tar -xzf "$TARBALL"
EXTRACTED_DIR=$(find . -maxdepth 1 -type d -name "loko_backup_*" | head -n 1)

if [ -z "$EXTRACTED_DIR" ]; then
    error "Could not find extracted backup directory"
fi

log "  ✓ Extracted to: $EXTRACTED_DIR"

# 3. Restore to target directory
log "Restoring to target directory..."
mkdir -p "$TARGET_DIR"

# Restore databases
if [ -f "${EXTRACTED_DIR}/accounts.db" ]; then
    cp "${EXTRACTED_DIR}/accounts.db" "${TARGET_DIR}/accounts.db"
    log "  ✓ Restored accounts.db"
fi

if [ -d "${EXTRACTED_DIR}/bots" ]; then
    mkdir -p "${TARGET_DIR}/bots"
    cp -r "${EXTRACTED_DIR}/bots"/* "${TARGET_DIR}/bots/"
    log "  ✓ Restored bot configs"
fi

# Restore models and manifests
if [ -d "${EXTRACTED_DIR}/models" ]; then
    cp -r "${EXTRACTED_DIR}/models" "${TARGET_DIR}/models"
    log "  ✓ Restored models"
fi

if [ -d "${EXTRACTED_DIR}/manifests" ]; then
    cp -r "${EXTRACTED_DIR}/manifests" "${TARGET_DIR}/manifests"
    log "  ✓ Restored manifests"
fi

# Restore configs
if [ -d "${EXTRACTED_DIR}/configs" ]; then
    cp -r "${EXTRACTED_DIR}/configs" "${TARGET_DIR}/configs"
    log "  ✓ Restored configs"
fi

# Restore sessions (if present)
if [ -d "${EXTRACTED_DIR}/sessions" ]; then
    mkdir -p "${TARGET_DIR}/sessions"
    cp -r "${EXTRACTED_DIR}/sessions"/* "${TARGET_DIR}/sessions/" 2>/dev/null || true
    log "  ✓ Restored sessions"
fi

# 4. Verify restoration
log "Verifying restoration..."

# Check databases are readable
if [ -f "${TARGET_DIR}/accounts.db" ]; then
    sqlite3 "${TARGET_DIR}/accounts.db" "SELECT COUNT(*) FROM sqlite_master;" > /dev/null
    log "  ✓ accounts.db is readable"
fi

# Verify manifest integrity (if manifests exist)
if [ -d "${TARGET_DIR}/manifests" ]; then
    MANIFEST_COUNT=$(find "${TARGET_DIR}/manifests" -name "*.json" | wc -l)
    log "  ✓ Found ${MANIFEST_COUNT} model manifests"

    # Verify first manifest JSON is valid
    FIRST_MANIFEST=$(find "${TARGET_DIR}/manifests" -name "*.json" | head -n 1)
    if [ -f "$FIRST_MANIFEST" ]; then
        if command -v jq &> /dev/null; then
            jq empty "$FIRST_MANIFEST" 2>/dev/null && log "  ✓ Manifest JSON is valid"
        else
            python3 -c "import json; json.load(open('$FIRST_MANIFEST'))" && log "  ✓ Manifest JSON is valid"
        fi
    fi
fi

log "✅ Restoration completed successfully"
log "   Target directory: $TARGET_DIR"
log "   You can now test the bot with LOKO_DATA_DIR=$TARGET_DIR"

# Print summary
log ""
log "Restoration summary:"
[ -f "${TARGET_DIR}/accounts.db" ] && log "  - Accounts database restored"
[ -d "${TARGET_DIR}/bots" ] && log "  - Bot configs: $(ls ${TARGET_DIR}/bots/*.db 2>/dev/null | wc -l) bots"
[ -d "${TARGET_DIR}/models" ] && log "  - Models directory restored"
[ -d "${TARGET_DIR}/manifests" ] && log "  - Manifests: $(find ${TARGET_DIR}/manifests -name '*.json' 2>/dev/null | wc -l) files"
[ -d "${TARGET_DIR}/configs" ] && log "  - Bot configs directory restored"

exit 0
