-- =============================================================================
-- Wide vs Narrow Benchmark — Query Pairs
-- =============================================================================
-- Each query exists in two versions: wide and narrow, doing identical
-- analytical work. Run each pair under benchmark.py for repeated, averaged
-- timing rather than a single EXPLAIN ANALYZE run.
-- Source data: 5,000,000 row fct_orders (Project 1, scaled).
-- =============================================================================


-- Query 1: Simple single-dimension aggregation 
-- Simple reporting scenario, Basic join overhead tested

-- WIDE
SELECT 
    category, 
    SUM(net_revenue)                AS revenue
FROM wide_orders
WHERE order_year = 2023
GROUP BY category;

-- NARROW
SELECT 
    p.category, 
    SUM(o.net_revenue)              AS revenue
FROM fct_orders o
JOIN dim_product p ON o.product_key = p.product_key
JOIN dim_date    d ON o.date_key    = d.date_key
WHERE d.year = 2023
GROUP BY p.category;


-- Query 2: Multi-dimension slice with distinct count
-- Dashboard analytics scenario, Multiple joins + distinct count tested

-- WIDE
SELECT
    region, 
    category, 
    DATE_TRUNC('month', date)       AS order_month,
    SUM(net_revenue)                AS revenue,
    COUNT(DISTINCT customer_id)     AS distinct_customers
FROM wide_orders
WHERE is_refunded = FALSE
GROUP BY region, category, order_month;

-- NARROW
SELECT
    c.region, 
    p.category, 
    DATE_TRUNC('month', d.date)     AS order_month,
    SUM(o.net_revenue)              AS revenue,
    COUNT(DISTINCT c.customer_id)   AS distinct_customers
FROM fct_orders o
JOIN dim_customer c ON o.customer_key = c.customer_key
JOIN dim_product  p ON o.product_key  = p.product_key
JOIN dim_date     d ON o.date_key     = d.date_key
WHERE o.is_refunded = FALSE
GROUP BY c.region, p.category, DATE_TRUNC('month', d.date);


-- Query 3: Point lookup on multiple filter predicates
-- Selective filtering scenario, Predicate evaluation tested

-- WIDE
SELECT 
    product_name, 
    SUM(net_revenue)                AS revenue
FROM wide_orders
WHERE segment = 'Enterprise' AND subcategory = 'Premium'
GROUP BY product_name
ORDER BY revenue DESC
LIMIT 20;

-- NARROW
SELECT 
    p.name AS product_name, 
    SUM(o.net_revenue)              AS revenue
FROM fct_orders o
JOIN dim_customer c ON o.customer_key = c.customer_key
JOIN dim_product  p ON o.product_key  = p.product_key
WHERE c.segment = 'Enterprise' AND p.subcategory = 'Premium'
GROUP BY p.name
ORDER BY revenue DESC
LIMIT 20;


-- Query 4: Full scan aggregation, no filter
-- Full-table aggregation scenario, Maximum join cost tested

-- WIDE
SELECT
    region, segment, category,
    SUM(net_revenue) AS revenue,
    AVG(net_revenue) AS avg_revenue
FROM wide_orders
GROUP BY region, segment, category;

-- NARROW

SELECT
    c.region, c.segment, p.category,
    SUM(o.net_revenue) AS revenue,
    AVG(o.net_revenue) AS avg_revenue
FROM fct_orders o
JOIN dim_customer c ON o.customer_key = c.customer_key
JOIN dim_product  p ON o.product_key  = p.product_key
GROUP BY c.region, c.segment, p.category;