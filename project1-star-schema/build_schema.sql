-- Dimension tables
dim_date        -- date_key, date, year, quarter, month, day_of_week, is_weekend
dim_customer    -- customer_key (surrogate), customer_id (natural), 
                -- region, country, segment, valid_from, valid_to
dim_product     -- product_key (surrogate), product_id (natural), 
                -- name, category, subcategory, cost_price

-- Fact table
fct_orders      -- order_key, date_key (FK), customer_key (FK), 
                -- product_key (FK), quantity, unit_price, 
                -- gross_revenue, is_refunded, net_revenue