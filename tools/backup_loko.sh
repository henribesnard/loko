#!/bin/bash
# LOKO Backup Script
# Implements O3 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
# Usage: ./backup_loko.sh
# Cron: 0 2 * * * /path/to/backup_loko.sh

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backup/loko}"
DATA_DIR="${LOKO_DATA_DIR:-/root/.loko}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="loko_backup_${TIMESTAMP}"
WORK_DIR="${BACKUP_DIR}/.tmp/${BACKUP_NAME}"

# Retention policy
DAILY_RETENTION=7
WEEKLY_RETENTION=4

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${BACKUP_DIR}/backup.log"
}

error() {
    log "ERROR: $*"
    exit 1
}

# Create directories
mkdir -p "${WORK_DIR}"
mkdir -p "${BACKUP_DIR}/daily"
mkdir -p "${BACKUP_DIR}/weekly"

log "Starting LOKO backup: ${BACKUP_NAME}"

# 1. Backup SQLite databases (using .backup for consistency)
log "Backing up SQLite databases..."
if [ -f "${DATA_DIR}/accounts.db" ]; then
    sqlite3 "${DATA_DIR}/accounts.db" ".backup ${WORK_DIR}/accounts.db"
    log "  ✓ accounts.db backed up"
fi

# Backup config databases (if they exist)
if [ -d "${DATA_DIR}/bots" ]; then
    mkdir -p "${WORK_DIR}/bots"
    for db in "${DATA_DIR}"/bots/*.db; do
        if [ -f "$db" ]; then
            bot_id=$(basename "$db" .db)
            sqlite3 "$db" ".backup ${WORK_DIR}/bots/${bot_id}.db"
            log "  ✓ Bot config ${bot_id} backed up"
        fi
    done
fi

# 2. Backup model stores and manifests
log "Backing up models and manifests..."
if [ -d "${DATA_DIR}/models" ]; then
    cp -r "${DATA_DIR}/models" "${WORK_DIR}/models"
    log "  ✓ Models backed up"
fi

if [ -d "${DATA_DIR}/manifests" ]; then
    cp -r "${DATA_DIR}/manifests" "${WORK_DIR}/manifests"
    log "  ✓ Manifests backed up"
fi

# 3. Backup bot configs
log "Backing up bot configurations..."
if [ -d "${DATA_DIR}/configs" ]; then
    cp -r "${DATA_DIR}/configs" "${WORK_DIR}/configs"
    log "  ✓ Configs backed up"
fi

# 4. Backup session stores (optional, based on retention policy)
if [ -d "${DATA_DIR}/sessions" ]; then
    # Only backup recent sessions (last 7 days)
    mkdir -p "${WORK_DIR}/sessions"
    find "${DATA_DIR}/sessions" -name "*.json" -mtime -7 -exec cp {} "${WORK_DIR}/sessions/" \;
    log "  ✓ Recent sessions backed up"
fi

# 5. Create tarball
log "Creating tarball..."
cd "${BACKUP_DIR}/.tmp"
tar -czf "${BACKUP_NAME}.tar.gz" "${BACKUP_NAME}"
log "  ✓ Tarball created: ${BACKUP_NAME}.tar.gz"

# 6. Encryption (using age if available, otherwise gpg)
log "Encrypting backup..."
if command -v age &> /dev/null && [ -f "${HOME}/.loko_backup_key.txt" ]; then
    age -r "$(cat ${HOME}/.loko_backup_key.txt)" -o "${BACKUP_DIR}/daily/${BACKUP_NAME}.tar.gz.age" "${BACKUP_NAME}.tar.gz"
    ENCRYPTED_FILE="${BACKUP_DIR}/daily/${BACKUP_NAME}.tar.gz.age"
    log "  ✓ Encrypted with age"
elif command -v gpg &> /dev/null && [ -f "${HOME}/.loko_backup_gpg_recipient" ]; then
    gpg --encrypt --recipient "$(cat ${HOME}/.loko_backup_gpg_recipient)" \
        --output "${BACKUP_DIR}/daily/${BACKUP_NAME}.tar.gz.gpg" "${BACKUP_NAME}.tar.gz"
    ENCRYPTED_FILE="${BACKUP_DIR}/daily/${BACKUP_NAME}.tar.gz.gpg"
    log "  ✓ Encrypted with gpg"
else
    # Fallback: no encryption (not recommended for production)
    mv "${BACKUP_NAME}.tar.gz" "${BACKUP_DIR}/daily/"
    ENCRYPTED_FILE="${BACKUP_DIR}/daily/${BACKUP_NAME}.tar.gz"
    log "  ⚠ WARNING: No encryption configured!"
fi

# 7. Copy to remote storage (if rclone is configured)
if command -v rclone &> /dev/null && rclone listremotes | grep -q "loko-backup:"; then
    log "Copying to remote storage..."
    rclone copy "${ENCRYPTED_FILE}" "loko-backup:loko/daily/" --progress
    log "  ✓ Copied to remote storage"
else
    log "  ⚠ WARNING: rclone not configured, backup is local only"
fi

# 8. Write timestamp file (for O2 health check)
echo "${TIMESTAMP}" > "${BACKUP_DIR}/last_backup_timestamp"
log "  ✓ Timestamp written"

# 9. Cleanup work directory
rm -rf "${WORK_DIR}"
rm -f "${BACKUP_DIR}/.tmp/${BACKUP_NAME}.tar.gz"
log "  ✓ Temporary files cleaned"

# 10. Retention: daily backups
log "Applying retention policy..."
find "${BACKUP_DIR}/daily" -name "loko_backup_*.tar.gz*" -mtime +${DAILY_RETENTION} -delete
log "  ✓ Removed daily backups older than ${DAILY_RETENTION} days"

# 11. Promote to weekly (every Sunday)
if [ "$(date +%u)" -eq 7 ]; then
    log "Promoting to weekly backup..."
    cp "${ENCRYPTED_FILE}" "${BACKUP_DIR}/weekly/"
    if command -v rclone &> /dev/null && rclone listremotes | grep -q "loko-backup:"; then
        rclone copy "${ENCRYPTED_FILE}" "loko-backup:loko/weekly/" --progress
    fi
    log "  ✓ Weekly backup created"

    # Clean old weekly backups (keep only WEEKLY_RETENTION weeks = 28 days)
    find "${BACKUP_DIR}/weekly" -name "loko_backup_*.tar.gz*" -mtime +$((WEEKLY_RETENTION * 7)) -delete
    log "  ✓ Removed weekly backups older than ${WEEKLY_RETENTION} weeks"
fi

# 12. Verify backup integrity
log "Verifying backup integrity..."
if [ -f "${ENCRYPTED_FILE}" ]; then
    SIZE=$(stat -c%s "${ENCRYPTED_FILE}" 2>/dev/null || stat -f%z "${ENCRYPTED_FILE}" 2>/dev/null || echo "0")
    if [ "$SIZE" -gt 1000 ]; then
        log "  ✓ Backup file size: ${SIZE} bytes (OK)"
    else
        error "Backup file too small: ${SIZE} bytes"
    fi
else
    error "Backup file not found"
fi

log "✅ Backup completed successfully: ${BACKUP_NAME}"
log "   Backup location: ${ENCRYPTED_FILE}"
log "   Size: ${SIZE} bytes"

# Exit with success
exit 0
