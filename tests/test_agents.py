import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from agents import checkpoint as checkpoint_cli
from agents.checkpoint import describe
from agents.context import build_context
from agents.gitops import submit
from agents.harness import (
    SELECTION_ENV,
    fallback_chain,
    is_writer_handoff,
    profile_for,
    writer_identity,
)
from agents.memory import CANONICAL, writer_lock
from agents.merge_gate import evaluate
from agents.models import PRIORITY, REPORTS, Task, branch_parts
from agents.providers import CloudflareProvider, NebiusProvider, ProviderError, SmokeResult
from agents.research import ResearchError, ResearchGateway
from agents.security import ensure_no_secrets, redact
from agents.tasks import (
    create_task,
    handoff,
    load_task,
    save_task,
    transition,
    validate_report,
    write_owned,
)

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


def test_handoff_preserves_base_and_checkpoint_sha(control):
    # Switching Codex to OpenCode (writer glm) is an explicit writer handoff that
    # preserves the same task, branch, base/HEAD SHA, memory, reports and
    # coordinator state: the recorded base SHA stays, and the replacement writer
    # resumes at the exact recorded checkpoint (HEAD) SHA.
    update_task(control, commit_sha="b" * 40)
    result = handoff(
        control, "TEST-001", "glm", {**handoff_details(), "last_commit_sha": "b" * 40}, True
    )
    assert result.base_sha == SHA
    assert result.commit_sha == "b" * 40
    assert result.branch == "agent/glm/TEST-001"
    record = result.handoffs[-1]
    assert record["base_sha"] == SHA
    assert record["checkpoint_sha"] == "b" * 40
    assert (record["old_writer"], record["new_writer"]) == ("codex", "glm")


def test_merge_gate_ready_after_handoff_with_preserved_base(control, monkeypatch):
    # Because the handoff preserves the recorded base/HEAD SHA and coordinator
    # state, the merge gate still validates against the main-anchored base after
    # a Codex -> OpenCode harness switch.
    monkeypatch.setattr("agents.merge_gate.git", lambda root, *args: "")
    merge_gate_reports(control)
    update_task(control, commit_sha="b" * 40)
    handoff(control, "TEST-001", "glm", {**handoff_details(), "last_commit_sha": "b" * 40}, True)
    update_task(control, status="ci")
    report = evaluate(
        control,
        "TEST-001",
        branch="agent/glm/TEST-001",
        base_sha=SHA,
        head_sha="b" * 40,
        ci_pass=True,
        test_results={"foundation": True},
        main_head=SHA,
    )
    assert report["result"] == "MERGE_READY"
    assert report["failed"] == []


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


def test_glm_structural_smoke_accepts_plain_content():
    # The direct Cloudflare GLM test returned HTTP 200 with a valid choices list and
    # content "CONNECT"; structural validation must PASS without an exact phrase.
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "success": True,
                "result": {"choices": [{"message": {"role": "assistant", "content": "CONNECT"}}]},
            },
        )
    )
    result = CloudflareProvider(
        env={"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic"},
        transport=transport,
    ).smoke("glm")
    assert result.status == "PASS"


def test_smoke_accepts_reasoning_content_without_content():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"choices": [{"message": {"reasoning_content": "verified reasoning"}}]}
        )
    )
    result = NebiusProvider(env={"NEBIUS_API_KEY": "synthetic"}, transport=transport).smoke("kimi")
    assert result.status == "PASS"


def test_cloudflare_legacy_response_shape_still_valid():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"success": True, "result": {"response": "ok"}})
    )
    result = CloudflareProvider(
        env={"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic"},
        transport=transport,
    ).smoke("glm")
    assert result.status == "PASS"


