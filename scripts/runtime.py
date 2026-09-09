"""Exact-Git development releases. Standard library only; never loads application secrets."""

import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

DEFAULT_ROOT = Path("/srv/kemirix/runtime/development")
DEFAULT_REPO = Path("/srv/kemirix/deploy/repository.git")
DEV_DB_ENV_FILE = Path("/srv/kemirix/secrets/dev-postgres.env")


def command(args, **kwargs):
    kwargs.setdefault("timeout", 120)
    result = subprocess.run(args, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError("command failed; details suppressed")
    return result.stdout


def git(repo, *args):
    return command(["git", f"--git-dir={repo}", *args])


def valid_sha(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("full lowercase Git SHA required")
    return sha


def archive_files(repo, sha):
    valid_sha(sha)
    if git(repo, "rev-parse", f"{sha}^{{commit}}").decode().strip() != sha:
        raise ValueError("commit mismatch")
    files = {}
    # Archive input is the exact Git object, never the checkout.
    with tarfile.open(fileobj=io.BytesIO(git(repo, "archive", "--format=tar", sha))) as archive:
        for member in archive:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("unsafe archive path")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("release Git tree must contain regular files only")
            files[member.name] = (archive.extractfile(member).read(), member.mode)
    return files


def inventory(release):
    result = {}
    for path in sorted(release.rglob("*")):
        relative = path.relative_to(release).as_posix()
        if path.is_symlink():
            result[relative] = {"link": os.readlink(path)}
        elif path.is_file():
            result[relative] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "executable": bool(path.stat().st_mode & 0o111),
            }
    return result


def atomic(path, text):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".deploy.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def integrity(repo, release, sha, manifest):
    expected = archive_files(repo, sha)
    for name, (content, mode) in expected.items():
        path = release / name
        if any(parent.is_symlink() for parent in path.parents if parent != release.parent):
            return False
        if (
            path.is_symlink()
            or not path.is_file()
            or path.read_bytes() != content
            or bool(path.stat().st_mode & 0o111) != bool(mode & 0o111)
        ):
            return False
    # Dependency bytes and unexpected extra files are checked against deployment-time inventory.
    if not manifest.is_file() or inventory(release) != json.loads(manifest.read_text()):
        return False
    return True


def smoke(release):
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    command(
        [str(release / ".venv/bin/python"), "scripts/validate_config.py"],
        cwd=release,
        env=env,
        timeout=60,
    )


def dev_database_env(path=None):
    """Operator-provisioned development database credentials, or None when absent.

    Only a regular, non-symlink 0600 file owned by the deploying user holding a
    postgres:// or postgresql:// DATABASE_URL is accepted. The URL is parsed
    in-process into PG* variables; the password never reaches a command line,
    log or error.
    """
    if path is None:
        path = DEV_DB_ENV_FILE
    try:
        info = path.stat()
    except OSError:
        return None
    if path.is_symlink() or not path.is_file():
        return None
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError("unsafe development credential file permissions")
    if info.st_uid != os.getuid():
        raise RuntimeError("development credential file ownership mismatch")
    url = None
    for line in path.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip("'\"").strip()
    if not url:
        return None
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("postgres", "postgresql")
        or not parsed.hostname
        or not parsed.username
        or parsed.password is None
        or not parsed.path.lstrip("/")
    ):
        raise RuntimeError("invalid development database credential format")
    env = {
        "PGHOST": parsed.hostname,
        "PGUSER": parsed.username,
        "PGPASSWORD": parsed.password,
        "PGDATABASE": parsed.path.lstrip("/"),
    }
    if parsed.port:
        env["PGPORT"] = str(parsed.port)
    query = parse_qs(parsed.query)
    env["PGSSLMODE"] = query["sslmode"][0] if "sslmode" in query else "require"
    return env


