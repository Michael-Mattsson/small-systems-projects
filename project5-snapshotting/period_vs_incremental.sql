-- =============================================================================
-- Periodic vs Incremental — Reference SQL
-- =============================================================================
-- See periodic_vs_incremental.py for the executable version with printed
-- diagnostics. This file documents the four query categories:
--   1. Storage comparison
--   2. Gap detection (robust to logged AND silent failures)
--   3. Reconstruction under the gap (naive exact-match vs as-of vs incremental)
--   4. Naive vs defensive incremental (the corruption bug)
-- =============================================================================

-- 1. Storage comparison
SELECT 'periodic' AS strategy, COUNT(*) AS total_rows FROM periodic_snapshots
UNION ALL
SELECT 'incremental',
       (SELECT COUNT(*) FROM incremental_base_snapshot)
     + (SELECT COUNT(*) FROM incremental_deltas);


-- 2. Gap detection — calendar spine anti-joined against success log
WITH night_spine AS (SELECT UNNEST(RANGE(1, 31)) AS night_number)
SELECT s.night_number
FROM night_spine s
LEFT JOIN snapshot_log l
    ON s.night_number = l.night_number AND l.status = 'success'
WHERE l.night_number IS NULL
GROUP BY s.night_number;


-- 3a. Periodic — naive exact match (dangerous: silently returns empty)
SELECT * FROM periodic_snapshots WHERE night_number = 12;

-- 3b. Periodic — correct "as of" with explicit fallback night surfaced
WITH latest_available AS (
    SELECT MAX(night_number) AS fallback_night
    FROM periodic_snapshots WHERE night_number <= 12
)
SELECT la.fallback_night AS reconstructed_as_of_night, p.*
FROM latest_available la
JOIN periodic_snapshots p ON p.night_number = la.fallback_night;

-- 3c. Incremental — reconstruction naturally falls back within delta chain
WITH applicable_deltas AS (
    SELECT customer_id, region, country, segment,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY night_number DESC) AS rn
    FROM incremental_deltas WHERE night_number <= 12
)
SELECT b.customer_id, COALESCE(d.region, b.region) AS region
FROM incremental_base_snapshot b
LEFT JOIN (SELECT * FROM applicable_deltas WHERE rn = 1) d
       ON b.customer_id = d.customer_id;


-- 4. Naive (wrong) vs defensive (correct) Night 13 delta size
-- Naive: diffs against a missing night_number = 12 lookup -> everything
-- looks changed.
WITH night_12_lookup AS (
    SELECT customer_id FROM incremental_deltas WHERE night_number = 12
)
SELECT COUNT(*) AS naive_delta_size
FROM (SELECT customer_id FROM incremental_base_snapshot EXCEPT SELECT customer_id FROM night_12_lookup);

-- Defensive: diffs against tracking_state (last successful capture) -> correct.
SELECT COUNT(*) AS defensive_delta_size
FROM incremental_deltas WHERE night_number = 13;