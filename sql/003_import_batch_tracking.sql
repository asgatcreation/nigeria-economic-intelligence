
-- Track each file ingestion as a separate batch.
CREATE TABLE IF NOT EXISTS data_import_batches (
    batch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_id BIGINT
        REFERENCES data_sources(source_id),

    original_filename TEXT NOT NULL,
    file_sha256 CHAR(64) NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'completed', 'failed')),

    rows_received BIGINT NOT NULL DEFAULT 0
        CHECK (rows_received >= 0),

    rows_processed BIGINT NOT NULL DEFAULT 0
        CHECK (rows_processed >= 0),

    rows_rejected BIGINT NOT NULL DEFAULT 0
        CHECK (rows_rejected >= 0),

    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    initiated_by TEXT NOT NULL DEFAULT CURRENT_USER,
    error_message TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_import_batches_source
    ON data_import_batches(source_id);

CREATE INDEX IF NOT EXISTS idx_import_batches_started_at
    ON data_import_batches(started_at);

-- Track the most recent import that touched each observation.
ALTER TABLE indicator_observations
    ADD COLUMN IF NOT EXISTS last_import_batch_id BIGINT
    REFERENCES data_import_batches(batch_id);

-- Link recorded revisions to an import batch when available.
ALTER TABLE indicator_observation_revisions
    ADD COLUMN IF NOT EXISTS batch_id BIGINT
    REFERENCES data_import_batches(batch_id);

-- Extend revision tracking to capture the active import batch.
CREATE OR REPLACE FUNCTION record_indicator_observation_revision()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    active_batch_id BIGINT;
BEGIN
    IF OLD.value IS DISTINCT FROM NEW.value
       OR OLD.unit IS DISTINCT FROM NEW.unit
       OR OLD.observation_status IS DISTINCT FROM NEW.observation_status
       OR OLD.notes IS DISTINCT FROM NEW.notes
    THEN
        active_batch_id :=
            NULLIF(
                current_setting('app.import_batch_id', true),
                ''
            )::BIGINT;

        INSERT INTO indicator_observation_revisions (
            observation_id,
            previous_value,
            new_value,
            previous_unit,
            new_unit,
            previous_status,
            new_status,
            previous_notes,
            new_notes,
            batch_id
        )
        VALUES (
            OLD.observation_id,
            OLD.value,
            NEW.value,
            OLD.unit,
            NEW.unit,
            OLD.observation_status,
            NEW.observation_status,
            OLD.notes,
            NEW.notes,
            active_batch_id
        );
    END IF;

    RETURN NEW;
END;
$$;