@pytest.mark.parametrize(
    "body",
    [
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": "  ", "reasoning_content": ""}}]},
        {"choices": "not-a-list"},
        {"success": True, "result": {"response": ""}},
        {"success": True, "result": {}},
        {},
    ],
)
def test_smoke_rejects_malformed_structures(body):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    if "result" in body or "success" in body:
        provider = CloudflareProvider(
            env={"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic"},
            transport=transport,
        )
        role = "glm"
    else:
        provider = NebiusProvider(env={"NEBIUS_API_KEY": "synthetic"}, transport=transport)
        role = "kimi"
    with pytest.raises(ProviderError, match="invalid_response|provider_rejected"):
        provider.smoke(role)


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


@pytest.mark.parametrize("initially_staged", [False, True])
def test_submit_infers_working_tree_without_manual_staging(control, monkeypatch, initially_staged):
    path = control / "tests/fixtures/engineering.txt"
    path.parent.mkdir(parents=True)
    path.write_text("harmless fixture")
    commands, checked = [], []
    state = {"sha": SHA, "staged": initially_staged}

    def fake_git(root, *args):
        commands.append(args)
        if args == ("branch", "--show-current"):
            return "agent/codex/TEST-001"
        if args == ("rev-parse", "HEAD"):
            return state["sha"]
        if args == ("diff", "--cached", "--name-only", "--no-renames", "-z"):
            return "tests/fixtures/engineering.txt" if state["staged"] else ""
        if args[0] == "diff":
            return "tests/fixtures/engineering.txt"
        if args[0] == "add":
            state["staged"] = True
        if args[0] == "commit":
            state["sha"] = "b" * 40
        return ""

    monkeypatch.setattr("agents.gitops.git", fake_git)
    monkeypatch.setattr("agents.gitops.control_root", lambda root: control)
    monkeypatch.setattr(
        "agents.gitops.safe_checks", lambda root, profiles: checked.append(profiles)
    )
    monkeypatch.setattr("agents.gitops.shutil.which", lambda command: None)
    assert submit(control, "TEST-001 inferred working-tree checkpoint") == "b" * 40
    assert checked == [["foundation"]]
    assert ("add", "--", "tests/fixtures/engineering.txt") in commands
    assert ("commit", "-m", "TEST-001 inferred working-tree checkpoint") in commands
    assert ("push", "--set-upstream", "origin", "HEAD:refs/heads/agent/codex/TEST-001") in commands
    assert not any(cmd[0] in ["merge", "reset", "checkout"] for cmd in commands)
    assert load_task(control, "TEST-001").commit_sha == "b" * 40


def test_submit_refuses_path_scope_missing_unrelated_change(control, monkeypatch):
    monkeypatch.setattr("agents.gitops.git", lambda root, *args: "agent/codex/TEST-001")
    monkeypatch.setattr("agents.gitops.control_root", lambda root: control)
    monkeypatch.setattr(
        "agents.gitops.changed_paths",
        lambda root: {"tests/fixtures/engineering.txt", "docs/unrelated.md"},
    )
    with pytest.raises(ValueError, match="isolated"):
        submit(control, "TEST-001 checkpoint", ["tests/fixtures/engineering.txt"])


def test_submit_refuses_unauthorized_inferred_change(control, monkeypatch):
    monkeypatch.setattr("agents.gitops.git", lambda root, *args: "agent/codex/TEST-001")
    monkeypatch.setattr("agents.gitops.control_root", lambda root: control)
    monkeypatch.setattr("agents.gitops.changed_paths", lambda root: {"docs/unowned.md"})
    with pytest.raises(PermissionError, match="ownership"):
        submit(control, "TEST-001 checkpoint")


def test_submit_refuses_clean_working_tree(control, monkeypatch):
    monkeypatch.setattr("agents.gitops.git", lambda root, *args: "agent/codex/TEST-001")
    monkeypatch.setattr("agents.gitops.control_root", lambda root: control)
    monkeypatch.setattr("agents.gitops.changed_paths", lambda root: set())
    with pytest.raises(ValueError, match="no working-tree changes"):
        submit(control, "TEST-001 checkpoint")


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


def update_task(control, **changes):
    data = load_task(control, "TEST-001").model_dump()
    data.update(changes)
    save_task(control, Task.model_validate(data))


