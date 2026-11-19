-- Add 'geography' to the indicator domains.
--
-- Land area is not demographics, economy or poverty: it is an attribute
-- of the geographic unit itself, and it is what turns a population count
-- into a density. Filing it under 'other' would work and would also be
-- the first step towards 'other' meaning nothing in particular, which is
-- the failure mode this column exists to avoid.
--
-- ingestion.ALLOWED_DOMAINS must be kept in step with this list; a test
-- reconciles the two so they cannot drift apart silently.

ALTER TABLE indicators
    DROP CONSTRAINT IF EXISTS indicators_domain_check;

ALTER TABLE indicators
    ADD CONSTRAINT indicators_domain_check
    CHECK (domain IN (
        'economy', 'labour_market', 'demographics',
        'prices', 'trade', 'agriculture', 'poverty',
        'geography', 'other'
    ));
