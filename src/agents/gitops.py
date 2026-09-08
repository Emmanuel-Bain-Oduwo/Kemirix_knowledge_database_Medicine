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
    role, task_id = branch_parts(branch)  # Refuse main before any checks/mutation.
    if not message.strip():
        raise ValueError("meaningful checkpoint message required")
    control = control_root(root)
    with writer_lock(control):
        task = load_task(control, task_id)
        if role == task.active_writer and task.branch != branch:
            raise PermissionError("active writer branch mismatch")
        # Branch, active writer and allowed paths are validated above and below;
        # the checkpoint itself must also build on the recorded task base SHA.
        try:
            git(root, "merge-base", "--is-ancestor", task.base_sha, git(root, "rev-parse", "HEAD"))
        except RuntimeError:
            raise ValueError("checkpoint must descend from the recorded task base SHA") from None
        changed = changed_paths(root)
        intended = set(paths) if paths else changed
        if not intended:
            raise ValueError("no working-tree changes to submit")
        if intended != changed:
            raise ValueError(
                "path scope must cover all working-tree changes; unrelated changes must be isolated"
            )
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
        try:
            pull = existing_pr(root, branch)
        except RuntimeError:
            print("PR status unavailable")
        else:
            print(json.dumps({"pr": pull}) if pull else "no open PR for branch")
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


def approved_main(root, sha):
    import re

    if not re.fullmatch("[0-9a-f]{40}", sha):
        raise ValueError("approved main SHA required")
    git(root, "fetch", "origin", "main")
    if git(root, "rev-parse", "FETCH_HEAD") != sha:
        raise ValueError("approved SHA is not latest fetched main; obtain renewed approval")
    return sha


def existing_pr(root, branch):
    if not shutil.which("gh"):
        return None
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
            "number,isDraft,baseRefName",
            "--base",
            "main",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("PR lookup failed; details withheld")
    pulls = json.loads(result.stdout)
    return pulls[0] if pulls else None


def enable_auto_merge(root, pull):
    # GitHub auto-merge respects branch protection and required checks; never bypasses CI.
    if pull["isDraft"]:
        result = subprocess.run(
            ["gh", "pr", "ready", str(pull["number"])], cwd=root, capture_output=True, text=True
        )
        if result.returncode:
            raise RuntimeError("marking PR ready failed; details withheld")
    result = subprocess.run(
        ["gh", "pr", "merge", str(pull["number"]), "--auto", "--squash"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(
            "auto-merge enablement failed; verify the one-time repository configuration"
        )
    print("Auto-merge (squash) enabled; GitHub merges once required checks pass.")


def open_pr(root, title, body_file, auto_merge=False):
    branch = git(root, "branch", "--show-current")
    branch_parts(branch)  # Task branches only; main refused.
    ensure_no_secrets(title)
    ensure_no_secrets(Path(body_file).read_text())
    if not shutil.which("gh"):
        raise RuntimeError("gh unavailable; PR status not checked")
    pull = existing_pr(root, branch)
    if pull:
        print(json.dumps({"branch": branch, "reused_pr": pull, "base": "main"}))
    else:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--draft",
                "--base",
                "main",
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
        pull = existing_pr(root, branch)
        print(json.dumps({"branch": branch, "created_pr": pull, "base": "main"}))
    if auto_merge:
        if not pull:
            raise RuntimeError("cannot enable auto-merge without an open PR")
        enable_auto_merge(root, pull)
    return pull["number"] if pull else None
