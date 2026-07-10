-- =============================================================================
-- Metric Inflation — Fixes (Reference SQL)
-- =============================================================================
-- Three approaches, each valid depending on the business requirement.
-- All three are verified against the correct baseline (fct_orders with
-- no join at all) to confirm the fix actually resolves the inflation.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Fix 1: Select a single promotion per customer based on business rules.
-- Use when: only the most recent/relevant promotion matters for the query,
-- and other promotion details can be discarded.
--
-- ROW_NUMBER() = 1 replaces the DISTINCT + FIRST_VALUE pattern — FIRST_VALUE
-- OVER() does not collapse rows on its own; ROW_NUMBER() with a WHERE filter
-- is the correct way to select exactly one row per partition.
-- -----------------------------------------------------------------------------

WITH ranked_promos AS (
    SELECT
        customer_id,
        promo_code,
        discount_pct,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY promo_start DESC
        ) AS rn
    FROM promotions
),
latest_promo AS (
    SELECT 
        customer_id, 
        promo_code, 
        discount_pct
    FROM ranked_promos
    WHERE rn = 1
)
SELECT SUM(o.net_revenue) AS total_revenue
FROM fct_orders o
LEFT JOIN latest_promo p ON o.customer_id = p.customer_id;


-- -----------------------------------------------------------------------------
-- Fix 2: Aggregate promotions to customer grain, then join
-- Use when: promotion count or max discount is needed as an analytical
-- attribute, but individual promotion rows don't need to be preserved.
-- -----------------------------------------------------------------------------

WITH promo_summary AS (
    SELECT
        customer_id,
        COUNT(*)          AS promo_count,
        MAX(discount_pct) AS max_discount
    FROM promotions
    GROUP BY customer_id
)
SELECT
    SUM(o.net_revenue) AS total_revenue,
    AVG(p.promo_count) AS avg_promos_per_customer
FROM fct_orders o
LEFT JOIN promo_summary p ON o.customer_id = p.customer_id;


-- -----------------------------------------------------------------------------
-- Fix 3: Change fact table grain — attach promo_key at ingestion time
-- Use when: promotion attribution needs to persist at the order-line grain
-- Requires the business rule for attribution to be decided upfront 
-- (e.g. "most recent promotion active at order time" — itself a temporal join, 
-- same pattern as Project 3).
-- -----------------------------------------------------------------------------

WITH order_promo_attribution AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.net_revenue,
        p.promo_code,
        ROW_NUMBER() OVER (
            PARTITION BY o.order_id
            ORDER BY p.promo_start DESC
        ) AS rn
    FROM fct_orders o
    LEFT JOIN promotions p
        ON  o.customer_id = p.customer_id
        AND o.order_date >= p.promo_start
        AND o.order_date <  p.promo_end
)
SELECT SUM(net_revenue) AS total_revenue
FROM order_promo_attribution
WHERE rn = 1;


-- -----------------------------------------------------------------------------
-- Verification: all three fixes should return the same total_revenue,
-- and it should match fct_orders with no join at all.
-- -----------------------------------------------------------------------------

SELECT SUM(net_revenue) AS baseline_revenue_no_join
FROM fct_orders;