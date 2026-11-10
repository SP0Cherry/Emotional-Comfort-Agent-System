-- Proposed initial schema for the implementation plan, not a finished backend.
-- PostgreSQL 17 + pgvector. Run against a NEW development database only.
-- Production uses Alembic migrations and a non-superuser application role.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_ciphertext bytea,
    phone_lookup_hash text UNIQUE,
    nickname text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled','deleting')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE refresh_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    device_label text NOT NULL DEFAULT '',
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE otp_challenges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_lookup_hash text NOT NULL,
    code_hmac text NOT NULL,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    invalidated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rate_limit_counters (
    scope text NOT NULL,
    subject_hash text NOT NULL,
    bucket_start timestamptz NOT NULL,
    count integer NOT NULL DEFAULT 0 CHECK (count >= 0),
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (scope, subject_hash, bucket_start)
);

CREATE TABLE assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    object_key text NOT NULL UNIQUE,
    purpose text NOT NULL CHECK (purpose IN ('avatar','asr_input','tts_output')),
    mime_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ready','deleting','deleted')),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, owner_id)
);

CREATE TABLE personas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    avatar_asset_id uuid,
    display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 40),
    relationship_reference text NOT NULL DEFAULT '',
    style_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(style_json) = 'object'),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','resetting','deleting')),
    style_version integer NOT NULL DEFAULT 1 CHECK (style_version > 0),
    context_version bigint NOT NULL DEFAULT 1 CHECK (context_version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, owner_id),
    FOREIGN KEY (avatar_asset_id, owner_id) REFERENCES assets(id, owner_id)
);

CREATE TABLE persona_examples (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL,
    persona_id uuid NOT NULL,
    sample_text text NOT NULL CHECK (char_length(sample_text) BETWEEN 1 AND 500),
    approved boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (persona_id, owner_id) REFERENCES personas(id, owner_id) ON DELETE CASCADE
);

CREATE TABLE conversations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL,
    persona_id uuid NOT NULL,
    title text NOT NULL DEFAULT '',
    mode text NOT NULL DEFAULT 'chat' CHECK (mode IN ('chat','preview')),
    next_message_seq bigint NOT NULL DEFAULT 1 CHECK (next_message_seq > 0),
    summary text NOT NULL DEFAULT '',
    summary_until_seq bigint NOT NULL DEFAULT 0,
    summary_context_version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, owner_id, persona_id),
    FOREIGN KEY (persona_id, owner_id) REFERENCES personas(id, owner_id) ON DELETE CASCADE
);

CREATE TABLE messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL,
    persona_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    seq bigint NOT NULL CHECK (seq > 0),
    role text NOT NULL CHECK (role IN ('user','assistant')),
    content text NOT NULL DEFAULT '',
    status text NOT NULL CHECK (status IN ('pending','completed','failed','cancelled','interrupted','redacted')),
    memory_blocked boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, seq),
    UNIQUE (id, owner_id, persona_id),
    UNIQUE (id, conversation_id, owner_id, persona_id),
    FOREIGN KEY (conversation_id, owner_id, persona_id)
        REFERENCES conversations(id, owner_id, persona_id) ON DELETE CASCADE
);

CREATE TABLE chat_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL,
    persona_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    client_message_id uuid NOT NULL,
    request_hash text NOT NULL CHECK (length(request_hash) = 64),
    user_message_id uuid NOT NULL,
    assistant_message_id uuid NOT NULL,
    retry_of_run_id uuid,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','preparing','generating','reviewing','completed','failed','cancelled','interrupted')),
    context_version bigint NOT NULL,
    next_event_seq bigint NOT NULL DEFAULT 1,
    cancel_requested_at timestamptz,
    config_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    usage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_code text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, client_message_id),
    UNIQUE (id, owner_id),
    UNIQUE (assistant_message_id),
    CHECK (user_message_id <> assistant_message_id),
    FOREIGN KEY (conversation_id, owner_id, persona_id)
        REFERENCES conversations(id, owner_id, persona_id) ON DELETE CASCADE,
    FOREIGN KEY (user_message_id, conversation_id, owner_id, persona_id)
        REFERENCES messages(id, conversation_id, owner_id, persona_id),
    FOREIGN KEY (assistant_message_id, conversation_id, owner_id, persona_id)
        REFERENCES messages(id, conversation_id, owner_id, persona_id),
    FOREIGN KEY (retry_of_run_id, owner_id) REFERENCES chat_runs(id, owner_id)
);

CREATE UNIQUE INDEX uq_one_active_run_per_conversation ON chat_runs(conversation_id)
    WHERE status IN ('queued','preparing','generating','reviewing');

