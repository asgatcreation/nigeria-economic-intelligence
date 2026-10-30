
CREATE TABLE IF NOT EXISTS indicator_observation_revisions (
    revision_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    observation_id BIGINT NOT NULL
        REFERENCES indicator_observations(observation_id),

    previous_value NUMERIC,
    new_value NUMERIC,

    previous_unit VARCHAR(100),
    new_unit VARCHAR(100),

    previous_status VARCHAR(20),
    new_status VARCHAR(20),

    previous_notes TEXT,
    new_notes TEXT,

    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recorded_by TEXT NOT NULL DEFAULT CURRENT_USER
);

CREATE INDEX IF NOT EXISTS idx_observation_revisions_observation
    ON indicator_observation_revisions(observation_id, recorded_at);

CREATE OR REPLACE FUNCTION record_indicator_observation_revision()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.value IS DISTINCT FROM NEW.value
       OR OLD.unit IS DISTINCT FROM NEW.unit
       OR OLD.observation_status IS DISTINCT FROM NEW.observation_status
       OR OLD.notes IS DISTINCT FROM NEW.notes
    THEN
        INSERT INTO indicator_observation_revisions (
            observation_id,
            previous_value,
            new_value,
            previous_unit,
            new_unit,
            previous_status,
            new_status,
            previous_notes,
            new_notes
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
            NEW.notes
        );
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_observation_revision_history
    ON indicator_observations;

CREATE TRIGGER trg_observation_revision_history
AFTER UPDATE ON indicator_observations
FOR EACH ROW
EXECUTE FUNCTION record_indicator_observation_revision();
