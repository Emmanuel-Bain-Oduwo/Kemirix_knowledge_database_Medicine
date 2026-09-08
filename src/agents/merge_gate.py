"""Deterministic mechanical PR merge gate. No LLM decides merge readiness; fail closed."""

import re

from .gitops import git
from .models import PRIORITY, REPORTS, STAGES, branch_parts
from .security import safe_repo_path
from .tasks import load_task, validate_report

REQUIRED_RESULTS = {"qwen": "PASS", "glm": "PASS", "nemotron": "QA_PASS"}


def is_ancestor(root, ancestor, descendant):
    if not (re.fullmatch("[0-9a-f]{40}", ancestor) and re.fullmatch("[0-9a-f]{40}", descendant)):
        return False
    try:
        git(root, "merge-base", "--is-ancestor", ancestor, descendant)
    except RuntimeError:
        return False
    return True


def report_result(root, task_id, role):
    try:
        path = safe_repo_path(root, f"ops/reports/{task_id}/{REPORTS[role]}")
        return validate_report(path.read_text(), role)
    except Exception:
        return None


def evaluate(
    root, task_id, branch, base_sha, head_sha, ci_pass=False, test_results=None, main_head=None
):
    """Every check is mechanical; any unverifiable condition counts as failed."""
    test_results = dict(test_results or {})
    try:
        task = load_task(root, task_id)
    except Exception:
        return {
            "task_id": task_id,
            "result": "NOT_READY",
            "checks": {"task_contract": False},
            "failed": ["task_contract"],
        }
    checks = {}

    checks["task_contract"] = task.task_id == task_id
    checks["expected_branch"] = branch == task.branch and branch_parts(branch) == (
        task.active_writer,
        task_id,
    )
    checks["expected_base_sha"] = re.fullmatch("[0-9a-f]{40}", base_sha or "") is not None and (
        base_sha == task.base_sha
    )
    checks["base_on_main"] = is_ancestor(root, task.base_sha, main_head or "")
    checks["active_writer"] = (
        task.active_writer == task.production_writer and task.active_writer in PRIORITY
    )
    checks["head_checkpoint"] = re.fullmatch("[0-9a-f]{40}", head_sha or "") is not None and (
        head_sha == task.commit_sha
    )
    for role, expected in REQUIRED_RESULTS.items():
        checks[f"report_{role}"] = report_result(root, task_id, role) == expected
    if task.research_required:
        checks["report_kimi"] = report_result(root, task_id, "kimi") == "ANALYSIS_COMPLETE"
    checks["required_tests"] = all(
        test_results.get(profile) is True for profile in task.required_tests
    )
    checks["ci_pass"] = ci_pass is True
    # Unresolved blockers: the task must have cleared the independent QA loop.
    checks["no_unresolved_blockers"] = STAGES.index(task.status) >= STAGES.index("ci")

    failed = [name for name, passed in checks.items() if not passed]
    return {
        "task_id": task_id,
        "result": "MERGE_READY" if not failed else "NOT_READY",
        "checks": checks,
        "failed": failed,
    }
