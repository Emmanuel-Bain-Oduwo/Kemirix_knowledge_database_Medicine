import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from agents.context import build_context
from agents.gitops import submit
from agents.memory import CANONICAL, writer_lock
from agents.models import PRIORITY, Task, branch_parts
from agents.providers import CloudflareProvider, NebiusProvider, ProviderError
from agents.research import ResearchError, ResearchGateway
from agents.security import ensure_no_secrets, redact
from agents.tasks import handoff, load_task, save_task, transition, validate_report, write_owned

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


@pytest.fixture
def task():
    stamp = datetime.now(timezone.utc)
    return Task(
        task_id="TEST-001",
        phase="phase_0f",
        goal="Harmless engineering fixture",
        production_writer="codex",
        active_writer="codex",
        writer_priority=PRIORITY,
        allowed_paths=["tests/fixtures/engineering.txt"],
        forbidden_paths=["migrations", "src/kmx", "src/evidence", "src/rules"],
        base_sha=SHA,
        branch="agent/codex/TEST-001",
        acceptance_criteria=["fixture valid"],
        required_tests=["foundation"],
        status="implementation",
        created_at=stamp,
        updated_at=stamp,
        completed_at=None,
        commit_sha=SHA,
        deployed_sha=None,
    )


@pytest.fixture
def control(tmp_path, task):
    for name in CANONICAL + ["ops/agents/CODEX.md", "ops/agents/KIMI.md"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    save_task(tmp_path, task)
    return tmp_path


@pytest.mark.parametrize(
    "mutation",
    [
        {"goal": ""},
        {"base_sha": "main"},
        {"allowed_paths": []},
        {"active_writer": "glm"},
        {"writer_priority": ["glm", "codex"]},
        {"branch": "develop"},
        {"status": "approved"},
        {"allowed_paths": ["../runtime"]},
        {"allowed_paths": ["src/kmx"]},
        {"allowed_paths": ["SKILL.md"]},
        {"unknown": "extra"},
        {"completed_at": "2026-09-07"},
    ],
)
def test_invalid_tasks_fail_closed(task, mutation):
    with pytest.raises(ValidationError):
        Task.model_validate({**task.model_dump(), **mutation})


def test_missing_task_field(task):
    data = task.model_dump()
    del data["required_tests"]
    with pytest.raises(ValidationError):
        Task.model_validate(data)


def test_writer_and_reviewer_permissions(task):
    task.authorize("codex", "tests/fixtures/engineering.txt")
    for role, filename in [
        ("kimi", "kimi-analysis.md"),
        ("qwen", "qwen-crosscheck.md"),
        ("glm", "glm-review.md"),
        ("nemotron", "nemotron-qa.md"),
    ]:
        task.authorize(role, f"ops/reports/TEST-001/{filename}")
        with pytest.raises(PermissionError):
            task.authorize(role, "tests/fixtures/engineering.txt")
    with pytest.raises(PermissionError):
        task.authorize("codex", "ops/reports/TEST-001/glm-review.md")
    with pytest.raises(PermissionError):
        task.authorize("codex", "ops/memory/INVARIANTS.md")


def test_writer_lock(control):
    with writer_lock(control):
        with pytest.raises(RuntimeError, match="lock"):
            with writer_lock(control):
                pass


def test_context_order_and_metadata(control):
    context = build_context(control, "TEST-001", "kimi")
    assert [s["path"] for s in context["sections"][:5]] == CANONICAL
    assert context["sections"][5]["path"] == "ops/agents/KIMI.md"
    assert context["sections"][6]["path"] == "ops/tasks/TEST-001.yaml"
    assert context["metadata"]["WRITE_PERMISSION"] == "own_report_only"
    assert context["metadata"]["ACTIVE_WRITER"] == "codex"
    with pytest.raises(ValueError):
        build_context(control, "TEST-001", "kimi", max_bytes=5)


def test_context_invalid_contract(control):
    (control / "ops/tasks/TEST-001.yaml").write_text("task_id: TEST-001\n")
    with pytest.raises(ValidationError):
        build_context(control, "TEST-001", "codex")


def test_symlink_write_rejected(control):
    target = control / "tests/fixtures"
    target.mkdir(parents=True)
    (target / "engineering.txt").symlink_to(control / "SKILL.md")
    with pytest.raises(ValueError, match="symlink"):
        write_owned(control, control, "TEST-001", "codex", "tests/fixtures/engineering.txt", "oops")


def handoff_details():
    return dict(
        last_commit_sha=SHA,
        completed_work=["fixture"],
        remaining_work=["review"],
        tests_passed=["foundation"],
        tests_failed=[],
        known_issues=[],
        files_touched=["tests/fixtures/engineering.txt"],
        forbidden_changes=["migrations"],
        next_action="Review fixture",
    )


def test_human_handoff_and_old_writer_revoked(control):
    with pytest.raises(PermissionError):
        handoff(control, "TEST-001", "glm", handoff_details())
    result = handoff(control, "TEST-001", "glm", handoff_details(), human=True)
    assert result.branch == "agent/glm/TEST-001"
    assert result.base_sha == SHA
    assert load_task(control, "TEST-001").active_writer == "glm"
    with pytest.raises(PermissionError):
        result.authorize("codex", "tests/fixtures/engineering.txt")
    result.authorize("glm", "tests/fixtures/engineering.txt")
    assert (control / "ops/reports/TEST-001/handoff.md").exists()


def test_no_nemotron_failover(control):
    with pytest.raises(ValueError):
        handoff(control, "TEST-001", "nemotron", handoff_details(), human=True)
    assert load_task(control, "TEST-001").active_writer == "codex"


def test_handoff_wrong_checkpoint(control):
    with pytest.raises(ValueError):
        handoff(
            control, "TEST-001", "glm", {**handoff_details(), "last_commit_sha": "b" * 40}, True
        )


def test_review_blocks_and_fixes_repeat_review(control):
    transition(control, "TEST-001", "crosscheck", "implementation fixture ready")
    with pytest.raises(FileNotFoundError):
        transition(control, "TEST-001", "review", "missing review")
    report = control / "ops/reports/TEST-001/qwen-crosscheck.md"
    report.parent.mkdir(parents=True)
    report.write_text("REQUEST_CHANGES\nFindings: fix fixture.\nChecks: fixture mismatch.\n")
    with pytest.raises(ValueError):
        transition(control, "TEST-001", "review", "failed review")
    transition(control, "TEST-001", "fixes", "review requested changes")
    with pytest.raises(ValueError):
        transition(control, "TEST-001", "ci", "attempt to skip repeat review")


@pytest.mark.parametrize(
    "branch",
    [
        "main",
        "develop",
        "feature/test",
        "agent/codex/",
        "agent/unknown/T1",
        "agent/codex/T1/escape",
    ],
)
def test_branch_rejection(branch):
    with pytest.raises(ValueError):
        branch_parts(branch)


@pytest.mark.parametrize("branch", ["main", "develop"])
def test_submit_rejects_before_mutation(monkeypatch, tmp_path, branch):
    calls = []

    def fake_git(root, *args):
        calls.append(args)
        return branch

    monkeypatch.setattr("agents.gitops.git", fake_git)
    with pytest.raises(ValueError):
        submit(tmp_path, "TEST-001 checkpoint")
    assert calls == [("branch", "--show-current")]


def test_secret_redaction():
    token = "ghp_" + "x" * 32
    assert redact("token=" + token) == "token=[REDACTED]"
    with pytest.raises(ValueError):
        ensure_no_secrets(token)
    assert (
        redact("KEMIRIX_DEV_VM_SSH_KEY is a secret name")
        == "KEMIRIX_DEV_VM_SSH_KEY is a secret name"
    )


@pytest.mark.parametrize(
    "status,kind",
    [
        (401, "authentication_or_permission"),
        (429, "rate_limit_or_quota"),
        (404, "model_or_endpoint_unavailable"),
        (503, "provider_unavailable"),
    ],
)
def test_provider_error_does_not_leak(status, kind):
    secret = "synthetic-private-value"
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=secret))
    provider = NebiusProvider(env={"NEBIUS_API_KEY": secret}, transport=transport)
    with pytest.raises(ProviderError) as exc:
        provider.smoke("kimi")
    assert str(exc.value) == kind and secret not in str(exc.value)


