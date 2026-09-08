"""The frozen manifest value object.

Manifests never contain credentials, bearer tokens, passwords or presigned
URLs: the model rejects unknown fields outright.
"""

import re

from pydantic import BaseModel, ConfigDict, field_validator

from kmx.exceptions import ConfigurationError

from .keys import validate_lane_id, validate_source_slug
from .models import AcquisitionMode, ParseStatus, RightsStatus

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ADAPTER_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class ManifestArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_type: str
    original_filename: str
    content_type: str
    byte_size: int
    object_key: str
    sha256: str

    @field_validator("byte_size")
    @classmethod
    def _size(cls, value):
        if value < 0:
            raise ConfigurationError("byte_size cannot be negative")
        return value

    @field_validator("sha256")
    @classmethod
    def _sha(cls, value):
        if not _SHA256.fullmatch(value):
            raise ConfigurationError("artifact sha256 must be 64 lowercase hex characters")
        return value

    @field_validator("artifact_type", "original_filename", "content_type", "object_key")
    @classmethod
    def _nonempty(cls, value, info):
        if not value.strip():
            raise ConfigurationError(f"{info.field_name} must not be blank")
        return value


class Manifest(BaseModel):
    """A raw-vault record manifest; upload it only after every artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    lane_id: str
    source_id: str
    source_version: str
    source_record_key: str
    acquisition_mode: str
    fetched_at: str
    upstream_published_at: str | None
    adapter_git_sha: str
    rights_status: str
    parse_status: str
    artifacts: list[ManifestArtifact]

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value):
        if value != 1:
            raise ConfigurationError("manifest schema_version must be 1")
        return value

    @field_validator("lane_id")
    @classmethod
    def _lane(cls, value):
        return validate_lane_id(value)

    @field_validator("source_id")
    @classmethod
    def _source(cls, value):
        return validate_source_slug(value)

    @field_validator("acquisition_mode")
    @classmethod
    def _acquisition(cls, value):
        return AcquisitionMode.parse(value)

    @field_validator("rights_status")
    @classmethod
    def _rights(cls, value):
        return RightsStatus.parse(value)

    @field_validator("parse_status")
    @classmethod
    def _parse(cls, value):
        return ParseStatus.parse(value)

    @field_validator("adapter_git_sha")
    @classmethod
    def _git_sha(cls, value):
        if not _ADAPTER_GIT_SHA.fullmatch(value):
            raise ConfigurationError("adapter_git_sha must be 40 lowercase hex characters")
        return value

    @field_validator("artifacts")
    @classmethod
    def _artifacts(cls, value):
        if not value:
            raise ConfigurationError("a manifest describes at least one artifact")
        for artifact in value:
            validate_source_slug(artifact.object_key.split("/")[0])
        return value