def merge_gate_reports(control, research=True):
    reports = control / "ops/reports/TEST-001"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "qwen-crosscheck.md").write_text("PASS\nFindings: none.\nChecks: fixture.\n")
    (reports / "glm-review.md").write_text(
        "PASS\nFindings: none.\nSeverity: MINOR\nChecks: fixture.\n"
    )
    (reports / "nemotron-qa.md").write_text("QA_PASS\nFindings: none.\nChecks: fixture.\n")
    if research:
        (reports / "kimi-analysis.md").write_text(
            "ANALYSIS_COMPLETE\nFindings: fixture.\nReferences: fixture.\n"
        )


def test_merge_gate_fails_closed_without_reports_ci_or_tests(control, monkeypatch):
    monkeypatch.setattr("agents.merge_gate.git", lambda root, *args: "")
    update_task(control, status="ci")
    report = evaluate(
        control,
        "TEST-001",
        branch="agent/codex/TEST-001",
        base_sha=SHA,
        head_sha=SHA,
        ci_pass=False,
        test_results={},
        main_head=SHA,
    )
    assert report["result"] == "NOT_READY"
    for failed in ["report_qwen", "report_glm", "report_nemotron", "ci_pass", "required_tests"]:
        assert failed in report["failed"]


def test_merge_gate_ready_when_all_gates_pass(control, monkeypatch):
    monkeypatch.setattr("agents.merge_gate.git", lambda root, *args: "")
    merge_gate_reports(control)
    update_task(control, status="ci")
    report = evaluate(
        control,
        "TEST-001",
        branch="agent/codex/TEST-001",
        base_sha=SHA,
        head_sha=SHA,
        ci_pass=True,
        test_results={"foundation": True},
        main_head=SHA,
    )
    assert report["result"] == "MERGE_READY"
    assert report["failed"] == []


def test_merge_gate_rejects_wrong_branch_base_or_head(control, monkeypatch):
    monkeypatch.setattr("agents.merge_gate.git", lambda root, *args: "")
    merge_gate_reports(control)
    update_task(control, status="ci")
    for kwargs in [
        {"branch": "agent/glm/TEST-001", "base_sha": SHA, "head_sha": SHA},
        {"branch": "agent/codex/TEST-001", "base_sha": "b" * 40, "head_sha": SHA},
        {"branch": "agent/codex/TEST-001", "base_sha": SHA, "head_sha": "b" * 40},
    ]:
        report = evaluate(
            control,
            "TEST-001",
            ci_pass=True,
            test_results={"foundation": True},
            main_head=SHA,
            **kwargs,
        )
        assert report["result"] == "NOT_READY"


def test_merge_gate_rejects_base_not_on_main(control, monkeypatch):
    def refuse(root, *args):
        raise RuntimeError("not an ancestor")

    monkeypatch.setattr("agents.merge_gate.git", refuse)
    merge_gate_reports(control)
    update_task(control, status="ci")
    report = evaluate(
        control,
        "TEST-001",
        branch="agent/codex/TEST-001",
        base_sha=SHA,
        head_sha=SHA,
        ci_pass=True,
        test_results={"foundation": True},
        main_head="c" * 40,
    )
    assert "base_on_main" in report["failed"]
    assert report["result"] == "NOT_READY"


def test_merge_gate_open_qa_loop_blocks_merge(control, monkeypatch):
    monkeypatch.setattr("agents.merge_gate.git", lambda root, *args: "")
    merge_gate_reports(control)
    report = evaluate(
        control,
        "TEST-001",
        branch="agent/codex/TEST-001",
        base_sha=SHA,
        head_sha=SHA,
        ci_pass=True,
        test_results={"foundation": True},
        main_head=SHA,
    )
    assert "no_unresolved_blockers" in report["failed"]


