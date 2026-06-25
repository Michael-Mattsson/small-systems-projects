import duckdb
import pandas as pd
import os


# ---------------------------------------------------------------------------
# FinMart Star Schema — Validation Queries
# Runs all analytical queries against the star schema (not raw tables).
# All joins go through surrogate keys. Revenue uses precomputed columns
# from fct_orders rather than recalculating at query time.
#
# Each query is labeled with what it validates about the schema design.
# ---------------------------------------------------------------------------


DB_PATH = "data/project1_finmart.duckdb"
print("Database exists:", os.path.exists(DB_PATH))
con = duckdb.connect(DB_PATH)


pd.set_option("display.float_format", "{:,.2f}".format)
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 120)


def run(label, query):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = con.execute(query).fetchdf()
    print(result.to_string(index=False))


# Build warehouse
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(
    os.path.join(BASE_DIR, "build_schema.sql"),
    "r",
    encoding="utf-8"
) as f:
    con.execute(f.read())

print("Star schema built.")


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


print(con.execute("""
SELECT table_schema, table_name
FROM information_schema.tables
""").fetchdf())


run("Row counts across all tables", """
    SELECT 'raw_orders'  AS table_name, COUNT(*) AS rows FROM raw_orders
    UNION ALL SELECT 'dim_date',     COUNT(*) FROM dim_date
    UNION ALL SELECT 'dim_customer', COUNT(*) FROM dim_customer
    UNION ALL SELECT 'dim_product',  COUNT(*) FROM dim_product
    UNION ALL SELECT 'fct_orders',   COUNT(*) FROM fct_orders
""")

run("FK integrity — unmatched keys in fct_orders (expect all zeros)", """
    SELECT 'unmatched_dates'     AS check_name,
           COUNT(*)              AS unmatched_rows
    FROM fct_orders
    WHERE date_key NOT IN (SELECT date_key FROM dim_date)
    UNION ALL
    SELECT 'unmatched_customers', COUNT(*)
    FROM fct_orders
    WHERE customer_key NOT IN (SELECT customer_key FROM dim_customer)
    UNION ALL
    SELECT 'unmatched_products',  COUNT(*)
    FROM fct_orders
    WHERE product_key NOT IN (SELECT product_key FROM dim_product)
""")


# How many orders in total

result = con.execute("SELECT COUNT(*) AS total_orders FROM raw_orders").fetchdf()
print(result)

# .fetchdf() returns a pandas DataFrame which prints nicely in the terminal
# .fetchall() for raw tuples but DataFrames are much more readable.


# Total revenue

result = con.execute("""
    SELECT SUM(unit_price * quantity) AS total_revenue \
    FROM raw_orders
    WHERE is_refunded = FALSE
""").fetchdf()
print(result.to_string(index=False))


# Revenue by product category by quarter, excluding refunds

print("\n\n" + "Revenue by product category by quarter, excluding refunds" + "\n")
result = con.execute("""
    SELECT
        p.category,
        EXTRACT(QUARTER FROM o.order_date) AS quarter,
        SUM(o.unit_price * o.quantity) AS revenue
    FROM raw_orders o
    JOIN raw_products p ON o.product_id = p.product_id
    WHERE o.is_refunded = FALSE
    GROUP BY p.category, EXTRACT(QUARTER FROM o.order_date)
    ORDER BY p.category, quarter
""").fetchdf()
print(result.to_string(index=False))


# Top 10 customers by net revenue in 2023

print("\n\n" + "Top 10 customers by net revenue in 2023" + "\n")
result = con.execute("""
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
""").fetchdf()
print(result.to_string(index=False)) 


# Weekend vs weekday revenue comparison by region

print("\n\n" + "Weekend vs weekday revenue comparison by region" + "\n")
result = con.execute("""
    SELECT
        c.region,
        CASE WHEN EXTRACT(DOW FROM o.order_date) IN (0, 6) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
        SUM(o.unit_price * o.quantity) AS revenue
    FROM raw_orders o
    JOIN raw_customers c ON o.customer_id = c.customer_id
    WHERE o.is_refunded = FALSE
    GROUP BY c.region, day_type
""").fetchdf()
print(result.to_string(index=False)) 


# Month-over-month revenue growth by category

print("\n\n" + "Month-over-month revenue growth by category" + "\n")
result = con.execute("""
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
""").fetchdf()
print(result.to_string(index=False)) 