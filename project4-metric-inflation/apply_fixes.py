import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# Metric Inflation — Fix Verification Runner
#
# Applies all three fixes and compares each against the baseline
# (fct_orders with no join). All four numbers must match — if any fix
# produces a different total, that fix has its own bug.
# ---------------------------------------------------------------------------

DB_PATH = "../small-systems-projects/data/project4_inflation.duckdb"

con = duckdb.connect(DB_PATH)
pd.set_option("display.float_format", "{:,.2f}".format)


def get_revenue(label, query):
    result = con.execute(query).fetchone()[0]
    print(f"  {label:<40} {result:>15,.2f}")
    return result


print("\n--- Revenue Comparison: Baseline vs Broken vs Fixes ---\n")

baseline = get_revenue(
    "Baseline (no join, correct)",
    "SELECT SUM(net_revenue) FROM fct_orders"
)

broken = get_revenue(
    "Broken (unbounded join)",
    """
    SELECT SUM(o.net_revenue)
    FROM fct_orders o
    LEFT JOIN promotions p ON o.customer_id = p.customer_id
    """
)

fix1 = get_revenue(
    "Fix 1 (dedupe before join)",
    """
    WITH ranked_promos AS (
        SELECT customer_id, promo_code, discount_pct,
               ROW_NUMBER() OVER (
                   PARTITION BY customer_id ORDER BY promo_start DESC
               ) AS rn
        FROM promotions
    ),
    latest_promo AS (
        SELECT customer_id FROM ranked_promos WHERE rn = 1
    )
    SELECT SUM(o.net_revenue)
    FROM fct_orders o
    LEFT JOIN latest_promo p ON o.customer_id = p.customer_id
    """
)

fix2 = get_revenue(
    "Fix 2 (aggregate before join)",
    """
    WITH promo_summary AS (
        SELECT customer_id, COUNT(*) AS promo_count, MAX(discount_pct) AS max_discount
        FROM promotions GROUP BY customer_id
    )
    SELECT SUM(o.net_revenue)
    FROM fct_orders o
    LEFT JOIN promo_summary p ON o.customer_id = p.customer_id
    """
)

fix3 = get_revenue(
    "Fix 3 (fact grain, attribution join)",
    """
    WITH order_promo_attribution AS (
        SELECT
            o.order_id, o.net_revenue,
            ROW_NUMBER() OVER (
                PARTITION BY o.order_id ORDER BY p.promo_start DESC
            ) AS rn
        FROM fct_orders o
        LEFT JOIN promotions p
            ON  o.customer_id = p.customer_id
            AND p.promo_start <= (SELECT date FROM dim_date d WHERE d.date_key = o.date_key)
    )
    SELECT SUM(net_revenue) FROM order_promo_attribution WHERE rn = 1
    """
)

print("\n--- Verification ---")
tolerance = 0.01
for label, value in [("Fix 1", fix1), ("Fix 2", fix2), ("Fix 3", fix3)]:
    status = "PASS" if abs(value - baseline) < tolerance else "FAIL"
    print(f"  {label} matches baseline: {status}  (diff: {value - baseline:,.2f})")

inflation_pct = (broken - baseline) / baseline * 100
print(f"\nBroken join inflated revenue by {inflation_pct:.2f}% "
      f"({broken - baseline:,.2f} absolute)")

con.close()