def execute_development_migrations(release):
    """Apply or verify the executable migration prefix on the development database.

    The reviewed runner (src/database/migrations.py, packaged inside the
    release) owns every SQL decision: PostgreSQL 17 check, clean-database
    from-zero apply in one transaction, idempotent prefix verification,
    prefix-based multi-migration upgrades and fail-closed state validation.
    Credentials come only from the operator-provisioned env file and reach
    the runner only through the PG* environment; the password never appears
    on a command line, in a log or in an error.
    """
    pg_env = dev_database_env()
    if pg_env is None:
        raise RuntimeError(
            "development migration hook requires operator-provisioned credentials "
            f"at {DEV_DB_ENV_FILE} (0600, owner-only)"
        )
    runner = release / ".venv/bin/python"
    if not runner.is_file():
        raise RuntimeError("release virtual environment missing; deploy incomplete")
    result = subprocess.run(
        [str(runner), "-m", "database.migrations", str(release)],
        capture_output=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C", **pg_env},
        timeout=300,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("development migration runner failed; details suppressed")
    status = result.stdout.decode().strip()
    if status:
        print(status)


def verify(repo, root, sha, health=True):
    valid_sha(sha)
    current = root / "current"
    deployed = (
        (root / "DEPLOYED_SHA").read_text().strip() if (root / "DEPLOYED_SHA").is_file() else None
    )
    target = os.readlink(current) if current.is_symlink() else None
    release = root / "releases" / sha
    report = {
        "expected_sha": sha,
        "DEPLOYED_SHA": deployed,
        "current_symlink_target": target,
        "release_exists": release.is_dir(),
        "integrity": "FAIL",
        "smoke": "NOT_RUN",
    }
    valid = (
        deployed == sha
        and target == f"releases/{sha}"
        and release.is_dir()
        and not release.is_symlink()
        and current.resolve() == release.resolve()
    )
    if valid:
        try:
            valid = integrity(repo, release, sha, root / "manifests" / f"{sha}.json")
        except Exception:
            valid = False
    if not valid:
        report["result"] = "RUNTIME DRIFT DETECTED"
        return report
    report["integrity"] = "PASS"
    if health:
        try:
            smoke(release)
            report["smoke"] = "PASS"
        except Exception:
            report["smoke"] = "FAIL"
    report["result"] = "PASS" if report["smoke"] == "PASS" or not health else "HEALTH_CHECK_FAILED"
    return report


def activate(root, sha):
    # Two atomic replacements cannot form one filesystem transaction. Verifier detects mismatch;
    # Restore previous pointers on failure; crashes fail closed on the next verification.
    temporary = root / ".current-next"
    if temporary.is_symlink():
        temporary.unlink()
    if temporary.exists():
        raise ValueError("unexpected activation temporary path")
    temporary.symlink_to(f"releases/{sha}")
    os.replace(temporary, root / "current")
    atomic(root / "DEPLOYED_SHA", sha + "\n")


def deploy(repo, root, sha, rollback=False):
    valid_sha(sha)
    with lock(root):
        for managed in [root / "releases", root / "manifests", root / "DEPLOYED_SHA"]:
            if managed.is_symlink():
                raise ValueError("unsafe runtime layout")
        if (root / "current").exists() and not (root / "DEPLOYED_SHA").is_file():
            raise RuntimeError("RUNTIME DRIFT DETECTED")
        git(repo, "fetch", "origin", sha)
        git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
        git(repo, "merge-base", "--is-ancestor", sha, "refs/remotes/origin/main")
        previous = (
            (root / "DEPLOYED_SHA").read_text().strip()
            if (root / "DEPLOYED_SHA").exists()
            else None
        )
        if previous:
            if verify(repo, root, previous)["result"] != "PASS":
                raise RuntimeError("RUNTIME DRIFT DETECTED; repair pointers or investigate first")
            if not rollback:
                git(repo, "merge-base", "--is-ancestor", previous, sha)  # Reject stale deployments.
        releases, manifests = root / "releases", root / "manifests"
        releases.mkdir(exist_ok=True)
        manifests.mkdir(exist_ok=True)
        release, manifest = releases / sha, manifests / f"{sha}.json"
        if release.exists():
            if release.is_symlink() or not integrity(repo, release, sha, manifest):
                raise RuntimeError("RUNTIME DRIFT DETECTED")
        else:
            if rollback:
                raise ValueError("rollback requires an existing known-good release")
            files = archive_files(repo, sha)
            release.mkdir()
            for name, (content, mode) in files.items():
                target = release / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                target.chmod(mode & 0o777)
            # Fixed final path: virtualenv entry points must not embed a temporary directory.
            env = {
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "HOME": str(root),
                "UV_CACHE_DIR": str(root / "uv-cache"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            }
            command(
                ["uv", "sync", "--frozen", "--no-dev", "--python", "3.12", "--no-editable"],
                cwd=release,
                env=env,
                timeout=300,
            )
            smoke(release)
            # Future migration hook: no automatic DDL until separately reviewed.
            command(
                [str(release / ".venv/bin/python"), "scripts/migration_gate.py"],
                cwd=release,
                env=env,
                timeout=30,
            )
            if "state: executable" in (release / "config/migration_suite.yaml").read_text():
                # Separately approved development migration execution: apply or
                # verify the executable prefix against the development database
                # using only operator-provisioned credentials; fails closed.
                execute_development_migrations(release)
            atomic(manifest, json.dumps(inventory(release), sort_keys=True) + "\n")
            for path in release.rglob("*"):
                if not path.is_symlink():
                    path.chmod(stat.S_IMODE(path.stat().st_mode) & ~0o222)
            release.chmod(0o555)
        smoke(release)
        try:
            activate(root, sha)
            result = verify(repo, root, sha)
            if result["result"] != "PASS":
                raise RuntimeError("post-switch verification failed")
        except Exception:
            if previous:
                activate(root, previous)
            else:
                if (root / "current").is_symlink():
                    (root / "current").unlink()
                (root / "DEPLOYED_SHA").unlink(missing_ok=True)
            raise
        # Retain all releases initially, including at least the last three.
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["deploy", "verify", "rollback"])
    parser.add_argument("sha")
    args = parser.parse_args()
    try:
        if args.operation == "verify":
            with lock(DEFAULT_ROOT):
                result = verify(DEFAULT_REPO, DEFAULT_ROOT, args.sha)
        else:
            result = deploy(DEFAULT_REPO, DEFAULT_ROOT, args.sha, args.operation == "rollback")
        print(json.dumps(result, indent=2))
        return 0 if result["result"] == "PASS" else 1
    except Exception:
        print("Runtime operation failed; possible RUNTIME DRIFT DETECTED. Details withheld.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
