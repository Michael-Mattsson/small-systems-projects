-- How many orders in total?
SELECT COUNT(*) AS total_orders FROM raw_orders


-- Total revenue

    SELECT SUM(unit_price * quantity) AS total_revenue \
    FROM raw_orders
    WHERE is_refunded = FALSE


-- Revenue by product category by quarter, excluding refunds

    SELECT
        p.category,
        EXTRACT(QUARTER FROM o.order_date) AS quarter,
        SUM(o.unit_price * o.quantity) AS revenue
    FROM raw_orders o
    JOIN raw_products p ON o.product_id = p.product_id
    WHERE o.is_refunded = FALSE
    GROUP BY p.category, EXTRACT(QUARTER FROM o.order_date)
    ORDER BY p.category, quarter


-- Top 10 customers by net revenue in 2023

    SELECT
        c.customer_id,
        SUM(o.unit_price * o.quantity) AS net_revenue
    FROM raw_orders o
    JOIN raw_customers c ON o.customer_id = c.customer_id
    WHERE o.is_refunded = FALSE
      AND EXTRACT(YEAR FROM o.order_date) = 2023
    GROUP BY c.customer_id
    ORDER BY net_revenue DESC
    LIMIT 10


-- Weekend vs weekday revenue comparison by region

    SELECT
        c.region,
        CASE WHEN EXTRACT(DOW FROM o.order_date) IN (0, 6) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
        SUM(o.unit_price * o.quantity) AS revenue
    FROM raw_orders o
    JOIN raw_customers c ON o.customer_id = c.customer_id
    WHERE o.is_refunded = FALSE
    GROUP BY c.region, day_type


-- Month-over-month revenue growth by category

    WITH monthly_revenue AS (
        SELECT
            p.category,
            EXTRACT(YEAR FROM o.order_date) AS year,
            EXTRACT(MONTH FROM o.order_date) AS month,
            SUM(o.unit_price * o.quantity) AS revenue
        FROM raw_orders o
        JOIN raw_products p ON o.product_id = p.product_id
        WHERE o.is_refunded = FALSE
        GROUP BY p.category, EXTRACT(YEAR FROM o.order_date), EXTRACT(MONTH FROM o.order_date)
    )
    SELECT
        category,
        year,
        month,
        revenue,
        LAG(revenue) OVER (PARTITION BY category ORDER BY year, month) AS previous_month_revenue,
        CASE
            WHEN LAG(revenue) OVER (PARTITION BY category ORDER BY year, month) IS NULL THEN NULL
            ELSE (revenue - LAG(revenue) OVER (PARTITION BY category ORDER BY year, month)) / LAG(revenue) OVER (PARTITION BY category ORDER BY year, month) * 100
        END AS revenue_growth_pct
    FROM monthly_revenue

