"""Initial database schema."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "001_init_init_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "feed_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "feed_id",
            sa.Integer(),
            sa.ForeignKey("feeds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_feed_items_feed_id_published",
        "feed_items",
        ["feed_id", "published"],
    )
    op.create_index(
        "ix_feed_items_feed_id_link",
        "feed_items",
        ["feed_id", "link"],
        unique=True,
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname = 'ix_feed_items_feed_id_published'
            ) THEN
                CREATE INDEX ix_feed_items_feed_id_published
                ON feed_items (feed_id, published);
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname = 'ix_feed_items_feed_id_link'
            ) THEN
                CREATE UNIQUE INDEX ix_feed_items_feed_id_link
                ON feed_items (feed_id, link);
            END IF;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_feed_items_feed_id_link", table_name="feed_items")
    op.drop_index("ix_feed_items_feed_id_published", table_name="feed_items")
    op.drop_table("feed_items")
    op.drop_table("feeds")