def test_merge_gate_invalid_contract_fails_closed(control):
    (control / "ops/tasks/TEST-001.yaml").write_text("task_id: TEST-001\n")
    report = evaluate(
        control,
        "TEST-001",
        branch="agent/codex/TEST-001",
        base_sha=SHA,
        head_sha=SHA,
        ci_pass=True,
        test_results={"foundation": True},
        main_head=SHA,
    )
    assert report["result"] == "NOT_READY"
    assert report["failed"] == ["task_contract"]


def test_merge_gate_kimi_report_only_when_research_required(control, monkeypatch):
    monkeypatch.setattr("agents.merge_gate.git", lambda root, *args: "")
    merge_gate_reports(control, research=False)
    update_task(control, status="ci", research_required=False)
    report = evaluate(
        control,
        "TEST-001",
        branch="agent/codex/TEST-001",
        base_sha=SHA,
        head_sha=SHA,
        ci_pass=True,
        test_results={"foundation": True},
        main_head=SHA,
    )
    assert report["result"] == "MERGE_READY"


def test_research_required_only_when_relevant(control):
    update_task(control, status="research")
    with pytest.raises(FileNotFoundError):
        transition(control, "TEST-001", "implementation", "kimi report missing")
    update_task(control, status="research", research_required=False)
    assert (
        transition(control, "TEST-001", "implementation", "infrastructure task").status
        == "implementation"
    )


def test_harness_chain_matches_frozen_writer_priority():
    # Codex + GPT-6 Astra primary; OpenCode + GLM 5.3 first fallback;
    # OpenCode + Qwen 3.8 second fallback. The fallback order must match the
    # frozen writer priority prefix (codex -> glm -> qwen).
    assert [p.name for p in fallback_chain()] == [
        "codex-gpt-6-astra",
        "opencode-glm-5.3",
        "opencode-qwen-3.8-27b",
    ]
    assert [p.harness for p in fallback_chain()] == ["codex", "opencode", "opencode"]
    assert [p.writer for p in fallback_chain()] == PRIORITY[:3]


def test_harness_switch_is_explicit_writer_handoff():
    # GLM/Qwen are independent OpenCode harnesses, not Codex model brains:
    # every step down the chain changes the writer identity and therefore
    # requires the human-approved writer handoff.
    chain = fallback_chain()
    for old, new in zip(chain, chain[1:]):
        assert is_writer_handoff(old, new)
        assert writer_identity(old) != writer_identity(new)
    assert not is_writer_handoff(chain[0], chain[0])


@pytest.mark.parametrize(
    "name,writer",
    [
        ("codex-gpt-6-astra", "codex"),
        ("opencode-glm-5.3", "glm"),
        ("opencode-qwen-3.8-27b", "qwen"),
    ],
)
def test_harness_writer_identity(name, writer):
    assert writer_identity(profile_for(name)) == writer


def test_harness_selection_env_and_fail_closed(monkeypatch):
    monkeypatch.delenv(SELECTION_ENV, raising=False)
    assert profile_for(env={}).name == "codex-gpt-6-astra"
    monkeypatch.setenv(SELECTION_ENV, "opencode-glm-5.3")
    assert profile_for().model == "@cf/zai-org/glm-5.3"
    with pytest.raises(ValueError):
        profile_for("made-up-harness")


def test_harness_profiles_carry_no_secret_values():
    from agents.harness import REGISTRY

    for profile in REGISTRY.values():
        ensure_no_secrets(repr(profile))
        assert profile.harness in ["codex", "opencode"]


def load_smoke_script():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "provider_smoke_test", ROOT / "scripts/provider-smoke-test.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_smoke_script_exit_codes(monkeypatch, capsys):
    module = load_smoke_script()
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["provider-smoke-test.py", "--provider", "glm"])
    assert module.main() == 1  # missing_configuration: nonzero exit on genuine failure

    class Stub:
        def smoke(self, role, timeout=None):
            return SmokeResult("glm", "PASS", "structural fixture")

    monkeypatch.setattr(sys, "argv", ["provider-smoke-test.py", "--provider", "glm"])
    monkeypatch.setattr(module, "provider_for", lambda role, **kwargs: Stub())
    assert module.main() == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "synthetic" not in out


