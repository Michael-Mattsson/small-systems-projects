import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# Metric Inflation — Detection Runner
#
# Executes the three-step diagnostic sequence from detect_inflation.sql
# and prints the actual measured inflation from the generated data —
# not an assumed or invented figure.
# ---------------------------------------------------------------------------

DB_PATH = "../small-systems-projects/data/project4_inflation.duckdb"

con = duckdb.connect(DB_PATH)
pd.set_option("display.float_format", "{:,.2f}".format)
pd.set_option("display.width", 120)


def run(label, query):
    print(f"\n{'='*65}")
    print(f"  {label}")
    print(f"{'='*65}")
    result = con.execute(query).fetchdf()
    print(result.to_string(index=False))


# ---------------------------------------------------------------------------
# Step 1: Row count comparison
# ---------------------------------------------------------------------------

run("Step 1: Row count — before vs after the broken join", """
    SELECT 'fct_orders (baseline)' AS stage, COUNT(*) AS row_count
    FROM fct_orders
    UNION ALL
    SELECT 'fct_orders LEFT JOIN promotions', COUNT(*)
    FROM fct_orders o
    LEFT JOIN promotions p ON o.customer_id = p.customer_id
""")


# ---------------------------------------------------------------------------
# Step 2: Affected customers by promo count
# ---------------------------------------------------------------------------

run("Step 2: Customers grouped by promotion count", """
    SELECT
        promo_count,
        COUNT(*) AS customer_count
    FROM (
        SELECT customer_id, COUNT(*) AS promo_count
        FROM promotions
        GROUP BY customer_id
    )
    GROUP BY promo_count
    ORDER BY promo_count
""")


# ---------------------------------------------------------------------------
# Step 3: Correct quantification of aggregate inflation
# ---------------------------------------------------------------------------

run("Step 3: Aggregate revenue inflation — correct vs broken join", """
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
    FROM correct_revenue c, inflated_revenue i
""")

run("Worst-affected customers — inflation factor by promo count", """
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
        FROM promotions GROUP BY customer_id
    )
    SELECT
        c.customer_id,
        COALESCE(pc.promo_count, 0)                                 AS promo_count,
        c.correct_rows, b.inflated_rows,
        ROUND(c.correct_revenue, 2)                                 AS correct_revenue,
        ROUND(b.inflated_revenue, 2)                                AS inflated_revenue,
        ROUND(b.inflated_revenue / NULLIF(c.correct_revenue, 0), 2) AS inflation_factor
    FROM correct c
    JOIN broken b       ON c.customer_id = b.customer_id
    LEFT JOIN promo_counts pc ON c.customer_id = pc.customer_id
    WHERE COALESCE(pc.promo_count, 0) >= 2
    ORDER BY inflation_factor DESC
    LIMIT 10
""")

print("\nDetection complete.")
con.close()