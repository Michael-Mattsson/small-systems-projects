import duckdb
import random
from datetime import date, timedelta

con = duckdb.connect('data/finmart.duckdb')

# Generate dates
con.execute("""
CREATE OR REPLACE TABLE raw_orders AS
SELECT
    ROW_NUMBER() OVER () as order_id,
    (DATE '2022-01-01' + INTERVAL (RANDOM() * 730) DAY)::DATE as order_date,
    FLOOR(RANDOM() * 10000 + 1)::INT as customer_id,
    FLOOR(RANDOM() * 500 + 1)::INT as product_id,
    FLOOR(RANDOM() * 10 + 1)::INT as quantity,
    ROUND((RANDOM() * 200 + 5)::NUMERIC, 2) as unit_price,
    CASE WHEN RANDOM() < 0.05 THEN TRUE ELSE FALSE END as is_refunded
FROM RANGE(200000)
""")