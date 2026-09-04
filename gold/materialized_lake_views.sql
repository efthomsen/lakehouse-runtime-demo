-- Gold-layer Materialized Lake View definitions for the synthetic commerce
-- example used throughout Boundaries of the Lakehouse.
--
-- These are illustrative: the exact authoring syntax should be verified
-- against the Fabric runtime and MLV authoring mode in use before running
-- them for real (see article 3, "Before publishing"). Silver inputs
-- (silver.orders, silver.customers) are produced by this repo's
-- src/silver package via delta-rs -- not by Fabric compute.

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

CREATE MATERIALIZED LAKE VIEW gold.daily_revenue AS
SELECT
    o.order_date,
    SUM(o.net_amount) AS gross_revenue,
    COUNT(DISTINCT o.order_id) AS order_count
FROM silver.orders AS o
WHERE o.order_status = 'completed'
GROUP BY
    o.order_date;

-- gold.commercial_summary depends on BOTH upstream Gold views, exercising
-- the dependency-aware refresh graph described in article 3, fig. 03.
CREATE MATERIALIZED LAKE VIEW gold.commercial_summary AS
SELECT
    cv.market,
    COUNT(DISTINCT cv.customer_id) AS customers,
    SUM(cv.lifetime_net_revenue) AS lifetime_net_revenue,
    (
        SELECT SUM(dr.gross_revenue)
        FROM gold.daily_revenue AS dr
    ) AS total_daily_revenue_all_time
FROM gold.customer_value AS cv
GROUP BY
    cv.market;
