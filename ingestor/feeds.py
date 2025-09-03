import argparse
import logging

logger = logging.getLogger(__name__)


def insert_items(items):
    """Insert items into storage."""
    success = 0
    for item in items:
        try:
            logger.debug("Inserting %r", item)
            # TODO: replace with actual insertion logic
            success += 1
        except Exception:
            logger.exception("Failed to insert %r", item)
    logger.info("Successfully inserted %d/%d items", success, len(items))


def main():
    parser = argparse.ArgumentParser(description="Ingest feed items")
    parser.add_argument(
        "--verbose", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    items = []  # TODO: fetch items from feed
    logger.info("Retrieved %d items from feed", len(items))
    insert_items(items)


if __name__ == "__main__":
    main()
