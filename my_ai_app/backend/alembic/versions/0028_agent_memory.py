"""Create persistent agent memory storage matching harness 0.12.0.

The harness also performs idempotent schema checks on first use. Keep this
migration in sync when intentionally upgrading the pinned harness dependency.
"""

from alembic import op

revision = "0028_agent_memory"
down_revision = "0027_user_magic_link_epoch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SELECT pg_advisory_xact_lock(hashtext('agent_memory_metadata'))")
    op.execute(
        "CREATE TABLE IF NOT EXISTS agent_memory (path TEXT PRIMARY KEY, content TEXT NOT NULL, version BIGINT NOT NULL DEFAULT 1, last_operation_id TEXT)"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS agent_memory_operations (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, version TEXT, existed BOOLEAN NOT NULL, completed BOOLEAN NOT NULL)"
    )
    op.execute("CREATE SEQUENCE IF NOT EXISTS agent_memory_versions MINVALUE 0 START 0")
    op.execute(
        "CREATE TABLE IF NOT EXISTS agent_memory_metadata (id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id), versions_initialized BOOLEAN NOT NULL)"
    )
    # The harness initializes sequence-backed versions under the same lock on
    # first use, preserving its compare-and-swap and operation receipt rules.


def downgrade() -> None:
    op.drop_table("agent_memory_operations")
    op.drop_table("agent_memory_metadata")
    op.drop_table("agent_memory")
    op.execute("DROP SEQUENCE agent_memory_versions")
