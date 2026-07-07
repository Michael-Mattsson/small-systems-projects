-- =============================================================================
-- SCD Type 2 — Point-in-Time Queries
-- =============================================================================
-- Demonstrates the analytical value of Type 2 history and the exact failure
-- mode when the temporal join is omitted.
--
-- Query categories:
--   1. Correct temporal join pattern
--   2. Broken join pattern (documented failure mode)
--   3. Revenue inflation quantification
--   4. Point-in-time business questions
--   5. Current-state queries (Type 1 equivalent using is_current flag)
-- =============================================================================


-- =============================================================================
-- Section 1: Correct temporal join
-- =============================================================================

-- Q1: For each order, what were the customer's attributes at time of purchase?
SELECT
    o.order_id,
    o.order_date,
    o.net_revenue,
    c.region    AS region_at_order,
    c.country   AS country_at_order,
    c.segment   AS segment_at_order
FROM fct_orders o
JOIN dim_customer_scd2 c
    ON  o.customer_id  = c.customer_id
    AND o.order_date  >= c.valid_from
    AND (o.order_date  < c.valid_to OR c.valid_to IS NULL)
LIMIT 20;


-- Q2: Revenue by region — using region at time of order
-- This is the correct version. Each order is attributed to the region
-- the customer was in when they placed it, not their current region.
SELECT
    c.region AS region_at_order,
    d.year,
    SUM(o.net_revenue)          AS net_revenue,
    COUNT(DISTINCT o.order_id)  AS order_count
FROM fct_orders o
JOIN dim_customer_scd2 c
    ON  o.customer_id  = c.customer_id
    AND o.order_date  >= c.valid_from
    AND (o.order_date  < c.valid_to OR c.valid_to IS NULL)
JOIN dim_date d
    ON o.date_key = d.date_key
GROUP BY c.region, d.year
ORDER BY d.year, net_revenue DESC;


-- Q3: What segment was customer 5000 in for each of their orders?
-- This directly tests the multi-change scenario from simulate_changes.sql.
-- Orders placed before 2022-09-01 → Consumer
-- Orders placed 2022-09-01 to 2023-04-30 → Business
-- Orders placed after 2023-05-01 → Enterprise
SELECT
    o.order_id,
    o.order_date,
    o.net_revenue,
    c.segment   AS segment_at_order,
    c.valid_from,
    c.valid_to
FROM fct_orders o
JOIN dim_customer_scd2 c
    ON  o.customer_id  = c.customer_id
    AND o.order_date  >= c.valid_from
    AND (o.order_date  < c.valid_to OR c.valid_to IS NULL)
WHERE o.customer_id = 5000
ORDER BY o.order_date;


-- =============================================================================
-- Section 2: Broken join — documented failure mode
-- =============================================================================

-- Q4_BROKEN: Revenue by region WITHOUT temporal join bounds
-- Joining on natural key alone returns one row per SCD2 version per order.
-- Customer 5000 (3 versions) appears 3x in every order row.
-- Revenue is inflated by the number of SCD2 records per customer.
SELECT
    c.region,
    SUM(o.net_revenue) AS inflated_revenue
FROM fct_orders o
JOIN dim_customer_scd2 c
    ON o.customer_id = c.customer_id   -- missing date bounds
GROUP BY c.region;

-- Compare this output to Q2's net_revenue column.
-- The difference is the inflation caused by the broken join.


-- =============================================================================
-- Section 3: Revenue inflation quantification
-- =============================================================================

