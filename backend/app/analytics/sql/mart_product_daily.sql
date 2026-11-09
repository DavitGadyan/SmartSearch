-- Product-level performance per day (search + recommendation surfaces).
DROP MATERIALIZED VIEW IF EXISTS mart_product_daily;
-- @@
CREATE MATERIALIZED VIEW mart_product_daily AS
SELECT date_trunc('day', ts)::date                                            AS day,
       product_id,
       count(*) FILTER (WHERE event_type = 'impression')                       AS impressions,
       avg(position) FILTER (WHERE event_type = 'impression')                  AS avg_impression_position,
       count(*) FILTER (WHERE event_type = 'click')                            AS clicks,
       count(*) FILTER (WHERE event_type = 'add_to_cart')                      AS carts,
       count(*) FILTER (WHERE event_type = 'purchase')                         AS purchases,
       coalesce(sum(quantity) FILTER (WHERE event_type = 'purchase'), 0)       AS units,
       coalesce(sum(revenue) FILTER (WHERE event_type = 'purchase'), 0)::float AS revenue,
       count(*) FILTER (WHERE event_type = 'rec_impression')                   AS rec_impressions,
       count(*) FILTER (WHERE event_type = 'rec_click')                        AS rec_clicks
FROM events
WHERE product_id IS NOT NULL
GROUP BY 1, 2;
-- @@
CREATE INDEX ix_mart_product_daily ON mart_product_daily (product_id, day);
