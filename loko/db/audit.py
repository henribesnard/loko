"""
Audit logging system for LOKO
Implements K2 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

Provides append-only audit trail for administrative actions and authentication events.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import json


class AuditLogger:
    """
    Audit logger for tracking administrative actions and security events.

    Features:
    - Append-only audit trail (no updates or deletes)
    - Structured action names (e.g., "bot.create", "auth.login_failed")
    - JSON details without sensitive data
    - IP address tracking
    - Automatic timestamp in UTC
    """

    # Standard action names (use these for consistency)
    # Bot management
    ACTION_BOT_CREATE = "bot.create"
    ACTION_BOT_UPDATE = "bot.update"
    ACTION_BOT_DELETE = "bot.delete"
    ACTION_BOT_PUBLISH = "bot.publish"

    # Intent management
    ACTION_INTENT_CREATE = "intent.create"
    ACTION_INTENT_UPDATE = "intent.update"
    ACTION_INTENT_DELETE = "intent.delete"

    # Knowledge management
    ACTION_KNOWLEDGE_ADD = "knowledge.add"
    ACTION_KNOWLEDGE_DELETE = "knowledge.delete"

    # API key management
    ACTION_KEY_CREATE = "key.create"
    ACTION_KEY_ROTATE = "key.rotate"
    ACTION_KEY_REVOKE = "key.revoke"
    ACTION_KEY_EXPIRED = "key.expired"

    # Authentication
    ACTION_AUTH_LOGIN = "auth.login"
    ACTION_AUTH_LOGIN_FAILED = "auth.login_failed"
    ACTION_AUTH_LOGOUT = "auth.logout"
    ACTION_AUTH_SIGNUP = "auth.signup"
    ACTION_AUTH_PASSWORD_RESET = "auth.password_reset"
    ACTION_AUTH_EMAIL_VERIFY = "auth.email_verify"

    # User management
    ACTION_USER_CREATE = "user.create"
    ACTION_USER_UPDATE = "user.update"
    ACTION_USER_DELETE = "user.delete"

    # Model training
    ACTION_MODEL_TRAIN = "model.train"
    ACTION_MODEL_DELETE = "model.delete"

    def __init__(self, db_path: str = ".loko/audit.db"):
        """
        Initialize audit logger.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_database()

    def _ensure_database(self):
        """Create audit_logs table if it doesn't exist."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    resource_id TEXT,
                    ip_address TEXT,
                    details TEXT,
                    created_at_utc TEXT NOT NULL
                )
            """)

            # Index for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_logs(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_user
                ON audit_logs(user_id, timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_action
                ON audit_logs(action, timestamp DESC)
            """)

            conn.commit()
        finally:
            conn.close()

    def log(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        """
        Log an audit event.

        Args:
            action: Action name (use ACTION_* constants)
            user_id: User ID performing the action (None for anonymous)
            resource_id: ID of the resource affected (bot_id, intent_id, etc.)
            ip_address: IP address of the client
            details: Additional details as dict (will be serialized to JSON)

        Notes:
            - Details must not contain sensitive data (passwords, tokens, messages)
            - Timestamps are automatically added in UTC
            - This is an append-only operation (no updates or deletes)
        """
        now = datetime.now(timezone.utc)
        timestamp_iso = now.isoformat()

        # Sanitize details (remove sensitive keys if present)
        if details:
            details = self._sanitize_details(details)
            details_json = json.dumps(details)
        else:
            details_json = None

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO audit_logs
                (timestamp, user_id, action, resource_id, ip_address, details, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp_iso,
                    user_id,
                    action,
                    resource_id,
                    ip_address,
                    details_json,
                    timestamp_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _sanitize_details(self, details: dict[str, Any]) -> dict[str, Any]:
        """
        Remove sensitive keys from details dict.

        Args:
            details: Original details dict

        Returns:
            Sanitized details dict (copy)
        """
        # Keys that should never appear in audit logs
        SENSITIVE_KEYS = {
            "password",
            "password_hash",
            "token",
            "api_key",
            "secret",
            "message",  # User messages (RGPD)
            "content",  # User content
            "session_token",
            "auth_token",
            "bearer_token",
        }

        sanitized = {}
        for key, value in details.items():
            # Skip sensitive keys
            if key.lower() in SENSITIVE_KEYS or any(
                sensitive in key.lower()
                for sensitive in ["password", "token", "secret", "key"]
            ):
                sanitized[key] = "[REDACTED]"
            # Recursively sanitize nested dicts
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_details(value)
            else:
                sanitized[key] = value

        return sanitized

    def get_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query audit logs.

        Args:
            user_id: Filter by user ID
            action: Filter by action name
            since: Filter by timestamp (only logs after this time)
            limit: Maximum number of logs to return

        Returns:
            List of audit log entries as dicts
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if action:
            query += " AND action = ?"
            params.append(action)

        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        try:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            logs = []
            for row in rows:
                log_entry = dict(row)
                # Parse JSON details
                if log_entry["details"]:
                    log_entry["details"] = json.loads(log_entry["details"])
                logs.append(log_entry)

            return logs
        finally:
            conn.close()

    def export_csv(
        self,
        output_path: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ):
        """
        Export audit logs to CSV file.

        Args:
            output_path: Path to output CSV file
            since: Start date (None = from beginning)
            until: End date (None = until now)
        """
        import csv

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []

        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())

        if until:
            query += " AND timestamp <= ?"
            params.append(until.isoformat())

        query += " ORDER BY timestamp ASC"

        try:
            cursor = conn.execute(query, params)

            with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)

                # Header
                writer.writerow(
                    [
                        "id",
                        "timestamp",
                        "user_id",
                        "action",
                        "resource_id",
                        "ip_address",
                        "details",
                    ]
                )

                # Rows
                for row in cursor:
                    writer.writerow(
                        [
                            row["id"],
                            row["timestamp"],
                            row["user_id"] or "",
                            row["action"],
                            row["resource_id"] or "",
                            row["ip_address"] or "",
                            row["details"] or "",
                        ]
                    )
        finally:
            conn.close()

    def purge_old_logs(self, days: int = 365):
        """
        Delete audit logs older than specified days.

        Args:
            days: Number of days to retain (default 365)

        Returns:
            Number of deleted logs

        Notes:
            - Aligned with retention policy (lot Q)
            - Should be called periodically (e.g., daily cron)
        """
        cutoff_date = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        cutoff_date = cutoff_date.replace(day=cutoff_date.day - days)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM audit_logs WHERE timestamp < ?",
                (cutoff_date.isoformat(),),
            )
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count
        finally:
            conn.close()
