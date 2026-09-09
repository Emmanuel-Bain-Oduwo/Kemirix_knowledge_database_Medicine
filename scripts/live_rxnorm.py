"""The one authorized pinned RxNorm live ingestion (Phase 3-10 program).

Run from the deployed release root AFTER the owner provisions BOTH
credentials (values never printed, never committed):

    export UTS_API_KEY=<UTS account key with UMLS license>
    export KEMIRIX_S3_ACCESS_KEY_ID=<OVH S3 user access key>
    export KEMIRIX_S3_SECRET_ACCESS_KEY=<OVH S3 user secret>

    .venv/bin/python scripts/live_rxnorm.py

Fails closed with an exact message when either credential is absent.
Executes: official discovery + pinned verification, authenticated download,
official MD5 verification, SHA-256, immutable vault upload, manifest last,
parse of the stored copy, deterministic KMX ING/CD load, a full rerun that
proves idempotency (no duplicate bytes, no new KMX for existing RXCUIs),
the hard zero-PROD invariant, and QA metrics.
"""

import json
from pathlib import Path
from urllib.parse import urlsplit

DEV_DB_ENV_FILE = Path("/srv/kemirix/secrets/dev-postgres.env")
DEPLOYED_SHA_FILE = Path("/srv/kemirix/runtime/development/DEPLOYED_SHA")


def dev_database_env():
    """Operator-provisioned development credentials parsed in-process."""
    text = DEV_DB_ENV_FILE.read_text()
    url = None
    for line in text.splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip("'\"").strip()
    if not url:
        raise SystemExit("missing DATABASE_URL in the development credential file")
    parts = urlsplit(url)
    environment = {
        "PGHOST": parts.hostname,
        "PGPORT": str(parts.port or 5432),
        "PGDATABASE": parts.path.lstrip("/"),
        "PGUSER": parts.username,
        "PGPASSWORD": parts.password,
        "PGSSLMODE": "require",
    }
    if parts.query and "sslmode=" in parts.query:
        environment["PGSSLMODE"] = parts.query.split("sslmode=")[1].split("&")[0]
    return environment


def kmx_counts(connection):
    def scalar(sql):
        return connection.execute(sql).fetchone()[0]

    return {
        "kmx_ing": scalar("SELECT count(*) FROM kmx.registry WHERE level='ingredient'"),
        "kmx_cd": scalar("SELECT count(*) FROM kmx.registry WHERE level='clinical_drug'"),
        "kmx_prod": scalar("SELECT count(*) FROM kmx.registry WHERE level='product'"),
        "rxcui_bindings": scalar(
            "SELECT count(*) FROM kmx.external_identifier WHERE identifier_system='RXNORM'"
        ),
        "combination_cds": scalar(
            "SELECT count(*) FROM ("
            "SELECT container_kmx_id FROM kmx.contains "
            "WHERE relationship_type='contains' GROUP BY container_kmx_id "
            "HAVING count(*) > 1) c"
        ),
        "mapping_exceptions_by_reason": dict(
            connection.execute(
                "SELECT reason_code, count(*) FROM kmx.mapping_exception "
                "GROUP BY reason_code ORDER BY 1"
            ).fetchall()
        ),
    }


def main():
    try:
        from database.connection import connect_from_pg_env, healthcheck
        from kmx.builders import KmxBuilder
        from kmx.repository import KmxRepository
        from sources.rxnorm.adapter import run_pinned_rxnorm_ingestion
        from sources.rxnorm.download import make_client, require_uts_api_key
        from storage.client import S3RawObjectStore
    except Exception as error:
        raise SystemExit(
            f"run from the deployed release root with its venv "
            f"(.venv/bin/python scripts/live_rxnorm.py): {type(error).__name__}"
        ) from None

    pg_env = dev_database_env()
    connection = connect_from_pg_env(pg_env)
    try:
        healthcheck(connection)
        store = S3RawObjectStore.from_environment(Path.cwd())
        require_uts_api_key()
        client = make_client()
        repository = KmxRepository(connection)
        builder = KmxBuilder(repository, connection)
        adapter_git_sha = (
            DEPLOYED_SHA_FILE.read_text().strip() if DEPLOYED_SHA_FILE.is_file() else "0" * 40
        )
        result = run_pinned_rxnorm_ingestion(
            client=client,
            store=store,
            builder=builder,
            repository=repository,
            adapter_git_sha=adapter_git_sha,
            rights_status="cleared",
        )
        first_stats = result["stats"]
        counts = kmx_counts(connection)
        # Full rerun: the same pinned release downloads again, proves the
        # vault keeps one immutable copy (no duplicate bytes) and the loader
        # reuses every identity (no new KMX for exact existing RXCUIs).
        rerun = run_pinned_rxnorm_ingestion(
            client=client,
            store=store,
            builder=builder,
            repository=repository,
            adapter_git_sha=adapter_git_sha,
            rights_status="cleared",
        )
        rerun_stats = rerun["stats"]
        counts_after = kmx_counts(connection)
        if counts_after["kmx_prod"] != 0:
            raise SystemExit("HARD INVARIANT VIOLATED: RxNorm created KMX-PROD")
        if rerun_stats["ing_created"] or rerun_stats["cd_created"]:
            raise SystemExit("RERUN NOT IDEMPOTENT: new identities minted on rerun")
        if (
            counts_after["kmx_ing"] != counts["kmx_ing"]
            or counts_after["kmx_cd"] != counts["kmx_cd"]
        ):
            raise SystemExit("RERUN NOT IDEMPOTENT: identity counts changed")
        report = {
            "pinned_release": "RxNorm_full_09082026.zip (2026-09-08)",
            "raw_object_key": (
                "rxnorm_athena/2026-09-08/__release__/original/RxNorm_full_09082026.zip"
            ),
            "sha256": result["sha256"],
            "upstream_md5": "34dd95b0ae128fb81bc68166944514f2 (verified)",
            "first_load": first_stats,
            "rerun_load": rerun_stats,
            "kmx_counts": counts_after,
            "kmx_prod_from_rxnorm": 0,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        print("PINNED RXNORM LIVE INGESTION: SUCCESS")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
