"""CLI entry points for explicit, meaningful Git checkpoints."""

import argparse
from pathlib import Path

from pydantic import ValidationError

from .gitops import open_pr, submit
from .security import redact

MAX_DIAGNOSTIC = 500


def describe(exc):
    """Sanitized one-line exception class and message, never input values.

    Pydantic validation errors are reduced to their location/message lines so
    contract payloads are never echoed; all text passes the secret redactor and
    is length-capped. Headers, tokens and environment values stay private.
    """
    if isinstance(exc, ValidationError):
        parts = []
        for error in exc.errors():
            location = ".".join(str(item) for item in error.get("loc", ()))
            message = str(error.get("msg", ""))
            parts.append(f"{location}: {message}" if location else message)
        text = "; ".join(dict.fromkeys(part for part in parts if part))
    else:
        text = str(exc)
    text = redact(" ".join(text.split()))
    if len(text) > MAX_DIAGNOSTIC:
        text = text[: MAX_DIAGNOSTIC - 3] + "..."
    return f"{type(exc).__name__}: {text or 'no details'}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    send = sub.add_parser("submit")
    send.add_argument("message")
    send.add_argument("--path", action="append", default=[])
    pr = sub.add_parser("open-pr")
    pr.add_argument("--title", required=True)
    pr.add_argument("--body-file", type=Path, required=True)
    pr.add_argument("--auto-merge", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "submit":
            submit(Path.cwd(), args.message, args.path)
        else:
            open_pr(Path.cwd(), args.title, args.body_file, auto_merge=args.auto_merge)
    except Exception as exc:
        parser.exit(
            1,
            f"Checkpoint/PR operation refused or failed ({describe(exc)}); "
            "preserve work and inspect locally.\n",
        )


if __name__ == "__main__":
    main()
