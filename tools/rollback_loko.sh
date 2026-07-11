#!/bin/bash
# LOKO — Quick rollback to a previous stable version.
#
# Usage:
#   ./tools/rollback_loko.sh              # rollback to the previous version
#   ./tools/rollback_loko.sh 0.3.7        # rollback to a specific version
#   ./tools/rollback_loko.sh --list       # show available versions
#
# This is a convenience wrapper around deploy_version.sh.
# Designed to run on the VPS (/opt/loko).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_SCRIPT="$SCRIPT_DIR/deploy_version.sh"

log()   { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { log "ERROR: $*"; exit 1; }

# Ensure deploy_version.sh exists
if [ ! -x "$DEPLOY_SCRIPT" ]; then
    error "deploy_version.sh not found or not executable at $DEPLOY_SCRIPT"
fi

# Handle --list
if [ "${1:-}" = "--list" ] || [ "${1:-}" = "-l" ]; then
    exec "$DEPLOY_SCRIPT" --list
fi

# Handle --help
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    echo "LOKO Rollback — Quick rollback to a previous stable version"
    echo ""
    echo "Usage:"
    echo "  $0              Rollback to the previous version"
    echo "  $0 <version>    Rollback to a specific version (e.g. 0.3.7)"
    echo "  $0 --list       Show available versions and current version"
    echo ""
    echo "Examples:"
    echo "  $0              # auto-detect previous version, rollback"
    echo "  $0 0.3.7        # rollback to v0.3.7"
    echo "  $0 v0.3.7       # same (leading 'v' is stripped)"
    exit 0
fi

TARGET="${1:-}"

if [ -z "$TARGET" ]; then
    # Auto-detect: find the version before the current one
    log "Auto-detecting previous version..."

    PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

    # Get current version from health endpoint
    CURRENT=$(curl -sf "http://localhost:8001/health" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('version',''))" 2>/dev/null || true)

    if [ -z "$CURRENT" ]; then
        # Fallback: current git tag
        CURRENT=$(git -C "$PROJECT_DIR" describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' || true)
    fi

    if [ -z "$CURRENT" ]; then
        error "Cannot determine current version. Specify a target version: $0 <version>"
    fi

    # Find the tag just before the current one
    TARGET=$(git -C "$PROJECT_DIR" tag -l "v*.*.*" --sort=-version:refname \
        | sed 's/^v//' \
        | awk -v cur="$CURRENT" 'found{print;exit} $0==cur{found=1}')

    if [ -z "$TARGET" ]; then
        error "No previous version found before v$CURRENT. Use: $0 <version>"
    fi

    log "Current: v$CURRENT -> Rollback target: v$TARGET"
    echo ""
    read -rp "Proceed with rollback to v$TARGET? [y/N] " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        log "Rollback cancelled."
        exit 0
    fi
fi

# Strip leading 'v' if provided
TARGET="${TARGET#v}"

log "=== ROLLBACK to v$TARGET ==="
exec "$DEPLOY_SCRIPT" "$TARGET"
