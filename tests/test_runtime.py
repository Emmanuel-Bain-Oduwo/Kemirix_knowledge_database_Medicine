import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import runtime
from scripts.migration_gate import plan

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def release(tmp_path, monkeypatch):
    sha = "a" * 40
    root = tmp_path / "development"
    path = root / "releases" / sha
    path.mkdir(parents=True)
    (path / "source.py").write_text('print("fixture")\n')
    (root / "manifests").mkdir()
    manifest = root / "manifests" / f"{sha}.json"
    manifest.write_text(json.dumps(runtime.inventory(path)))
    monkeypatch.setattr(
        runtime, "archive_files", lambda repo, commit: {"source.py": (b'print("fixture")\n', 0o644)}
    )
    monkeypatch.setattr(runtime, "smoke", lambda release: None)
    runtime.activate(root, sha)
    return root, path, sha


def test_runtime_exact_sha(release):
    root, path, sha = release
    result = runtime.verify(Path("/unused"), root, sha)
    assert result["result"] == "PASS"
    assert result["current_symlink_target"] == f"releases/{sha}"


@pytest.mark.parametrize("drift", ["source", "extra", "sha", "symlink", "dependency"])
def test_runtime_drift(release, drift):
    root, path, sha = release
    if drift == "source":
        (path / "source.py").write_text("changed")
    elif drift == "extra":
        (path / "extra.py").write_text("unexpected")
    elif drift == "sha":
        (root / "DEPLOYED_SHA").write_text("b" * 40)
    elif drift == "symlink":
        (root / "current").unlink()
        (root / "current").symlink_to("releases/" + "b" * 40)
    else:
        (path / ".venv").mkdir()
        (path / ".venv/unexpected").write_text("modified environment")
    assert runtime.verify(Path("/unused"), root, sha)["result"] == "RUNTIME DRIFT DETECTED"


def test_migrations_executable_kmx_prefix():
    ready, pending = plan(ROOT)
    assert ready == ["migrations/001_kmx.sql"]
    assert pending == ["migrations/002_evidence.sql", "migrations/003_rules.sql"]


def test_migration_cannot_hide_ddl(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "migrations").mkdir()
    (tmp_path / "config/migration_suite.yaml").write_text(
        "migrations:\n  - path: migrations/001_test.sql\n    state: pending\n"
    )
    (tmp_path / "migrations/001_test.sql").write_text("CREATE TABLE unexpected (id int);")
    with pytest.raises(ValueError):
        plan(tmp_path)


def test_workflows_security_and_syntax():
    ci = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    cd = yaml.load((ROOT / ".github/workflows/deploy-dev.yml").read_text(), Loader=yaml.BaseLoader)
    assert ci["on"]["pull_request"]["branches"] == ["main"]
    assert ci["on"]["push"]["branches"] == ["main"]
    assert ci["jobs"]["foundation"]["runs-on"] == "ubuntu-latest"
    assert ci["jobs"]["foundation"]["services"]["postgres"]["image"] == "postgres:17"
    assert cd["on"]["workflow_run"]["branches"] == ["main"]
    assert "pull_request" not in cd["on"]
    gate = cd["jobs"]["deploy"]["if"]
    for required in [
        "conclusion == 'success'",
        "event == 'push'",
        "head_branch == 'main'",
        "head_repository.full_name == github.repository",
    ]:
        assert required in gate
    for workflow in [ci, cd]:
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                if "run" in step:
                    subprocess.run(["bash", "-n"], input=step["run"], text=True, check=True)
    text = (ROOT / ".github/workflows/deploy-dev.yml").read_text()
    assert "github.event.workflow_run.head_sha" in text
    assert "StrictHostKeyChecking=yes" in text
    assert "refs/remotes/origin/main" in text
    for forbidden in ["DATABASE_URL", "NEBIUS_API_KEY", "CLOUDFLARE_API_TOKEN", "/etc/kemirix"]:
        assert forbidden not in text


@pytest.mark.integration
def test_exact_git_archive_ignores_uncommitted_files(tmp_path):
    # Isolated synthetic Git object database. No commit or staging in the actual repository.
    repository = tmp_path / "fixture"
    subprocess.run(["git", "init", "-q", str(repository)], check=True)

    def git(*args, data=None):
        return (
            subprocess.check_output(["git", "-C", str(repository), *args], input=data)
            .decode()
            .strip()
        )

    blob = git("hash-object", "-w", "--stdin", data=b"exact committed bytes\n")
    tree = git("mktree", data=f"100644 blob {blob}\tfixture.txt\n".encode())
    commit = git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit-tree",
        tree,
        "-m",
        "synthetic fixture",
    )
    (repository / "fixture.txt").write_text("dirty working tree bytes")
    (repository / "untracked.txt").write_text("not part of release")
    files = runtime.archive_files(repository / ".git", commit)
    assert files["fixture.txt"][0] == b"exact committed bytes\n"
    assert "untracked.txt" not in files


