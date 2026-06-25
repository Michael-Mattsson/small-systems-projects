import duckdb
import time
import statistics

# ---------------------------------------------------------------------------
# Wide vs Narrow Benchmark Runner
#
# Data: 
#   5,000,000 row fct_orders, sourced from Project 1's star schema
#   (regenerated at scale), copied into Project 2's local database by
#   build_tables.sql.
#
# Methodology:
#   - Each query (copied from benchmark_queries.sql) runs 5 times. First run 
#     discarded (cold cache / compile overhead), remove startup effects that are 
#     not representative of normal query execution. Remaining 4 runs averaged.
#   - Wall-clock time captured per run; mean, median, and stdev reported.
#     Stdev matters — a single timing number without variance is not
#     a credible benchmark result.
# ---------------------------------------------------------------------------

DB_PATH = "data/project2_benchmark.duckdb"  
RUNS_PER_QUERY = 5
DISCARD_FIRST_RUN = True

con = duckdb.connect(DB_PATH)

queries = {
    "Query 1": {
        "wide": """
            SELECT category, SUM(net_revenue) AS revenue
            FROM wide_orders WHERE order_year = 2023 GROUP BY category
        """,
        "narrow": """
            SELECT p.category, SUM(o.net_revenue) AS revenue
            FROM fct_orders o
            JOIN dim_product p ON o.product_key = p.product_key
            JOIN dim_date    d ON o.date_key    = d.date_key
            WHERE d.year = 2023
            GROUP BY p.category
        """
    },
    "Query 2": {
        "wide": """
            SELECT region, category, DATE_TRUNC('month', date) AS m,
                   SUM(net_revenue) AS revenue,
                   COUNT(DISTINCT customer_id) AS distinct_customers
            FROM wide_orders WHERE is_refunded = FALSE
            GROUP BY region, category, m
        """,
        "narrow": """
            SELECT c.region, p.category, DATE_TRUNC('month', d.date) AS m,
                   SUM(o.net_revenue) AS revenue,
                   COUNT(DISTINCT c.customer_id) AS distinct_customers
            FROM fct_orders o
            JOIN dim_customer c ON o.customer_key = c.customer_key
            JOIN dim_product  p ON o.product_key  = p.product_key
            JOIN dim_date     d ON o.date_key     = d.date_key
            WHERE o.is_refunded = FALSE
            GROUP BY c.region, p.category, DATE_TRUNC('month', d.date)
        """
    },
    "Query 3": {
        "wide": """
            SELECT product_name, SUM(net_revenue) AS revenue
            FROM wide_orders
            WHERE segment = 'Enterprise' AND subcategory = 'Premium'
            GROUP BY product_name ORDER BY revenue DESC LIMIT 20
        """,
        "narrow": """
            SELECT p.name AS product_name, SUM(o.net_revenue) AS revenue
            FROM fct_orders o
            JOIN dim_customer c ON o.customer_key = c.customer_key
            JOIN dim_product  p ON o.product_key  = p.product_key
            WHERE c.segment = 'Enterprise' AND p.subcategory = 'Premium'
            GROUP BY p.name ORDER BY revenue DESC LIMIT 20
        """
    },
    "Query 4": {
        "wide": """
            SELECT region, segment, category,
                   SUM(net_revenue) AS revenue, AVG(net_revenue) AS avg_revenue
            FROM wide_orders GROUP BY region, segment, category
        """,
        "narrow": """
            SELECT c.region, c.segment, p.category,
                   SUM(o.net_revenue) AS revenue, AVG(o.net_revenue) AS avg_revenue
            FROM fct_orders o
            JOIN dim_customer c ON o.customer_key = c.customer_key
            JOIN dim_product  p ON o.product_key  = p.product_key
            GROUP BY c.region, c.segment, p.category
        """
    },
}


def time_query(sql, runs=RUNS_PER_QUERY, discard_first=DISCARD_FIRST_RUN):
    times = []
    for i in range(runs):
        start = time.perf_counter()
        con.execute(sql).fetchall()
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    if discard_first and len(times) > 1:
        times = times[1:]
    return {
        "mean_ms": statistics.mean(times) * 1000,
        "median_ms": statistics.median(times) * 1000,
        "stdev_ms": statistics.stdev(times) * 1000 if len(times) > 1 else 0,
    }

# use con.execute(sql).fetchall otherwise some engines may defer work
# multiply by 1000 to convert seconds to milliseconds, makes it easier to read and compare results

print(f"{'Query':<6} {'Variant':<8} {'Mean (ms)':>12} {'Median (ms)':>14} {'Stdev (ms)':>12}")
print("-" * 56)

# Above prints the header for the benchmark results, using alignments to format the output nicely

results = {}
for qname, variants in queries.items():
    results[qname] = {}
    for variant, sql in variants.items():
        stats = time_query(sql)
        results[qname][variant] = stats
        print(f"{qname:<6} {variant:<8} {stats['mean_ms']:>12.2f} "
              f"{stats['median_ms']:>14.2f} {stats['stdev_ms']:>12.2f}")

print("\n" + "=" * 56)
print("Summary — wide vs narrow ratio (narrow_time / wide_time)")
print("Ratio > 1 means wide was faster. Ratio < 1 means narrow was faster.")
print("=" * 56)

for qname in queries:
    wide_t = results[qname]["wide"]["mean_ms"]
    narrow_t = results[qname]["narrow"]["mean_ms"]
    ratio = narrow_t / wide_t if wide_t else float("nan")
    winner = "wide" if ratio > 1 else "narrow"
    print(f"{qname}: wide={wide_t:.2f}ms  narrow={narrow_t:.2f}ms  "
          f"ratio={ratio:.2f}  winner={winner}")

con.close()