def test_blank_secret_template_does_not_capture_next_line():
    ensure_no_secrets("OVH_S3_SECRET_KEY=\nOVH_S3_BUCKET=kemirix-knowledge-raw\n")
    with pytest.raises(ValueError):
        ensure_no_secrets("OVH_S3_SECRET_KEY=" + "s" * 32 + "\n")


CLINICAL_PATHS = [
    "migrations",
    "migrations/001_clinical.sql",
    "src/kmx",
    "src/kmx/identity.py",
    "src/evidence",
    "src/evidence/trials.py",
    "src/rules",
    "src/rules/engine.py",
    "src/sources",
    "src/sources/fetch.py",
]


def foundation_contract(**overrides):
    stamp = datetime.now(timezone.utc)
    contract = dict(
        task_id="FOUNDATION-001",
        phase="phase_0",
        goal="Finalize and externally verify the phase 0 engineering foundation",
        production_writer="codex",
        active_writer="codex",
        writer_priority=PRIORITY,
        allowed_paths=[
            ".github/workflows/ci.yml",
            "docs/ENGINEERING_HARNESSES.md",
            "ops/agents/AGENTS.md",
            "ops/memory/CURRENT_STATE.md",
            "ops/tasks/FOUNDATION-001.yaml",
            "ops/reports/FOUNDATION-DRYRUN-001/README.md",
            "ops/reports/foundation-validation.md",
            "scripts/agent-submit.sh",
            "src/agents/models.py",
            "tests/test_agents.py",
        ],
        forbidden_paths=[
            "SKILL.md",
            "ops/memory/INVARIANTS.md",
            "migrations",
            "src/kmx",
            "src/evidence",
            "src/rules",
            "src/sources",
        ],
        base_sha=SHA,
        branch="agent/codex/FOUNDATION-001",
        research_required=False,
        acceptance_criteria=["Phase 0 foundation stays clinically untouched"],
        required_tests=["foundation"],
        status="implementation",
        created_at=stamp,
        updated_at=stamp,
        completed_at=None,
        commit_sha=None,
        deployed_sha=None,
        handoffs=[],
        events=[],
    )
    contract.update(overrides)
    return contract


