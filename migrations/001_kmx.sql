-- KMX identity schema (KMX-SCHEMA-001, phase_1).
-- Frozen scope: owner-approved blueprints 2026-09-08 (execution book sections
-- 6.1-6.5 and SKILL NEW(3) sections 2/2A/11) and config/database.yaml.
-- Exactly five tables: registry, contains, external_identifier, name_index,
-- mapping_exception. No data loading, no evidence/rules DDL.
-- Executed by the CI migration-from-zero gate on a clean PostgreSQL 17 database.
-- lane_id (S01-S27) is the permanent architecture lane. source_id is a stable
-- implementation slug (for example dailymed). They are deliberately separate.
-- External-identifier conflicts stay recordable: the database does not hide
-- them behind a global unique binding, and the application fails them closed
-- into kmx.mapping_exception for human review.

CREATE SCHEMA kmx;

COMMENT ON SCHEMA kmx IS 'Kemirix medication identity: KMX-ING/KMX-CD/KMX-PROD and crosswalks';

CREATE TABLE kmx.registry (
    kmx_id          text        NOT NULL,
    level           text        NOT NULL,
    preferred_name  text        NOT NULL,
    normalized_name text        NOT NULL,
    status          text        NOT NULL DEFAULT 'active',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT registry_pkey PRIMARY KEY (kmx_id),
    CONSTRAINT registry_kmx_id_format
        CHECK (kmx_id ~ '^KMX-(ING|CD|PROD)-[0-9]{6}$'),
    CONSTRAINT registry_level CHECK (
        level IN ('ingredient', 'clinical_drug', 'product')
    ),
    CONSTRAINT registry_prefix_matches_level CHECK (
        (level = 'ingredient' AND kmx_id LIKE 'KMX-ING-%')
        OR (level = 'clinical_drug' AND kmx_id LIKE 'KMX-CD-%')
        OR (level = 'product' AND kmx_id LIKE 'KMX-PROD-%')
    ),
    CONSTRAINT registry_status CHECK (status IN ('active', 'retired')),
    CONSTRAINT registry_preferred_name_not_blank
        CHECK (length(btrim(preferred_name)) > 0),
    CONSTRAINT registry_normalized_name_not_blank
        CHECK (length(btrim(normalized_name)) > 0)
);

COMMENT ON TABLE kmx.registry IS
    'Stable Kemirix identity registry: ingredient (KMX-ING-######), clinical drug (KMX-CD-######), product (KMX-PROD-######). Source refreshes never renumber established identity.';

CREATE TABLE kmx.contains (
    container_kmx_id  text     NOT NULL,
    member_kmx_id     text     NOT NULL,
    relationship_type text    NOT NULL,
    ordinal           integer,
    CONSTRAINT contains_pkey
        PRIMARY KEY (container_kmx_id, member_kmx_id, relationship_type),
    CONSTRAINT contains_container_fkey
        FOREIGN KEY (container_kmx_id) REFERENCES kmx.registry (kmx_id),
    CONSTRAINT contains_member_fkey
        FOREIGN KEY (member_kmx_id) REFERENCES kmx.registry (kmx_id),
    CONSTRAINT contains_not_self CHECK (container_kmx_id <> member_kmx_id),
    CONSTRAINT contains_relationship_type_not_blank
        CHECK (length(btrim(relationship_type)) > 0)
);

CREATE INDEX contains_member_idx ON kmx.contains (member_kmx_id);

COMMENT ON TABLE kmx.contains IS
    'Identity containment: a combination clinical drug contains ingredient members, and a product contains a clinical drug. container/member naming avoids the ambiguous parent/child wording. Application validation enforces legal combinations.';

CREATE TABLE kmx.external_identifier (
    external_identifier_id bigint      GENERATED ALWAYS AS IDENTITY,
    kmx_id                 text        NOT NULL,
    identifier_system      text        NOT NULL,
    identifier_value       text        NOT NULL,
    source_id              text        NOT NULL,
    jurisdiction           text,
    active                 boolean     NOT NULL DEFAULT true,
    created_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT external_identifier_pkey PRIMARY KEY (external_identifier_id),
    CONSTRAINT external_identifier_binding
        UNIQUE (kmx_id, identifier_system, identifier_value),
    CONSTRAINT external_identifier_kmx_fkey
        FOREIGN KEY (kmx_id) REFERENCES kmx.registry (kmx_id),
    CONSTRAINT external_identifier_source CHECK (
        source_id ~ '^[a-z][a-z0-9_]*$'
    ),
    CONSTRAINT external_identifier_system_not_blank
        CHECK (length(btrim(identifier_system)) > 0),
    CONSTRAINT external_identifier_value_not_blank
        CHECK (length(btrim(identifier_value)) > 0)
);

