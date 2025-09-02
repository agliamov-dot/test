"""initial schema

Revision ID: 0001_init
Revises: 
Create Date: 2023-01-01
"""
from __future__ import annotations

from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE feeds (
  id                  SERIAL PRIMARY KEY,
  rss_url             TEXT UNIQUE NOT NULL,
  site_url            TEXT,
  title               TEXT,
  etag                TEXT,
  last_modified_hdr   TEXT,
  fetch_every_minutes INT  NOT NULL DEFAULT 60,
  last_checked_at     TIMESTAMPTZ,
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  notes               TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE items (
  id                BIGSERIAL PRIMARY KEY,
  feed_id           INT NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
  guid              TEXT,
  link              TEXT NOT NULL,
  link_hash         BYTEA NOT NULL,
  title             TEXT,
  summary           TEXT,
  content_html      TEXT,
  content_text      TEXT,
  author            TEXT,
  published_at      TIMESTAMPTZ,
  updated_at_src    TIMESTAMPTZ,
  language          TEXT,
  categories        JSONB,
  canonical_url     TEXT,
  content_hash      BYTEA,
  simhash64         BIGINT,
  image_primary_id  BIGINT,
  video_url         TEXT,
  status            TEXT NOT NULL DEFAULT 'imported',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (feed_id, guid),
  UNIQUE (link_hash)
);

CREATE TABLE media_assets (
  id             BIGSERIAL PRIMARY KEY,
  item_id        BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  source         TEXT NOT NULL,
  role           TEXT NOT NULL,
  media_type     TEXT NOT NULL,
  original_url   TEXT NOT NULL,
  local_path     TEXT,
  mime_type      TEXT,
  width          INT,
  height         INT,
  duration_sec   INT,
  hash_sha256    BYTEA,
  status         TEXT NOT NULL DEFAULT 'new',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE variants (
  id               BIGSERIAL PRIMARY KEY,
  item_id          BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  lang             TEXT NOT NULL,
  variant_type     TEXT NOT NULL,
  title            TEXT,
  content_html     TEXT,
  content_text     TEXT,
  seo_title        TEXT,
  seo_description  TEXT,
  provider         TEXT,
  quality_score    REAL,
  is_selected      BOOLEAN NOT NULL DEFAULT FALSE,
  status           TEXT NOT NULL DEFAULT 'draft',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_items_feed_published ON items(feed_id, published_at DESC);
CREATE INDEX idx_items_status ON items(status);
CREATE INDEX idx_items_simhash ON items(simhash64);
CREATE INDEX idx_media_item ON media_assets(item_id);
CREATE INDEX idx_media_status ON media_assets(status);
""")


def downgrade() -> None:
    op.execute("""
DROP TABLE variants;
DROP TABLE media_assets;
DROP TABLE items;
DROP TABLE feeds;
""")
