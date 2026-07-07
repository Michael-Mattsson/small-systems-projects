import duckdb
import os

# ---------------------------------------------------------------------------
# SCD Type 2 Customer Dimension — Builder
#
# Extends Project 1's customer data with full Type 2 slowly changing
# dimension logic. Each customer attribute change creates a new row
# rather than overwriting the existing one, preserving full history
# for point-in-time reconstruction.
#
# Project 3 is built as a standalone database. The fact table and
# unchanged dimensions are copied from Project 1 so this project can be
# run independently without modifying the original warehouse.
#
# Customer attributes are deterministically generated from customer_id
# for reproducibility — the same input always produces the same dimension.
#
# Input:  ../small-systems-projects/data/project1_finmart.duckdb
# Output: ../small-systems-projects/data/project3_scd2.duckdb
# ---------------------------------------------------------------------------

SOURCE_DB = "../small-systems-projects/data/project1_finmart.duckdb"
SCD2_DB   = "../small-systems-projects/data/project3_scd2.duckdb"

os.makedirs("../small-systems-projects/data", exist_ok=True)

con = duckdb.connect(SCD2_DB)

print("Attaching Project 1 database...")
con.execute(f"ATTACH '{SOURCE_DB}' AS src (READ_ONLY)")

print("Copying fact and supporting tables, adding additional columns to fact table...")
con.execute("""
CREATE OR REPLACE TABLE fct_orders AS
SELECT
    f.*,
    d.date AS order_date,
    c.customer_id
FROM src.fct_orders f
JOIN src.dim_date d
    ON f.date_key = d.date_key
JOIN src.dim_customer c
    ON f.customer_key = c.customer_key
""")
con.execute("CREATE OR REPLACE TABLE dim_date    AS SELECT * FROM src.dim_date")
con.execute("CREATE OR REPLACE TABLE dim_customer AS SELECT * FROM src.dim_customer")
con.execute("CREATE OR REPLACE TABLE dim_product AS SELECT * FROM src.dim_product")

con.execute("DETACH src")

# ---------------------------------------------------------------------------
# Build dim_customer_scd2 — initial load
#
# All customers loaded with a single version covering the full history
# from 2022-01-01. valid_to = NULL means currently active.
#
# fct_orders stores customer_id (natural key), not a version-specific
# surrogate key. Because no surrogate key exists, all point-in-time joins 
# must use customer_id together with the validity date bounds 
# (valid_from, valid_to). 
# ---------------------------------------------------------------------------

print("Building dim_customer_scd2 (initial load)...")
con.execute("""
CREATE OR REPLACE TABLE dim_customer_scd2 AS
WITH base_customers AS (
    SELECT
        customer_id,
        region,
        country,
        segment
    FROM dim_customer
)
SELECT
    ROW_NUMBER() OVER (ORDER BY customer_id)  AS customer_key,
    customer_id,
    region,
    country,
    segment,
    DATE '2022-01-01'   AS valid_from,
    NULL::DATE          AS valid_to,
    TRUE                AS is_current
FROM base_customers
""")

# ---------------------------------------------------------------------------
# Current-state view
# Useful because most reporting only needs current attributes and 
# should not require SCD2 date logic.
# Equivalent to WHERE is_current = TRUE but cleaner in downstream queries.
# dim_customer_current provides Type-1 style access over a Type-2 dimension.
# ---------------------------------------------------------------------------

con.execute("""
CREATE OR REPLACE VIEW dim_customer_current AS
SELECT
    customer_key,
    customer_id,
    region,
    country,
    segment
FROM dim_customer_scd2
WHERE is_current = TRUE
""")

# ---------------------------------------------------------------------------
# Automated integrity checks — run after every load or change batch
# ---------------------------------------------------------------------------

print("\n--- Integrity Checks ---")

def assert_check(label, query, expected=0):
    result = con.execute(query).fetchone()[0]
    status = "PASS" if result == expected else f"FAIL (got {result}, expected {expected})"
    print(f"  {label}: {status}")
    if result != expected:
        raise ValueError(f"Integrity check failed: {label}")

assert_check(
    "No duplicate is_current records per customer",
    """
    SELECT COUNT(*) FROM (
        SELECT customer_id
        FROM dim_customer_scd2
        WHERE is_current = TRUE
        GROUP BY customer_id
        HAVING COUNT(*) > 1
    )
    """
)

assert_check(
    "No open records with is_current = FALSE",
    """
    SELECT COUNT(*)
    FROM dim_customer_scd2
    WHERE valid_to IS NULL AND is_current = FALSE
    """
)

assert_check(
    "No overlapping date ranges per customer",
    """
    SELECT COUNT(*) FROM (
        SELECT a.customer_id
        FROM dim_customer_scd2 a
        JOIN dim_customer_scd2 b
            ON  a.customer_id  = b.customer_id
            AND b.valid_from   > a.valid_from
            AND b.valid_from  <= a.valid_to
            AND a.valid_to    IS NOT NULL
            AND b.customer_key != a.customer_key
    )
    """
)

# Row counts
counts = con.execute("""
    SELECT
        COUNT(*)                                                  AS total_rows,
        COUNT(DISTINCT customer_id)                               AS distinct_customers,
        SUM(CASE WHEN is_current    THEN 1 ELSE 0 END)            AS current_records,
        SUM(CASE WHEN valid_to IS NULL THEN 1 ELSE 0 END)         AS open_records
    FROM dim_customer_scd2
""").fetchdf()

print("\n--- Initial Load Summary ---")
print(counts.to_string(index=False))
print(f"\nDone. SCD2 database written to: {SCD2_DB}")
con.close()