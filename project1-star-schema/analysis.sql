-- =============================================================================
-- FinMart Star Schema — Analytical Queries
-- =============================================================================
-- Design principles
-- -----------------
-- • All queries use the star schema (fct_orders + dimensions).
-- • All joins use surrogate keys.
-- • Revenue calculations use the governed metrics stored in fct_orders
--   (gross_revenue and net_revenue) rather than recalculating them.
-- • Business logic is centralized in the warehouse model, not duplicated
--   across analytical queries.
-- =============================================================================


-- QUERY: Revenue by Product Category by Quarter

SELECT
    p.category,
    d.year,
    d.quarter,
    COUNT(DISTINCT o.order_id)           AS order_count,
    SUM(o.net_revenue)                   AS net_revenue,
    ROUND(AVG(o.net_revenue), 2)         AS avg_order_revenue
FROM fct_orders o
JOIN dim_product p
    ON o.product_key = p.product_key
JOIN dim_date d
    ON o.date_key = d.date_key
GROUP BY
    p.category, d.year, d.quarter
ORDER BY
    p.category, d.year, d.quarter;


-- QUERY: Top 10 Customers by Net Revenue (2023)

SELECT
    c.customer_id,
    c.region,
    c.segment,
    COUNT(DISTINCT o.order_id)           AS order_count,
    SUM(o.net_revenue)                   AS net_revenue
FROM fct_orders o
JOIN dim_customer c
    ON o.customer_key = c.customer_key
JOIN dim_date d
    ON o.date_key = d.date_key
WHERE 
    d.year = 2023
GROUP BY
    c.customer_id, c.region, c.segment
ORDER BY
    net_revenue DESC
LIMIT 10;


-- QUERY: Weekend vs Weekday Revenue by Region

SELECT
    c.region,
    CASE
        WHEN d.is_weekend THEN 'Weekend'
        ELSE 'Weekday'
    END                                         AS day_type,
    COUNT(DISTINCT o.order_id)                  AS order_count,
    SUM(o.net_revenue)                          AS net_revenue,
    ROUND(
        SUM(o.net_revenue)/SUM(SUM(o.net_revenue)) OVER (PARTITION BY c.region) * 100, 1
    )                                           AS pct_of_region_revenue
FROM fct_orders o
JOIN dim_customer c
    ON o.customer_key = c.customer_key
JOIN dim_date d
    ON o.date_key = d.date_key
GROUP BY
    c.region, d.is_weekend
ORDER BY
    c.region, day_type;


-- QUERY: Month-over-Month Revenue Growth by Category

WITH monthly_revenue AS (
    SELECT
        p.category,
        d.year,
        d.month,
        SUM(o.net_revenue) AS revenue
    FROM fct_orders o
    JOIN dim_product p
        ON o.product_key = p.product_key
    JOIN dim_date d
        ON o.date_key = d.date_key
    GROUP BY
        p.category, d.year, d.month
)

SELECT
    category,
    year,
    month,
    revenue,
    LAG(revenue) OVER (PARTITION BY category ORDER BY year, month) AS previous_month_revenue,
    CASE
        WHEN LAG(revenue) OVER (PARTITION BY category ORDER BY year, month) IS NULL
        THEN NULL
        ELSE
            (revenue - LAG(revenue) OVER (PARTITION BY category ORDER BY year, month))
            /
            LAG(revenue) OVER (PARTITION BY category ORDER BY year, month)
        * 100
    END AS revenue_growth_pct
FROM monthly_revenue
ORDER BY
    category, year, month;


-- QUERY: Gross vs Net Revenue by Category

SELECT
    p.category,
    SUM(o.gross_revenue)                            AS gross_revenue,
    SUM(o.net_revenue)                              AS net_revenue,
    SUM(o.gross_revenue) - SUM(o.net_revenue)       AS refund_value,
    ROUND(
        (SUM(o.gross_revenue) - SUM(o.net_revenue))
        /
        SUM(o.gross_revenue)
        * 100, 2
    )                                               AS refund_rate_pct
FROM fct_orders o
JOIN dim_product p
    ON o.product_key = p.product_key
GROUP BY
    p.category
ORDER BY
    refund_rate_pct DESC;


-- QUERY: Revenue and Margin by Product Subcategory

SELECT
    p.category,
    p.subcategory,
    SUM(o.net_revenue)                              AS net_revenue,
    SUM(o.quantity * p.cost_price)                  AS total_cost,
    ROUND(
        (SUM(o.net_revenue) - SUM(o.quantity * p.cost_price))
        /
        NULLIF(SUM(o.net_revenue), 0)
        * 100, 1
    )                                               AS margin_pct
FROM fct_orders o
JOIN dim_product p
    ON o.product_key = p.product_key
GROUP BY
    p.category, p.subcategory
ORDER BY
    p.category, margin_pct DESC;