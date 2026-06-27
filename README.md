# Warehouse Architecture & Modeling Systems

Four production-focused modeling projects covering star schema design, 
denormalization tradeoffs, SCD Type 2 history, and metric inflation debugging.

## Projects
1. **Star Schema** — NorthMart e-commerce, 2M orders, 
   3 conformed dimensions, documented grain decisions
2. **Wide vs Narrow Benchmark** — query performance and 
   schema evolution tradeoff analysis with recommendation memo
3. **SCD Type 2** — point-in-time customer dimension with 
   temporal join patterns and inflation trap documentation
4. **Metric Inflation** — root cause analysis of 35% revenue 
   overcount from many-to-many join, three fix approaches compared

raw_orders
      │
      ▼
Project 1
fact_orders
dim_customer
dim_product
dim_date
      │
      ▼
Project 2
wide_orders


## Stack
DuckDB · SQL · Python (data generation) · Markdown (documentation)

## Key Concepts Demonstrated
Surrogate keys · Conformed dimensions · Temporal joins · 
Join cardinality · Grain decisions · Postmortem documentation

------------------------------------------------------------------------------

# Project 2 — Wide vs Narrow Table Benchmark

Benchmarks two data modeling approaches against identical analytical
workloads on a 5,000,000 row FinMart order dataset.

## What this tests
- Query performance: 4 query pairs (wide vs star schema) run 5 times
  each, first run discarded, remaining runs averaged with variance reported
- Storage cost: row count and duplicated dimension attribute bytes compared
- Schema evolution cost: 3 sequential changes measured by rows touched

## Files
| File | Purpose |
|------|---------|
| `build_tables.sql` | Attaches Project 1 database, copies star schema, builds wide table |
| `benchmark.py` | Runs all query pairs, reports timing with variance |
| `benchmark_queries.sql` | All 8 queries (4 pairs) for manual inspection |
| `schema_evolution_test.sql` | 3 schema changes executed on both designs |
| `tradeoff_analysis.md` | Recommendation memo with real benchmark numbers |

## How to run
```bash
# From project2-wide-vs-narrow/
mkdir data
python -c "import duckdb; duckdb.connect('data/project2_benchmark.duckdb')"
duckdb data/project2_benchmark.duckdb < build_tables.sql
python benchmark.py
```

## Key finding
[Fill in after running — one sentence summarizing the headline result]

## Stack
DuckDB · SQL · Python

------------------------------------------------------------------------------

# Project 3 — SCD Type 2 Customer Dimension

Implements a Type 2 slowly changing dimension for FinMart's customer
data, demonstrating point-in-time historical reconstruction and the
exact failure mode when temporal joins are incorrectly applied.

## What this tests

- Correct SCD Type 2 structure: surrogate keys, valid_from/valid_to
  ranges, is_current flag
- The two-step close/insert change operation
- Point-in-time temporal join pattern and its failure mode
- Revenue inflation quantification when date bounds are omitted
- Integrity checks: no overlapping ranges, no duplicate is_current records


## Files

| File | Purpose |
|------|---------|
| `build_scd2.py` | Builds dim_customer_scd2 from Project 1 data |
| `build_scd2.sql` | Human-readable reference: structure + core operations |
| `simulate_changes.sql` | Applies three change scenarios, validates integrity |
| `point_in_time_queries.sql` | All analytical queries including broken join |
| `point_in_time_queries.py` | Runs all queries, prints labeled output |
| `notes.md` | Design decisions, failure mode documentation |


## Project workflow

1. Run build_scd2.py
   • Creates initial SCD2 database.

2. Run simulate_changes.py
   • Applies customer changes.
   • Runs integrity checks.

3. Run point_in_time_queries.py
   • Demonstrates correct temporal joins.
   • Demonstrates broken joins.
   • Shows revenue inflation.

         CRM
            │
         Incoming customer feed
            │
         Hash comparison
            │
         Changed?
         ┌───────┐
         │  No   │──────► Ignore
         └───────┘
         ┌───────┐
         │ Yes   │
         └───────┘
            │
         Close current row
            │
         Insert new version
            │
         dim_customer_scd2
            │
         Temporal joins
            │
         Historical reporting


## Scenarios

| Customer | Change                  | Effective Date         | Versions |
|----------|-------------------------|------------------------|----------|
| 1001     | Regional relocation     | 2023-03-01             | 2        |
| 2500     | Segment upgrade         | 2023-06-15             | 2        |
| 5000     | Two sequential changes  | 2022-09-01, 2023-05-01 | 3        |

Customer 5000 (3 versions) explicitly tests the hardest case —
queries omitting date bounds return 3x row duplication for this customer.


## How to run

```bash
# Step 1: build initial dimension (resets database to clean state)
python build_scd2.py

# Step 2: simulate changes (hash detection → apply updates → validation)
python simulate_changes.py

# Step 3: run point-in-time analytical queries
python point_in_time_queries.py
```

Rerunning `build_scd2.py` resets the database. `simulate_changes.py`
can then be rerun cleanly from the initial state.


## Key finding

A temporal join omitting date bounds inflates revenue by exactly the
number of SCD2 versions per customer. This is silent — the query
completes without error and produces plausible-looking numbers.
Detection requires comparing against a known baseline or row count
check before and after the join.

## Stack
DuckDB · SQL · Python