CREATE INDEX external_identifier_kmx_idx ON kmx.external_identifier (kmx_id);

COMMENT ON TABLE kmx.external_identifier IS
    'Deterministic crosswalks from external identifier systems to exactly one KMX per source assertion. Disagreeing bindings are deliberately recordable (no global source+value unique constraint) so identifier conflicts fail closed into kmx.mapping_exception instead of being hidden by the database. Duplicate projections of the same upstream identity are not independent votes.';

CREATE TABLE kmx.name_index (
    name_index_id    bigint      GENERATED ALWAYS AS IDENTITY,
    kmx_id           text        NOT NULL,
    normalized_name  text        NOT NULL,
    name_type        text        NOT NULL,
    language         text        NOT NULL DEFAULT 'en',
    source_id        text        NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT name_index_pkey PRIMARY KEY (name_index_id),
    CONSTRAINT name_index_kmx_fkey FOREIGN KEY (kmx_id) REFERENCES kmx.registry (kmx_id),
    CONSTRAINT name_index_source CHECK (
        source_id ~ '^[a-z][a-z0-9_]*$'
    ),
    CONSTRAINT name_index_normalized_name_not_blank
        CHECK (length(btrim(normalized_name)) > 0),
    CONSTRAINT name_index_name_type_not_blank
        CHECK (length(btrim(name_type)) > 0)
);

CREATE INDEX name_index_normalized_name_idx ON kmx.name_index (normalized_name);

COMMENT ON TABLE kmx.name_index IS
    'Name lookup aid for deterministic resolution only. Names never mint identity and may legitimately map to several KMX rows. Resolution decisions and ambiguity live in the resolver and kmx.mapping_exception.';

CREATE TABLE kmx.mapping_exception (
    exception_id       bigint      GENERATED ALWAYS AS IDENTITY,
    lane_id            text        NOT NULL,
    source_id          text        NOT NULL,
    source_version_key text,
    source_record_key  text        NOT NULL,
    reason_code        text        NOT NULL,
    normalized_input   jsonb       NOT NULL,
    candidate_kmx_ids  jsonb       NOT NULL DEFAULT '[]'::jsonb,
    status             text        NOT NULL DEFAULT 'open',
    created_at         timestamptz NOT NULL DEFAULT now(),
    reviewed_at        timestamptz,
    reviewed_by        text,
    CONSTRAINT mapping_exception_pkey PRIMARY KEY (exception_id),
    CONSTRAINT mapping_exception_lane CHECK (
        lane_id ~ '^S(0[1-9]|1[0-9]|2[0-7])$'
    ),
    CONSTRAINT mapping_exception_source CHECK (
        source_id ~ '^[a-z][a-z0-9_]*$'
    ),
    CONSTRAINT mapping_exception_reason CHECK (
        reason_code IN (
            'NO_MATCH',
            'MULTIPLE_MATCHES',
            'IDENTIFIER_CONFLICT',
            'FORMULATION_AMBIGUITY',
            'PRODUCT_IDENTITY_UNPROVEN'
        )
    ),
    CONSTRAINT mapping_exception_status CHECK (
        status IN ('open', 'resolved', 'dismissed')
    ),
    CONSTRAINT mapping_exception_record_key_not_blank
        CHECK (length(btrim(source_record_key)) > 0),
    CONSTRAINT mapping_exception_review_provenance CHECK (
        status <> 'resolved'
        OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)
    )
);

COMMENT ON TABLE kmx.mapping_exception IS
    'Every source item resolves deterministically to KMX or is preserved here with full provenance: lane, source, source version, source record, reason code, normalized input, candidate KMX IDs and review state. Never guess on zero, multiple or conflicting matches because ambiguous identity requires human review. Plain provenance columns only: no cross-schema dependency on future Evidence tables.';
