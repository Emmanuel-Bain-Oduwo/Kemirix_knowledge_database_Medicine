"""Report pending migrations honestly; execute only an explicitly declared ready prefix in CI."""

import argparse
import os
import subprocess
from pathlib import Path

import yaml


def contains_sql(text):
    """Recognize whitespace/comments only, including nested comments and CR line endings."""
    i, depth = 0, 0
    while i < len(text):
        if depth:
            if text.startswith("/*", i):
                depth += 1
                i += 2
            elif text.startswith("*/", i):
                depth -= 1
                i += 2
            else:
                i += 1
        elif text[i].isspace():
            i += 1
        elif text.startswith("--", i):
            while i < len(text) and text[i] not in "\r\n":
                i += 1
        elif text.startswith("/*", i):
            depth = 1
            i += 2
        else:
            return True
    if depth:
        raise ValueError("unterminated SQL comment")
    return False


def plan(root):
    config = yaml.safe_load((root / "config/migration_suite.yaml").read_text())["migrations"]
    listed = [item["path"] for item in config]
    actual = [p.relative_to(root).as_posix() for p in sorted((root / "migrations").glob("*.sql"))]
    if listed != actual or not listed or len(set(listed)) != len(listed):
        raise ValueError("migration inventory/order mismatch")
    ready, pending = [], []
    for item in config:
        path = root / item["path"]
        sql = contains_sql(path.read_text())
        if item["state"] == "pending" and not sql:
            pending.append(item["path"])
        elif item["state"] == "executable" and sql and not pending:
            ready.append(item["path"])
        else:
            raise ValueError("migration declaration/content mismatch or non-prefix execution")
    return ready, pending


def execute(root, ready):
    expected = {
        "KEMIRIX_CI_POSTGRES": "1",
        "GITHUB_ACTIONS": "true",
        "PGHOST": "127.0.0.1",
        "PGDATABASE": "kemirix_knowledge",
        "PGUSER": "kemirix_ci",
        "PGPORT": "5432",
    }
    if any(os.environ.get(k) != v for k, v in expected.items()):
        raise ValueError("only isolated hosted CI PostgreSQL is permitted")

    def query(sql):
        return subprocess.check_output(
            ["psql", "-XAt", "--set=ON_ERROR_STOP=1", "-c", sql], text=True
        ).strip()

    version = int(query("SHOW server_version_num"))
    if not 170000 <= version < 180000:
        raise ValueError("PostgreSQL 17 required")
    if (
        query(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog','information_schema')"
        )
        != "0"
    ):
        raise ValueError("migration-from-zero requires empty database")
    if (
        query(
            "SELECT count(*) FROM information_schema.schemata "
            "WHERE schema_name IN ('kmx','evidence','rules')"
        )
        != "0"
    ):
        raise ValueError("domain schemas must not exist before migration-from-zero")
    if ready:
        subprocess.run(
            [
                "psql",
                "-X",
                "--set=ON_ERROR_STOP=1",
                "--single-transaction",
                *[f"--file={root / p}" for p in ready],
            ],
            check=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-ci", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        ready, pending = plan(root)
        if args.execute_ci:
            execute(root, ready)
        state = "pending" if pending else "executable"
        print(f"Migration suite: {state}; executable files={len(ready)}, pending={len(pending)}")
        if pending:
            print(
                "PLACEHOLDER MIGRATIONS ARE NOT EXECUTABLE. "
                "Domain schema/contract validation pending."
            )
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as out:
                out.write(f"state={state}\nexecutable_count={len(ready)}\n")
    except Exception:
        parser.exit(1, "Migration gate failed; verify declarations and isolated CI database.\n")


if __name__ == "__main__":
    main()