def test_nebius_smoke_request():
    def respond(request):
        payload = json.loads(request.content)
        assert payload["model"] == "moonshotai/Kimi-K3"
        assert "connectivity" in payload["messages"][0]["content"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"connectivity":"ok"}'}}]}
        )

    result = NebiusProvider(
        env={"NEBIUS_API_KEY": "synthetic"}, transport=httpx.MockTransport(respond)
    ).smoke("kimi")
    assert result.status == "PASS"


def test_cloudflare_smoke():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"success": True, "result": {"response": '{"connectivity":"ok"}'}}
        )
    )
    result = CloudflareProvider(
        env={"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic"},
        transport=transport,
    ).smoke("glm")
    assert result.status == "PASS"


def test_missing_configuration():
    with pytest.raises(ProviderError, match="missing_configuration"):
        NebiusProvider(env={}).smoke("kimi")


def resolver(address):
    return lambda *args, **kwargs: [(2, 1, 6, "", (address, 443))]


def test_disabled_research(monkeypatch):
    monkeypatch.setenv("RESEARCH_SEARCH_PROVIDER", "disabled")
    with pytest.raises(ResearchError, match="disabled"):
        ResearchGateway().search("public engineering docs")


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_research_private_targets_blocked(address):
    with pytest.raises(ResearchError, match="rejected"):
        ResearchGateway(resolver=resolver(address)).fetch("https://public.example/docs")


