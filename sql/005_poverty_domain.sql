-- Add 'poverty' to the indicator domains.
--
-- Multidimensional poverty measures are not output, prices or labour
-- supply, and filing them under 'economy' would make the domain column
-- useless for the one question it exists to answer: what kind of thing
-- is this indicator. The domain list is a CHECK constraint, so widening
-- it needs a migration rather than an application change alone.
--
-- ingestion.ALLOWED_DOMAINS must be kept in step with this list; a test
-- reconciles the two so they cannot drift apart silently.

ALTER TABLE indicators
    DROP CONSTRAINT IF EXISTS indicators_domain_check;

ALTER TABLE indicators
    ADD CONSTRAINT indicators_domain_check
    CHECK (domain IN (
        'economy', 'labour_market', 'demographics',
        'prices', 'trade', 'agriculture', 'poverty', 'other'
    ));
