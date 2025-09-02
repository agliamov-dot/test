from __future__ import annotations

from datetime import datetime
from typing import Iterable
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from .config import Config
from .db import create_session_factory, session_scope
from .models import Feed, Item
from .parser import fetch_and_parse
from .normalize import canonicalize_url, sha256_bytes


Session = None


def get_session_factory(cfg: Config):
    global Session
    if Session is None:
        Session = create_session_factory(cfg)
    return Session


def add_feed(cfg: Config, rss_url: str, interval: int | None) -> int:
    Session = get_session_factory(cfg)
    with session_scope(Session) as s:
        feed = Feed(
            rss_url=rss_url,
            fetch_every_minutes=interval or cfg.default_fetch_every_minutes,
        )
        s.add(feed)
        s.flush()
        return feed.id


def list_feeds(cfg: Config) -> Iterable[Feed]:
    Session = get_session_factory(cfg)
    with session_scope(Session) as s:
        feeds = s.execute(select(Feed).where(Feed.is_active)).scalars().all()
    return feeds


def poll_once(cfg: Config, feed_id: int | None = None) -> None:
    Session = get_session_factory(cfg)
    with session_scope(Session) as s:
        q = select(Feed).where(Feed.is_active)
        if feed_id:
            q = q.where(Feed.id == feed_id)
        feeds = s.execute(q).scalars().all()
        for feed in feeds:
            parsed = fetch_and_parse(cfg, feed.rss_url)
            feed.title = parsed.title
            feed.last_checked_at = datetime.utcnow()
            for item in parsed.items:
                link = canonicalize_url(item.link)
                link_hash = sha256_bytes(link)
                stmt = (
                    insert(Item)
                    .values(
                        feed_id=feed.id,
                        guid=item.guid,
                        link=link,
                        link_hash=link_hash,
                        title=item.title,
                        summary=item.summary,
                        published_at=item.published_at,
                    )
                    .on_conflict_do_nothing(index_elements=[Item.link_hash])
                )
                s.execute(stmt)
