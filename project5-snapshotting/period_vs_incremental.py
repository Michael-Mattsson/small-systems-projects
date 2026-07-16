import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# Snapshotting — Periodic vs Incremental Analysis
#
# Three parts:
#   1. Storage comparison — total rows, ratio
#   2. Gap detection — which nights are missing, for each strategy
#   3. Reconstruction under the gap — what "as of Night 12" queries
#      actually return, for periodic (naive vs as-of) and incremental,
#      verified against true ground truth
#   4. Naive vs defensive incremental — demonstrates the corruption bug
#      that occurs when an incremental process diffs against a rigid
#      "night - 1" lookup instead of "last successful capture"
# ---------------------------------------------------------------------------

DB_PATH = "../small-systems-projects/data/project5_snapshots.duckdb"
FAILED_NIGHT = 12

con = duckdb.connect(DB_PATH)
pd.set_option("display.float_format", "{:,.2f}".format)
pd.set_option("display.width", 120)


def run(label, query):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    result = con.execute(query).fetchdf()
    print(result.to_string(index=False))


# ---------------------------------------------------------------------------
# Part 1: Storage comparison
# ---------------------------------------------------------------------------

run("Storage — periodic vs incremental total rows", """
    SELECT 'periodic'    AS strategy, COUNT(*) AS total_rows FROM periodic_snapshots
    UNION ALL
    SELECT 'incremental (base + deltas)',
           (SELECT COUNT(*) FROM incremental_base_snapshot)
         + (SELECT COUNT(*) FROM incremental_deltas)
""")

periodic_rows = con.execute("SELECT COUNT(*) FROM periodic_snapshots").fetchone()[0]
incremental_rows = con.execute("""
    SELECT (SELECT COUNT(*) FROM incremental_base_snapshot)
         + (SELECT COUNT(*) FROM incremental_deltas)
""").fetchone()[0]
print(f"\nStorage reduction: {periodic_rows / incremental_rows:.1f}x fewer rows "
      f"with incremental snapshotting")


# ---------------------------------------------------------------------------
# Part 2: Gap detection
#
# A calendar spine anti-joined against successful snapshot_log entries
# finds missing nights. This method is robust to BOTH logged failures
# (status='failed') and completely silent failures (no log row at all) —
# it only checks for the ABSENCE of a success record, which covers both
# cases identically. This robustness is itself worth noting: a detection
# query that only checked for status='failed' rows would miss a
# pipeline that crashed before writing any log entry at all.
# ---------------------------------------------------------------------------

run("Gap detection — nights missing a successful snapshot", """
    WITH night_spine AS (
        SELECT UNNEST(RANGE(1, 31)) AS night_number
    )
    SELECT
        s.night_number,
        MAX(CASE WHEN l.snapshot_type = 'periodic'    AND l.status = 'success'
                  THEN 1 ELSE 0 END) AS periodic_success,
        MAX(CASE WHEN l.snapshot_type = 'incremental' AND l.status = 'success'
                  THEN 1 ELSE 0 END) AS incremental_success
    FROM night_spine s
    LEFT JOIN snapshot_log l ON s.night_number = l.night_number
    GROUP BY s.night_number
    HAVING MAX(CASE WHEN l.snapshot_type = 'periodic'    AND l.status = 'success' THEN 1 ELSE 0 END) = 0
        OR MAX(CASE WHEN l.snapshot_type = 'incremental' AND l.status = 'success' THEN 1 ELSE 0 END) = 0
    ORDER BY s.night_number
""")


# ---------------------------------------------------------------------------
# Part 3: Reconstruction under the gap — "what did it look like on Night 12?"
# ---------------------------------------------------------------------------

run("PERIODIC — naive exact-match query for Night 12 (dangerous)", """
    SELECT COUNT(*) AS rows_returned
    FROM periodic_snapshots
    WHERE night_number = 12
""")
print("  -> Returns 0 rows. An analyst unfamiliar with the gap could easily")
print("     misread this as 'zero customers existed that night' rather than")
print("     'the snapshot for that night was never captured.'")

run("PERIODIC — correct 'as of' query for Night 12 (explicit fallback)", """
    WITH latest_available AS (
        SELECT MAX(night_number) AS fallback_night
        FROM periodic_snapshots
        WHERE night_number <= 12
    )
    SELECT
        la.fallback_night AS reconstructed_as_of_night,
        p.customer_id, p.region, p.country, p.segment
    FROM latest_available la
    JOIN periodic_snapshots p ON p.night_number = la.fallback_night
    LIMIT 5
""")
print("  -> Falls back to Night 11 and is explicit about it via the")
print("     reconstructed_as_of_night column — honest about staleness")
print("     rather than silently pretending to answer for Night 12.")

