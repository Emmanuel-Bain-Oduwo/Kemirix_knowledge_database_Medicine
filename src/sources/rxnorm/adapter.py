"""The S01 RxNorm adapter: the full pinned release flow.

    discovery -> pinned verification -> authenticated download to temp
    -> flush/close -> official MD5 verification -> SHA-256
    -> immutable vault upload -> manifest LAST -> parse the stored copy
    -> deterministic KMX ING/CD load (zero PROD)

The live execution runs this against the real UTS endpoint, the real vault
and the real database; everything is testable offline through the shared
fakes for the HTTP client, the vault store and the repository/builder stack.
"""

import tempfile
from pathlib import Path

from ..acquisition import parse_stored_original
from ..exceptions import SourceContractError
from .download import (
    download_pinned_release,
    fetch_current_release,
    require_uts_api_key,
    verify_official_md5,
)
from .loader import RxNormKmxLoader
from .release import (
    PINNED_FILENAME,
    PINNED_RELEASE_VERSION,
    pinned_release_metadata,
)


def run_pinned_rxnorm_ingestion(
    *,
    client,
    store,
    builder,
    repository,
    adapter_git_sha,
    rights_status="pending_review",
    env=None,
):
    """Execute the one authorized pinned RxNorm ingestion end-to-end."""
    metadata = pinned_release_metadata()
    # 1-2. Official discovery and pinned verification BEFORE any download.
    fetch_current_release(client)
    # 3-5. Authenticated streamed download to a closed temp file, then the
    # official MD5 check.
    api_key = require_uts_api_key(env=env)
    with tempfile.NamedTemporaryFile(prefix="kemirix-rxnorm-") as temp:
        download_pinned_release(client, api_key, temp)
        temp.flush()
        verify_official_md5(temp.name)
        # 6-8. Immutable vault upload of the verified original.
        from storage.checksum import sha256_file

        sha256 = sha256_file(Path(temp.name))
        put = store.put_immutable(
            source_path=Path(temp.name),
            object_key=metadata["object_key"],
            expected_sha256=sha256,
        )
        # 9-10. Manifest LAST through the frozen hardened model.
        from storage.manifest import Manifest

        manifest = Manifest.model_validate(
            {
                "schema_version": 1,
                "lane_id": "S01",
                "source_id": "rxnorm_athena",
                "source_version": PINNED_RELEASE_VERSION,
                "source_record_key": "__release__",
                "acquisition_mode": "bulk",
                "fetched_at": _now(),
                "upstream_published_at": PINNED_RELEASE_VERSION,
                "adapter_git_sha": adapter_git_sha,
                "rights_status": rights_status,
                "parse_status": "staged",
                "artifacts": [
                    {
                        "artifact_type": "bulk_release_archive",
                        "original_filename": PINNED_FILENAME,
                        "content_type": "application/zip",
                        "byte_size": Path(temp.name).stat().st_size,
                        "object_key": metadata["object_key"],
                        "sha256": sha256,
                    }
                ],
            }
        )
        store.write_manifest(manifest)
    # Parser reads the STORED original, never the network bytes.
    loader = RxNormKmxLoader(builder, repository)
    stats = {}

    def parser(destination):
        stats.update(loader.load(Path(destination.name)))

    with tempfile.NamedTemporaryFile(prefix="kemirix-rxnorm-parse-") as parse_temp:
        parse_result = parse_stored_original(
            store=store,
            identity={
                "lane_id": "S01",
                "source_id": "rxnorm_athena",
                "source_version": PINNED_RELEASE_VERSION,
                "source_record_key": "__release__",
            },
            object_key=metadata["object_key"],
            destination=parse_temp,
            parser=parser,
        )
    if parse_result.status != "succeeded":
        raise SourceContractError(f"pinned RxNorm parse failed: {parse_result.failure_class}")
    return {"put": put.status, "sha256": sha256, "manifest": manifest, "stats": stats}


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
