-- =============================================================================
-- Metric Inflation — Promotions Table (Reference SQL)
-- =============================================================================
-- Human-readable reference for build_promotions.py.
--
-- Promotions distribution is deliberately controlled rather than purely
-- random, so the resulting inflation factors are predictable and
-- reproducible:
--   ~50% of customers — 0 promotions (no row)
--   ~30% of customers — 1 promotion
--   ~15% of customers — 2 promotions
--   ~5%  of customers — 3 promotions
--
-- This mirrors a real scenario: a promotions campaign feature launches,
-- most customers are unaffected, some are in one campaign, a smaller
-- group is in overlapping campaigns — and whoever wrote the join query
-- didn't account for that overlap.
-- =============================================================================

CREATE OR REPLACE TABLE promotions AS
WITH promo_bucket AS (
    SELECT customer_id, customer_key % 20 AS bucket
    FROM dim_customer
),
promo_counts AS (
    SELECT
        customer_id,
        CASE
            WHEN bucket < 10 THEN 0
            WHEN bucket < 16 THEN 1
            WHEN bucket < 19 THEN 2
            ELSE 3
        END AS promo_count
    FROM promo_bucket
),
expanded AS (
    SELECT customer_id, UNNEST(RANGE(promo_count)) AS promo_index
    FROM promo_counts
    WHERE promo_count > 0
)
SELECT
    customer_id,
    CASE promo_index WHEN 0 THEN 'PROMO_A' WHEN 1 THEN 'PROMO_B' ELSE 'PROMO_C' END AS promo_code,
    CASE promo_index WHEN 0 THEN 0.10      WHEN 1 THEN 0.15      ELSE 0.20 END       AS discount_pct,
    DATE '2023-01-01' + CAST(HASH(customer_id, promo_index) % 365 AS INT) * INTERVAL 1 DAY AS promo_start
FROM expanded;


-- -----------------------------------------------------------------------------
-- The broken query — what the junior analyst wrote
--
-- No grain guard on the join. Every order for a customer joins to every
-- one of that customer's active promotions. A customer with 3 promotions
-- has each of their orders tripled in this result set.
-- -----------------------------------------------------------------------------

-- DO NOT USE IN PRODUCTION — shown to document the failure mode
SELECT SUM(o.net_revenue) AS total_revenue
FROM fct_orders o
LEFT JOIN promotions p ON o.customer_id = p.customer_id;