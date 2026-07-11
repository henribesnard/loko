#!/bin/bash
# LOKO — Deploy a specific version (or rollback to a previous one).
#
# Usage:
#   ./tools/deploy_version.sh 0.3.8          # deploy version 0.3.8
#   ./tools/deploy_version.sh 0.3.8 --no-backup   # skip backup
#   ./tools/deploy_version.sh --list          # list available versions
#
# This script is designed to run on the VPS (/opt/loko).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
REGISTRY="ghcr.io/henribesnard/loko"
DEPLOY_LOG="${PROJECT_DIR}/.deploy_history"
HEALTH_URL="http://localhost:8001/health"
HEALTH_RETRIES=30
HEALTH_INTERVAL=2

# --- Helpers ---------------------------------------------------------------

log()   { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { log "ERROR: $*"; exit 1; }

current_version() {
    # Try health endpoint first, then fall back to git tag
    local ver
    ver=$(curl -sf "$HEALTH_URL" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('version',''))" 2>/dev/null || true)
    if [ -n "$ver" ]; then
        echo "$ver"
        return
    fi
    # Fall back to LOKO_VERSION env or git tag
    if [ -n "${LOKO_VERSION:-}" ]; then
        echo "$LOKO_VERSION"
        return
    fi
    git -C "$PROJECT_DIR" describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' || echo "unknown"
}

list_versions() {
    log "Available versions (git tags):"
    echo ""
    git -C "$PROJECT_DIR" tag -l "v*.*.*" --sort=-version:refname | head -20 | while read -r tag; do
        ver="${tag#v}"
        # Mark current version
        if [ "$ver" = "$(current_version)" ]; then
            echo "  $tag  <-- CURRENT"
        else
            echo "  $tag"
        fi
    done
    echo ""

    # Show deploy history if it exists
    if [ -f "$DEPLOY_LOG" ]; then
        echo "Recent deployment history:"
        tail -10 "$DEPLOY_LOG"
        echo ""
    fi
}

wait_healthy() {
    log "Waiting for health check..."
    for i in $(seq 1 "$HEALTH_RETRIES"); do
        if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
            local deployed_ver
            deployed_ver=$(curl -sf "$HEALTH_URL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
            log "Health check passed (version: $deployed_ver)"
            return 0
        fi
        echo "  Waiting... ($i/$HEALTH_RETRIES)"
        sleep "$HEALTH_INTERVAL"
    done
    return 1
}

record_deploy() {
    local version="$1"
    local status="$2"
    local prev="$3"
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $status | v$version (was: v$prev)" >> "$DEPLOY_LOG"
}

# --- Main ------------------------------------------------------------------

# Parse arguments
SKIP_BACKUP=false
TARGET_VERSION=""

for arg in "$@"; do
    case "$arg" in
        --list|-l)
            list_versions
            exit 0
            ;;
        --no-backup)
            SKIP_BACKUP=true
            ;;
        --help|-h)
            echo "Usage: $0 <version> [--no-backup] [--list]"
            echo ""
            echo "  <version>     Target version to deploy (e.g. 0.3.8)"
            echo "  --no-backup   Skip pre-deploy backup"
            echo "  --list, -l    List available versions"
            echo "  --help, -h    Show this help"
            exit 0
            ;;
        *)
            TARGET_VERSION="$arg"
            ;;
    esac
done

if [ -z "$TARGET_VERSION" ]; then
    echo "Error: No version specified."
    echo ""
    echo "Usage: $0 <version> [--no-backup]"
    echo "       $0 --list"
    exit 1
fi

# Strip leading 'v' if provided
TARGET_VERSION="${TARGET_VERSION#v}"

cd "$PROJECT_DIR"

PREV_VERSION=$(current_version)
log "=== LOKO Deploy: v$PREV_VERSION -> v$TARGET_VERSION ==="

# Verify tag exists
if ! git -C "$PROJECT_DIR" tag -l "v$TARGET_VERSION" | grep -q .; then
    error "Tag v$TARGET_VERSION does not exist. Use --list to see available versions."
fi

# 1. Backup (unless skipped)
if [ "$SKIP_BACKUP" = false ]; then
    log "Creating pre-deploy backup..."
    if [ -x "$SCRIPT_DIR/backup_loko.sh" ]; then
        "$SCRIPT_DIR/backup_loko.sh" || log "WARNING: Backup failed, continuing anyway"
    else
        log "WARNING: backup_loko.sh not found or not executable, skipping backup"
    fi
fi

# 2. Checkout git tag (for compose files and scripts)
log "Checking out v$TARGET_VERSION..."
git fetch --tags --force
git checkout "v$TARGET_VERSION"

# 3. Set version and pull image
log "Pulling Docker image $REGISTRY:$TARGET_VERSION..."
export LOKO_VERSION="$TARGET_VERSION"
$COMPOSE_CMD pull

# 4. Deploy
log "Deploying v$TARGET_VERSION..."
$COMPOSE_CMD up -d

# 5. Health check
if wait_healthy; then
    log "=== Deploy successful: v$TARGET_VERSION ==="
    record_deploy "$TARGET_VERSION" "DEPLOYED" "$PREV_VERSION"
else
    log "=== Health check FAILED for v$TARGET_VERSION ==="
    log "Attempting automatic rollback to v$PREV_VERSION..."

    if [ "$PREV_VERSION" != "unknown" ] && [ "$PREV_VERSION" != "$TARGET_VERSION" ]; then
        git checkout "v$PREV_VERSION"
        export LOKO_VERSION="$PREV_VERSION"
        $COMPOSE_CMD pull
        $COMPOSE_CMD up -d

        if wait_healthy; then
            log "Rollback to v$PREV_VERSION successful."
            record_deploy "$TARGET_VERSION" "FAILED+ROLLBACK" "$PREV_VERSION"
        else
            log "CRITICAL: Rollback to v$PREV_VERSION also failed!"
            record_deploy "$TARGET_VERSION" "FAILED+ROLLBACK_FAILED" "$PREV_VERSION"
        fi
    else
        record_deploy "$TARGET_VERSION" "FAILED" "$PREV_VERSION"
    fi

    exit 1
fi
