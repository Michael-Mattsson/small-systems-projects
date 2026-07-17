import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# Snapshot Pipeline Monitoring Dashboard
#
# This script simulates the type of operational dashboard an analytics
# engineer or senior data analyst might review each morning after the
# nightly snapshot pipeline has completed.
#
# Unlike pipeline_validation.py, which verifies correctness, this script
# answers:
#
#     "Is the pipeline operating normally?"
#
# It summarizes pipeline execution, storage efficiency, checkpoint
# progress, failures and validation status.
# ---------------------------------------------------------------------------

DB_PATH = "../small-systems-projects/data/project5_snapshots.duckdb"

con = duckdb.connect(DB_PATH)

pd.set_option("display.width", 120)


def section(title):
    print("\n")
    print("=" * 70)
    print(title)
    print("=" * 70)


# ---------------------------------------------------------------------------
# PIPELINE STATUS
# ---------------------------------------------------------------------------

section("Pipeline Status")

status = con.execute("""
    SELECT
        MAX(checkpoint_night)                           AS current_checkpoint,
        COUNT(*) FILTER(WHERE status='success')         AS successful_jobs,
        COUNT(*) FILTER(WHERE status='failed')          AS failed_jobs
    FROM snapshot_job_history
""").fetchdf()

print(status)


# ---------------------------------------------------------------------------
# STORAGE
# ---------------------------------------------------------------------------

section("Storage")

storage = con.execute("""
    SELECT
        (SELECT COUNT(*) FROM periodic_snapshots)       AS periodic_rows,
        (SELECT COUNT(*) FROM incremental_base_snapshot) +
        (SELECT COUNT(*) FROM incremental_deltas)       AS incremental_rows

""").fetchdf()

storage["storage_ratio"] = (
    storage["periodic_rows"]
    /
    storage["incremental_rows"]
)

print(storage)


# ---------------------------------------------------------------------------
# LATEST PIPELINE ACTIVITY
# ---------------------------------------------------------------------------

section("Latest Snapshot Activity")

activity = con.execute("""
    SELECT 
        MAX(night_number)                               AS latest_snapshot,
        COUNT(*)                                        AS rows_changed
    FROM incremental_deltas
    WHERE night_number = (SELECT MAX(night_number)
                           FROM incremental_deltas
                          )
""").fetchdf()

print(activity)


# ---------------------------------------------------------------------------
# PIPELINE WARNINGS
# ---------------------------------------------------------------------------

section("Warnings")

warnings = con.execute("""
    SELECT
        night_number,
        status
    FROM snapshot_job_history
    WHERE status='failed'
    ORDER BY night_number
""").fetchdf()

if len(warnings) == 0:
    print("No active warnings.")
else:
    print(warnings)


# ---------------------------------------------------------------------------
# PIPELINE HEALTH SUMMARY
# ---------------------------------------------------------------------------

section("Pipeline Health")

failed = con.execute("""
    SELECT COUNT(*)
    FROM snapshot_job_history
    WHERE status='failed'
""").fetchone()[0]

duplicates = con.execute("""
    SELECT COUNT(*)
    FROM (SELECT customer_id
          FROM periodic_snapshots
          GROUP BY customer_id, night_number
            HAVING COUNT(*)>1
         )
""").fetchone()[0]

latest_snapshot = con.execute("""
    SELECT MAX(night_number)
    FROM periodic_snapshots
""").fetchone()[0]

print(f"Latest Snapshot : Night {latest_snapshot}")
print(f"Failed Jobs     : {failed}")
print(f"Duplicate Rows  : {duplicates}")

if failed == 0 and duplicates == 0:

    print("\nOverall Status : HEALTHY")

else:

    print("\nOverall Status : ATTENTION REQUIRED")

con.close()