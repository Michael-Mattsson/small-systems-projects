dim_date: grain = one row per calendar date. 
  Decision: include is_weekend flag in dimension rather than 
  calculating in queries — reduces downstream complexity.

fct_orders: grain = one row per order line item, not per order.
  Decision: line item grain chosen because product-level analysis 
  is required. Order-level grain would require exploding later.

dim_customer: surrogate key generated as hash of customer_id + valid_from.
  Decision: natural key (customer_id) cannot be used as FK because 
  Type 2 SCD will create multiple rows per customer.