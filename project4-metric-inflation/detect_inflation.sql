-- =============================================================================
-- Metric Inflation — Detection (Reference SQL)
-- =============================================================================
-- Three-step diagnostic sequence:
--   1. Row count comparison — before/after the join
--   2. Identify affected customers — grouped by promo_count
--   3. Quantify actual inflation — correct revenue vs inflated revenue,
--      computed properly rather than as a self-canceling formula
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Step 1: Row count comparison
-- Any join that increases row count against a fact table needs explicit
-- justification. This is the first and cheapest check to run on any
-- revenue-producing query involving a join.
-- -----------------------------------------------------------------------------

SELECT 'fct_orders (baseline)' AS stage, COUNT(*) AS row_count
FROM fct_orders
UNION ALL
SELECT 'fct_orders LEFT JOIN promotions', COUNT(*)
FROM fct_orders o
LEFT JOIN promotions p ON o.customer_id = p.customer_id;

-- If the second row count exceeds the first, the join has fanned out.
-- The excess is exactly the number of "phantom" rows introduced.


-- -----------------------------------------------------------------------------
-- Step 2: Identify affected customers
-- Customers with more than one promotion are the ones whose orders
-- get duplicated in the broken join.
-- -----------------------------------------------------------------------------

SELECT
    promo_count,
    COUNT(*) AS customer_count
FROM (
    SELECT customer_id, COUNT(*) AS promo_count
    FROM promotions
    GROUP BY customer_id
)
GROUP BY promo_count
ORDER BY promo_count;

-- Customers with promo_count = 1 do not inflate (one join match, no fanout).
-- Customers with promo_count >= 2 inflate proportionally to their promo_count.


-- -----------------------------------------------------------------------------
-- Step 3: Quantify inflation correctly
--
-- Correct revenue is total net_revenue with NO join at all — this is
-- the accounting-system truth, since revenue does not depend on
-- promotions in any way. Inflated revenue is what the broken join
-- actually returns. The difference is the inflation.
-- -----------------------------------------------------------------------------

WITH correct_revenue AS (
    SELECT SUM(net_revenue) AS revenue, COUNT(*) AS row_count
    FROM fct_orders
),
inflated_revenue AS (
    SELECT SUM(o.net_revenue) AS revenue, COUNT(*) AS row_count
    FROM fct_orders o
    LEFT JOIN promotions p ON o.customer_id = p.customer_id
)
SELECT
    c.row_count                        AS correct_row_count,
    i.row_count                        AS inflated_row_count,
    i.row_count - c.row_count          AS phantom_rows,
    ROUND(c.revenue, 2)                AS correct_revenue,
    ROUND(i.revenue, 2)                AS inflated_revenue,
    ROUND(i.revenue - c.revenue, 2)    AS inflation_amount,
    ROUND((i.revenue - c.revenue) / c.revenue * 100, 2) AS inflation_pct
FROM correct_revenue c, inflated_revenue i;


-- -----------------------------------------------------------------------------
-- Per-customer inflation detail — the three worst-affected customers
-- -----------------------------------------------------------------------------

WITH correct AS (
    SELECT o.customer_id, SUM(o.net_revenue) AS correct_revenue, COUNT(*) AS correct_rows
    FROM fct_orders o
    GROUP BY o.customer_id
),
broken AS (
    SELECT o.customer_id, SUM(o.net_revenue) AS inflated_revenue, COUNT(*) AS inflated_rows
    FROM fct_orders o
    LEFT JOIN promotions p ON o.customer_id = p.customer_id
    GROUP BY o.customer_id
),
promo_counts AS (
    SELECT customer_id, COUNT(*) AS promo_count
    FROM promotions
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    COALESCE(pc.promo_count, 0)                                     AS promo_count,
    c.correct_rows,
    b.inflated_rows,
    ROUND(c.correct_revenue, 2)                                     AS correct_revenue,
    ROUND(b.inflated_revenue, 2)                                    AS inflated_revenue,
    ROUND(b.inflated_revenue / NULLIF(c.correct_revenue, 0), 2)     AS inflation_factor
FROM correct c
JOIN broken b       ON c.customer_id = b.customer_id
LEFT JOIN promo_counts pc ON c.customer_id = pc.customer_id
WHERE COALESCE(pc.promo_count, 0) >= 2
ORDER BY inflation_factor DESC
LIMIT 10;