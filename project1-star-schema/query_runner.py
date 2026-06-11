import duckdb
import pandas as pd


con = duckdb.connect('data/finmart.duckdb')

# All columns

result = con.execute("SELECT * FROM raw_orders LIMIT 5").fetchdf()
print(result)


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
print(result)




