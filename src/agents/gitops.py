"""Explicit checkpoint submission and worktrees. Importing never mutates Git."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .memory import atomic_text, now, writer_lock
from .models import branch_parts
from .security import ensure_no_secrets, safe_repo_path
from .tasks import load_task, save_task


def git(root, *args):
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False, timeout=300
    )
    if result.returncode:
        raise RuntimeError("Git operation failed; details withheld to protect credentials")
    return result.stdout.decode().strip()


def control_root(root):
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    return common.parent


def changed_paths(root):
    files = set()
    for args in [
        ("diff", "--name-only", "--no-renames", "-z"),
        ("diff", "--cached", "--name-only", "--no-renames", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ]:
        files.update(p for p in git(root, *args).split("\0") if p)
    return files


def scan_paths(root, paths):
    for relative in paths:
        path = safe_repo_path(root, relative)
        if (path.name.startswith(".env") and path.name != ".env.example") or path.name in [
            "agents.env",
            "app.env",
            ".pgpass",
        ]:
            raise ValueError("secret file cannot be submitted")
        if path.is_file():
            if path.stat().st_size > 2_000_000:
                raise ValueError("large files require separate review")
            try:
                ensure_no_secrets(path.read_text())
            except UnicodeError:
                raise ValueError("binary checkpoint files require separate review") from None


def fingerprint(root, paths):
    return {
        p: hashlib.sha256(safe_repo_path(root, p).read_bytes()).hexdigest()
        if safe_repo_path(root, p).is_file()
        else None
        for p in sorted(paths)
    }


def safe_checks(root, profiles=("foundation",)):
    commands = [
        ["uv", "sync", "--frozen", "--python", "3.12"],
        ["uv", "run", "--frozen", "python", "scripts/validate_config.py"],
        ["uv", "run", "--frozen", "ruff", "check", "."],
        ["uv", "run", "--frozen", "ruff", "format", "--check", "."],
        ["uv", "run", "--frozen", "pytest", "-q", "-m", "not integration and not contract"],
        ["git", "diff", "--check"],
        ["git", "diff", "--cached", "--check"],
    ]
    for profile in profiles:
        if profile not in ["foundation", "integration", "contract"]:
            raise ValueError("unknown required test profile")
        if profile != "foundation":
            commands.append(["uv", "run", "--frozen", "pytest", "-q", "-m", profile])
    for command in commands:
        result = subprocess.run(command, cwd=root, capture_output=True, check=False, timeout=300)
        if result.returncode:
            raise RuntimeError("safe checks failed; review locally without logging secrets")


def submit(root, message, paths=()):
    ensure_no_secrets(message)
    branch = git(root, "branch", "--show-current")
    role, task_id = branch_parts(branch)  # Refuse main/develop before any checks/mutation.
    if not message.strip():
        raise ValueError("meaningful checkpoint message required")
    control = control_root(root)
    with writer_lock(control):
        task = load_task(control, task_id)
        if role == task.active_writer and task.branch != branch:
            raise PermissionError("active writer branch mismatch")
        intended = set(paths) or set(
            filter(
                None, git(root, "diff", "--cached", "--name-only", "--no-renames", "-z").split("\0")
            )
        )
        if not intended or changed_paths(root) != intended:
            raise ValueError(
                "stage intended changes or pass --path; unrelated changes must be isolated"
            )
        if not paths and set(filter(None, git(root, "diff", "--name-only", "-z").split("\0"))):
            raise ValueError("partially staged files refused; use explicit full-file --path scope")
        for path in intended:
            task.authorize(role, path)
        scan_paths(root, intended)
        before = fingerprint(root, intended)
        base_head = git(root, "rev-parse", "HEAD")
        safe_checks(root, task.required_tests)
        if (
            fingerprint(root, intended) != before
            or changed_paths(root) != intended
            or git(root, "rev-parse", "HEAD") != base_head
        ):
            raise RuntimeError("files changed during checks; checkpoint refused")
        git(root, "add", "--", *sorted(intended))
        if (
            set(
                filter(
                    None,
                    git(root, "diff", "--cached", "--name-only", "--no-renames", "-z").split("\0"),
                )
            )
            != intended
        ):
            raise RuntimeError("index changed; checkpoint refused")
        git(root, "commit", "-m", message)
        sha = git(root, "rev-parse", "HEAD")
        if role == task.active_writer:
            task.commit_sha = sha
        task.updated_at = now()
        task.events.append(
            {
                "operation": "checkpoint",
                "role": role,
                "commit_sha": sha,
                "timestamp": now().isoformat(),
            }
        )
        save_task(control, task)
        # Mirror only the role-owned committed report into shared canonical context.
        for relative in intended:
            if relative.startswith(f"ops/reports/{task_id}/"):
                content = git(root, "show", f"{sha}:{relative}")
                atomic_text(safe_repo_path(control, relative), content + "\n")
        # Explicit branch refspec. A failed push preserves the local checkpoint.
        print(json.dumps({"branch": branch, "commit_sha": sha, "push": "starting"}))
        git(root, "push", "--set-upstream", "origin", f"HEAD:refs/heads/{branch}")
        print(json.dumps({"branch": branch, "commit_sha": sha, "push": "PASS"}))
        if shutil.which("gh"):
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--head",
                    branch,
                    "--state",
                    "open",
                    "--json",
                    "number,isDraft,state",
                ],
                cwd=root,
                capture_output=True,
                text=True,
            )
            print(result.stdout.strip() if result.returncode == 0 else "PR status unavailable")
        else:
            print("gh unavailable; PR status not checked")
        return sha


def setup_worktree(root, role, task_id, sha, base=Path("/srv/kemirix/worktrees")):
    branch = f"agent/{role}/{task_id}"
    branch_parts(branch)
    if git(root, "rev-parse", f"{sha}^{{commit}}") != sha:
        raise ValueError("full checkpoint SHA required")
    path = Path(base).resolve() / role
    if path.is_relative_to(Path("/srv/kemirix/runtime")):
        raise ValueError("runtime is not a worktree")
    if path.is_symlink():
        raise ValueError("worktree path cannot be a symlink")
    if path.exists():
        if control_root(path) != control_root(root):
            raise ValueError("existing worktree belongs to another control repository")
        if (
            git(path, "branch", "--show-current") != branch
            or git(path, "rev-parse", "HEAD") != sha
            or git(path, "status", "--porcelain")
        ):
            raise ValueError("existing worktree conflicts; preserve and hand off explicitly")
        return path
    existing = git(root, "for-each-ref", "--format=%(refname)", f"refs/heads/{branch}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if existing:
        if git(root, "rev-parse", branch) != sha:
            raise ValueError("existing branch has a different checkpoint")
        git(root, "worktree", "add", str(path), branch)
    else:
        git(root, "worktree", "add", "-b", branch, str(path), sha)
    return path


def approved_develop(root, sha):
    import re

    if not re.fullmatch("[0-9a-f]{40}", sha):
        raise ValueError("approved develop SHA required")
    git(root, "fetch", "origin", "develop")
    if git(root, "rev-parse", "FETCH_HEAD") != sha:
        raise ValueError("approved SHA is not latest fetched develop; obtain renewed approval")
    return sha


def open_pr(root, title, body_file):
    branch = git(root, "branch", "--show-current")
    branch_parts(branch)
    ensure_no_secrets(title)
    ensure_no_secrets(Path(body_file).read_text())
    result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--draft",
            "--base",
            "develop",
            "--head",
            branch,
            "--title",
            title,
            "--body-file",
            str(body_file),
        ],
        cwd=root,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("draft PR creation failed; details withheld")
    print("Draft PR created; no merge or deployment requested.")
