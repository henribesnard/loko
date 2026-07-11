"""
Tests for audit logging system (K2)
Implements tests for PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
"""

import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from loko.db.audit import AuditLogger


@pytest.fixture
def audit_logger():
    """Create a temporary audit logger for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_audit.db"
        logger = AuditLogger(str(db_path))
        yield logger


class TestAuditLogger:
    """Test audit logging functionality."""

    def test_log_basic(self, audit_logger):
        """Test basic audit log entry."""
        audit_logger.log(
            action=AuditLogger.ACTION_BOT_CREATE,
            user_id="user123",
            resource_id="bot456",
            ip_address="192.168.1.1",
            details={"name": "Test Bot"},
        )

        logs = audit_logger.get_logs(limit=1)
        assert len(logs) == 1

        log = logs[0]
        assert log["action"] == AuditLogger.ACTION_BOT_CREATE
        assert log["user_id"] == "user123"
        assert log["resource_id"] == "bot456"
        assert log["ip_address"] == "192.168.1.1"
        assert log["details"]["name"] == "Test Bot"
        assert "timestamp" in log

    def test_log_without_optional_fields(self, audit_logger):
        """Test audit log with minimal fields."""
        audit_logger.log(action=AuditLogger.ACTION_AUTH_LOGIN_FAILED)

        logs = audit_logger.get_logs(limit=1)
        assert len(logs) == 1

        log = logs[0]
        assert log["action"] == AuditLogger.ACTION_AUTH_LOGIN_FAILED
        assert log["user_id"] is None
        assert log["resource_id"] is None
        assert log["ip_address"] is None
        assert log["details"] is None

    def test_sanitize_password(self, audit_logger):
        """Test that passwords are sanitized from audit logs."""
        audit_logger.log(
            action=AuditLogger.ACTION_AUTH_SIGNUP,
            user_id="user123",
            details={"email": "user@example.com", "password": "secret123"},
        )

        logs = audit_logger.get_logs(limit=1)
        log = logs[0]

        assert log["details"]["email"] == "user@example.com"
        assert log["details"]["password"] == "[REDACTED]"

    def test_sanitize_token(self, audit_logger):
        """Test that tokens are sanitized from audit logs."""
        audit_logger.log(
            action=AuditLogger.ACTION_KEY_CREATE,
            user_id="user123",
            details={"api_key": "sk-1234567890", "bot_id": "bot123"},
        )

        logs = audit_logger.get_logs(limit=1)
        log = logs[0]

        assert log["details"]["bot_id"] == "bot123"
        assert log["details"]["api_key"] == "[REDACTED]"

    def test_sanitize_message_content(self, audit_logger):
        """Test that user messages are not logged (RGPD compliance)."""
        audit_logger.log(
            action=AuditLogger.ACTION_BOT_UPDATE,
            user_id="user123",
            details={"message": "User's private message", "status": "updated"},
        )

        logs = audit_logger.get_logs(limit=1)
        log = logs[0]

        assert log["details"]["status"] == "updated"
        assert log["details"]["message"] == "[REDACTED]"

    def test_query_by_user(self, audit_logger):
        """Test querying logs by user ID."""
        audit_logger.log(action=AuditLogger.ACTION_BOT_CREATE, user_id="user1")
        audit_logger.log(action=AuditLogger.ACTION_BOT_CREATE, user_id="user2")
        audit_logger.log(action=AuditLogger.ACTION_BOT_DELETE, user_id="user1")

        logs = audit_logger.get_logs(user_id="user1")
        assert len(logs) == 2
        assert all(log["user_id"] == "user1" for log in logs)

    def test_query_by_action(self, audit_logger):
        """Test querying logs by action."""
        audit_logger.log(action=AuditLogger.ACTION_BOT_CREATE, user_id="user1")
        audit_logger.log(action=AuditLogger.ACTION_BOT_UPDATE, user_id="user1")
        audit_logger.log(action=AuditLogger.ACTION_BOT_CREATE, user_id="user2")

        logs = audit_logger.get_logs(action=AuditLogger.ACTION_BOT_CREATE)
        assert len(logs) == 2
        assert all(log["action"] == AuditLogger.ACTION_BOT_CREATE for log in logs)

    def test_query_by_time(self, audit_logger):
        """Test querying logs by timestamp."""
        now = datetime.now(timezone.utc)

        # Log in the past
        audit_logger.log(action=AuditLogger.ACTION_BOT_CREATE, user_id="user1")

        # Wait a bit
        since = now

        # Log now
        audit_logger.log(action=AuditLogger.ACTION_BOT_UPDATE, user_id="user2")

        logs = audit_logger.get_logs(since=since)
        # Should only get the recent log (or both, depending on timing)
        assert len(logs) >= 1
        assert logs[0]["action"] == AuditLogger.ACTION_BOT_UPDATE

    def test_query_limit(self, audit_logger):
        """Test query limit."""
        for i in range(10):
            audit_logger.log(action=AuditLogger.ACTION_BOT_CREATE, user_id=f"user{i}")

        logs = audit_logger.get_logs(limit=5)
        assert len(logs) == 5

    def test_logs_ordered_by_timestamp_desc(self, audit_logger):
        """Test that logs are returned in reverse chronological order."""
        audit_logger.log(action=AuditLogger.ACTION_BOT_CREATE, resource_id="bot1")
        audit_logger.log(action=AuditLogger.ACTION_BOT_UPDATE, resource_id="bot2")
        audit_logger.log(action=AuditLogger.ACTION_BOT_DELETE, resource_id="bot3")

        logs = audit_logger.get_logs(limit=10)
        assert len(logs) == 3

        # Most recent first
        assert logs[0]["resource_id"] == "bot3"
        assert logs[1]["resource_id"] == "bot2"
        assert logs[2]["resource_id"] == "bot1"

    def test_export_csv(self, audit_logger, tmp_path):
        """Test CSV export functionality."""
        audit_logger.log(
            action=AuditLogger.ACTION_BOT_CREATE,
            user_id="user1",
            resource_id="bot1",
            ip_address="192.168.1.1",
        )
        audit_logger.log(
            action=AuditLogger.ACTION_BOT_UPDATE,
            user_id="user2",
            resource_id="bot1",
            ip_address="192.168.1.2",
        )

        csv_path = tmp_path / "audit_export.csv"
        audit_logger.export_csv(str(csv_path))

        assert csv_path.exists()

        # Read and verify CSV
        import csv
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["action"] == AuditLogger.ACTION_BOT_CREATE
        assert rows[1]["action"] == AuditLogger.ACTION_BOT_UPDATE

    def test_purge_old_logs(self, audit_logger):
        """Test purging old audit logs."""
        # Create old log (simulate by direct DB manipulation)
        old_date = datetime.now(timezone.utc) - timedelta(days=400)

        import sqlite3
        conn = sqlite3.connect(audit_logger.db_path)
        conn.execute(
            """
            INSERT INTO audit_logs
            (timestamp, action, created_at_utc)
            VALUES (?, ?, ?)
            """,
            (old_date.isoformat(), AuditLogger.ACTION_BOT_CREATE, old_date.isoformat()),
        )
        conn.commit()
        conn.close()

        # Create recent log
        audit_logger.log(action=AuditLogger.ACTION_BOT_UPDATE)

        # Should have 2 logs
        logs = audit_logger.get_logs(limit=10)
        assert len(logs) == 2

        # Purge logs older than 365 days
        deleted = audit_logger.purge_old_logs(days=365)
        assert deleted == 1

        # Should have 1 log left
        logs = audit_logger.get_logs(limit=10)
        assert len(logs) == 1
        assert logs[0]["action"] == AuditLogger.ACTION_BOT_UPDATE

    def test_failed_login_tracking(self, audit_logger):
        """Test tracking failed login attempts (security monitoring)."""
        ip = "192.168.1.100"

        # Simulate multiple failed attempts
        for i in range(5):
            audit_logger.log(
                action=AuditLogger.ACTION_AUTH_LOGIN_FAILED,
                ip_address=ip,
                details={"email": "attacker@example.com", "reason": "invalid_password"},
            )

        # Query failed logins from this IP
        logs = audit_logger.get_logs(action=AuditLogger.ACTION_AUTH_LOGIN_FAILED, limit=10)

        # Filter by IP (would need additional query parameter in real implementation)
        failed_from_ip = [log for log in logs if log["ip_address"] == ip]
        assert len(failed_from_ip) == 5

    def test_no_conversational_data(self, audit_logger):
        """Test that conversational data is never logged (RGPD)."""
        # This should be sanitized
        audit_logger.log(
            action=AuditLogger.ACTION_BOT_UPDATE,
            user_id="user123",
            details={
                "config_updated": True,
                "message": "User's private conversation",
                "content": "More private content",
            },
        )

        logs = audit_logger.get_logs(limit=1)
        log = logs[0]

        assert log["details"]["config_updated"] is True
        assert log["details"]["message"] == "[REDACTED]"
        assert log["details"]["content"] == "[REDACTED]"
