#!/bin/bash
# Setup LOKO Backup Cron Job
# Implements O3 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup_loko.sh"

# Check if backup script exists
if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo "ERROR: Backup script not found: $BACKUP_SCRIPT"
    exit 1
fi

# Make backup script executable
chmod +x "$BACKUP_SCRIPT"
chmod +x "${SCRIPT_DIR}/restore_loko.sh"

echo "Setting up LOKO backup cron job..."

# Add cron job (runs daily at 2 AM)
CRON_CMD="0 2 * * * $BACKUP_SCRIPT >> /var/log/loko_backup.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "backup_loko.sh"; then
    echo "⚠ Backup cron job already exists. Removing old entry..."
    crontab -l 2>/dev/null | grep -v "backup_loko.sh" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo "✅ Backup cron job configured:"
echo "   Schedule: Daily at 2:00 AM"
echo "   Script: $BACKUP_SCRIPT"
echo "   Log: /var/log/loko_backup.log"
echo ""
echo "Current crontab:"
crontab -l | grep "backup_loko.sh"

# Setup encryption (age recommended)
echo ""
echo "📝 Next steps for encryption setup:"
echo ""
echo "Option 1 - Using age (recommended):"
echo "  1. Install age: https://github.com/FiloSottile/age"
echo "  2. Generate keypair:"
echo "     age-keygen -o ~/.loko_backup_key_private.txt"
echo "  3. Extract public key to:"
echo "     grep 'public key:' ~/.loko_backup_key_private.txt | cut -d: -f2 | tr -d ' ' > ~/.loko_backup_key.txt"
echo ""
echo "Option 2 - Using gpg:"
echo "  1. Create GPG key: gpg --gen-key"
echo "  2. Save recipient: echo 'your@email.com' > ~/.loko_backup_gpg_recipient"
echo ""
echo "Option 3 - rclone remote storage setup:"
echo "  1. Install rclone: https://rclone.org/"
echo "  2. Configure remote: rclone config"
echo "  3. Name the remote: 'loko-backup'"
echo ""
echo "⚠ Without encryption/remote, backups are local and unencrypted!"

exit 0
