"""CLI entry points for explicit, meaningful Git checkpoints."""

import argparse
from pathlib import Path

from .gitops import open_pr, submit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    send = sub.add_parser("submit")
    send.add_argument("message")
    send.add_argument("--path", action="append", default=[])
    pr = sub.add_parser("open-pr")
    pr.add_argument("--title", required=True)
    pr.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "submit":
            submit(Path.cwd(), args.message, args.path)
        else:
            open_pr(Path.cwd(), args.title, args.body_file)
    except Exception:
        parser.exit(
            1, "Checkpoint/PR operation refused or failed; preserve work and inspect locally.\n"
        )


if __name__ == "__main__":
    main()
