import duckdb

con = duckdb.connect('data/finmart.duckdb')

con.execute("""
SELECT COUNT(*) FROM raw_orders;
""").fetchall()