def test_research_fetch_pins_ip_and_limits():
    def respond(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == "public.example"
        assert request.extensions["sni_hostname"] == "public.example"
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="docs")

    gateway = ResearchGateway(
        resolver=resolver("93.184.216.34"), transport=httpx.MockTransport(respond)
    )
    assert gateway.fetch("https://public.example/docs").trust.startswith("untrusted")
    gateway.max_bytes = 2
    with pytest.raises(ResearchError, match="size"):
        gateway.fetch("https://public.example/docs")


def test_redirect_to_private_rejected():
    def resolve(host, *args, **kwargs):
        return resolver("127.0.0.1" if host == "localhost" else "93.184.216.34")()

    gateway = ResearchGateway(
        resolver=resolve,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"location": "https://localhost/"})
        ),
    )
    with pytest.raises(ResearchError, match="rejected"):
        gateway.fetch("https://public.example/")


def test_review_output_contract():
    assert (
        validate_report("QA_PASS\nFindings: none.\nChecks: synthetic fixture.", "nemotron")
        == "QA_PASS"
    )
    with pytest.raises(ValueError):
        validate_report("Clinical Evidence approved", "glm")


def test_wrapper_shell_syntax():
    for script in (ROOT / "scripts").glob("*.sh"):
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_handoff_invalid_details_has_no_branch_side_effect(control):
    prepared = []
    with pytest.raises(ValidationError):
        handoff(
            control,
            "TEST-001",
            "glm",
            {"last_commit_sha": SHA},
            True,
            lambda task: prepared.append(task.branch),
        )
    assert prepared == []
    assert load_task(control, "TEST-001").active_writer == "codex"


def test_failover_cannot_self_review_but_human_can(control):
    task = handoff(control, "TEST-001", "glm", handoff_details(), True)
    task.status = "review"
    save_task(control, task)
    with pytest.raises(PermissionError):
        transition(control, "TEST-001", "qa", "writer cannot review itself")
    updated = transition(control, "TEST-001", "qa", "Independent human review reference", True)
    assert updated.status == "qa"
    assert updated.events[-1]["human_approved"] is True


def test_partial_staging_rejected(control, monkeypatch):
    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return "agent/codex/TEST-001"
        if args[0] == "diff":
            return "tests/fixtures/engineering.txt"
        raise AssertionError("mutation should never occur")

    monkeypatch.setattr("agents.gitops.git", fake_git)
    monkeypatch.setattr("agents.gitops.control_root", lambda root: control)
    monkeypatch.setattr(
        "agents.gitops.changed_paths", lambda root: {"tests/fixtures/engineering.txt"}
    )
    with pytest.raises(ValueError, match="partially staged"):
        submit(control, "TEST-001 intended staged change")


