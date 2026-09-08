"""Task ownership and human-approved transitions; no model decides control flow."""

import json

import yaml

from .memory import atomic_text, load_yaml, now, writer_lock
from .models import PRIORITY, REPORTS, STAGES, HandoffDetails, Task
from .security import ensure_no_secrets, safe_repo_path


def task_path(root, task_id):
    import re

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", task_id):
        raise ValueError("invalid task ID")
    return safe_repo_path(root, f"ops/tasks/{task_id}.yaml")


def load_task(root, task_id):
    task = Task.model_validate(load_yaml(task_path(root, task_id)))
    if task.task_id != task_id:
        raise ValueError("task filename mismatch")
    return task


def save_task(root, task):
    task = Task.model_validate(task.model_dump())
    atomic_text(
        task_path(root, task.task_id), yaml.safe_dump(task.model_dump(mode="json"), sort_keys=False)
    )


def create_task(root, data):
    """Create a new task; the contract must be schema-valid before any submit.

    Administrative lifecycle fields default automatically, so a completed
    TEMPLATE.yaml only needs the meaningful scope fields. Creation refuses
    duplicates, invalid contracts and non-initial statuses, and the saved
    contract round-trips through the strict loader.
    """
    data = dict(data)
    if data.get("status") not in (None, "created"):
        raise ValueError("new task must be created")
    stamp = now()
    defaults = {
        "schema_version": 2,
        "status": "created",
        "writer_priority": PRIORITY,
        "created_at": stamp,
        "updated_at": stamp,
        "completed_at": None,
        "commit_sha": None,
        "deployed_sha": None,
        "handoffs": [],
        "events": [],
    }
    for field, default in defaults.items():
        if data.get(field) is None:
            data[field] = default
    task = Task.model_validate(data)
    with writer_lock(root):
        if task_path(root, task.task_id).exists():
            raise ValueError("task already exists")
        save_task(root, task)
        return task


def write_owned(root, worktree, task_id, role, relative, content):
    with writer_lock(root):
        task = load_task(root, task_id)
        task.authorize(role, relative)
        destination = safe_repo_path(worktree, relative)
        ensure_no_secrets(content)
        atomic_text(destination, content)


def next_stage(task):
    if task.status == "closed":
        return None
    return STAGES[STAGES.index(task.status) + 1]


def validate_report(text, role):
    ensure_no_secrets(text)
    allowed = {
        "kimi": ["ANALYSIS_COMPLETE", "BLOCKED"],
        "minimax": ["PASS", "REQUEST_CHANGES"],
        "glm": ["PASS", "REQUEST_CHANGES"],
        "nemotron": ["QA_PASS", "QA_FAIL"],
    }
    first = text.strip().splitlines()[0] if text.strip() else ""
    if first not in allowed[role] or len(text.strip().splitlines()) < 3:
        raise ValueError("report needs status, findings and validation evidence")
    if role == "glm" and not any(v in text for v in ["CRITICAL", "MAJOR", "MINOR"]):
        raise ValueError("GLM report needs severity classification")
    return first


def transition(root, task_id, target, evidence, human=False, commit_sha=None, deployed_sha=None):
    if not evidence.strip():
        raise ValueError("transition evidence required")
    ensure_no_secrets(evidence)
    with writer_lock(root):
        task = load_task(root, task_id)
        permitted = [next_stage(task)]
        if task.status in ["crosscheck", "review", "qa"]:
            permitted.append("fixes")
        if task.status == "fixes":
            permitted = ["crosscheck"]  # Fixes require renewed independent review.
        if task.status == "qa":
            permitted.append("ci")
        if target not in permitted:
            raise ValueError("invalid lifecycle transition")
        role_gate = {
            "research": ("kimi", "ANALYSIS_COMPLETE"),
            "crosscheck": ("minimax", "PASS"),
            "review": ("glm", "PASS"),
            "qa": ("nemotron", "QA_PASS"),
        }
        # Kimi research is required only where the task contract declares it.
        gated = task.status in role_gate and not (
            task.status == "research" and not task.research_required
        )
        if gated and target != "fixes":
            role, expected = role_gate[task.status]
            if role == task.active_writer:
                if not human:
                    raise PermissionError("independent human review required after writer failover")
            else:
                path = safe_repo_path(root, f"ops/reports/{task_id}/{REPORTS[role]}")
                if validate_report(path.read_text(), role) != expected:
                    raise ValueError("review blocks progress")
        if target in ["merged", "deployed", "verified", "closed"] and not human:
            raise PermissionError("human attestation required for external lifecycle results")
        data = task.model_dump()
        data.update(status=target, updated_at=now())
        if commit_sha:
            data["commit_sha"] = commit_sha
        if deployed_sha:
            data["deployed_sha"] = deployed_sha
        if target == "closed":
            data["completed_at"] = now()
        data["events"] = [
            *task.events,
            {
                "from": task.status,
                "to": target,
                "evidence": evidence,
                "human_approved": human,
                "timestamp": now().isoformat(),
            },
        ]
        result = Task.model_validate(data)
        save_task(root, result)
        return result


def handoff(root, task_id, new_writer, details, human=False, prepare=None):
    if not human:
        raise PermissionError("writer switching requires explicit human approval")
    details = HandoffDetails.model_validate(details).model_dump()
    ensure_no_secrets(json.dumps(details))
    with writer_lock(root):
        task = load_task(root, task_id)
        if new_writer not in PRIORITY or new_writer == task.active_writer:
            raise ValueError("invalid replacement writer")
        if task.status not in ["implementation", "fixes"]:
            raise ValueError("handoff requires an implementation checkpoint")
        if not task.commit_sha or task.commit_sha != details["last_commit_sha"]:
            raise ValueError("handoff must use the recorded exact checkpoint")
        # The handoff preserves the task's recorded base and checkpoint (HEAD)
        # SHA; the replacement writer resumes at the exact recorded checkpoint.
        record = {
            **details,
            "task_id": task_id,
            "old_writer": task.active_writer,
            "new_writer": new_writer,
            "old_branch": task.branch,
            "new_branch": f"agent/{new_writer}/{task_id}",
            "base_sha": task.base_sha,
            "checkpoint_sha": task.commit_sha,
            "timestamp": now().isoformat(),
            "human_approved": True,
        }
        data = task.model_dump()
        data.update(
            active_writer=new_writer,
            production_writer=new_writer,
            branch=record["new_branch"],
            updated_at=now(),
            handoffs=[*task.handoffs, record],
        )
        updated = Task.model_validate(data)
        if prepare:
            prepare(updated)
        # Task YAML is atomic authority; report is a recoverable projection of its handoff history.
        save_task(root, updated)
        atomic_text(
            safe_repo_path(root, f"ops/reports/{task_id}/handoff.md"),
            "# Writer handoffs\n\n" + yaml.safe_dump(updated.handoffs, sort_keys=False),
        )
        return updated
