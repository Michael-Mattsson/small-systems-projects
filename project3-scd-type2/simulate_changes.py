import duckdb

# ---------------------------------------------------------------------------
# SCD Type 2 — Change Simulation
#
# Applies three customer attribute change scenarios to dim_customer_scd2,
# following a realistic ETL sequence:
#
#   1. Define incoming customer update feed (simulates source system data)
#   2. Hash comparison — detect which customers actually changed
#   3. Apply SCD2 updates for detected changes only
#   4. Run integrity checks
#
# Hash detection precedes updates — this is the correct pipeline order.
# Changes are only applied where the incoming hash differs from the
# current dimension hash. Unchanged customers are no-ops.
#
# See simulate_changes.sql for the equivalent reference SQL.
#
# Run after build_scd2.py. Rerunning build_scd2.py resets the database
# to its initial state — simulate_changes.py can then be rerun cleanly.
# ---------------------------------------------------------------------------

DB_PATH = "../small-systems-projects/data/project3_scd2.duckdb"

con = duckdb.connect(DB_PATH)


# ---------------------------------------------------------------------------
# Step 1: Incoming customer update feed
#
# In production this would be a staging table populated from the source
# system (CRM, ERP, etc.). Here it is defined inline as a list of dicts.
# Each record represents the current state of a customer in the source.
# ---------------------------------------------------------------------------

incoming_updates = [
    # Scenario A: customer 1001 has relocated — region and country changed
    {
        "customer_id": 1001,
        "region":      "East",
        "country":     "Finland",
        "segment":     None,          # None = carry forward existing value
        "change_date": "2023-03-01",
        "scenario":    "A — regional relocation"
    },
    # Scenario B: customer 2500 has upgraded segment
    {
        "customer_id": 2500,
        "region":      None,
        "country":     None,
        "segment":     "Business",
        "change_date": "2023-06-15",
        "scenario":    "B — segment upgrade"
    },
    # Scenario C: customer 5000, first change
    {
        "customer_id": 5000,
        "region":      None,
        "country":     None,
        "segment":     "Business",
        "change_date": "2022-09-01",
        "scenario":    "C1 — first segment change"
    },
    # Scenario C: customer 5000, second change
    {
        "customer_id": 5000,
        "region":      None,
        "country":     None,
        "segment":     "Enterprise",
        "change_date": "2023-05-01",
        "scenario":    "C2 — second segment change"
    },
]


# ---------------------------------------------------------------------------
# Step 2: Hash-based change detection
#
# For each incoming record, resolve any None fields by carrying forward
# the current dimension value, then compare the incoming attribute hash
# against the current dimension hash.
#
# Customers where the hash differs require a new SCD2 version.
# Customers where the hash matches are no-ops — no update needed.
#
# This detection step mirrors how production ETL frameworks (dbt snapshots,
# Fivetran, custom Spark jobs) identify SCD2 changes without scanning
# full history on every run.
# ---------------------------------------------------------------------------

def get_current_state(customer_id):
    """Fetch the current active record for a customer."""
    result = con.execute("""
        SELECT customer_id, region, country, segment, customer_key
        FROM dim_customer_scd2
        WHERE customer_id = ? AND is_current = TRUE
    """, [customer_id]).fetchone()
    if result is None:
        raise ValueError(f"No current record found for customer_id {customer_id}")
    return {
        "customer_id":  result[0],
        "region":       result[1],
        "country":      result[2],
        "segment":      result[3],
        "customer_key": result[4],
    }


def compute_hash(region, country, segment):
    """Compute attribute hash for change detection."""
    result = con.execute(
        "SELECT MD5(CONCAT(?, '|', ?, '|', ?))",
        [region, country, segment]
    ).fetchone()[0]
    return result


def get_next_customer_key():
    """Retrieve next available surrogate key. Maintained in Python to
    avoid repeated MAX()+1 subqueries and potential concurrency issues.
    In production this would typically come from a sequence or identity 
    column rather than MAX()+1."""
    return con.execute(
        "SELECT MAX(customer_key) + 1 FROM dim_customer_scd2"
    ).fetchone()[0]


print("\n--- Step 2: Hash-Based Change Detection ---")
print(f"{'Scenario':<30} {'Customer':>10} {'Change Detected':>16}")
print("-" * 60)

changes_to_apply = []
next_key = get_next_customer_key()

