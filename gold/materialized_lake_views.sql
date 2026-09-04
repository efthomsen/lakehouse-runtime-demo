-- Gold-layer Materialized Lake View definitions for the synthetic commerce
-- example used throughout Boundaries of the Lakehouse.
--
-- STATUS: UNVERIFIED AGAINST A REAL FABRIC WORKSPACE.
-- The `CREATE MATERIALIZED LAKE VIEW` syntax below (including the
-- CONSTRAINT ... ON MISMATCH clause) matches the syntax documented at
-- https://learn.microsoft.com/fabric/data-engineering/materialized-lake-views/create-materialized-lake-view
-- as checked on 2026-09-04, but nothing here has been executed in a Fabric
-- Lakehouse. Before the article calls this final: run it in the companion
-- environment against a schema-enabled lakehouse (Runtime 1.3+), record the
-- runtime / authoring mode / date in a LAST TESTED block, and re-check
-- refresh behaviour -- incremental refresh requires Change Data Feed on
-- every source table referenced (silver.orders, silver.customers,
-- silver.calendar); without CDF the refresh engine falls back to full or
-- skip. PySpark-authored MLVs currently perform full refresh only.
--
-- Silver inputs (silver.orders, silver.customers) are produced by this
-- repo's silver/ package via delta-rs, not by Fabric compute -- see
-- silver/prepare_orders.py and silver/prepare_customers.py.
-- silver.calendar is a static date-spine reference table maintained
-- directly in Fabric; it is not produced by this repo.
--
-- Dependency graph (article 3, fig. 03):
--   silver.orders + silver.customers -> gold.customer_value  \
--   silver.calendar ----------------> gold.daily_revenue      >-> gold.commercial_summary
-- The article's own dependency-graph sketch draws no orders edge into
-- daily_revenue (a drafting gap in the source material) -- resolved here
-- deliberately by using silver.calendar as the date spine, LEFT JOINed to
-- completed orders, so every calendar day appears even with zero revenue.

CREATE MATERIALIZED LAKE VIEW gold.customer_value AS
SELECT
    c.customer_id,
    c.market,
    MIN(o.order_date) AS first_order_date,
    MAX(o.order_date) AS latest_order_date,
    SUM(o.net_amount) AS lifetime_net_revenue,
    COUNT(DISTINCT o.order_id) AS completed_orders
FROM silver.customers AS c
LEFT JOIN silver.orders AS o
    ON c.customer_id = o.customer_id
   AND o.order_status = 'completed'
GROUP BY
    c.customer_id,
    c.market;

CREATE MATERIALIZED LAKE VIEW gold.daily_revenue (
    CONSTRAINT non_negative_revenue CHECK (gross_revenue >= 0) ON MISMATCH FAIL
) AS
SELECT
    d.calendar_date,
    COUNT(DISTINCT o.order_id) AS order_count,
    COALESCE(SUM(o.net_amount), 0) AS gross_revenue
FROM silver.calendar AS d
LEFT JOIN silver.orders AS o
    ON o.order_date = d.calendar_date
   AND o.order_status = 'completed'
GROUP BY
    d.calendar_date;

-- gold.commercial_summary depends on BOTH upstream Gold views, exercising
-- the dependency-aware refresh graph described in article 3, fig. 03. The
-- last-30-days figure is computed once in a non-correlated CTE and joined
-- in, rather than as a correlated subquery per output row.
CREATE MATERIALIZED LAKE VIEW gold.commercial_summary AS
WITH last_30_days AS (
    SELECT SUM(gross_revenue) AS revenue_last_30_days
    FROM gold.daily_revenue
    WHERE calendar_date >= CURRENT_DATE - INTERVAL 30 DAYS
)
SELECT
    cv.market,
    COUNT(DISTINCT cv.customer_id) AS customers,
    SUM(cv.lifetime_net_revenue) AS lifetime_net_revenue,
    MAX(last_30_days.revenue_last_30_days) AS revenue_last_30_days
FROM gold.customer_value AS cv
CROSS JOIN last_30_days
GROUP BY
    cv.market;