def test_sql_comment_detection():
    from scripts.migration_gate import contains_sql

    assert not contains_sql("/* outer /* nested */ comment */ -- placeholder\r\n")
    assert contains_sql("-- comment\rCREATE TABLE example (id int);")
    with pytest.raises(ValueError):
        contains_sql("/* unterminated")


def test_runtime_bad_manifest_reports_drift(release):
    root, path, sha = release
    (root / "manifests" / f"{sha}.json").write_text("malformed")
    report = runtime.verify(Path("/unused"), root, sha)
    assert report["result"] == "RUNTIME DRIFT DETECTED"
    assert report["expected_sha"] == sha


@pytest.mark.integration
def test_worktree_creation_and_conflict_preservation(tmp_path):
    from agents.gitops import setup_worktree

    repo = tmp_path / "control"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    def git(*args, data=None):
        return subprocess.check_output(["git", "-C", str(repo), *args], input=data).decode().strip()

    tree = git("mktree", data=b"")
    sha = git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit-tree",
        tree,
        "-m",
        "isolated empty fixture",
    )
    git("update-ref", "refs/heads/main", sha)
    path = setup_worktree(repo, "codex", "TEST-001", sha, base=tmp_path / "worktrees")
    assert path.name == "codex"
    assert setup_worktree(repo, "codex", "TEST-001", sha, base=tmp_path / "worktrees") == path
    (path / "preserve.txt").write_text("uncommitted work")
    with pytest.raises(ValueError):
        setup_worktree(repo, "codex", "OTHER-001", sha, base=tmp_path / "worktrees")
    assert (path / "preserve.txt").read_text() == "uncommitted work"


@pytest.mark.integration
def test_release_switch_rollback_and_failure_recovery(tmp_path, monkeypatch):
    import sys

    repo = tmp_path / "git-fixture"
    subprocess.run(["git", "init", "-q", "--bare", str(repo)], check=True)

    def git(*args, data=None):
        return (
            subprocess.check_output(["git", f"--git-dir={repo}", *args], input=data)
            .decode()
            .strip()
        )

    commits = []
    for number in range(3):
        files = {
            "fixture.txt": f"revision {number}",
            "scripts/validate_config.py": 'print("offline fixture smoke")',
            "scripts/migration_gate.py": 'print("pending synthetic migration gate")',
            "config/migration_suite.yaml": "state: pending\n",
        }
        for name, content in files.items():
            blob = git("hash-object", "-w", "--stdin", data=content.encode())
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{name}")
        tree = git("write-tree")
        parent = ["-p", commits[-1]] if commits else []
        commits.append(
            git(
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit-tree",
                tree,
                *parent,
                "-m",
                "synthetic release",
            )
        )
    git("update-ref", "refs/remotes/origin/main", commits[-1])
    actual_git, actual_command = runtime.git, runtime.command

    def no_network_git(repo, *args):
        return b"" if args[0] == "fetch" else actual_git(repo, *args)

    def fake_dependency_sync(args, **kwargs):
        if args[:2] == ["uv", "sync"]:
            bin_path = kwargs["cwd"] / ".venv/bin"
            bin_path.mkdir(parents=True)
            (bin_path / "python").symlink_to(Path(sys.executable).resolve())
            return b""
        return actual_command(args, **kwargs)

    monkeypatch.setattr(runtime, "git", no_network_git)
    monkeypatch.setattr(runtime, "command", fake_dependency_sync)
    root = tmp_path / "runtime"
    try:
        for sha in commits:
            assert runtime.deploy(repo, root, sha)["result"] == "PASS"
        assert len(list((root / "releases").iterdir())) == 3
        with pytest.raises(RuntimeError):
            runtime.deploy(repo, root, commits[0])  # stale automatic deploy rejected
        assert runtime.deploy(repo, root, commits[0], rollback=True)["result"] == "PASS"
        actual_verify = runtime.verify

        def failing_post_switch(repo, root, sha, health=True):
            if sha == commits[1]:
                return {"result": "HEALTH_CHECK_FAILED"}
            return actual_verify(repo, root, sha, health)

        monkeypatch.setattr(runtime, "verify", failing_post_switch)
        with pytest.raises(RuntimeError):
            runtime.deploy(repo, root, commits[1])
        assert (root / "DEPLOYED_SHA").read_text().strip() == commits[0]
        assert (root / "current").readlink() == Path("releases") / commits[0]
    finally:
        # Fixture-only cleanup permissions; actual runtime is never touched.
        for path in root.rglob("*"):
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o755)
