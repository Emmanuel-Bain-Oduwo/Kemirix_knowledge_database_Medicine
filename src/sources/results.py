"""The typed common acquisition result (no secrets, ever).

Every acquisition — HTTP or operator-provided local file — reports through
this one frozen value object: what record it was for, how many attempts it
took, whether it failed and why (safe class only), and which immutable vault
objects it produced.
"""

from pydantic import BaseModel, ConfigDict, field_validator

from .exceptions import SourceContractError

STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

FAILURE_CLASSES = (
    "deterministic_http",
    "rate_limited",
    "transient_http",
    "timeout",
    "network",
    "retry_exhausted",
    "storage",
    "parse",
    "configuration",
)


class AcquisitionResult(BaseModel):
    """One record/version acquisition outcome against the raw vault."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lane_id: str
    source_id: str
    source_version: str
    source_record_key: str
    status: str
    started_at: str
    finished_at: str
    attempts: int = 1
    retryable: bool = False
    failure_class: str | None = None
    http_status: int | None = None
    artifact_keys: tuple[str, ...] = ()
    manifest_key: str | None = None
    detail: str | None = None

    @field_validator("lane_id")
    @classmethod
    def _lane(cls, value):
        from storage.keys import validate_lane_id

        return validate_lane_id(value)

    @field_validator("source_id")
    @classmethod
    def _source(cls, value):
        from storage.keys import validate_source_slug

        return validate_source_slug(value)

    @field_validator("status")
    @classmethod
    def _status(cls, value):
        if value not in (STATUS_SUCCEEDED, STATUS_FAILED):
            raise SourceContractError(f"unknown acquisition status: {value!r}")
        return value

    @field_validator("failure_class")
    @classmethod
    def _failure(cls, value):
        if value is not None and value not in FAILURE_CLASSES:
            raise SourceContractError(f"unknown failure class: {value!r}")
        return value

    @field_validator("attempts")
    @classmethod
    def _attempts(cls, value):
        if value < 1:
            raise SourceContractError("attempts must be at least 1")
        return value

    @field_validator("source_version", "source_record_key")
    @classmethod
    def _nonempty(cls, value, info):
        if not isinstance(value, str) or not value.strip() or "/" in value:
            raise SourceContractError(f"{info.field_name} must be a safe segment")
        return value
