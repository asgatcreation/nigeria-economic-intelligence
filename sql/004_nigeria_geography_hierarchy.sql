-- Seed Nigeria's administrative geography: the country, its six
-- geopolitical zones, and the 36 states plus the Federal Capital
-- Territory.
--
-- This is reference data, not measurement: the zone-to-state assignment
-- is Nigeria's standard geopolitical classification, and state codes are
-- the OCHA/NBS P-codes (NG001-NG037) used by the humanitarian common
-- operational datasets, so state-level imports key on published codes
-- rather than on names that vary in spelling.
--
-- Written as upserts that also repair parent_id, so it is idempotent and
-- can be applied after states have already been created by an import.

INSERT INTO geographies (geo_code, geo_name, geo_level, country_code)
VALUES ('NGA', 'Nigeria', 'country', 'NGA')
ON CONFLICT (geo_code) DO UPDATE SET
    geo_name = EXCLUDED.geo_name,
    geo_level = EXCLUDED.geo_level;

INSERT INTO geographies (geo_code, geo_name, geo_level, parent_id)
SELECT
    zone.geo_code,
    zone.geo_name,
    'zone',
    (SELECT geography_id FROM geographies WHERE geo_code = 'NGA')
FROM (
    VALUES
        ('NG-NC', 'North Central'),
        ('NG-NE', 'North East'),
        ('NG-NW', 'North West'),
        ('NG-SE', 'South East'),
        ('NG-SS', 'South South'),
        ('NG-SW', 'South West')
) AS zone(geo_code, geo_name)
ON CONFLICT (geo_code) DO UPDATE SET
    geo_name = EXCLUDED.geo_name,
    geo_level = EXCLUDED.geo_level,
    parent_id = EXCLUDED.parent_id;

INSERT INTO geographies (geo_code, geo_name, geo_level, parent_id)
SELECT
    state.geo_code,
    state.geo_name,
    'state',
    zone.geography_id
FROM (
    VALUES
        ('NG001', 'Abia',                      'NG-SE'),
        ('NG002', 'Adamawa',                   'NG-NE'),
        ('NG003', 'Akwa Ibom',                 'NG-SS'),
        ('NG004', 'Anambra',                   'NG-SE'),
        ('NG005', 'Bauchi',                    'NG-NE'),
        ('NG006', 'Bayelsa',                   'NG-SS'),
        ('NG007', 'Benue',                     'NG-NC'),
        ('NG008', 'Borno',                     'NG-NE'),
        ('NG009', 'Cross River',               'NG-SS'),
        ('NG010', 'Delta',                     'NG-SS'),
        ('NG011', 'Ebonyi',                    'NG-SE'),
        ('NG012', 'Edo',                       'NG-SS'),
        ('NG013', 'Ekiti',                     'NG-SW'),
        ('NG014', 'Enugu',                     'NG-SE'),
        ('NG015', 'Federal Capital Territory', 'NG-NC'),
        ('NG016', 'Gombe',                     'NG-NE'),
        ('NG017', 'Imo',                       'NG-SE'),
        ('NG018', 'Jigawa',                    'NG-NW'),
        ('NG019', 'Kaduna',                    'NG-NW'),
        ('NG020', 'Kano',                      'NG-NW'),
        ('NG021', 'Katsina',                   'NG-NW'),
        ('NG022', 'Kebbi',                     'NG-NW'),
        ('NG023', 'Kogi',                      'NG-NC'),
        ('NG024', 'Kwara',                     'NG-NC'),
        ('NG025', 'Lagos',                     'NG-SW'),
        ('NG026', 'Nasarawa',                  'NG-NC'),
        ('NG027', 'Niger',                     'NG-NC'),
        ('NG028', 'Ogun',                      'NG-SW'),
        ('NG029', 'Ondo',                      'NG-SW'),
        ('NG030', 'Osun',                      'NG-SW'),
        ('NG031', 'Oyo',                       'NG-SW'),
        ('NG032', 'Plateau',                   'NG-NC'),
        ('NG033', 'Rivers',                    'NG-SS'),
        ('NG034', 'Sokoto',                    'NG-NW'),
        ('NG035', 'Taraba',                    'NG-NE'),
        ('NG036', 'Yobe',                      'NG-NE'),
        ('NG037', 'Zamfara',                   'NG-NW')
) AS state(geo_code, geo_name, zone_code)
JOIN geographies AS zone
  ON zone.geo_code = state.zone_code
ON CONFLICT (geo_code) DO UPDATE SET
    geo_name = EXCLUDED.geo_name,
    geo_level = EXCLUDED.geo_level,
    parent_id = EXCLUDED.parent_id;
