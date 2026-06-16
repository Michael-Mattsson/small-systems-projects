
# FinMart Star Schema — Modeling Decisions

This document records the grain, key decisions, and rejected alternatives
for each table in the FinMart star schema. It is intended to serve as
internal reference for anyone maintaining or extending this model.

--------


## dim_date
--------
**Grain:** One row per calendar date present in the order history.

**Date key format:** Integer YYYYMMDD (e.g. 20230615).
Integer keys are faster to join on than DATE types and are compatible with 
downstream BI tools that expect integer surrogate keys on date dimensions.

**is_weekend flag:** Pre-calculated in the dimension rather than derived
in analytical queries. Consistent definition across all consumers — avoids
possible conflicting DAYOFWEEK logic

**Rejected alternative:** Using order_date directly as the FK in fct_orders.
Rejected because DATE-to-DATE joins are slower than integer key lookups at
scale and prevent the use of pre-aggregated date attributes (quarter, month,
is_weekend) without repeated EXTRACT calls in every downstream query.

**Known limitation:** Dimension only covers dates present in raw_orders.
A production dim_date would cover a fixed multi-year range regardless of
data presence, so that dashboards with date filters never return NULL for
dates with no orders.


## dim_customer
------------
**Grain:** One row per customer — current attributes only

**Surrogate key:** customer_key generated via ROW_NUMBER() ordered by
customer_id. Natural keys from source systems (customer_id) change 
meaning when customers are merged, deleted, or migrated. Surrogate 
keys decouple the warehouse model from sourcesystem changes.

**Natural key retained:** customer_id is kept as a business key column
for traceability back to source systems. It is not used as a FK in
fact tables.

**SCD Type 0 (no history) — deliberate simplification:** Customer region,
country, and segment are treated as static in this project.
Project 3 (SCD Type 2) extends this dimension to preserve attribute
history and support point-in-time reconstruction.

**Rejected alternative:** Embedding region and country directly in
fct_orders at load time (denormalization). Rejected because it would
require backfilling the entire fact table when customer attributes change,
and prevents point-in-time historical analysis when SCD Type 2 is
introduced.


## dim_product
-----------
**Grain:** One row per product.

**Surrogate key:** product_key generated via ROW_NUMBER() ordered by
product_id. Same reasoning as dim_customer — decouples warehouse FK
relationships from source system natural keys.

**cost_price stored in dimension, not fact table:** Cost is a product
attribute, not an order attribute. Storing it in the dimension means
cost can be updated centrally without touching the fact table. Margin
calculations (unit_price - cost_price) are performed at query time by
joining to the dimension.

**category and subcategory in dimension, not fact table:** Product
groupings belong in the dimension. Storing them in fct_orders would
require updating millions of fact rows if a product is recategorized.
Dimension updates propagate automatically to all historical queries.

**Rejected alternative:** Storing cost_price in fct_orders at order
time to lock in historical cost. Rejected for this exercise because
the synthetic data has no cost history — cost is static per product.
In a production model with vendor pricing changes, locking cost at
order time in the fact table would be the correct approach. I would 
snapshot cost into the fact table (or use a historical cost dimension) 
to preserve accurate margin calculations over time.


## fct_orders
----------
**Grain:** One row per order line item.

**Line-item grain chosen over order grain:** The analytical requirements
include product-level and category-level revenue breakdowns. Order grain
would aggregate across products, making it impossible to answer
"revenue by product category" without a separate line-item table.
Line-item grain supports all required queries; order grain does not.

**Foreign keys reference surrogate keys:** date_key, customer_key,
and product_key all reference surrogate keys in their respective
dimensions. Natural keys (customer_id, product_id) from raw_orders
are not carried into the fact table — they exist only in dimensions
for source traceability.

**gross_revenue and net_revenue precomputed at load time:**
Consistent metric definitions enforced at the model layer, not the
query layer. Every analyst querying net_revenue gets the same number
because the refund logic (CASE WHEN is_refunded THEN 0) is applied
once during load, not reimplemented per query.

**is_refunded retained as a flag:** Kept in the fact table so analysts
can filter, count, or analyze refund patterns independently of the
revenue metrics. Dropping it after computing net_revenue would
prevent refund rate analysis.

**Rejected alternative:** Calculating revenue ad-hoc in queries as
quantity * unit_price with inline refund filters. Rejected because
different analysts apply refund logic differently — some exclude
refunded rows entirely, some zero the revenue, some leave gross
revenue intact. Precomputing both gross_revenue and net_revenue
makes the distinction explicit and governed.