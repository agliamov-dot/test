from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    Text,
    DateTime,
    JSON,
    LargeBinary,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Feed(Base):
    __tablename__ = "feeds"

    id = Column(Integer, primary_key=True)
    rss_url = Column(Text, unique=True, nullable=False)
    site_url = Column(Text)
    title = Column(Text)
    etag = Column(Text)
    last_modified_hdr = Column(Text)
    fetch_every_minutes = Column(Integer, nullable=False, default=60)
    last_checked_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items = relationship("Item", back_populates="feed")


class Item(Base):
    __tablename__ = "items"

    id = Column(BigInteger, primary_key=True)
    feed_id = Column(
        Integer, ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False
    )
    guid = Column(Text)
    link = Column(Text, nullable=False)
    link_hash = Column(LargeBinary, nullable=False)
    title = Column(Text)
    summary = Column(Text)
    content_html = Column(Text)
    content_text = Column(Text)
    author = Column(Text)
    published_at = Column(DateTime(timezone=True))
    updated_at_src = Column(DateTime(timezone=True))
    language = Column(Text)
    categories = Column(JSON)
    canonical_url = Column(Text)
    content_hash = Column(LargeBinary)
    simhash64 = Column(BigInteger)
    image_primary_id = Column(BigInteger)
    video_url = Column(Text)
    status = Column(Text, nullable=False, default="imported")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    feed = relationship("Feed", back_populates="items")
    media = relationship("MediaAsset", back_populates="item")

    __table_args__ = (
        Index(
            "idx_items_feed_published",
            "feed_id",
            "published_at",
            postgresql_using="btree",
        ),
        Index("idx_items_status", "status"),
        Index("idx_items_simhash", "simhash64"),
    )


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id = Column(BigInteger, primary_key=True)
    item_id = Column(
        BigInteger, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    source = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    media_type = Column(Text, nullable=False)
    original_url = Column(Text, nullable=False)
    local_path = Column(Text)
    mime_type = Column(Text)
    width = Column(Integer)
    height = Column(Integer)
    duration_sec = Column(Integer)
    hash_sha256 = Column(LargeBinary)
    status = Column(Text, nullable=False, default="new")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    item = relationship("Item", back_populates="media")

    __table_args__ = (
        Index("idx_media_item", "item_id"),
        Index("idx_media_status", "status"),
    )


class Variant(Base):
    __tablename__ = "variants"

    id = Column(BigInteger, primary_key=True)
    item_id = Column(
        BigInteger, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    lang = Column(Text, nullable=False)
    variant_type = Column(Text, nullable=False)
    title = Column(Text)
    content_html = Column(Text)
    content_text = Column(Text)
    seo_title = Column(Text)
    seo_description = Column(Text)
    provider = Column(Text)
    quality_score = Column(Integer)
    is_selected = Column(Boolean, nullable=False, default=False)
    status = Column(Text, nullable=False, default="draft")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    item = relationship("Item")
