#!/bin/bash
# Setup Docker Secrets for LOKO
# Implements K1 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
#
# Usage:
#   ./setup_secrets.sh init         # Create secrets directory and templates
#   ./setup_secrets.sh generate     # Generate secure random secrets
#   ./setup_secrets.sh verify       # Verify secret files exist and have correct permissions

set -euo pipefail

SECRETS_DIR="${LOKO_SECRETS_DIR:-.}/secrets"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Initialize secrets directory
init_secrets() {
    log_info "Initializing secrets directory: $SECRETS_DIR"

    mkdir -p "$SECRETS_DIR"
    chmod 700 "$SECRETS_DIR"

    # Create template files
    cat > "$SECRETS_DIR/README.md" << 'EOF'
# LOKO Secrets Directory

This directory contains sensitive secrets for LOKO deployment.

## Files

- `loko_admin_token.txt` - Admin API token (required)
- `smtp_password.txt` - SMTP password for email sending (optional)
- `loko_llm_api_key.txt` - LLM provider API key (optional)

## Security

- **Never commit these files to git** (already in .gitignore)
- Files should have 600 permissions (owner read/write only)
- Keep backups in a secure location (password manager, encrypted storage)

## Usage

### Docker Compose (Production)

Set `LOKO_SECRETS_DIR` environment variable:

```bash
export LOKO_SECRETS_DIR=/path/to/secrets
docker compose up -d
```

### Docker Swarm (Advanced)

Use Docker secrets:

```bash
echo "your-token" | docker secret create loko_admin_token -
docker stack deploy -c docker-compose.yml loko
```

## Generation

Generate secure random secrets:

```bash
./setup_secrets.sh generate
```

## Rotation

To rotate secrets:

1. Generate new secret: `openssl rand -base64 32 > secrets/loko_admin_token.txt.new`
2. Update deployment with new secret
3. After verification, remove old secret

## Verification

Check secret files exist and have correct permissions:

```bash
./setup_secrets.sh verify
```
EOF

    log_info "✅ Secrets directory initialized"
    log_info "   Location: $SECRETS_DIR"
    log_info "   Permissions: $(stat -c %a "$SECRETS_DIR" 2>/dev/null || stat -f %A "$SECRETS_DIR")"
    echo ""
    log_info "Next steps:"
    log_info "  1. Run: ./setup_secrets.sh generate"
    log_info "  2. Edit secrets in: $SECRETS_DIR"
    log_info "  3. Run: ./setup_secrets.sh verify"
}

# Generate secure random secrets
generate_secrets() {
    log_info "Generating secure random secrets..."

    # Admin token (required)
    if [ ! -f "$SECRETS_DIR/loko_admin_token.txt" ]; then
        openssl rand -base64 32 > "$SECRETS_DIR/loko_admin_token.txt"
        chmod 600 "$SECRETS_DIR/loko_admin_token.txt"
        log_info "✅ Generated: loko_admin_token.txt"
    else
        log_warn "⚠ Skipped: loko_admin_token.txt already exists"
    fi

    # SMTP password (optional, create template)
    if [ ! -f "$SECRETS_DIR/smtp_password.txt" ]; then
        echo "your-smtp-password-here" > "$SECRETS_DIR/smtp_password.txt"
        chmod 600 "$SECRETS_DIR/smtp_password.txt"
        log_info "✅ Created template: smtp_password.txt (edit with your SMTP password)"
    else
        log_warn "⚠ Skipped: smtp_password.txt already exists"
    fi

    # LLM API key (optional, create template)
    if [ ! -f "$SECRETS_DIR/loko_llm_api_key.txt" ]; then
        echo "your-llm-api-key-here" > "$SECRETS_DIR/loko_llm_api_key.txt"
        chmod 600 "$SECRETS_DIR/loko_llm_api_key.txt"
        log_info "✅ Created template: loko_llm_api_key.txt (edit with your LLM API key)"
    else
        log_warn "⚠ Skipped: loko_llm_api_key.txt already exists"
    fi

    echo ""
    log_info "Secrets generated in: $SECRETS_DIR"
    log_info "⚠ Remember to edit template files with your actual values!"
}

