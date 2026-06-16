import duckdb
import os

# ---------------------------------------------------------------------------
# FinMart Sales Data — Synthetic Data Generation
# Generates raw source tables simulating an e-commerce order system.
# Produces 300k orders across 10k customers and 500 products (2022–2023).
#
# Output: data/finmart.duckdb
# Tables: raw_orders, raw_customers, raw_products
# ---------------------------------------------------------------------------

DB_PATH = "data/finmart.duckdb"
os.makedirs("data", exist_ok=True)

con = duckdb.connect(DB_PATH)


# Orders table
con.execute("""
CREATE OR REPLACE TABLE raw_orders AS
SELECT
    ROW_NUMBER() OVER ()                                       AS order_id,
    (DATE '2022-01-01' + INTERVAL (RANDOM() * 730) DAY)::DATE  AS order_date,
    FLOOR(RANDOM() * 10000 + 1)::INT                           AS customer_id,
    FLOOR(RANDOM() * 500  + 1)::INT                            AS product_id,
    FLOOR(RANDOM() * 10   + 1)::INT                            AS quantity,
    ROUND((RANDOM() * 200 + 5)::NUMERIC, 2)                    AS unit_price,
    CASE WHEN RANDOM() < 0.05 THEN TRUE ELSE FALSE END         AS is_refunded
FROM RANGE(300000)
""")


# Customers table
con.execute("""
CREATE OR REPLACE TABLE raw_customers AS
SELECT
    customer_id,
    CASE
        WHEN RANDOM() < 0.22 THEN 'North'
        WHEN RANDOM() < 0.50 THEN 'South'
        WHEN RANDOM() < 0.82 THEN 'East'
        ELSE                      'West'
    END AS region,
    CASE
        WHEN RANDOM() < 0.23 THEN 'Finland'
        WHEN RANDOM() < 0.71 THEN 'Sweden'
        ELSE                      'Norway'
    END AS country,
    CASE
        WHEN RANDOM() < 0.60 THEN 'Consumer'
        WHEN RANDOM() < 0.90 THEN 'Business'
        ELSE                      'Enterprise'
    END AS segment
FROM (
    SELECT DISTINCT customer_id
    FROM raw_orders
)
""")


# Products table
con.execute("""
CREATE OR REPLACE TABLE raw_products AS
SELECT
    product_id,
    CONCAT('Product_', product_id)                             AS product_name,
    CASE
        WHEN product_id <= 110 THEN 'Electronics'
        WHEN product_id <= 265 THEN 'Home'
        WHEN product_id <= 325 THEN 'Sports'
        ELSE                        'Clothing'
    END AS category,
    CASE
        WHEN product_id % 20 < 8 THEN 'Premium'
        WHEN product_id % 20 < 15 THEN 'Standard'
        WHEN product_id % 20 < 18 THEN 'Budget'
        ELSE                         'Specialty'
    END AS subcategory,
    ROUND((RANDOM() * 100 + 2)::NUMERIC, 2)                     AS cost_price
FROM (
    SELECT DISTINCT product_id
    FROM raw_orders
)
""")

# ---------------------------------------------------------------------------
# Validation — confirm row counts and no nulls in key columns
# ---------------------------------------------------------------------------

checks = {
    "raw_orders row count":    "SELECT COUNT(*) FROM raw_orders",
    "raw_customers row count": "SELECT COUNT(*) FROM raw_customers",
    "raw_products row count":  "SELECT COUNT(*) FROM raw_products",
    "orders with null date":   "SELECT COUNT(*) FROM raw_orders WHERE order_date IS NULL",
    "orders with null price":  "SELECT COUNT(*) FROM raw_orders WHERE unit_price IS NULL",
    "customers with null region": "SELECT COUNT(*) FROM raw_customers WHERE region IS NULL",
}

for label, query in checks.items():
    result = con.execute(query).fetchone()[0]
    print(f"  {label}: {result}")

print("\nDone. Database written to:", DB_PATH)
con.close()