run("INCREMENTAL — reconstruction as of Night 12 (base + deltas <= 12)", """
    WITH applicable_deltas AS (
        SELECT customer_id, region, country, segment,
               ROW_NUMBER() OVER (
                   PARTITION BY customer_id ORDER BY night_number DESC
               ) AS rn
        FROM incremental_deltas
        WHERE night_number <= 12
    ),
    latest_delta AS (
        SELECT customer_id, region, country, segment
        FROM applicable_deltas WHERE rn = 1
    )
    SELECT
        b.customer_id,
        COALESCE(d.region,  b.region)  AS region,
        COALESCE(d.country, b.country) AS country,
        COALESCE(d.segment, b.segment) AS segment
    FROM incremental_base_snapshot b
    LEFT JOIN latest_delta d ON b.customer_id = d.customer_id
    LIMIT 5
""")
print("  -> Naturally uses whatever deltas exist for nights <= 11, since")
print("     night 12 has none. Also effectively 'as of Night 11' — but")
print("     unlike periodic, nothing in the query surfaces that this is")
print("     stale unless you separately check snapshot_log.")


# ---------------------------------------------------------------------------
# Part 4: Naive vs defensive incremental — the corruption bug
#
# Naive: night 13's job rigidly looks up "night_number = 12" as its
# comparison baseline. Since that doesn't exist, the comparison baseline
# is empty — every customer in night 13's true state appears to have
# "no prior row," which a naive process would treat as "everything
# changed." This produces a delta the size of the full table instead
# of a handful of rows — a clear, quantifiable red flag.
#
# Defensive (already built in build_snapshot_history.py): diffs against
# tracking_state, which reflects Night 11 (the last successful capture).
# Correctly identifies only the true handful of changes across nights
# 12 and 13 combined.
# ---------------------------------------------------------------------------

run("NAIVE incremental — Night 13 delta if diffed against missing Night 12", """
    WITH night_12_lookup AS (
        -- Simulates a rigid process fetching "night_number = 12" directly
        -- from incremental_deltas as its comparison baseline. This is
        -- empty, since night 12's job failed.
        SELECT customer_id, region, country, segment
        FROM incremental_deltas
        WHERE night_number = 12
    )
    SELECT COUNT(*) AS naive_night13_delta_row_count
    FROM (
        SELECT customer_id FROM incremental_base_snapshot
        EXCEPT
        SELECT customer_id FROM night_12_lookup
    )
""")
print("  -> Every customer appears 'changed' because the comparison")
print("     baseline is empty. A naive incremental process would write")
print("     ~10,000 rows for what should be a 1-2 row delta.")

run("DEFENSIVE incremental — actual Night 13 delta (correct)", """
    SELECT COUNT(*) AS defensive_night13_delta_row_count
    FROM incremental_deltas
    WHERE night_number = 13
""")
print("  -> Correctly small, because build_snapshot_history.py's tracking_state")
print("     diffed against Night 11 (last successful capture), bundling any")
print("     Night 12 changes into this delta without corruption.")


# ---------------------------------------------------------------------------
# Verification against ground truth
# ---------------------------------------------------------------------------

run("Verification — reconstructed Night 20 vs true Night 20 state (should match)", """
    WITH true_state AS (
        WITH ranked_changes AS (
            SELECT customer_id, new_region, new_country, new_segment,
                   ROW_NUMBER() OVER (
                       PARTITION BY customer_id ORDER BY night_number DESC
                   ) AS rn
            FROM change_log WHERE night_number <= 20
        ),
        latest_change AS (
            SELECT customer_id, new_region FROM ranked_changes WHERE rn = 1
        )
        SELECT b.customer_id, COALESCE(lc.new_region, b.region) AS region
        FROM customer_baseline b
        LEFT JOIN latest_change lc ON b.customer_id = lc.customer_id
    ),
    reconstructed AS (
        SELECT customer_id, region FROM periodic_snapshots WHERE night_number = 20
    )
    SELECT
        COUNT(*) AS mismatches
    FROM true_state t
    JOIN reconstructed r ON t.customer_id = r.customer_id
    WHERE t.region != r.region
""")
print("  -> Expect 0 mismatches for a night where the snapshot job succeeded.")

print("\nAnalysis complete.")
con.close()