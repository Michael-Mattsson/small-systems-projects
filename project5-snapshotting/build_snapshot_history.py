import duckdb
import os

# ---------------------------------------------------------------------------
# Snapshotting — History Builder
#
# Scenario: FinMart's customer source system exposes only CURRENT state —
# no change history, no audit log. To reconstruct history, a nightly job
# polls the source and stores a snapshot. This script simulates 30 nights
# of that polling process under two snapshot strategies:
#
#   PERIODIC:    store a full copy of all ~10,000 customers every night.
#   INCREMENTAL: store a full copy once (Night 1), then only the rows
#                that changed since the last successfully captured night.
#
# A synthetic change_log (~45 customers changing on random nights) drives
# a hidden "true_nightly_state" — the ground truth of what the source
# system actually looked like each night. This ground truth is used only
# for verification; the snapshot processes never see it directly, exactly
# as a real nightly poller never sees the future or the true change log,
# only whatever the source shows at poll time.
#
# Night 12 is deliberately simulated as a failed job — no snapshot,
# periodic or incremental, is written for that night. This sets up the
# stale/missing snapshot debugging task in periodic_vs_incremental.py.
#
# Input:  ../small-systems-projects/data/project3_scd2.duckdb
# Output: ../small-systems-projects/data/project5_snapshots.duckdb
# ---------------------------------------------------------------------------

SOURCE_DB    = "../small-systems-projects/data/project3_scd2.duckdb"
SNAPSHOT_DB  = "../small-systems-projects/data/project5_snapshots.duckdb"

NUM_NIGHTS   = 30
FAILED_NIGHT = 12   # night on which both snapshot jobs fail to run

os.makedirs("../small-systems-projects/data", exist_ok=True)
con = duckdb.connect(SNAPSHOT_DB)


# ---------------------------------------------------------------------------
# Step 1: Establish the Night 1 baseline
#
# Project 3's dim_customer_scd2 current state becomes the starting point
# for a NEW 30-night monitoring window. This project does not reuse
# Project 3's specific change dates — it layers its own change events on
# top of Project 3's final state, treating "today" as Night 1 of a fresh
# nightly snapshot job.
# ---------------------------------------------------------------------------

print("Attaching Project 3 database...")
con.execute(f"ATTACH '{SOURCE_DB}' AS src (READ_ONLY)")

con.execute("""
CREATE OR REPLACE TABLE customer_baseline AS
SELECT customer_id, region, country, segment
FROM src.dim_customer_scd2
WHERE is_current = TRUE
""")

con.execute("DETACH src")

baseline_count = con.execute("SELECT COUNT(*) FROM customer_baseline").fetchone()[0]
print(f"Night 1 baseline: {baseline_count:,} customers")


# ---------------------------------------------------------------------------
# Step 2: Generate the ground-truth change log
#
# ~45 customers are deterministically selected to change on a random
# night between Night 2 and Night 30. This is the hidden ground truth —
# used only to compute what the source system actually looked like each
# night, and later to verify whether periodic/incremental reconstruction
# recovers the correct historical state. The snapshot-building logic
# below never reads this table directly except through the nightly
# "true state" query, mirroring how a poller only ever sees current state.
# ---------------------------------------------------------------------------

print("Generating synthetic change log...")
con.execute(f"""
CREATE OR REPLACE TABLE change_log AS
WITH candidates AS (
    SELECT customer_id, ROW_NUMBER() OVER (ORDER BY customer_id) AS rn
    FROM customer_baseline
),
selected AS (
    -- Deterministic ~1-in-217 selection yields ~45 customers out of ~10,000
    SELECT customer_id FROM candidates WHERE rn % 217 = 0
)
SELECT
    ROW_NUMBER() OVER (ORDER BY customer_id)               AS change_id,
    customer_id,
    2 + CAST(HASH(customer_id) % {NUM_NIGHTS - 1} AS INT)  AS night_number,
    CASE CAST(HASH(customer_id, 1) % 4 AS INT)
        WHEN 0 THEN 'North' WHEN 1 THEN 'South'
        WHEN 2 THEN 'East'  ELSE 'West'
    END AS new_region,
    CASE CAST(HASH(customer_id, 2) % 3 AS INT)
        WHEN 0 THEN 'Finland' WHEN 1 THEN 'Sweden' ELSE 'Norway'
    END AS new_country,
    CASE WHEN CAST(HASH(customer_id, 3) % 10 AS INT) < 6 THEN 'Consumer'
         WHEN CAST(HASH(customer_id, 3) % 10 AS INT) < 9 THEN 'Business'
         ELSE 'Enterprise'
    END AS new_segment
FROM selected
""")

change_count = con.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
print(f"Change log: {change_count} customers scheduled to change across nights 2-{NUM_NIGHTS}")


# ---------------------------------------------------------------------------
# Helper: compute the TRUE state of the dimension as of a given night
#
# This is ground truth — the actual state of the source system on that
# night, computed by applying all change_log entries with
# night_number <= target_night, most recent change per customer wins.
# Used both to drive the snapshot-building loop and, separately, for
# verification later.
# ---------------------------------------------------------------------------

def true_state_at_night(con, night_number):
    return con.execute(f"""
        WITH ranked_changes AS (
            SELECT
                customer_id, new_region, new_country, new_segment,
                ROW_NUMBER() OVER (
                    PARTITION BY customer_id ORDER BY night_number DESC
                ) AS rn
            FROM change_log
            WHERE night_number <= {night_number}
        ),
        latest_change AS (
            SELECT customer_id, new_region, new_country, new_segment
            FROM ranked_changes WHERE rn = 1
        )
        SELECT
            b.customer_id,
            COALESCE(lc.new_region,  b.region)  AS region,
            COALESCE(lc.new_country, b.country) AS country,
            COALESCE(lc.new_segment, b.segment) AS segment
        FROM customer_baseline b
        LEFT JOIN latest_change lc ON b.customer_id = lc.customer_id
    """).fetchdf()


