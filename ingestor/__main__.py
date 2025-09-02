import argparse
import logging
from .config import load_config
from .feeds import add_feed, list_feeds, poll_once

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ingestor")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add-feed")
    p_add.add_argument("rss_url")
    p_add.add_argument("--interval", type=int, default=None)

    sub.add_parser("list-feeds")

    p_poll = sub.add_parser("poll")
    p_poll.add_argument("--feed-id", type=int, default=None)

    args = parser.parse_args()
    cfg = load_config()

    if args.command == "add-feed":
        feed_id = add_feed(cfg, args.rss_url, args.interval)
        print(feed_id)
    elif args.command == "list-feeds":
        for f in list_feeds(cfg):
            print(f"{f.id}\t{f.rss_url}")
    elif args.command == "poll":
        poll_once(cfg, feed_id=args.feed_id)


if __name__ == "__main__":
    main()
