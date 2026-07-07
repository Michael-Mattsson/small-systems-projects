import duckdb
import os

# ---------------------------------------------------------------------------
# Metric Inflation — Promotions Table Builder
#
# Generates a promotions table with a deliberately realistic multi-promo
# distribution: most customers have 0 or 1 active promotion, a smaller
# group has 2, and a small group has 3+. This mirrors how the bug actually
# happens in production — a promotions feature is added for a subset of
# customers running concurrent campaigns, and the join is written without
# a grain guard.
#
# Input:  ../small-systems-projects/data/project1_finmart.duckdb
# Output: ../small-systems-projects/data/project4_inflation.duckdb
# ---------------------------------------------------------------------------

SOURCE_DB     = "../small-systems-projects/data/project1_finmart.duckdb"
INFLATION_DB  = "../small-systems-projects/data/project4_inflation.duckdb"

os.makedirs("../small-systems-projects/data", exist_ok=True)

con = duckdb.connect(INFLATION_DB)

print("Attaching Project 1 database...")
con.execute(f"ATTACH '{SOURCE_DB}' AS src (READ_ONLY)")

print("Copying fact and dimension tables unchanged...")
con.execute("CREATE OR REPLACE TABLE fct_orders   AS SELECT * FROM src.fct_orders")
con.execute("CREATE OR REPLACE TABLE dim_customer AS SELECT * FROM src.dim_customer")
con.execute("CREATE OR REPLACE TABLE dim_product  AS SELECT * FROM src.dim_product")
con.execute("CREATE OR REPLACE TABLE dim_date     AS SELECT * FROM src.dim_date")

con.execute("DETACH src")

# ---------------------------------------------------------------------------
# Build promotions with a controlled multi-promo distribution:
#   ~50% of customers: 0 active promotions (no row in this table)
#   ~30% of customers: 1 active promotion
#   ~15% of customers: 2 active promotions
#   ~5%  of customers: 3 active promotions
#
# Using customer_key modulo buckets rather than pure RANDOM() makes the
# distribution deterministic and reproducible across reruns — matching
# the approach used for customer attribute generation in Projects 1 and 3.
# ---------------------------------------------------------------------------

print("Building promotions table...")
con.execute("""
CREATE OR REPLACE TABLE promotions AS
WITH promo_bucket AS (
    SELECT
        customer_id,
        customer_key % 20 AS bucket
    FROM dim_customer
),
promo_counts AS (
    SELECT
        customer_id,
        CASE
            WHEN bucket < 10 THEN 0   -- 50% no promotions
            WHEN bucket < 16 THEN 1   -- 30% one promotion
            WHEN bucket < 19 THEN 2   -- 15% two promotions
            ELSE 3                    -- 5% three promotions
        END AS promo_count
    FROM promo_bucket
),
expanded AS (
    SELECT
        customer_id,
        UNNEST(RANGE(promo_count)) AS promo_index
    FROM promo_counts
    WHERE promo_count > 0
)
SELECT
    customer_id,
    CASE promo_index
        WHEN 0 THEN 'PROMO_A'
        WHEN 1 THEN 'PROMO_B'
        ELSE        'PROMO_C'
    END AS promo_code,
    CASE promo_index
        WHEN 0 THEN 0.10
        WHEN 1 THEN 0.15
        ELSE        0.20
    END AS discount_pct,
    DATE '2023-01-01' + CAST(HASH(customer_id, promo_index) % 365 AS INT) * INTERVAL 1 DAY
        AS promo_start
FROM expanded
""")

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

print("\n--- Promotion Distribution ---")
dist = con.execute("""
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
""").fetchdf()
print(dist.to_string(index=False))

total_customers = con.execute("SELECT COUNT(*) FROM dim_customer").fetchone()[0]
customers_with_promo = con.execute("SELECT COUNT(DISTINCT customer_id) FROM promotions").fetchone()[0]
print(f"\nTotal customers: {total_customers:,}")
print(f"Customers with at least one promotion: {customers_with_promo:,}")
print(f"Customers with zero promotions: {total_customers - customers_with_promo:,}")

print(f"\nDone. Database written to: {INFLATION_DB}")
con.close()