-- =============================================================================
-- SCD Type 2 Customer Dimension — Reference SQL
-- =============================================================================
-- Human-readable reference for the logic executed by build_scd2.py.
-- Explains the SCD Type 2 structure and the three core operations:
--   1. Initial load
--   2. Applying a change (close old record, insert new record)
--   3. Point-in-time join pattern
-- =============================================================================


-- -----------------------------------------------------------------------------
-- SCD Type 2 structure
--
-- customer_key:  surrogate key — unique per row, not per customer.
--                The same customer_id appears in multiple rows after changes.
--                This is intentional — each row represents one version of
--                the customer's attributes over a specific time range.
--
-- valid_from:    the date this version became effective.
-- valid_to:      the date this version was superseded.
--                NULL means the record is currently active.
--
-- is_current:    convenience flag. Equivalent to WHERE valid_to IS NULL
--                but faster to filter on and more readable in queries.
--
-- Why surrogate key instead of customer_id as FK in fct_orders:
--   If fct_orders stores customer_id (natural key), the temporal join
--   must always include date bounds — missing them causes row duplication.
--   If fct_orders stores customer_key (surrogate, version-specific), the
--   join is always correct by construction — each order links to exactly
--   one customer version. Project 1's fact table stores customer_id. Because 
--   no version-specific surrogate key exists in the fact table, point-in-time 
--   joins must use the natural key together with the validity dates.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE dim_customer_scd2 (
    customer_key    INTEGER     NOT NULL,
    customer_id     INTEGER     NOT NULL,
    region          VARCHAR     NOT NULL,
    country         VARCHAR     NOT NULL,
    segment         VARCHAR     NOT NULL,
    valid_from      DATE        NOT NULL,
    valid_to        DATE,                   -- NULL = currently active
    is_current      BOOLEAN     NOT NULL
);


-- -----------------------------------------------------------------------------
-- Core SCD Type 2 operation: applying a customer attribute change
--
-- Two-step process — must be executed in order:
--   Step 1: Close the current record (set valid_to, clear is_current flag)
--   Step 2: Insert a new record with the updated attributes
--
-- The valid_to date on the closed record is set to change_date - 1 day so
-- that the ranges are non-overlapping:
--   Old record: valid_from = 2022-01-01, valid_to = 2023-06-14
--   New record: valid_from = 2023-06-15, valid_to = NULL
--
-- A temporal join on order_date will match exactly one record per customer
-- per date with no gaps and no overlaps.
-- -----------------------------------------------------------------------------

-- Step 1: Close the existing active record
UPDATE dim_customer_scd2
SET
    valid_to   = :change_date - INTERVAL 1 DAY,
    is_current = FALSE
WHERE customer_id = :customer_id
  AND is_current  = TRUE;

-- Step 2: Insert the new version
INSERT INTO dim_customer_scd2
    (customer_key, customer_id, region, country, segment,
     valid_from, valid_to, is_current)
SELECT
    (SELECT MAX(customer_key) + 1 FROM dim_customer_scd2),
    :customer_id,
    :new_region,
    :new_country,
    :new_segment,
    :change_date,
    NULL,
    TRUE;


-- -----------------------------------------------------------------------------
-- The correct temporal join pattern
--
-- The date bounds on the JOIN are not optional — omitting them causes
-- row duplication when a customer has multiple SCD2 records.
-- -----------------------------------------------------------------------------

SELECT
    o.order_id,
    o.order_date,
    o.net_revenue,
    c.region    AS region_at_time_of_order,
    c.country   AS country_at_time_of_order,
    c.segment   AS segment_at_time_of_order
FROM fct_orders o
JOIN dim_customer_scd2 c
    ON  o.customer_id  = c.customer_id
    AND o.order_date  >= c.valid_from
    AND (o.order_date  < c.valid_to OR c.valid_to IS NULL);


-- -----------------------------------------------------------------------------
-- The incorrect join — what row duplication looks like
--
-- Joining on natural key without date bounds returns one row per SCD2
-- version per order. A customer with 3 changes has 4 SCD2 records —
-- every order for that customer appears 4 times. Revenue is inflated
-- by exactly that multiplier for affected customers.
-- This is documented and deliberately reproduced in simulate_changes.sql.
-- -----------------------------------------------------------------------------

-- DO NOT USE IN PRODUCTION — shown here to document the failure mode
SELECT
    o.order_id,
    o.net_revenue,
    c.region
FROM fct_orders o
JOIN dim_customer_scd2 c
    ON o.customer_id = c.customer_id   -- missing date bounds
-- Result: row count = orders × SCD2 versions per customer
-- Revenue is inflated by the average number of SCD2 records per customer