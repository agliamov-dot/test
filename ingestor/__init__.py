import argparse
import feeds


def _poll(_args: argparse.Namespace) -> None:
    """Invoke feeds.main with verbose flag."""
    feeds.main(["--verbose"])


def main() -> None:
    """Entry point for the ingestor CLI."""
    parser = argparse.ArgumentParser(prog="ingestor")
    subparsers = parser.add_subparsers(dest="command")

    poll_parser = subparsers.add_parser("poll", help="Poll feeds with verbose output")
    poll_parser.set_defaults(func=_poll)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
