import duckdb
import os

# ---------------------------------------------------------------------------
# Wide vs Narrow Benchmark — Table Builder
#
# Run this once before benchmark.py.
# Rerun if Project 1's data is regenerated at a new scale.
#
# Input:  ../small-systems-projects/data/project1_finmart.duckdb
# Output: ../small-systems-projects/data/project2_benchmark.duckdb
# ---------------------------------------------------------------------------

SOURCE_DB = "../small-systems-projects/data/project1_finmart.duckdb"
BENCHMARK_DB  = "../small-systems-projects/data/project2_benchmark.duckdb"

os.makedirs("../small-systems-projects/data", exist_ok=True)

con = duckdb.connect(BENCHMARK_DB)

print("Attaching Project 1 database...")
con.execute(f"ATTACH '{SOURCE_DB}' AS src (READ_ONLY)")

con.execute("CREATE OR REPLACE TABLE dim_date     AS SELECT * FROM src.dim_date")
con.execute("CREATE OR REPLACE TABLE dim_customer AS SELECT * FROM src.dim_customer")
con.execute("CREATE OR REPLACE TABLE dim_product  AS SELECT * FROM src.dim_product")
con.execute("CREATE OR REPLACE TABLE fct_orders   AS SELECT * FROM src.fct_orders")

con.execute("DETACH src")

print("Building wide_orders...")
con.execute("""
CREATE OR REPLACE TABLE wide_orders AS
SELECT
    o.order_id,
    d.date,
    d.year                AS order_year,
    d.quarter             AS order_quarter,
    d.month               AS order_month,
    d.is_weekend,
    c.customer_id,
    c.region,
    c.country,
    c.segment,
    p.product_id,
    p.name                AS product_name,
    p.category,
    p.subcategory,
    p.cost_price,
    o.quantity,
    o.unit_price,
    o.gross_revenue,
    o.is_refunded,
    o.net_revenue
FROM fct_orders o
JOIN dim_date     d ON o.date_key     = d.date_key
JOIN dim_customer c ON o.customer_key = c.customer_key
JOIN dim_product  p ON o.product_key  = p.product_key
""")

# -----------------------------------------------------------------------
# Post-build validation
# -----------------------------------------------------------------------

print("\n--- Post-Build Validation ---")

counts = con.execute("""
    SELECT 'fct_orders'   AS table_name, COUNT(*) AS row_count FROM fct_orders
    UNION ALL SELECT 'wide_orders',   COUNT(*) FROM wide_orders
    UNION ALL SELECT 'dim_date',      COUNT(*) FROM dim_date
    UNION ALL SELECT 'dim_customer',  COUNT(*) FROM dim_customer
    UNION ALL SELECT 'dim_product',   COUNT(*) FROM dim_product
""").fetchdf()
print(counts.to_string(index=False))

# fct_orders and wide_orders must have identical row counts.
# A mismatch means the wide table join dropped or duplicated rows.
fct_count  = con.execute("SELECT COUNT(*) FROM fct_orders").fetchone()[0]
wide_count = con.execute("SELECT COUNT(*) FROM wide_orders").fetchone()[0]

if fct_count == wide_count:
    print(f"\nRow count check passed: {fct_count:,} rows in both tables.")
else:
    print(f"\nWARNING: Row count mismatch.")
    print(f"  fct_orders:  {fct_count:,}")
    print(f"  wide_orders: {wide_count:,}")
    print("  Check wide_orders join conditions before running benchmark.")

# Storage comparison
print("\n--- Storage Comparison ---")
storage = con.execute("""
    SELECT
        'wide_orders' AS table_name,
        COUNT(*) AS row_count,
        SUM(LENGTH(region) + LENGTH(country) + LENGTH(segment)
            + LENGTH(category) + LENGTH(subcategory))::BIGINT
            AS duplicated_dim_attribute_bytes
    FROM wide_orders
    UNION ALL
    SELECT 'fct_orders', COUNT(*), NULL
    FROM fct_orders
""").fetchdf()
print(storage.to_string(index=False))

print(f"\nDone. Benchmark database written to: {BENCHMARK_DB}")
con.close()