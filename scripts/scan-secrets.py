"""Scan tracked/intended files for common secret patterns without printing matches."""

import subprocess
from pathlib import Path

from agents.gitops import scan_paths


def main():
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], text=True
    ).split("\0")
    try:
        scan_paths(Path.cwd(), set(filter(None, paths)))
    except Exception:
        print("Secret/file safety scan FAILED; matching content withheld.")
        return 1
    print("Common-pattern secret/file safety scan PASS (not a guarantee of absence).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
