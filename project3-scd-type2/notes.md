# SCD Type 2 — Design Notes and Key Findings

## What this project demonstrates

SCD Type 2 preserves full attribute history by inserting a new row
on each change rather than overwriting the existing one. This enables
point-in-time reconstruction — answering "what was true at the time?"
rather than only "what is true now?"

Without Type 2, revenue by region, segment cohort analysis, and
historical attribution all silently use the customer's current
attributes, producing wrong results whenever customers have moved
or changed classification.

---

## Key design decisions

**Customer attributes are deterministically generated** using modulo
arithmetic on customer_id for reproducibility — the same input always
produces the same dimension.

**fct_orders stores customer_id (natural key):**
Because no version-specific surrogate key exists in the fact table,
all point-in-time joins must use customer_id together with the validity
date bounds (valid_from, valid_to). This is the standard pattern when
a fact table is built before Type 2 history is introduced. The natural
key join with date bounds is the correct and only approach available
given the existing schema.

**valid_to = change_date - 1 day:** Ranges are non-overlapping with
no gaps. An order placed on the exact change_date matches the new
record only.

**NULL check on valid_to is not optional:**
```sql
AND (o.order_date < c.valid_to OR c.valid_to IS NULL)
```
Active records have valid_to = NULL. Omitting the NULL check silently
excludes all orders placed after the most recent change.

---

## The failure mode: omitting date bounds

Joining on customer_id alone returns one row per SCD2 version per
order. A customer with N versions produces N rows per order.

At this dataset's change rate (4 changes across ~10,000 customers),
aggregate inflation is under 0.1% — easy to miss. For the three
specifically changed customers, inflation is exactly 2x or 3x.
The inflation quantification query (Q5) makes this precise.

In production with thousands of changes, aggregate inflation becomes
significant and is difficult to detect without a baseline.

---

## Scenarios

| Customer | Change          | Effective Date         | Versions |
|----------|-----------------|------------------------|----------|
| 1001     | Region/country  | 2023-03-01             | 2        |
| 2500     | Segment upgrade | 2023-06-15             | 2        |
| 5000     | Segment (×2)    | 2022-09-01, 2023-05-01 | 3        |

Customer 5000 (3 versions) is the critical test case — 3x row
duplication in the broken join is unambiguous.

---

## Hash-based change detection

Production SCD2 systems detect changes programmatically rather than
applying them manually. The standard pattern:

```sql
MD5(CONCAT_WS('|', region, country, segment)) AS attribute_hash
```

Compare hashes between incoming data and the current dimension record.
Attribute hashes are used as a fast change detector. Actual attribute 
values remain the source of truth.
A changed hash triggers the two-step close/insert operation. An
unchanged hash is a no-op. This avoids scanning full history and is
how dbt snapshots, Fivetran, and custom ETL jobs implement SCD2
at scale. The detection query in simulate_changes.sql demonstrates
this pattern against the post-simulation state. 

---

## Connection to adjacent projects

**Project 2:** Wide tables cannot represent point-in-time dimension
state. The star schema's fact/dimension separation is what makes
Type 2 possible without touching fct_orders at all.

**Project 4:** The metric inflation caused by omitting SCD2 date
bounds is the same pattern as Project 4's many-to-many join
inflation — different cause, identical diagnostic approach.