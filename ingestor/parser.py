from __future__ import annotations

import feedparser
from dataclasses import dataclass
from datetime import datetime
from .config import Config
from dateutil import parser as dateparser


@dataclass
class ParsedItem:
    guid: str | None
    link: str
    title: str | None
    summary: str | None
    published_at: datetime | None


@dataclass
class ParsedFeed:
    title: str | None
    items: list[ParsedItem]


def fetch_and_parse(cfg: Config, url: str) -> ParsedFeed:
    fp = feedparser.parse(url, agent=cfg.user_agent)
    items: list[ParsedItem] = []
    for e in fp.entries:
        pub = None
        if getattr(e, "published", None):
            pub = dateparser.parse(e.published)
        items.append(
            ParsedItem(
                guid=getattr(e, "id", None),
                link=e.link,
                title=getattr(e, "title", None),
                summary=getattr(e, "summary", None),
                published_at=pub,
            )
        )
    return ParsedFeed(title=getattr(fp.feed, "title", None), items=items)
