"""Deterministic, foreground task CLI. No provider is coordinator authority."""

import argparse
import json
from pathlib import Path

from .context import build_context
from .gitops import approved_main, control_root, git, setup_worktree
from .memory import load_yaml, record_run
from .merge_gate import evaluate
from .tasks import create_task, handoff, load_task, next_stage, transition, write_owned


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ["status", "context", "start", "finish", "handoff", "write"]:
        p = sub.add_parser(cmd)
        p.add_argument("task_id")
        if cmd == "context":
            p.add_argument("--role", required=True)
            p.add_argument("--code", action="append", default=[])
            p.add_argument("--record-run", action="store_true")
        if cmd == "start":
            p.add_argument("--approved-sha", required=True)
            p.add_argument("--role", default="codex")
        if cmd == "finish":
            p.add_argument("--to", required=True)
            p.add_argument("--evidence", required=True)
            p.add_argument("--human-approved", action="store_true")
            p.add_argument("--commit-sha")
            p.add_argument("--deployed-sha")
        if cmd == "handoff":
            p.add_argument("--new-writer", required=True)
            p.add_argument("--details", type=Path, required=True)
            p.add_argument("--human-approved", action="store_true")
        if cmd == "write":
            p.add_argument("--role", required=True)
            p.add_argument("--path", required=True)
            p.add_argument("--content-file", type=Path, required=True)
    create = sub.add_parser("create")
    create.add_argument("contract", type=Path)
    gate = sub.add_parser("merge-gate")
    gate.add_argument("task_id")
    gate.add_argument("--branch", required=True)
    gate.add_argument("--base-sha", required=True)
    gate.add_argument("--head-sha", required=True)
    gate.add_argument("--ci-pass", action="store_true")
    gate.add_argument("--test-result", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        root = control_root(args.root)
        if args.command == "create":
            print(create_task(root, load_yaml(args.contract)).task_id)
        elif args.command == "status":
            task = load_task(root, args.task_id)
            print(
                json.dumps(
                    {"task": task.model_dump(mode="json"), "next_stage": next_stage(task)}, indent=2
                )
            )
        elif args.command == "context":
            context = build_context(root, args.task_id, args.role, args.code, code_root=args.root)
            if args.record_run:
                record_run(load_task(root, args.task_id), args.role, "context")
            print(json.dumps(context, indent=2))
        elif args.command == "start":
            task = load_task(root, args.task_id)
            sha = approved_main(root, args.approved_sha)
            if task.base_sha != sha:
                raise ValueError("task base must match approved main")
            print(setup_worktree(root, args.role, args.task_id, sha))
        elif args.command == "finish":
            result = transition(
                root,
                args.task_id,
                args.to,
                args.evidence,
                args.human_approved,
                args.commit_sha,
                args.deployed_sha,
            )
            print(result.status)
        elif args.command == "handoff":
            if not args.human_approved:
                raise PermissionError("human approval required before branch creation")
            task = load_task(root, args.task_id)
            details = load_yaml(args.details)
            old = Path("/srv/kemirix/worktrees") / task.active_writer
            if (
                git(old, "status", "--porcelain")
                or git(old, "rev-parse", "HEAD") != task.commit_sha
                or git(old, "branch", "--show-current") != task.branch
            ):
                raise ValueError("old writer must stop at a clean recorded checkpoint")
            if details.get("last_commit_sha") != task.commit_sha:
                raise ValueError("handoff checkpoint mismatch")

            # New worktree is inert until handoff updates active_writer; no agent is launched.
            # The replacement harness resumes at the exact recorded checkpoint (HEAD) SHA.
            def prepare(updated):
                setup_worktree(root, updated.active_writer, updated.task_id, updated.commit_sha)

            print(handoff(root, args.task_id, args.new_writer, details, True, prepare).branch)
        elif args.command == "write":
            from .models import branch_parts

            if branch_parts(git(args.root, "branch", "--show-current")) != (
                args.role,
                args.task_id,
            ):
                raise PermissionError("write must run in the matching agent task worktree")
            write_owned(
                root, args.root, args.task_id, args.role, args.path, args.content_file.read_text()
            )
            print("Owned path updated.")
        elif args.command == "merge-gate":
            from .gitops import git as git_command

            test_results = {name: True for name in args.test_result}
            # Fail closed when the approved main head cannot be fetched.
            git_command(root, "fetch", "origin", "main")
            main_head = git_command(root, "rev-parse", "FETCH_HEAD")
            report = evaluate(
                root,
                args.task_id,
                branch=args.branch,
                base_sha=args.base_sha,
                head_sha=args.head_sha,
                ci_pass=args.ci_pass,
                test_results=test_results,
                main_head=main_head,
            )
            print(json.dumps(report, indent=2))
            if report["result"] != "MERGE_READY":
                parser.exit(1, "Merge gate: NOT READY.\n")
    except Exception:
        # Validation errors can contain input values: never dump them into shared logs.
        parser.exit(
            1, "Coordinator refused operation: invalid contract, ownership, state or setup.\n"
        )


if __name__ == "__main__":
    main()
