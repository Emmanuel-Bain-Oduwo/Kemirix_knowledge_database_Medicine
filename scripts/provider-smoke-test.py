"""Operator-invoked smoke checks; never loads /etc files or prints provider responses."""

import argparse
import json
from dataclasses import asdict

from agents.providers import ProviderError, SmokeResult, provider_for


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--provider", choices=["codex", "kimi", "nemotron", "glm", "minimax"])
    group.add_argument("--all", action="store_true")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if not 0 < args.timeout <= 120:
        parser.error("timeout must be between 0 and 120 seconds")
    failed = False
    for role in ["codex", "kimi", "nemotron", "glm", "minimax"] if args.all else [args.provider]:
        try:
            provider = provider_for(role, timeout=args.timeout)
            result = (
                provider.smoke(timeout=args.timeout) if role == "codex" else provider.smoke(role)
            )
        except ProviderError as error:
            result = SmokeResult(role, "FAIL", str(error))
            failed = True
        except Exception:
            result = SmokeResult(role, "FAIL", "unexpected_error_details_suppressed")
            failed = True
        print(json.dumps(asdict(result)))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
