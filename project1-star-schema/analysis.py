import duckdb
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# FinMart Star Schema — Analysis
# Executes the analytical queries defined in analysis.sql against the
# completed star schema.
# ---------------------------------------------------------------------------

DB_PATH = "data/project1_finmart.duckdb"
SQL_PATH = Path(__file__).with_name("analysis.sql")

pd.set_option("display.float_format", "{:,.2f}".format)
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 140)

con = duckdb.connect(DB_PATH)


# ---------------------------------------------------------------------------
# Load SQL
# ---------------------------------------------------------------------------

sql = SQL_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Split SQL into individual analytical queries.
# ---------------------------------------------------------------------------

sections = sql.split("-- QUERY:")

queries = []

for section in sections[1:]:
    lines = section.strip().splitlines()
    title = lines[0].strip()
    query = "\n".join(lines[1:]).strip()
    queries.append((title, query))


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

for title, query in queries:

    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)

    print("QUERY BEING EXECUTED:")
    print(query)
    print("=" * 90)

    result = con.execute(query)

    print("EXECUTE RESULT:", result)

    df = result.fetchdf()

    print(df.to_string(index=False))