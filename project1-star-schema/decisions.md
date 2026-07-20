# FinMart Star Schema — Modeling Decisions

This document records the modeling decisions behind the FinMart star schema, including the grain of each table, key design choices, rejected alternatives, and known limitations. It serves as a reference for understanding why the model was designed this way rather than simply documenting its structure.

## Implementation Note

The SQL scripts are the source of truth for schema creation and data transformations. Python is responsible for orchestration, data generation, query execution, and validation, while business logic remains in SQL. Separating SQL from Python makes the transformation logic easier to review, maintain, and extend without modifying application code.

---

## dim_date

### Grain

One row per calendar date present in the order history.

### Key Decisions

**Date key format:** Integer `YYYYMMDD` (e.g. `20230615`).

Using an integer surrogate key provides efficient joins and is widely compatible with downstream BI tools that commonly use integer date keys.

**Pre-computed calendar attributes:**

Attributes such as year, quarter, month, day, and `is_weekend` are calculated during dimension creation rather than during analysis. This provides consistent definitions across all analytical queries and avoids repeatedly applying date functions.

### Rejected Alternatives

**Using `order_date` directly as the foreign key in `fct_orders`.**

Rejected because DATE-to-DATE joins are generally less efficient than integer key joins at scale and require downstream queries to repeatedly derive calendar attributes.

### Known Limitations

The dimension only contains dates that appear in the source data.

A production data warehouse would typically generate a complete calendar covering multiple years so reports can display periods with zero sales instead of missing dates.

---

## dim_customer

### Grain

One row per customer containing the current customer attributes.

### Key Decisions

**Surrogate key:**

`customer_key` is used instead of the business identifier (`customer_id`) to decouple warehouse relationships from source-system identifiers.

**Business key retained:**

`customer_id` remains in the dimension for traceability back to the source system but is not referenced by fact tables.

**SCD Type 0 (current-state only):**

Customer attributes such as region, country, and segment are treated as static for this project.

Project 3 extends this model to a Slowly Changing Dimension (Type 2) to preserve historical customer attribute changes.

### Rejected Alternatives

**Embedding customer attributes directly in `fct_orders`.**

Rejected because changes to customer information would require updating historical fact records and would complicate future implementation of SCD Type 2.

### Known Limitations

Customer history is intentionally not preserved. Historical reporting assumes customer attributes never change.

---

## dim_product

### Grain

One row per product.

### Key Decisions

**Surrogate key:**

`product_key` replaces the source-system product identifier to provide stable warehouse relationships.

**Product attributes stored in the dimension:**

Attributes such as category, subcategory, and `cost_price` belong to the product rather than individual sales transactions.

Keeping these attributes in the dimension avoids unnecessary duplication and allows product information to be updated centrally.

**Margin calculation:**

Margin is calculated during analysis by combining fact table revenue with product cost from the dimension.

### Rejected Alternatives

**Storing `cost_price` in the fact table.**

Rejected because the synthetic dataset assumes product costs are static.

In a production environment with changing supplier costs, historical costs would typically be captured at transaction time (or through a historical cost dimension) to preserve accurate historical margins.

### Known Limitations

The model assumes product costs never change over time.

---

## fct_orders

### Grain

One row per order line item.

### Key Decisions

**Line-item grain:**

The fact table records one row per purchased product rather than one row per order.

This supports product-level, category-level, and customer-level analysis without requiring additional transactional tables.

**Surrogate foreign keys:**

The fact table references `date_key`, `customer_key`, and `product_key`.

Natural source-system identifiers remain only within the dimensions.

**Pre-computed revenue metrics:**

Both `gross_revenue` and `net_revenue` are calculated during loading.

This ensures revenue definitions remain consistent across all analytical queries instead of relying on each analyst to implement refund logic independently.

**Refund flag retained:**

`is_refunded` remains available for operational analysis, allowing refund rates and refund behaviour to be analysed independently of revenue calculations.

### Rejected Alternatives

**Calculating revenue entirely within analytical queries.**

Rejected because revenue definitions become inconsistent when each analyst implements refund handling differently.

Pre-computing governed metrics provides a single, consistent definition for reporting.

### Known Limitations

The model assumes refunds fully negate revenue.

More complex production scenarios (partial refunds, multiple refund events, exchanges, or adjustments) would require additional transactional modelling.

---

## Overall Design Philosophy

This project intentionally prioritises clarity and analytical best practices over production-scale complexity.

The model demonstrates:

* Star schema modelling with clearly defined grain.
* Separation of fact and dimension responsibilities.
* Use of surrogate keys for warehouse relationships.
* Consistent metric definitions through ETL rather than analytical queries.
* Documentation of design decisions and rejected alternatives to make modelling choices explicit.

Future projects build on these foundations by introducing historical dimensions (SCD Type 2), incremental loading, and more production-oriented warehouse patterns.
