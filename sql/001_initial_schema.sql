CREATE TABLE IF NOT EXISTS data_sources (
    source_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_code VARCHAR(80) NOT NULL UNIQUE,
    source_name VARCHAR(250) NOT NULL,
    organization VARCHAR(250),
    source_url TEXT,
    methodology TEXT,
    accessed_on DATE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS geographies (
    geography_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    geo_code VARCHAR(80) NOT NULL UNIQUE,
    geo_name VARCHAR(200) NOT NULL,
    geo_level VARCHAR(30) NOT NULL
        CHECK (geo_level IN (
            'country', 'zone', 'state', 'lga',
            'senatorial_district', 'other'
        )),
    parent_id BIGINT REFERENCES geographies(geography_id),
    country_code CHAR(3) NOT NULL DEFAULT 'NGA',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_geographies_parent
    ON geographies(parent_id);

CREATE TABLE IF NOT EXISTS indicators (
    indicator_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    indicator_code VARCHAR(100) NOT NULL UNIQUE,
    indicator_name VARCHAR(250) NOT NULL,
    domain VARCHAR(40) NOT NULL
        CHECK (domain IN (
            'economy', 'labour_market', 'demographics',
            'prices', 'trade', 'agriculture', 'other'
        )),
    unit VARCHAR(100),
    description TEXT,
    frequency VARCHAR(20)
        CHECK (frequency IN (
            'annual', 'quarterly', 'monthly',
            'weekly', 'daily', 'irregular'
        )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS indicator_observations (
    observation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    indicator_id BIGINT NOT NULL
        REFERENCES indicators(indicator_id),
    geography_id BIGINT NOT NULL
        REFERENCES geographies(geography_id),
    source_id BIGINT NOT NULL
        REFERENCES data_sources(source_id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    value NUMERIC,
    unit VARCHAR(100),
    observation_status VARCHAR(20) NOT NULL DEFAULT 'observed'
        CHECK (observation_status IN (
            'observed', 'estimated', 'provisional', 'revised'
        )),
    notes TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (period_end >= period_start),
    UNIQUE (
        indicator_id, geography_id, source_id,
        period_start, period_end
    )
);

CREATE INDEX IF NOT EXISTS idx_observations_indicator_period
    ON indicator_observations(indicator_id, period_start, period_end);

CREATE INDEX IF NOT EXISTS idx_observations_geography_period
    ON indicator_observations(geography_id, period_start, period_end);

CREATE INDEX IF NOT EXISTS idx_observations_source
    ON indicator_observations(source_id);