for update in incoming_updates:
    current = get_current_state(update["customer_id"])

    # Resolve None fields — carry forward current values
    resolved = {
        "region":  update["region"]   or current["region"],
        "country": update["country"]  or current["country"],
        "segment": update["segment"]  or current["segment"],
    }

    current_hash  = compute_hash(current["region"], current["country"], current["segment"])
    incoming_hash = compute_hash(resolved["region"], resolved["country"], resolved["segment"])

    changed = current_hash != incoming_hash
    status  = "YES — new version required" if changed else "no change"
    print(f"{update['scenario']:<30} {update['customer_id']:>10} {status:>16}")

    if changed:
        changes_to_apply.append({
            "customer_id":   update["customer_id"],
            "change_date":   update["change_date"],
            "new_region":    resolved["region"],
            "new_country":   resolved["country"],
            "new_segment":   resolved["segment"],
            "new_key":       next_key,
            "scenario":      update["scenario"],
        })
        next_key += 1


# ---------------------------------------------------------------------------
# Step 3: Apply SCD2 updates for detected changes only
#
# Each detected change follows the two-step pattern:
#   1. Close current record: valid_to = change_date - 1, is_current = FALSE
#   2. Insert new record:    valid_from = change_date, valid_to = NULL, is_current = TRUE
#
# Encapsulated in apply_customer_change() so the logic is defined once
# and called per detected change — not repeated inline for each scenario.
# ---------------------------------------------------------------------------

def apply_customer_change(customer_id, change_date, region, country,
                           segment, new_key):
    """
    Apply a single SCD2 change: close current record, insert new version.
    change_date: string in 'YYYY-MM-DD' format.
    """
    # Step 1: close current record
    con.execute("""
        UPDATE dim_customer_scd2
        SET valid_to   = CAST(? AS DATE) - INTERVAL 1 DAY,
            is_current = FALSE
        WHERE customer_id = ? AND is_current = TRUE
    """, [change_date, customer_id])

    # Step 2: insert new version
    con.execute("""
        INSERT INTO dim_customer_scd2
            (customer_key, customer_id, region, country, segment,
             valid_from, valid_to, is_current)
        VALUES (?, ?, ?, ?, ?, CAST(? AS DATE), NULL, TRUE)
    """, [new_key, customer_id, region, country, segment, change_date])


print(f"\n--- Step 3: Applying {len(changes_to_apply)} Detected Changes ---")
for change in changes_to_apply:
    apply_customer_change(
        customer_id  = change["customer_id"],
        change_date  = change["change_date"],
        region       = change["new_region"],
        country      = change["new_country"],
        segment      = change["new_segment"],
        new_key      = change["new_key"],
    )
    print(f"  Applied: {change['scenario']} (customer {change['customer_id']}, "
          f"effective {change['change_date']})")


# ---------------------------------------------------------------------------
# Step 4: Integrity checks — run after every change batch
# ---------------------------------------------------------------------------

print("\n--- Step 4: Integrity Checks ---")

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
        SELECT customer_id FROM dim_customer_scd2
        WHERE is_current = TRUE
        GROUP BY customer_id HAVING COUNT(*) > 1
    )
    """
)

assert_check(
    "No open records with is_current = FALSE",
    """
    SELECT COUNT(*) FROM dim_customer_scd2
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

# Summary
summary = con.execute("""
    SELECT
        COUNT(*)                                           AS total_rows,
        COUNT(DISTINCT customer_id)                        AS distinct_customers,
        SUM(CASE WHEN is_current THEN 1 ELSE 0 END)       AS current_records,
        MAX(
            SELECT COUNT(*) FROM dim_customer_scd2 g
            WHERE g.customer_id = dim_customer_scd2.customer_id
        )                                                  AS max_versions_one_customer
    FROM dim_customer_scd2
""").fetchdf()

print("\n--- Post-Simulation Summary ---")
print(summary.to_string(index=False))

# Version breakdown for changed customers
versions = con.execute("""
    SELECT customer_id, COUNT(*) AS versions
    FROM dim_customer_scd2
    WHERE customer_id IN (1001, 2500, 5000)
    GROUP BY customer_id ORDER BY customer_id
""").fetchdf()
print("\nVersions per changed customer:")
print(versions.to_string(index=False))

con.close()
print("\nSimulation complete.")