-- Q5: Quantify the exact revenue inflation from the broken join
-- Shows correct revenue, inflated revenue, and inflation factor
-- for each of the three customers modified in simulate_changes.sql
WITH correct AS (
    SELECT
        o.customer_id,
        SUM(o.net_revenue) AS correct_revenue,
        COUNT(*)           AS correct_row_count
    FROM fct_orders o
    JOIN dim_customer_scd2 c
        ON  o.customer_id  = c.customer_id
        AND o.order_date  >= c.valid_from
        AND (o.order_date  < c.valid_to OR c.valid_to IS NULL)
    WHERE o.customer_id IN (1001, 2500, 5000)
    GROUP BY o.customer_id
),
broken AS (
    SELECT
        o.customer_id,
        SUM(o.net_revenue) AS inflated_revenue,
        COUNT(*)           AS inflated_row_count
    FROM fct_orders o
    JOIN dim_customer_scd2 c
        ON o.customer_id = c.customer_id
    WHERE o.customer_id IN (1001, 2500, 5000)
    GROUP BY o.customer_id
),
scd2_versions AS (
    SELECT customer_id, COUNT(*) AS version_count
    FROM dim_customer_scd2
    WHERE customer_id IN (1001, 2500, 5000)
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    v.version_count               AS scd2_versions,
    c.correct_row_count,
    b.inflated_row_count,
    ROUND(c.correct_revenue, 2)   AS correct_revenue,
    ROUND(b.inflated_revenue, 2)  AS inflated_revenue,
    ROUND(b.inflated_revenue / NULLIF(c.correct_revenue, 0), 2) AS inflation_factor
FROM correct c
JOIN broken b        ON c.customer_id = b.customer_id
JOIN scd2_versions v ON c.customer_id = v.customer_id
ORDER BY c.customer_id;

-- Expected output:
-- customer 1001: 2 versions → inflation_factor = 2.00
-- customer 2500: 2 versions → inflation_factor = 2.00
-- customer 5000: 3 versions → inflation_factor = 3.00


-- =============================================================================
-- Section 4: Point-in-time business questions
-- =============================================================================

-- Q6: Revenue from Enterprise customers in 2022
-- "Enterprise" means segment = Enterprise at time of purchase —
-- not current segment. Customer 5000 was Consumer in 2022,
-- so their 2022 orders should NOT appear here.
SELECT
    d.year,
    SUM(o.net_revenue)         AS net_revenue,
    COUNT(DISTINCT o.order_id) AS order_count
FROM fct_orders o
JOIN dim_customer_scd2 c
    ON  o.customer_id  = c.customer_id
    AND o.order_date  >= c.valid_from
    AND (o.order_date  < c.valid_to OR c.valid_to IS NULL)
JOIN dim_date d ON o.date_key = d.date_key
WHERE c.segment = 'Enterprise'
  AND d.year = 2022
GROUP BY d.year;


-- Q7: Customer journey — segment history for customers who upgraded
-- Shows all customers who changed segment at least once,
-- with their full attribute timeline and total revenue per version.
SELECT
    c.customer_id,
    c.segment,
    c.region,
    c.valid_from,
    c.valid_to,
    c.is_current,
    COALESCE(SUM(o.net_revenue), 0)      AS revenue_during_period,
    COUNT(o.order_id)                    AS orders_during_period
FROM dim_customer_scd2 c
LEFT JOIN fct_orders o
    ON  o.customer_id  = c.customer_id
    AND o.order_date  >= c.valid_from
    AND (o.order_date  < c.valid_to OR c.valid_to IS NULL)
WHERE c.customer_id IN (
    SELECT customer_id
    FROM dim_customer_scd2
    GROUP BY customer_id
    HAVING COUNT(*) > 1
)
GROUP BY
    c.customer_id, c.segment, c.region,
    c.valid_from, c.valid_to, c.is_current
ORDER BY c.customer_id, c.valid_from;


-- =============================================================================
-- Section 5: Current-state queries using is_current flag
-- =============================================================================

-- Q8: Current customer distribution by segment and region
-- Uses is_current = TRUE — equivalent to a Type 0/1 dimension query.
-- Demonstrates that Type 2 is backward compatible with current-state needs.
SELECT
    segment,
    region,
    COUNT(*) AS customer_count
FROM dim_customer_scd2
WHERE is_current = TRUE
GROUP BY segment, region
ORDER BY segment, customer_count DESC;


-- Q9: SCD2 dimension health check
-- Useful for ongoing monitoring in production.
-- All metrics should remain within expected bounds as data grows.
SELECT
    COUNT(*)                                             AS total_rows,
    COUNT(DISTINCT customer_id)                          AS distinct_customers,
    ROUND(COUNT(*)::NUMERIC / COUNT(DISTINCT customer_id), 2)
                                                         AS avg_versions_per_customer,
    (SELECT MAX(version_count) FROM (
        SELECT COUNT(*) AS version_count
        FROM dim_customer_scd2
        GROUP BY customer_id
    ))                                                   AS max_versions_single_customer,
    SUM(CASE WHEN is_current    THEN 1 ELSE 0 END)       AS current_records,
    SUM(CASE WHEN valid_to IS NULL THEN 1 ELSE 0 END)    AS open_records,
    SUM(CASE WHEN is_current AND valid_to IS NOT NULL
             THEN 1 ELSE 0 END)                          AS is_current_but_has_valid_to
FROM dim_customer_scd2;
-- is_current_but_has_valid_to should always be 0.
-- If nonzero, the close/insert logic has a bug.