def test_context_uses_worktree_code(control, tmp_path):
    worktree = tmp_path / "worktree"
    path = worktree / "tests/fixtures/engineering.txt"
    path.parent.mkdir(parents=True)
    path.write_text("current writer checkpoint")
    context = build_context(
        control, "TEST-001", "codex", ["tests/fixtures/engineering.txt"], code_root=worktree
    )
    assert context["sections"][-1]["content"] == "current writer checkpoint"
    assert "SKILL.md" in context["metadata"]["FORBIDDEN_PATHS"]


def test_unquoted_environment_secret_rejected():
    with pytest.raises(ValueError):
        ensure_no_secrets("NEBIUS_API_KEY=" + "x" * 32)


def test_provider_timeout_classified():
    def respond(request):
        raise httpx.ReadTimeout("sensitive diagnostic", request=request)

    provider = NebiusProvider(
        env={"NEBIUS_API_KEY": "synthetic"}, transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ProviderError, match="^timeout$"):
        provider.smoke("kimi")


def test_provider_invalid_payload_classified():
    provider = CloudflareProvider(
        env={"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic"},
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
    )
    with pytest.raises(ProviderError, match="invalid_response"):
        provider.smoke("glm")


def test_research_disallows_nontext():
    gateway = ResearchGateway(
        resolver=resolver("93.184.216.34"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "application/octet-stream"}
            )
        ),
    )
    with pytest.raises(ResearchError, match="content_type"):
        gateway.fetch("https://public.example/docs")


def test_explicit_checkpoint_adds_only_intended_and_never_merges(control, monkeypatch):
    path = control / "tests/fixtures/engineering.txt"
    path.parent.mkdir(parents=True)
    path.write_text("harmless fixture")
    commands, checked = [], []
    state = {"sha": SHA}

    def fake_git(root, *args):
        commands.append(args)
        if args == ("branch", "--show-current"):
            return "agent/codex/TEST-001"
        if args == ("rev-parse", "HEAD"):
            return state["sha"]
        if args[0] == "diff":
            return "tests/fixtures/engineering.txt"
        if args[0] == "commit":
            state["sha"] = "b" * 40
        return ""

    monkeypatch.setattr("agents.gitops.git", fake_git)
    monkeypatch.setattr("agents.gitops.control_root", lambda root: control)
    monkeypatch.setattr(
        "agents.gitops.changed_paths", lambda root: {"tests/fixtures/engineering.txt"}
    )
    monkeypatch.setattr(
        "agents.gitops.safe_checks", lambda root, profiles: checked.append(profiles)
    )
    monkeypatch.setattr("agents.gitops.shutil.which", lambda command: None)
    assert (
        submit(control, "TEST-001 fixture checkpoint", ["tests/fixtures/engineering.txt"])
        == "b" * 40
    )
    assert checked == [["foundation"]]
    assert ("add", "--", "tests/fixtures/engineering.txt") in commands
    assert ("push", "--set-upstream", "origin", "HEAD:refs/heads/agent/codex/TEST-001") in commands
    assert not any(cmd[0] in ["merge", "reset", "checkout"] for cmd in commands)
    assert load_task(control, "TEST-001").commit_sha == "b" * 40


def test_research_compressed_response_rejected():
    gateway = ResearchGateway(
        resolver=resolver("93.184.216.34"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "text/plain", "content-encoding": "br"}
            )
        ),
    )
    with pytest.raises(ResearchError, match="compressed_response"):
        gateway.fetch("https://public.example/docs")


def test_blank_secret_template_does_not_capture_next_line():
    ensure_no_secrets("OVH_S3_SECRET_KEY=\nOVH_S3_BUCKET=kemirix-knowledge-raw\n")
    with pytest.raises(ValueError):
        ensure_no_secrets("OVH_S3_SECRET_KEY=" + "s" * 32 + "\n")
