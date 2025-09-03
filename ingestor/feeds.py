import logging
from typing import List, Dict

import feedparser

logger = logging.getLogger(__name__)


def insert_items(items: List[Dict[str, str]]) -> None:
    """Insert a list of feed items into storage.

    This is a placeholder function. In a real application this would likely
    insert the provided items into a database or other data store.
    """
    # TODO: implement actual storage logic
    pass


def ingest_feed(url: str) -> None:
    """Fetch an RSS/Atom feed and store its items.

    Parameters
    ----------
    url: str
        The URL of the feed to fetch.
    """
    try:
        feed = feedparser.parse(url)
    except Exception as exc:
        logger.error("Network error when fetching %s: %s", url, exc)
        return

    status = getattr(feed, "status", None)
    if status != 200:
        logger.error("Unsuccessful request for %s: status %s", url, status)
        return

    if getattr(feed, "bozo", False):
        logger.error("Failed to parse feed %s: %s", url, feed.bozo_exception)
        return

    items: List[Dict[str, str]] = []
    for entry in getattr(feed, "entries", []):
        items.append(
            {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
            }
        )

    if items:
        insert_items(items)