CREATE TABLE run_events (
    run_id uuid NOT NULL REFERENCES chat_runs(id) ON DELETE CASCADE,
    seq bigint NOT NULL CHECK (seq > 0),
    event_type text NOT NULL CHECK (event_type IN ('status','message.completed','run.failed','run.cancelled','run.interrupted')),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE memories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL,
    persona_id uuid NOT NULL,
    content text NOT NULL CHECK (char_length(content) BETWEEN 1 AND 500),
    category text NOT NULL CHECK (category IN ('preference','life_event','family_memory')),
    status text NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate','indexing','active','rejected','superseded')),
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    embedding vector(1024),
    embedding_model text,
    embedding_revision integer,
    valid_until timestamptz,
    confirmed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, owner_id, persona_id),
    FOREIGN KEY (persona_id, owner_id) REFERENCES personas(id, owner_id) ON DELETE CASCADE,
    CHECK (status <> 'active' OR (
        embedding IS NOT NULL AND embedding_model IS NOT NULL
        AND embedding_revision IS NOT NULL AND embedding_revision = revision
        AND confirmed_at IS NOT NULL
    ))
);

CREATE TABLE memory_sources (
    memory_id uuid NOT NULL,
    message_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    persona_id uuid NOT NULL,
    PRIMARY KEY (memory_id, message_id),
    FOREIGN KEY (memory_id, owner_id, persona_id)
        REFERENCES memories(id, owner_id, persona_id) ON DELETE CASCADE,
    FOREIGN KEY (message_id, owner_id, persona_id)
        REFERENCES messages(id, owner_id, persona_id)
);

CREATE TABLE jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('generate_reply','extract_memory','embed_memory','summarize','purge_data','send_alert')),
    target_id uuid NOT NULL,
    target_version bigint NOT NULL DEFAULT 1,
    dedup_key text NOT NULL UNIQUE,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','leased','completed','failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 1 CHECK (max_attempts > 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    lease_token uuid,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (kind <> 'generate_reply' OR max_attempts = 1),
    CHECK (state <> 'leased' OR (lease_until IS NOT NULL AND lease_token IS NOT NULL))
);

CREATE TABLE consents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    persona_id uuid,
    scope text NOT NULL,
    document_version text NOT NULL,
    evidence_ref text,
    accepted_at timestamptz NOT NULL DEFAULT now(),
    withdrawn_at timestamptz,
    FOREIGN KEY (persona_id, owner_id) REFERENCES personas(id, owner_id) ON DELETE SET NULL (persona_id)
);

CREATE TABLE emergency_contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label text NOT NULL,
    contact_ciphertext bytea NOT NULL,
    verified_at timestamptz,
    enabled boolean NOT NULL DEFAULT true,
    UNIQUE (id, owner_id)
);

CREATE TABLE safety_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    run_id uuid,
    risk_type text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('review','urgent')),
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','acknowledged','closed')),
    policy_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    UNIQUE (id, owner_id),
    FOREIGN KEY (run_id, owner_id) REFERENCES chat_runs(id, owner_id) ON DELETE SET NULL (run_id)
);

CREATE TABLE alert_deliveries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    safety_event_id uuid NOT NULL,
    contact_id uuid,
    owner_id uuid NOT NULL,
    channel text NOT NULL CHECK (channel IN ('sms','operator')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','delivered','failed','acknowledged')),
    provider_message_id text,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_attempt_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (safety_event_id, contact_id, channel),
    FOREIGN KEY (safety_event_id, owner_id) REFERENCES safety_events(id, owner_id) ON DELETE CASCADE,
    FOREIGN KEY (contact_id, owner_id) REFERENCES emergency_contacts(id, owner_id) ON DELETE SET NULL (contact_id)
);

CREATE INDEX ix_assets_owner ON assets(owner_id, created_at DESC);
CREATE INDEX ix_otp_phone ON otp_challenges(phone_lookup_hash, created_at DESC);
CREATE INDEX ix_rate_limit_expiry ON rate_limit_counters(expires_at);
CREATE INDEX ix_personas_owner ON personas(owner_id, created_at DESC);
CREATE INDEX ix_conversations_owner ON conversations(owner_id, updated_at DESC);
CREATE INDEX ix_memories_scope ON memories(owner_id, persona_id, status);
CREATE INDEX ix_memory_sources_message ON memory_sources(message_id);
CREATE INDEX ix_jobs_ready ON jobs(available_at, created_at) WHERE state = 'queued';
CREATE INDEX ix_jobs_lease ON jobs(lease_until) WHERE state = 'leased';
CREATE INDEX ix_runs_owner ON chat_runs(owner_id, created_at DESC);
CREATE INDEX ix_safety_open ON safety_events(created_at) WHERE status = 'open';

-- Deliberately no global HNSW index: initially use scope-filtered exact search.
-- Cross-owner composite foreign keys supplement, but do not replace, endpoint authorization.
-- Application validates message roles, image readiness, JSON shape and job target ownership.
