"""Require explicit workspace departure before deleting an account."""

from alembic import op

revision = "0030_support_owner_retention"
down_revision = "0029_support"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "support_memberships_user_id_fkey", "support_memberships", type_="foreignkey"
    )
    op.create_foreign_key(
        "support_memberships_user_id_fkey",
        "support_memberships",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint(
        "support_memberships_user_id_fkey", "support_memberships", type_="foreignkey"
    )
    op.create_foreign_key(
        "support_memberships_user_id_fkey",
        "support_memberships",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
