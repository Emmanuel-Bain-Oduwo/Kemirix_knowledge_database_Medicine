"""Publish the deterministic agent gate for an exact PR head; never merge a PR."""

import argparse
import json
import re
import subprocess
from pathlib import Path

from .gitops import control_root, git, safe_checks
from .memory import writer_lock
from .merge_gate import evaluate
from .tasks import load_task

CONTEXT = "kemirix-agent-gate"


def api(endpoint, **fields):
    command = ["gh", "api", endpoint]
    for key, value in fields.items():
        command += ["-f", f"{key}={value}"]
    result = subprocess.run(command, capture_output=True, check=False, timeout=60)
    if result.returncode:
        raise RuntimeError("GitHub API request failed")
    return json.loads(result.stdout)


def publish(root, repository, number, task_id):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or number < 1:
        raise ValueError("repository and positive PR number required")
    endpoint = f"repos/{repository}/pulls/{number}"
    pull = api(endpoint)
    head = pull["head"]["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("invalid PR head")
    status_endpoint = f"repos/{repository}/statuses/{head}"

    def status(state):
        api(
            status_endpoint,
            state=state,
            context=CONTEXT,
            description="Mechanical agent gate: " + state,
        )

    # Invalidate any earlier success before attempting verification.
    status("pending")
    try:
        control = control_root(root)
        with writer_lock(control):
            task = load_task(control, task_id)
            if (
                pull["state"] != "open"
                or pull["draft"] is not False
                or pull["base"]["ref"] != "main"
                or pull["base"]["repo"]["full_name"] != repository
                or pull["head"]["repo"]["full_name"] != repository
                or pull["head"]["ref"] != task.branch
            ):
                raise ValueError("PR does not match task and main target")
            if (
                git(root, "rev-parse", "HEAD") != head
                or git(root, "branch", "--show-current") != task.branch
                or git(root, "status", "--porcelain")
            ):
                raise ValueError("clean exact PR checkpoint required for testing")
            git(control, "fetch", "origin", "main")
            main_head = git(control, "rev-parse", "FETCH_HEAD")

            if main_head != pull["base"]["sha"]:
                raise ValueError("fetched main does not match PR base")

            # Query the PR repository, never a model-provided CI PASS flag.
            def ci_passed():
                checks = api(f"repos/{repository}/commits/{head}/check-runs?per_page=100")
                runs = checks["check_runs"]
                if checks["total_count"] != len(runs):
                    return False  # Incomplete/paginated evidence is not success.
                workflows = api(
                    f"repos/{repository}/actions/workflows/ci.yml/runs"
                    f"?head_sha={head}&event=pull_request&per_page=100"
                )
                ci_runs = workflows["workflow_runs"]
                if (
                    not ci_runs
                    or workflows["total_count"] != len(ci_runs)
                    or not all(
                        run["head_sha"] == head
                        and run["head_branch"] == task.branch
                        and run["event"] == "pull_request"
                        and run["status"] == "completed"
                        and run["conclusion"] == "success"
                        for run in ci_runs
                    )
                ):
                    return False
                suite_ids = {run["check_suite_id"] for run in ci_runs}
                foundation = [run for run in runs if run["name"] == "foundation"]
                return bool(foundation) and all(
                    run["head_sha"] == head
                    and run["check_suite"]["id"] in suite_ids
                    and run["status"] == "completed"
                    and run["conclusion"] == "success"
                    and run["app"]["slug"] == "github-actions"
                    for run in foundation
                )

            if not ci_passed():
                raise ValueError("foundation CI has not passed for this SHA")
            safe_checks(root, task.required_tests)
            report = evaluate(
                control,
                task_id,
                pull["head"]["ref"],
                task.base_sha,
                head,
                ci_pass=True,
                test_results=dict.fromkeys(task.required_tests, True),
                main_head=main_head,
            )
            if report["result"] != "MERGE_READY":
                status("failure")
                return report
            # A moved/retargeted/closed PR or changed checkout invalidates this run.
            current = api(endpoint)
            if (
                any(current[key] != pull[key] for key in ("head", "base", "state", "draft"))
                or git(root, "rev-parse", "HEAD") != head
                or git(root, "branch", "--show-current") != task.branch
                or git(root, "status", "--porcelain")
                or not ci_passed()
            ):
                raise ValueError("PR, checkout or CI changed during evaluation")
            status("success")
            return report
    except Exception:
        status("failure")
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        report = publish(args.root, args.repository, args.pr, args.task_id)
        print(json.dumps(report, indent=2))
        if report["result"] != "MERGE_READY":
            parser.exit(1, "Agent gate: NOT READY.\n")
    except Exception:
        parser.exit(1, "Agent gate refused: unverifiable PR, reports, tests, CI or lifecycle.\n")


if __name__ == "__main__":
    main()
