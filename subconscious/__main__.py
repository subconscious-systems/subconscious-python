"""``python -m subconscious densify <run_id>`` — write a dense JSONL trace to stdout."""

from __future__ import annotations

import argparse
import sys

from .client import Subconscious
from .traces import densify_trace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m subconscious')
    sub = parser.add_subparsers(dest='command', required=True)

    densify = sub.add_parser('densify', help='Densify a trace to JSONL on stdout')
    densify.add_argument('run_id')
    densify.add_argument('--api-key', default=None, help='Override SUBCONSCIOUS_API_KEY')
    densify.add_argument('--concurrency', type=int, default=8)

    args = parser.parse_args(argv)

    if args.command == 'densify':
        client = Subconscious(api_key=args.api_key)
        densify_trace(
            client,
            args.run_id,
            output=sys.stdout,
            concurrency=args.concurrency,
        )
        return 0

    parser.print_help()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