@pytest.fixture
def foundation_control(tmp_path):
    for name in CANONICAL + ["ops/agents/CODEX.md", "ops/agents/KIMI.md"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    save_task(tmp_path, Task.model_validate(foundation_contract()))
    return tmp_path


def test_foundation_bootstrap_contract_validates():
    task = Task.model_validate(foundation_contract())
    assert task.foundation_bootstrap
    for path in [*task.allowed_paths, f"ops/reports/FOUNDATION-001/{REPORTS['codex']}"]:
        assert task.authorize("codex", path) == path


def test_foundation_bootstrap_keeps_baseline_protection():
    for path in [
        "SKILL.md",
        "ops/memory/INVARIANTS.md",
        "ops/memory",
        "ops",
        ".git",
        ".git/config",
        ".env",
    ]:
        with pytest.raises(ValidationError):
            Task.model_validate(foundation_contract(allowed_paths=[path]))


def test_foundation_bootstrap_cannot_authorize_protected_paths():
    task = Task.model_validate(foundation_contract())
    for path in ["SKILL.md", "ops/memory/INVARIANTS.md", ".git/config", ".env", "ops/.pgpass"]:
        with pytest.raises(PermissionError):
            task.authorize("codex", path)


@pytest.mark.parametrize("path", CLINICAL_PATHS)
def test_foundation_bootstrap_rejects_clinical_scope(path):
    with pytest.raises(ValidationError):
        Task.model_validate(foundation_contract(allowed_paths=[path]))


@pytest.mark.parametrize("path", CLINICAL_PATHS)
def test_foundation_bootstrap_cannot_authorize_clinical_paths(path):
    task = Task.model_validate(foundation_contract())
    with pytest.raises(PermissionError):
        task.authorize("codex", path)


@pytest.mark.parametrize(
    "path",
    [
        "ops/agents",
        "ops/agents/AGENTS.md",
        "ops/memory/CURRENT_STATE.md",
        "ops/tasks/TEMPLATE.yaml",
        ".github/workflows/ci.yml",
        "SKILL.md",
        "ops",
    ],
)
def test_ordinary_tasks_keep_full_governance_restriction(task, path):
    with pytest.raises(ValidationError, match="governance"):
        Task.model_validate({**task.model_dump(), "allowed_paths": [path]})


def test_foundation_exception_requires_exact_phase_and_prefix():
    for overrides in [
        {"phase": "phase_0f"},
        {"phase": "phase_1"},
        {"task_id": "ENG-001", "branch": "agent/codex/ENG-001"},
    ]:
        with pytest.raises(ValidationError, match="governance"):
            Task.model_validate(foundation_contract(**overrides))


def test_create_task_produces_submit_ready_contract(tmp_path):
    contract = foundation_contract(status=None)
    for field in [
        "schema_version",
        "created_at",
        "updated_at",
        "completed_at",
        "commit_sha",
        "deployed_sha",
        "handoffs",
        "events",
        "writer_priority",
    ]:
        contract[field] = None
    created = create_task(tmp_path, contract)
    assert created.status == "created"
    assert created.created_at is not None
    loaded = load_task(tmp_path, created.task_id)
    assert loaded == Task.model_validate(loaded.model_dump())
    assert loaded.foundation_bootstrap
    with pytest.raises(ValueError, match="exists"):
        create_task(tmp_path, foundation_contract(status=None))


def test_create_task_rejects_invalid_scope_and_status(tmp_path):
    with pytest.raises(ValidationError, match="governance"):
        create_task(
            tmp_path,
            foundation_contract(task_id="ENG-002", branch="agent/codex/ENG-002", status=None),
        )
    with pytest.raises(ValueError, match="created"):
        create_task(tmp_path, foundation_contract())


def test_submit_unstaged_governance_change_for_foundation_task(foundation_control, monkeypatch):
    path = foundation_control / "ops/agents/AGENTS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# updated governance\n")
    commands, checked = [], []
    state = {"sha": SHA, "staged": False}

    def fake_git(root, *args):
        commands.append(args)
        if args == ("branch", "--show-current"):
            return "agent/codex/FOUNDATION-001"
        if args == ("rev-parse", "HEAD"):
            return state["sha"]
        if args == ("diff", "--cached", "--name-only", "--no-renames", "-z"):
            return "ops/agents/AGENTS.md" if state["staged"] else ""
        if args[0] == "diff":
            return "ops/agents/AGENTS.md"
        if args[0] == "add":
            state["staged"] = True
        if args[0] == "commit":
            state["sha"] = "b" * 40
        return ""

    monkeypatch.setattr("agents.gitops.git", fake_git)
    monkeypatch.setattr("agents.gitops.control_root", lambda root: foundation_control)
    monkeypatch.setattr(
        "agents.gitops.safe_checks", lambda root, profiles: checked.append(profiles)
    )
    monkeypatch.setattr("agents.gitops.shutil.which", lambda command: None)
    assert submit(foundation_control, "FOUNDATION-001 unstaged checkpoint") == "b" * 40
    assert checked == [["foundation"]]
    assert ("add", "--", "ops/agents/AGENTS.md") in commands
    assert ("commit", "-m", "FOUNDATION-001 unstaged checkpoint") in commands
    assert (
        "push",
        "--set-upstream",
        "origin",
        "HEAD:refs/heads/agent/codex/FOUNDATION-001",
    ) in commands
    assert not any(cmd[0] in ["merge", "reset", "checkout"] for cmd in commands)
    task = load_task(foundation_control, "FOUNDATION-001")
    assert task.commit_sha == "b" * 40
    assert task.events[-1]["operation"] == "checkpoint"