# ---------------------------------------------------------------------------
# Step 3: Build PERIODIC snapshots
#
# Every night, store a full copy of all customers as they truly are that
# night. Night 12 is skipped entirely — simulating a failed job. Because
# periodic re-captures full state independently each night, this failure
# has a contained blast radius: Night 13 onward are entirely unaffected,
# since each periodic snapshot stands alone and doesn't depend on any
# prior night's snapshot.
# ---------------------------------------------------------------------------

print("\nBuilding periodic snapshots...")
con.execute("""
CREATE OR REPLACE TABLE periodic_snapshots (
    night_number INTEGER, customer_id INTEGER,
    region VARCHAR, country VARCHAR, segment VARCHAR
)
""")
con.execute("""
CREATE OR REPLACE TABLE snapshot_log (
    night_number INTEGER, snapshot_type VARCHAR,
    status VARCHAR, row_count INTEGER
)
""")

for night in range(1, NUM_NIGHTS + 1):
    if night == FAILED_NIGHT:
        con.execute(
            "INSERT INTO snapshot_log VALUES (?, 'periodic', 'failed', 0)",
            [night]
        )
        continue

    state = true_state_at_night(con, night)
    con.register("state_df", state)
    con.execute(f"""
        INSERT INTO periodic_snapshots
        SELECT {night} AS night_number, customer_id, region, country, segment
        FROM state_df
    """)
    con.execute(
        "INSERT INTO snapshot_log VALUES (?, 'periodic', 'success', ?)",
        [night, len(state)]
    )

periodic_total = con.execute("SELECT COUNT(*) FROM periodic_snapshots").fetchone()[0]
print(f"Periodic snapshots written: {periodic_total:,} total rows across "
      f"{NUM_NIGHTS - 1} successful nights (Night {FAILED_NIGHT} failed)")


# ---------------------------------------------------------------------------
# Step 4: Build INCREMENTAL snapshots (defensive design)
#
# Night 1: full base snapshot, no comparison needed.
# Nights 2-30: hash-compare current true state against the last
# SUCCESSFULLY captured state (not necessarily "yesterday" specifically),
# store only the rows that changed, then update the tracking state to
# reflect this night's capture.
#
# This "diff against last successful capture" design is what makes the
# process defensive: when Night 12 fails, Night 13's diff naturally
# compares against Night 11's tracked state, correctly bundling any
# Night 12 changes into Night 13's delta rather than losing them or
# corrupting the comparison. See periodic_vs_incremental.py for a
# contrasting "naive" implementation that does NOT have this property.
# ---------------------------------------------------------------------------

print("\nBuilding incremental snapshots (defensive design)...")

con.execute("""
CREATE OR REPLACE TABLE incremental_base_snapshot AS
SELECT customer_id, region, country, segment FROM customer_baseline
""")

# tracking_state mirrors "the last successfully captured state" —
# updated only on nights where the job actually succeeds
con.execute("""
CREATE OR REPLACE TABLE tracking_state AS
SELECT customer_id, region, country, segment FROM customer_baseline
""")

con.execute("""
CREATE OR REPLACE TABLE incremental_deltas (
    night_number INTEGER, customer_id INTEGER,
    region VARCHAR, country VARCHAR, segment VARCHAR
)
""")

for night in range(2, NUM_NIGHTS + 1):
    if night == FAILED_NIGHT:
        con.execute(
            "INSERT INTO snapshot_log VALUES (?, 'incremental', 'failed', 0)",
            [night]
        )
        continue

    true_state = true_state_at_night(con, night)
    con.register("true_state_df", true_state)

    changed = con.execute(f"""
        SELECT t.customer_id, t.region, t.country, t.segment
        FROM true_state_df t
        JOIN tracking_state ts ON t.customer_id = ts.customer_id
        WHERE MD5(CONCAT_WS('|', t.region, t.country, t.segment))
           != MD5(CONCAT_WS('|', ts.region, ts.country, ts.segment))
    """).fetchdf()

    con.register("changed_df", changed)
    con.execute(f"""
        INSERT INTO incremental_deltas
        SELECT {night} AS night_number, customer_id, region, country, segment
        FROM changed_df
    """)

    # Update tracking_state to this night's true state — this is the
    # defensive property: next night diffs against THIS state, whatever
    # night that ends up being.
    con.execute("""
        UPDATE tracking_state
        SET region = t.region, country = t.country, segment = t.segment
        FROM true_state_df t
        WHERE tracking_state.customer_id = t.customer_id
    """)

    con.execute(
        "INSERT INTO snapshot_log VALUES (?, 'incremental', 'success', ?)",
        [night, len(changed)]
    )

incremental_delta_rows = con.execute("SELECT COUNT(*) FROM incremental_deltas").fetchone()[0]
incremental_base_rows  = con.execute("SELECT COUNT(*) FROM incremental_base_snapshot").fetchone()[0]
print(f"Incremental base: {incremental_base_rows:,} rows (Night 1)")
print(f"Incremental deltas: {incremental_delta_rows} rows across nights 2-{NUM_NIGHTS} "
      f"(Night {FAILED_NIGHT} failed)")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

print("\n--- Storage Summary ---")
print(f"  Periodic total rows:              {periodic_total:,}")
print(f"  Incremental total rows (base+delta): {incremental_base_rows + incremental_delta_rows:,}")
print(f"  Storage ratio (periodic / incremental): "
      f"{periodic_total / (incremental_base_rows + incremental_delta_rows):.1f}x")

print(f"\nDone. Database written to: {SNAPSHOT_DB}")
con.close()