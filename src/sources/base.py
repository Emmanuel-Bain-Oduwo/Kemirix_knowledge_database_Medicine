"""The frozen SourceAdapter concept (owner directive 2026-09-09, Phase 4).

Every one of the 27 lane adapters will implement exactly this shape. In
Phase 4 the acquisition half is real through the shared HTTP client and the
raw vault: acquire, save_original and verify_hash work, and iter_source_items
reads STORED originals. The identity and Evidence halves (resolve_kmx,
create_source_blocks, build_full_evidence) are explicit not-implemented
boundaries until their phases — no adapter may contain Rule logic.
"""

import abc

from storage.checksum import sha256_file
from storage.exceptions import StorageContractError

from .config import SourceConfig
from .exceptions import SourceContractError


class SourceAdapter(abc.ABC):
    """One source lane adapter built on the shared acquisition framework."""

    def __init__(self, config, *, http_client=None, store=None):
        if not isinstance(config, SourceConfig):
            raise SourceContractError("an adapter wraps a validated SourceConfig")
        self.config = config
        self.http_client = http_client
        self.store = store

    # --- acquisition half: real in Phase 4 via the shared framework ---

    def acquire(self):
        """Acquire this lane's records into the immutable raw vault.

        Subclasses implement lane-specific discovery (release indexes,
        record listings) on top of sources.http and sources.acquisition; they
        must never parse network bytes directly.
        """
        raise NotImplementedError("lane adapters implement acquire")

    def save_original(
        self,
        *,
        source_path,
        source_version,
        source_record_key,
        original_filename,
        expected_sha256,
        adapter_git_sha,
    ):
        """Persist one original into the immutable vault (no overwrite)."""
        if self.store is None:
            raise SourceContractError("adapter has no raw vault store")
        from storage.keys import build_object_key

        object_key = build_object_key(
            self.config.source_id,
            source_version,
            source_record_key,
            original_filename,
        )
        return self.store.put_immutable(
            source_path=source_path,
            object_key=object_key,
            expected_sha256=expected_sha256,
        )

    def verify_hash(self, source_path, expected_sha256):
        """Streaming SHA-256 verification of a closed local file."""
        actual = sha256_file(source_path)
        if actual != expected_sha256:
            raise StorageContractError(
                f"artifact hash mismatch: expected {expected_sha256}, got {actual}"
            )
        return actual

    def iter_source_items(self):
        """Iterate parsed source items read from STORED vault originals.

        Subclasses download stored originals (parse_stored_original /
        store.download_to) and parse the stored copy; never transient
        network bytes.
        """
        raise NotImplementedError("lane adapters implement iter_source_items")

    # --- identity and Evidence halves: frozen phase boundaries ---

    def resolve_kmx(self, item):
        raise NotImplementedError("KMX resolution is not part of the Phase 4 ingestion framework")

    def create_source_blocks(self, item):
        raise NotImplementedError("source blocks are not part of the Phase 4 ingestion framework")

    def build_full_evidence(self, item):
        raise NotImplementedError(
            "Evidence creation is not part of the Phase 4 ingestion framework"
        )

    def validate(self):
        """Structural validation of the adapter's configuration contract."""
        return self.config.model_dump()
