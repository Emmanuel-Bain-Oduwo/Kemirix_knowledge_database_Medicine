"""Strict, fail-closed task contracts."""

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Agent = Literal["codex", "kimi", "minimax", "glm", "nemotron"]
PRIORITY = ["codex", "glm", "minimax", "kimi"]
STAGES = [
    "created",
    "research",
    "implementation",
    "crosscheck",
    "review",
    "qa",
    "fixes",
    "ci",
    "awaiting_human",
    "merged",
    "deployed",
    "verified",
    "closed",
]
REPORTS = {
    "kimi": "kimi-analysis.md",
    "minimax": "minimax-crosscheck.md",
    "glm": "glm-review.md",
    "nemotron": "nemotron-qa.md",
    "codex": "final-summary.md",
}
PROTECTED = [
    "SKILL.md",
    "ops/memory/INVARIANTS.md",
    ".git",
    ".env",
    "ops/tasks",
    "ops/memory",
    "ops/agents",
    ".github",
]
PHASE_ZERO = ["migrations", "src/kmx", "src/evidence", "src/rules", "src/sources"]
FOUNDATION_PREFIX = "FOUNDATION-"
# The phase 0 foundation bootstrap has to build engineering governance itself, so
# it may own the governance prefixes above; it never owns these baseline paths.
BOOTSTRAP_PROTECTED = ["SKILL.md", "ops/memory/INVARIANTS.md", ".git", ".env"]


def path_value(value):
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise ValueError("repository-relative path required")
    path = PurePosixPath(value)
    if ".." in path.parts or "." == value or any(c in value for c in "*?[]\\\n\r\x00"):
        raise ValueError("unsafe path")
    if path.as_posix() != value.rstrip("/"):
        raise ValueError("noncanonical path")
    return value.rstrip("/")


def inside(path, prefix):
    return path == prefix or path.startswith(prefix + "/")


def branch_parts(branch):
    match = re.fullmatch(
        r"agent/(codex|kimi|minimax|glm|nemotron)/([A-Za-z0-9][A-Za-z0-9_-]{0,79})", branch
    )
    if not match:
        raise ValueError("requires agent/<agent>/<task-id> branch; main refused")
    return match.groups()


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2] = 2
    task_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    phase: str = Field(pattern=r"^phase_[0-9]+[a-f]?$")
    goal: str = Field(min_length=10)
    production_writer: Agent
    researcher: Agent = "kimi"
    cross_checker: Agent = "minimax"
    reviewer: Agent = "glm"
    validator: Agent = "nemotron"
    active_writer: Agent
    writer_priority: list[Agent]
    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = Field(min_length=1)
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    branch: str
    research_required: bool = True
    acceptance_criteria: list[str] = Field(min_length=1)
    required_tests: list[Literal["foundation", "integration", "contract"]] = Field(min_length=1)
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    commit_sha: str | None
    deployed_sha: str | None
    handoffs: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)

    @field_validator("commit_sha", "deployed_sha")
    @classmethod
    def sha(cls, value):
        if value is not None and not re.fullmatch("[0-9a-f]{40}", value):
            raise ValueError("full SHA required")
        return value

    @field_validator("allowed_paths", "forbidden_paths")
    @classmethod
    def paths(cls, values):
        return [path_value(v) for v in values]

    @field_validator("acceptance_criteria", "required_tests")
    @classmethod
    def meaningful(cls, values):
        if any(not v.strip() for v in values):
            raise ValueError("empty task criterion")
        return values

    @model_validator(mode="after")
    def contract(self):
        if (self.researcher, self.cross_checker, self.reviewer, self.validator) != (
            "kimi",
            "minimax",
            "glm",
            "nemotron",
        ):
            raise ValueError(
                "review role reassignment requires a revised human coordination policy"
            )
        if self.status not in STAGES or self.writer_priority != PRIORITY:
            raise ValueError("invalid lifecycle or writer priority")
        if self.active_writer != self.production_writer or self.active_writer not in PRIORITY:
            raise ValueError("one production writer required; Nemotron is QA")
        if branch_parts(self.branch) != (self.active_writer, self.task_id):
            raise ValueError("branch ownership mismatch")
        if self.updated_at < self.created_at:
            raise ValueError("invalid timestamps")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("timezone required")
        for allowed in self.allowed_paths:
            if any(inside(allowed, p) or inside(p, allowed) for p in self.protected_scope()):
                raise ValueError("task cannot own governance or broad repository scope")
            if self.phase.startswith("phase_0") and any(
                inside(allowed, p) or inside(p, allowed) for p in PHASE_ZERO
            ):
                raise ValueError("Phase 0 domain writes forbidden")
        if self.status in ["merged", "deployed", "verified", "closed"] and not self.commit_sha:
            raise ValueError("merged task needs exact commit")
        if self.status in ["deployed", "verified"] and not self.deployed_sha:
            raise ValueError("deployment SHA required")
        if (self.status == "closed") != (self.completed_at is not None):
            raise ValueError("completion timestamp must match closed state")
        return self

    @property
    def foundation_bootstrap(self):
        """True only for the tightly scoped phase 0 foundation bootstrap.

        Requires phase_0 exactly, a FOUNDATION- task ID and the matching
        agent/<writer>/FOUNDATION-* branch (enforced structurally by contract
        validation). Subphases such as phase_0a, later phases, ordinary task IDs
        and mismatched branches keep the full governance restriction.
        """
        return (
            self.phase == "phase_0"
            and self.task_id.startswith(FOUNDATION_PREFIX)
            and self.branch.startswith(f"agent/{self.active_writer}/{FOUNDATION_PREFIX}")
        )

    def protected_scope(self):
        """Paths this task can never own; ordinary tasks keep the full set."""
        return BOOTSTRAP_PROTECTED if self.foundation_bootstrap else PROTECTED

    def allowed_for(self, role):
        if role not in REPORTS:
            raise ValueError("unknown role")
        report = f"ops/reports/{self.task_id}/{REPORTS[role]}"
        if role == self.active_writer and self.status in ["implementation", "fixes"]:
            return [*self.allowed_paths, report]
        return [report]

    def authorize(self, role, path):
        path = path_value(path)
        name = PurePosixPath(path).name
        if name.startswith(".env") or name in ["app.env", "agents.env", ".pgpass"]:
            raise PermissionError("secret environment paths are operator-owned")
        forbidden = [*self.protected_scope(), *self.forbidden_paths]
        if self.phase.startswith("phase_0"):
            forbidden += PHASE_ZERO
        if any(inside(path, p) for p in forbidden):
            raise PermissionError("forbidden task path")
        # Every role report stays independently owned. Only the phase 0
        # foundation bootstrap may own explicitly assigned non-report artifacts,
        # because it must author its own engineering-governance records.
        if (
            inside(path, "ops/reports")
            and path != f"ops/reports/{self.task_id}/{REPORTS.get(role)}"
            and not (
                self.foundation_bootstrap
                and name not in REPORTS.values()
                and any(inside(path, allowed) for allowed in self.allowed_paths)
            )
        ):
            raise PermissionError("report belongs to another role")
        if not any(inside(path, p) for p in self.allowed_for(role)):
            raise PermissionError("writer ownership rejects path")
        return path


class HandoffDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    completed_work: list[str]
    remaining_work: list[str]
    tests_passed: list[str]
    tests_failed: list[str]
    known_issues: list[str]
    files_touched: list[str]
    forbidden_changes: list[str]
    next_action: str = Field(min_length=5)
