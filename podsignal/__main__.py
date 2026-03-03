# podsignal/__main__.py
"""CLI entry point for `python -m podsignal`."""

import argparse
import sys

from podsignal.utils import setup_logging


def main():
    parser = argparse.ArgumentParser(
        prog="podsignal",
        description="PodSignal - Podcast guest intelligence for B2B lead generation",
    )

    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--podcasts", "-p",
        default="podcasts.yaml",
        help="path to podcasts.yaml (default: podcasts.yaml)",
    )
    parser.add_argument(
        "--days-back", "-d",
        type=int,
        default=None,
        help="override days_back from config",
    )
    parser.add_argument(
        "--min-score", "-s",
        type=int,
        default=None,
        help="override min_score from config",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["csv", "json"],
        default=None,
        help="override output format (csv or json)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="enable debug logging",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="disable deduplication (dedup is ON by default)",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    from podsignal.main import run

    try:
        run(
            config_path=args.config,
            podcasts_path=args.podcasts,
            days_back_override=args.days_back,
            min_score_override=args.min_score,
            format_override=args.format,
            no_dedup=args.no_dedup,
        )
    except KeyboardInterrupt:
        print("\nInterrupted. Exiting gracefully.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
