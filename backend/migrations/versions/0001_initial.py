"""Initial PostgreSQL 17 / pgvector schema.

Revision ID: 0001
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # The checked-in copy is immutable: subsequent changes use new revisions.
    sql = Path(__file__).with_name("0001_schema.sql").read_text(encoding="utf-8")
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    for table in ("alert_deliveries", "safety_events", "emergency_contacts", "consents", "jobs",
                  "memory_sources", "memories", "run_events", "chat_runs", "messages", "conversations",
                  "persona_examples", "personas", "assets", "rate_limit_counters", "otp_challenges",
                  "refresh_sessions", "users"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
