from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20251227154935_extend_gift_media_types"
down_revision = "0003_telegram_id_bigint"
branch_labels = None
depends_on = None


GIFT_TYPE_VALUES = ["text", "url", "payload", "photo", "video", "audio"]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in GIFT_TYPE_VALUES:
            op.execute(sa.text("ALTER TYPE gifttype ADD VALUE IF NOT EXISTS :value"), {"value": value})
    else:
        # SQLite and other dialects recreate enums automatically from models; nothing to do.
        pass


def downgrade() -> None:
    # Downgrading enums with removed values is unsafe; no-op to avoid data loss.
    pass
