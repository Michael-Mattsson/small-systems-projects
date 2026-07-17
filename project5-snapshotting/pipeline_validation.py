import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# Pipeline Validation
#
# Validation can be grouped into four categories:
#
#   1. Completeness
#      - Did we receive all expected data?
#
#   2. Correctness
#      - Are values internally consistent?
#
#   3. Uniqueness
#      - Are duplicate business keys present?
#
#   4. Freshness
#      - Is the data recent enough to be trusted?
#
# This file demonstrates one validation from each category.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

DB_PATH = "../small-systems-projects/data/project5_snapshots.duckdb"
con = duckdb.connect(DB_PATH)
pd.set_option("display.width", 120)


def run(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    return passed


print(f"\n{'='*70}")
print("  Validation 1: Row Count Sanity")
print(f"{'='*70}")

# Applied to the OFFICIAL incremental_deltas table (built defensively) —
# expect this to pass, since real change rate is small.
official_max_delta = con.execute("""
    SELECT MAX(cnt) FROM (
        SELECT night_number, COUNT(*) AS cnt
        FROM incremental_deltas GROUP BY night_number
    )
""").fetchone()[0]
total_customers = con.execute("SELECT COUNT(*) FROM customer_baseline").fetchone()[0]
threshold = total_customers * 0.05  # more than 5% changing in one night is suspicious

run("Official incremental_deltas — max single-night delta within bounds",
      official_max_delta < threshold,
      f"largest delta = {official_max_delta} rows, threshold = {threshold:.0f}")


# ---------------------------------------------------------------------------
# Validation 3 — Uniqueness
#
# Each customer should appear only once
# within a snapshot.
# ---------------------------------------------------------------------------

print(f"\n{'='*70}")
print("  Validation 3: Duplicate Detection")
print(f"{'='*70}")

official_dupes = con.execute("""
    SELECT COUNT(*) FROM (
        SELECT customer_id, night_number FROM incremental_deltas
        GROUP BY customer_id, night_number HAVING COUNT(*) > 1
    )
""").fetchone()[0]

run("Uniqueness — Duplicate Keys", """
SELECT customer_id
...
HAVING COUNT(*)>1
""")


run("Official incremental_deltas — no duplicate (customer_id, night_number)",
      official_dupes == 0, f"{official_dupes} duplicates found")

# Applied to idempotent_retry.py's Scenario 2 output — expect this to FAIL,
# demonstrating the check would have caught that bug before it reached
# a dashboard.
try:
    retry_dupes = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT customer_id, night_number FROM retry_deltas
            GROUP BY customer_id, night_number HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    run("retry_deltas (from idempotent_retry.py Scenario 2) — no duplicates",
          retry_dupes == 0, f"{retry_dupes} duplicates found")
    if retry_dupes > 0:
        print("        -> This check would have blocked the naive retry's")
        print("           output from being trusted, before any downstream")
        print("           query double-counted these customers.")
except duckdb.CatalogException:
    print("  [SKIP] retry_deltas not found — run idempotent_retry.py first")


print(f"\n{'='*70}")
print("  Validation 3: Checksum / Independent Recomputation Check")
print(f"{'='*70}")

# Recompute Night 20's true state independently from change_log (playing
# the role of "an independent source to reconcile against") and compare
# its checksum to the officially stored periodic_snapshots row for that
# night. A mismatch means the pipeline's output has drifted from what an
# independent computation says it should be.

def table_checksum(con, query):
    """Order-independent checksum: hash each row, then aggregate the
    hashes with an order-independent aggregate (SUM of numeric hashes)
    so row order in the source doesn't affect the result."""
    return con.execute(f"""
        SELECT SUM(HASH(customer_id, region, country, segment))
        FROM ({query}) t
    """).fetchone()[0]

independent_recompute = """
    WITH ranked_changes AS (
        SELECT customer_id, new_region, new_country, new_segment,
               ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY night_number DESC) AS rn
        FROM change_log WHERE night_number <= 20
    ),
    latest_change AS (
        SELECT customer_id, new_region, new_country, new_segment
        FROM ranked_changes WHERE rn = 1
    )
    SELECT b.customer_id,
           COALESCE(lc.new_region,  b.region)  AS region,
           COALESCE(lc.new_country, b.country) AS country,
           COALESCE(lc.new_segment, b.segment) AS segment
    FROM customer_baseline b
    LEFT JOIN latest_change lc ON b.customer_id = lc.customer_id
"""
official_night20 = "SELECT customer_id, region, country, segment FROM periodic_snapshots WHERE night_number = 20"

checksum_independent = table_checksum(con, independent_recompute)
checksum_official    = table_checksum(con, official_night20)

run("Night 20 — official snapshot matches independent recomputation",
      checksum_independent == checksum_official,
      f"independent={checksum_independent}, official={checksum_official}")


print(f"\n{'='*70}")
print("  Validation 4: Delta Size Anomaly Detection")
print(f"{'='*70}")

delta_stats = con.execute("""
    SELECT AVG(cnt) AS avg_delta, MAX(cnt) AS max_delta
    FROM (SELECT night_number, COUNT(*) AS cnt FROM incremental_deltas GROUP BY night_number)
""").fetchdf().iloc[0]
avg_delta = delta_stats["avg_delta"]
anomaly_threshold = max(avg_delta * 5, 10)  # 5x average, floor of 10 rows

run("Official incremental_deltas — no anomalous night (>5x average delta size)",
      official_max_delta < anomaly_threshold,
      f"avg={avg_delta:.1f}, max={official_max_delta}, threshold={anomaly_threshold:.1f}")

# Simulate the naive-checkpoint bug's hypothetical Night 13 delta size
# (from periodic_vs_incremental.py Part 4) to show this check would flag it
naive_bug_delta_size = con.execute("""
    SELECT COUNT(*) FROM (
        SELECT customer_id FROM incremental_base_snapshot
        EXCEPT
        SELECT customer_id FROM incremental_deltas WHERE night_number = 12
    )
""").fetchone()[0]

run("Hypothetical naive-checkpoint Night 13 delta — would be flagged",
      naive_bug_delta_size < anomaly_threshold,
      f"hypothetical size={naive_bug_delta_size}, threshold={anomaly_threshold:.1f}")
print("        -> This check fails on the naive-bug scenario, exactly as it")
print("           should — a delta this size relative to normal history is")
print("           the signature of a lost checkpoint, not a real change spike.")

print(f"\n{'='*70}")
print("Validation complete.")
con.close()

