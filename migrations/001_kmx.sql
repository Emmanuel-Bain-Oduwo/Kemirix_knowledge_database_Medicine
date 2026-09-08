-- KMX identity schema (KMX-SCHEMA-001, phase_1).
-- Frozen scope: SKILL.md sections 2/2A/11 and config/database.yaml.
-- Exactly five tables: registry, contains, external_identifier, name_index,
-- mapping_exception. No data loading, no evidence/rules DDL.
-- Executed by the CI migration-from-zero gate on a clean PostgreSQL 17 database.

CREATE SCHEMA kmx;

COMMENT ON SCHEMA kmx IS 'Kemirix medication identity: KMX-ING/KMX-CD/KMX-PROD and crosswalks';

CREATE TABLE kmx.registry (
    kmx_id         text        NOT NULL,
    level          text        NOT NULL,
    preferred_name text        NOT NULL,
    status         text        NOT NULL DEFAULT 'active',
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT registry_pkey PRIMARY KEY (kmx_id),
    CONSTRAINT registry_id_level_key UNIQUE (kmx_id, level),
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
    CONSTRAINT registry_name_not_blank CHECK (length(btrim(preferred_name)) > 0)
);

COMMENT ON TABLE kmx.registry IS
    'Stable Kemirix identity registry: ingredient (KMX-ING-######), clinical drug (KMX-CD-######), product (KMX-PROD-######). Source refreshes never renumber established identity.';

CREATE TABLE kmx.contains (
    parent_kmx_id text NOT NULL,
    parent_level  text NOT NULL,
    child_kmx_id  text NOT NULL,
    child_level   text NOT NULL,
    CONSTRAINT contains_pkey PRIMARY KEY (parent_kmx_id, child_kmx_id),
    CONSTRAINT contains_parent_fkey
        FOREIGN KEY (parent_kmx_id, parent_level)
        REFERENCES kmx.registry (kmx_id, level),
    CONSTRAINT contains_child_fkey
        FOREIGN KEY (child_kmx_id, child_level)
        REFERENCES kmx.registry (kmx_id, level),
    CONSTRAINT contains_level_order CHECK (
        (parent_level = 'ingredient' AND child_level = 'clinical_drug')
        OR (parent_level = 'clinical_drug' AND child_level = 'product')
    )
);

CREATE INDEX contains_child_idx ON kmx.contains (child_kmx_id);

COMMENT ON TABLE kmx.contains IS
    'Identity containment: KMX-ING -> KMX-CD and KMX-CD -> KMX-PROD. A combination clinical drug has multiple ingredient parents. Level ordering makes cycles structurally impossible.';

CREATE TABLE kmx.external_identifier (
    external_identifier_id bigint      GENERATED ALWAYS AS IDENTITY,
    source_id               text        NOT NULL,
    external_id_type        text        NOT NULL,
    external_id             text        NOT NULL,
    kmx_id                  text        NOT NULL,
    is_active               boolean     NOT NULL DEFAULT true,
    created_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT external_identifier_pkey PRIMARY KEY (external_identifier_id),
    CONSTRAINT external_identifier_binding
        UNIQUE (source_id, external_id_type, external_id),
    CONSTRAINT external_identifier_kmx_fkey
        FOREIGN KEY (kmx_id) REFERENCES kmx.registry (kmx_id),
    CONSTRAINT external_identifier_source CHECK (
        source_id ~ '^S(0[1-9]|1[0-9]|2[0-7])$'
    ),
    CONSTRAINT external_identifier_not_blank
        CHECK (length(btrim(external_id)) > 0),
    CONSTRAINT external_identifier_type_not_blank
        CHECK (length(btrim(external_id_type)) > 0)
);

CREATE INDEX external_identifier_kmx_idx ON kmx.external_identifier (kmx_id);

COMMENT ON TABLE kmx.external_identifier IS
    'Deterministic crosswalks: one active external identifier of a source binds to exactly one KMX. Duplicate projections of the same upstream identity are not independent votes and ambiguity goes to kmx.mapping_exception.';

CREATE TABLE kmx.name_index (
    name      text NOT NULL,
    name_type text NOT NULL,
    kmx_id    text NOT NULL,
    CONSTRAINT name_index_pkey PRIMARY KEY (name, name_type, kmx_id),
    CONSTRAINT name_index_kmx_fkey FOREIGN KEY (kmx_id) REFERENCES kmx.registry (kmx_id),
    CONSTRAINT name_index_type CHECK (name_type IN ('preferred', 'synonym')),
    CONSTRAINT name_index_not_blank CHECK (length(btrim(name)) > 0)
);

COMMENT ON TABLE kmx.name_index IS
    'Name lookup aid for deterministic resolution only. Names never mint identity and may legitimately map to several KMX rows. Resolution decisions and ambiguity live in the resolver and kmx.mapping_exception.';

CREATE TABLE kmx.mapping_exception (
    mapping_exception_id bigint      GENERATED ALWAYS AS IDENTITY,
    source_id            text,
    external_id_type     text,
    external_id          text,
    name_text            text,
    reason               text        NOT NULL,
    detail               jsonb       NOT NULL,
    status               text        NOT NULL DEFAULT 'open',
    resolution_kmx_id    text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    resolved_at          timestamptz,
    CONSTRAINT mapping_exception_pkey PRIMARY KEY (mapping_exception_id),
    CONSTRAINT mapping_exception_resolution_fkey
        FOREIGN KEY (resolution_kmx_id) REFERENCES kmx.registry (kmx_id),
    CONSTRAINT mapping_exception_source CHECK (
        source_id IS NULL OR source_id ~ '^S(0[1-9]|1[0-9]|2[0-7])$'
    ),
    CONSTRAINT mapping_exception_reason CHECK (
        reason IN ('zero_match', 'multiple_match', 'conflict')
    ),
    CONSTRAINT mapping_exception_status CHECK (
        status IN ('open', 'under_review', 'resolved')
    ),
    CONSTRAINT mapping_exception_context CHECK (
        source_id IS NOT NULL
        OR external_id IS NOT NULL
        OR length(btrim(coalesce(name_text, ''))) > 0
    ),
    CONSTRAINT mapping_exception_resolution_state CHECK (
        (status = 'resolved') = (resolved_at IS NOT NULL)
    )
);

COMMENT ON TABLE kmx.mapping_exception IS
    'Every source item resolves deterministically to KMX or is preserved here with its conflict evidence. Never guess on zero, multiple or conflicting matches because ambiguous identity requires human review.';
