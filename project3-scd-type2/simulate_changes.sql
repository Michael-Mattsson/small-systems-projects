-- =============================================================================
-- SCD Type 2 — Change Simulation Reference SQL
-- =============================================================================
-- This file documents the logic executed by simulate_changes.py.
-- It is not intended to be run directly — use simulate_changes.py instead.
--
-- Sections follow the correct ETL pipeline order:
--   1. Incoming customer feed (source system data)
--   2. Hash-based change detection
--   3. Apply SCD2 updates for detected changes
--   4. Integrity validation
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Section 1: Incoming customer feed
-- Simulates a staging table populated from the source system.
-- In production this would be a table, not an inline VALUES clause.
-- -----------------------------------------------------------------------------

CREATE TEMP TABLE IF NOT EXISTS incoming_customers AS
SELECT * FROM (VALUES
    (1001, 'East',  'Finland', 'Consumer',   '2023-03-01'),
    (2500, 'South', 'Sweden',  'Business',   '2023-06-15'),
    (5000, 'West',  'Norway',  'Business',   '2022-09-01'),
    (5000, 'West',  'Norway',  'Enterprise', '2023-05-01')
) AS t(customer_id, region, country, segment, change_date);


-- -----------------------------------------------------------------------------
-- Section 2: Hash-based change detection
-- Compare incoming attribute hash against current dimension hash.
-- Rows where hashes differ require a new SCD2 version.
-- -----------------------------------------------------------------------------

WITH current_state AS (
    SELECT
        customer_id,
        region, country, segment,
        MD5(CONCAT(region, '|', country, '|', segment)) AS current_hash
    FROM dim_customer_scd2
    WHERE is_current = TRUE
),
incoming_hashed AS (
    SELECT
        customer_id,
        region, country, segment, change_date,
        MD5(CONCAT(region, '|', country, '|', segment)) AS incoming_hash
    FROM incoming_customers
)
SELECT
    i.customer_id,
    i.change_date,
    c.region        AS current_region,    i.region   AS incoming_region,
    c.segment       AS current_segment,   i.segment  AS incoming_segment,
    CASE
        WHEN c.current_hash != i.incoming_hash
        THEN 'CHANGE DETECTED'
        ELSE 'no change'
    END             AS change_status
FROM incoming_hashed i
JOIN current_state c ON i.customer_id = c.customer_id
ORDER BY i.customer_id, i.change_date;


-- -----------------------------------------------------------------------------
-- Section 3: Apply SCD2 updates
-- For each detected change, run the two-step close/insert pattern.
-- Shown here for one customer — simulate_changes.py handles all cases
-- via apply_customer_change().
-- -----------------------------------------------------------------------------

-- Step 1: close current record
UPDATE dim_customer_scd2
SET valid_to   = DATE '2023-03-01' - INTERVAL 1 DAY,
    is_current = FALSE
WHERE customer_id = 1001 AND is_current = TRUE;

-- Step 2: insert new version
INSERT INTO dim_customer_scd2
    (customer_key, customer_id, region, country, segment,
     valid_from, valid_to, is_current)
VALUES (
    (SELECT MAX(customer_key) + 1 FROM dim_customer_scd2),
    1001, 'East', 'Finland', 'Consumer',
    DATE '2023-03-01', NULL, TRUE
);


-- -----------------------------------------------------------------------------
-- Section 4: Integrity validation (expect 0 on all checks)
-- -----------------------------------------------------------------------------

SELECT 'duplicate_is_current'      AS check_name, COUNT(*) AS violations
FROM (
    SELECT customer_id FROM dim_customer_scd2
    WHERE is_current = TRUE
    GROUP BY customer_id HAVING COUNT(*) > 1
);

SELECT 'open_records_not_current'  AS check_name, COUNT(*) AS violations
FROM dim_customer_scd2
WHERE valid_to IS NULL AND is_current = FALSE;

SELECT 'overlapping_ranges'        AS check_name, COUNT(*) AS violations
FROM (
    SELECT a.customer_id
    FROM dim_customer_scd2 a
    JOIN dim_customer_scd2 b
        ON  a.customer_id  = b.customer_id
        AND b.valid_from   > a.valid_from
        AND b.valid_from  <= a.valid_to
        AND a.valid_to    IS NOT NULL
        AND b.customer_key != a.customer_key
);