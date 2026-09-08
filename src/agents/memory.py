"""Canonical Git-backed memory and atomic lifecycle persistence."""

import fcntl
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .security import ensure_no_secrets, safe_repo_path

CANONICAL = [
    "SKILL.md",
    "ops/memory/INVARIANTS.md",
    "ops/memory/DECISIONS.md",
    "ops/memory/CURRENT_STATE.md",
    "ops/memory/PHASE_STATUS.yaml",
]


class Loader(yaml.SafeLoader):
    pass


def mapping(loader, node):
    values = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in values:
            raise ValueError("duplicate YAML key")
        values[key] = loader.construct_object(value_node)
    return values


Loader.add_constructor("tag:yaml.org,2002:map", mapping)


def load_yaml(path):
    text = Path(path).read_text()
    ensure_no_secrets(text)
    return yaml.load(text, Loader=Loader)


def now():
    return datetime.now(timezone.utc)


def atomic_text(path, text):
    ensure_no_secrets(text)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def writer_lock(root):
    # One control checkout for all worktrees: lock serializes state and gated writes.
    lock = safe_repo_path(root, "ops/.coordinator.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another coordinator writer owns the lock") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def record_run(task, role, operation, directory=Path("/srv/kemirix/agent-runs")):
    # Metadata only: no prompts, responses, environment, keys or provider bodies.
    record = {
        "task_id": task.task_id,
        "role": role,
        "operation": operation,
        "base_sha": task.base_sha,
        "timestamp": now().isoformat(),
    }
    destination = Path(directory) / f"{task.task_id}-{uuid.uuid4().hex}.json"
    atomic_text(destination, json.dumps(record, indent=2) + "\n")
    return destination