# Verify secrets exist and have correct permissions
verify_secrets() {
    log_info "Verifying secrets configuration..."
    echo ""

    local errors=0

    # Check directory exists and has correct permissions
    if [ ! -d "$SECRETS_DIR" ]; then
        log_error "Secrets directory not found: $SECRETS_DIR"
        log_error "Run: ./setup_secrets.sh init"
        return 1
    fi

    local dir_perms=$(stat -c %a "$SECRETS_DIR" 2>/dev/null || stat -f %A "$SECRETS_DIR")
    if [ "$dir_perms" != "700" ]; then
        log_warn "Directory permissions should be 700, found: $dir_perms"
        log_warn "Fix: chmod 700 $SECRETS_DIR"
    fi

    # Check required secrets
    log_info "Checking required secrets:"

    # Admin token (required)
    if [ -f "$SECRETS_DIR/loko_admin_token.txt" ]; then
        local perms=$(stat -c %a "$SECRETS_DIR/loko_admin_token.txt" 2>/dev/null || stat -f %A "$SECRETS_DIR/loko_admin_token.txt")
        local size=$(wc -c < "$SECRETS_DIR/loko_admin_token.txt" | tr -d ' ')

        if [ "$perms" = "600" ] || [ "$perms" = "400" ]; then
            if [ "$size" -gt 10 ]; then
                log_info "  ✅ loko_admin_token.txt (permissions: $perms, size: $size bytes)"
            else
                log_error "  ❌ loko_admin_token.txt is too short ($size bytes)"
                errors=$((errors + 1))
            fi
        else
            log_warn "  ⚠ loko_admin_token.txt has insecure permissions: $perms (should be 600)"
            log_warn "     Fix: chmod 600 $SECRETS_DIR/loko_admin_token.txt"
            errors=$((errors + 1))
        fi
    else
        log_error "  ❌ loko_admin_token.txt NOT FOUND (required)"
        errors=$((errors + 1))
    fi

    # Check optional secrets
    echo ""
    log_info "Checking optional secrets:"

    for secret in smtp_password.txt loko_llm_api_key.txt; do
        if [ -f "$SECRETS_DIR/$secret" ]; then
            local perms=$(stat -c %a "$SECRETS_DIR/$secret" 2>/dev/null || stat -f %A "$SECRETS_DIR/$secret")
            local content=$(cat "$SECRETS_DIR/$secret")

            if [ "$perms" = "600" ] || [ "$perms" = "400" ]; then
                if [[ "$content" == *"your-"*"-here"* ]]; then
                    log_warn "  ⚠ $secret is a template, edit with actual value"
                else
                    log_info "  ✅ $secret (permissions: $perms)"
                fi
            else
                log_warn "  ⚠ $secret has insecure permissions: $perms (should be 600)"
                log_warn "     Fix: chmod 600 $SECRETS_DIR/$secret"
            fi
        else
            log_info "  ⏭ $secret (optional, not configured)"
        fi
    done

    echo ""
    if [ $errors -eq 0 ]; then
        log_info "✅ All checks passed!"
        return 0
    else
        log_error "❌ Found $errors error(s)"
        return 1
    fi
}

# Main command dispatcher
case "${1:-}" in
    init)
        init_secrets
        ;;
    generate)
        if [ ! -d "$SECRETS_DIR" ]; then
            log_error "Secrets directory not found. Run: ./setup_secrets.sh init"
            exit 1
        fi
        generate_secrets
        ;;
    verify)
        verify_secrets
        ;;
    *)
        echo "LOKO Secrets Management"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  init      - Create secrets directory and templates"
        echo "  generate  - Generate secure random secrets"
        echo "  verify    - Verify secret files exist and have correct permissions"
        echo ""
        echo "Example workflow:"
        echo "  $0 init"
        echo "  $0 generate"
        echo "  # Edit secrets in: $SECRETS_DIR"
        echo "  $0 verify"
        echo ""
        exit 1
        ;;
esac
