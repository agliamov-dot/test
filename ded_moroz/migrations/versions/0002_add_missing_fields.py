from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_add_missing_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    safety_status_enum = sa.Enum("safe", "needs_review", "blocked", name="safetystatus")
    safety_status_enum.create(op.get_bind(), checkfirst=True)

    gift_type_enum = sa.Enum("text", "url", "payload", name="gifttype")
    gift_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("users", sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )

    op.add_column(
        "gifts",
        sa.Column("gift_type", gift_type_enum, server_default="text", nullable=False),
    )
    op.add_column("gifts", sa.Column("payload", sa.JSON(), nullable=True))

    op.add_column("poem_attempts", sa.Column("safety_status", safety_status_enum, server_default="safe", nullable=False))
    op.add_column("submissions", sa.Column("safety_status", safety_status_enum, server_default="safe", nullable=False))

    op.add_column("error_logs", sa.Column("service_name", sa.String(length=255), nullable=True))

    op.add_column(
        "service_heartbeats",
        sa.Column("beat_interval_seconds", sa.Integer(), server_default="600", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("service_heartbeats", "beat_interval_seconds")

    op.drop_column("error_logs", "service_name")

    op.drop_column("submissions", "safety_status")
    op.drop_column("poem_attempts", "safety_status")

    op.drop_column("gifts", "payload")
    op.drop_column("gifts", "gift_type")

    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "stopped_at")
    op.drop_column("users", "paused_at")
    op.drop_column("users", "enrolled_at")

    sa.Enum(name="gifttype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="safetystatus").drop(op.get_bind(), checkfirst=True)
