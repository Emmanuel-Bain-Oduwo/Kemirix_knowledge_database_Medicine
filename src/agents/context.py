"""Bounded canonical context; external research is untrusted input."""

from .memory import CANONICAL
from .models import PHASE_ZERO, REPORTS
from .security import ensure_no_secrets, safe_repo_path
from .tasks import load_task


def build_context(root, task_id, role, code_paths=(), max_bytes=180_000, code_root=None):
    task = load_task(root, task_id)
    if role not in REPORTS:
        raise ValueError("unknown role")
    metadata = {
        "TASK_ID": task.task_id,
        "ROLE": role,
        "CURRENT_PHASE": task.phase,
        "ACTIVE_WRITER": task.active_writer,
        "WRITE_PERMISSION": "production_and_own_report"
        if role == task.active_writer and task.status in ["implementation", "fixes"]
        else "own_report_only",
        "ALLOWED_PATHS": task.allowed_for(role),
        "FORBIDDEN_PATHS": [
            *task.protected_scope(),
            *task.forbidden_paths,
            *(PHASE_ZERO if task.phase.startswith("phase_0") else []),
        ],
        "BASE_SHA": task.base_sha,
    }
    paths = [*CANONICAL, f"ops/agents/{role.upper()}.md", f"ops/tasks/{task_id}.yaml"]
    report_dir = safe_repo_path(root, f"ops/reports/{task_id}")
    if report_dir.exists():
        paths += [p.relative_to(root).as_posix() for p in sorted(report_dir.glob("*.md"))]
    for path in code_paths:
        from .models import inside, path_value

        path_value(path)
        if not any(inside(path, allowed) for allowed in task.allowed_paths):
            raise PermissionError("context code must be task-scoped")
        paths.append(path)
    sections = []
    size = 0
    for relative in paths:
        path = safe_repo_path(code_root if code_root and relative in code_paths else root, relative)
        if path.stat().st_size > max_bytes:
            raise ValueError("context file exceeds budget")
        text = path.read_text()
        ensure_no_secrets(text)
        size += len(text.encode())
        if size > max_bytes:
            raise ValueError("context exceeds budget; select fewer relevant files")
        sections.append({"path": relative, "content": text})
    return {"metadata": metadata, "sections": sections}
