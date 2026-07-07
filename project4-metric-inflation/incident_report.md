# Incident: Revenue Metric Inflation — FinMart Dashboard

### Date: [fill in after running] | Detected by: finance reconciliation

---

## Symptom

Dashboard revenue (broken join): [fill in from apply_fixes.py output]
Accounting system baseline (no join): [fill in from apply_fixes.py output]
Discrepancy: [fill in] ([fill in]% inflation)

*Numbers are measured from detect_inflation.py and apply_fixes.py output,
not assumed. Run both scripts to populate this section with real figures.*

---

## Root Cause

A many-to-many join between `fct_orders` and `promotions` fans out every
order for a customer once per active promotion that customer has.
Customers with 0 or 1 promotion are unaffected. Customers with 2 or 3
promotions have their orders duplicated 2x or 3x respectively in the
join result, inflating `SUM(net_revenue)` proportionally.

The join has no grain guard — `LEFT JOIN promotions p ON o.customer_id = p.customer_id`
assumes at most one promotion per customer, which is false for roughly
20% of the customer base (see promo count distribution in
`detect_inflation.py` Step 2 output).

---

## Detection Method

1. **Row count comparison** — `fct_orders` alone vs `fct_orders LEFT JOIN promotions`.
   Any increase in row count against a fact table on a LEFT JOIN indicates
   fanout, since a fact table row should map to at most one row per
   dimension in a correctly designed join.

2. **Affected customer identification** — grouping `promotions` by
   `customer_id` and filtering `HAVING COUNT(*) > 1` isolates exactly
   which customers will have inflated orders.

3. **Quantification** — comparing `SUM(net_revenue)` from `fct_orders`
   alone (the correct baseline, since revenue has no dependency on
   promotions) against the same sum after the broken join.

---

## Fix Applied

Fix 2 (aggregate promotions to customer grain before joining) was
selected for the dashboard query specifically, because the dashboard
only needs `total_revenue` — it does not need individual promotion
detail preserved per order. Fix 1 and Fix 3 remain valid for other use
cases (see `apply_fixes.sql` for when each applies).

Verified: post-fix revenue exactly matches the accounting system baseline
(`fct_orders` with no join), confirmed by `apply_fixes.py`'s verification
step across all three fixes.

---

## Prevention

Add a row count assertion before and after any join in revenue-producing
queries. Any join that increases row count against a fact table requires
explicit justification — either the join is intentionally one-to-many
(and downstream aggregation must account for it), or it's a bug.

A generic guard function (see `notes.md`) can be added to any pipeline
or dbt test suite to catch this class of bug automatically before it
reaches a dashboard.