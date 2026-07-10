# Metric Inflation — Design Notes and Key Findings

## What this project demonstrates

A many-to-many join between a fact table and a dimension-like table that
isn't actually at the right grain silently inflates SUM aggregations.
Unlike Project 3's SCD2 inflation (caused by a missing temporal bound),
this inflation is caused by a table that was never designed to be
one-row-per-customer in the first place — `promotions` genuinely has
multiple valid rows per customer, and the join must account for that.

---

## Why this differs from Project 3's inflation

Project 3: `dim_customer_scd2` has multiple rows per customer by design
(one per historical version) — the fix is adding date bounds to select
the correct version.

Project 4: `promotions` has multiple rows per customer by design (one
per active campaign) — there is no "correct single row" to select via
date bounds alone, because a customer can have several *simultaneously
valid* promotions. The fix must decide a business rule: pick one
(Fix 1), aggregate them (Fix 2), or attribute at the order level
(Fix 3) — there's no universal single answer the way there was for SCD2.

This distinction matters in an interview context: not every join
inflation bug has the same fix, because not every one-to-many
relationship has the same resolution rule.

---

## A subtlety in Fix 3's verification

Fix 3's revenue total matches the baseline whether or not `promo_end`
bounds are included in the join — `ROW_NUMBER() ... WHERE rn = 1`
already guarantees exactly one row per order regardless of the date
filter, so SUM(net_revenue) is correct either way.

What the date bounds actually fix is *attribution correctness*, not
revenue correctness: without `promo_end`, Fix 3 would attribute every
order to whichever promotion has the latest `promo_start` overall,
even if that promotion wasn't active yet (or was already over) at the
time the order was placed. With both `promo_start` and `promo_end`
bounding the join, `promo_code` reflects the promotion genuinely
active when the order occurred.

This is a useful distinction to hold onto: a fix can produce the
correct aggregate while still being wrong about the underlying
attribution. Revenue verification alone would not have caught this —
it requires checking that `promo_code` values make temporal sense,
not just that `SUM(net_revenue)` matches the baseline.

---

## Reusable guard function

```python
def assert_no_join_inflation(con, base_query, joined_query, label):
    base_count   = con.execute(f"SELECT COUNT(*) FROM ({base_query})").fetchone()[0]
    joined_count = con.execute(f"SELECT COUNT(*) FROM ({joined_query})").fetchone()[0]
    if joined_count > base_count:
        raise ValueError(
            f"{label}: join inflated row count from {base_count:,} "
            f"to {joined_count:,} ({joined_count - base_count:,} phantom rows)"
        )
    print(f"{label}: PASS — no inflation ({base_count:,} rows preserved)")
```

This generalizes Step 1 of `detect_inflation.py` into a function that
could be dropped into any pipeline or dbt test suite as a pre-deployment
check on revenue-producing queries.

---

## Connection to adjacent projects

**Project 2:** The schema evolution test showed that maintaining
attribute changes in a normalized dimension is far cheaper than in a
wide table. This project shows a related but distinct risk: even a
correctly normalized schema can produce wrong aggregates if a join's
grain assumption is wrong. Normalization solves maintenance cost;
join discipline solves correctness.

**Project 3:** Both projects demonstrate the same diagnostic pattern —
compare row counts before and after a join, then quantify the exact
inflation against a known baseline. The root cause differs (missing
temporal bounds vs. genuine one-to-many business data), but the
detection method is identical. This is a strong indicator that "row
count before vs after any join" should be a standing habit, not a
one-off check.

**General principle across Projects 1–4:** every project in this
series ultimately traces back to grain. Project 1 established grain
explicitly for each table. Project 2 showed grain violations compound
maintenance cost. Project 3 showed grain violations from missing
temporal logic. Project 4 shows grain violations from an unaccounted
one-to-many relationship. Getting grain right at design time prevents
all four categories of problems demonstrated across this portfolio.