def test_submit_refuses_checkpoint_not_descending_from_base(foundation_control, monkeypatch):
    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return "agent/codex/FOUNDATION-001"
        if args == ("rev-parse", "HEAD"):
            return "b" * 40
        if args[:1] == ("merge-base",):
            raise RuntimeError("not an ancestor")
        raise AssertionError(args)

    monkeypatch.setattr("agents.gitops.git", fake_git)
    monkeypatch.setattr("agents.gitops.control_root", lambda root: foundation_control)
    with pytest.raises(ValueError, match="base SHA"):
        submit(foundation_control, "FOUNDATION-001 checkpoint")


def test_submit_rejects_wrong_writer_branch(foundation_control, monkeypatch):
    monkeypatch.setattr("agents.gitops.git", lambda root, *args: "agent/glm/FOUNDATION-001")
    monkeypatch.setattr("agents.gitops.control_root", lambda root: foundation_control)
    monkeypatch.setattr("agents.gitops.changed_paths", lambda root: {"ops/agents/AGENTS.md"})
    with pytest.raises(PermissionError, match="ownership"):
        submit(foundation_control, "FOUNDATION-001 checkpoint")


def test_describe_validation_error_is_actionable_and_sanitized(task):
    with pytest.raises(ValidationError) as info:
        Task.model_validate({**task.model_dump(), "allowed_paths": ["ops/agents"]})
    text = describe(info.value)
    assert "governance" in text
    assert task.goal not in text


def test_describe_redacts_secrets_and_truncates():
    token = "ghp_" + "x" * 40
    assert token not in describe(RuntimeError(f"failed near {token}"))
    truncated = describe(ValueError("x" * 900))
    assert truncated.endswith("...") and len(truncated) <= 520


def test_checkpoint_cli_reports_sanitized_missing_contract(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["checkpoint", "submit", "fixture message"])
    monkeypatch.setattr("agents.gitops.git", lambda root, *args: "agent/codex/MISSING-001")
    monkeypatch.setattr("agents.gitops.control_root", lambda root: tmp_path)
    with pytest.raises(SystemExit) as info:
        checkpoint_cli.main()
    assert info.value.code == 1
    err = capsys.readouterr().err
    assert "Checkpoint/PR operation refused or failed" in err
    assert "MISSING-001" in err


def test_checkpoint_cli_never_prints_secrets(monkeypatch, capsys):
    secret = "NEBIUS_API_KEY=" + "x" * 32

    def fail(root, message, paths=()):
        raise RuntimeError(secret)

    monkeypatch.setattr(sys, "argv", ["checkpoint", "submit", "fixture message"])
    monkeypatch.setattr("agents.checkpoint.submit", fail)
    with pytest.raises(SystemExit):
        checkpoint_cli.main()
    err = capsys.readouterr().err
    assert secret not in err and "x" * 32 not in err
    assert "[REDACTED]" in err


def test_merge_gate_foundation_task_fails_closed_without_reports(foundation_control, monkeypatch):
    monkeypatch.setattr("agents.merge_gate.git", lambda root, *args: "")
    report = evaluate(
        foundation_control,
        "FOUNDATION-001",
        branch="agent/codex/FOUNDATION-001",
        base_sha=SHA,
        head_sha=SHA,
        ci_pass=True,
        test_results={"foundation": True},
        main_head=SHA,
    )
    assert report["result"] == "NOT_READY"
    assert "report_qwen" in report["failed"]
    assert "no_unresolved_blockers" in report["failed"]


def test_context_keeps_invariants_forbidden_for_foundation(foundation_control):
    context = build_context(foundation_control, "FOUNDATION-001", "codex")
    forbidden = context["metadata"]["FORBIDDEN_PATHS"]
    assert "SKILL.md" in forbidden and "ops/memory/INVARIANTS.md" in forbidden
    assert "migrations" in forbidden and "src/kmx" in forbidden
    assert "ops/memory" not in forbidden
