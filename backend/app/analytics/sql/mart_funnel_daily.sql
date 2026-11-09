-- Site-wide daily funnel: visitors → searches → clicks → carts → purchases → revenue.
DROP MATERIALIZED VIEW IF EXISTS mart_funnel_daily;
-- @@
CREATE MATERIALIZED VIEW mart_funnel_daily AS
SELECT date_trunc('day', ts)::date                                              AS day,
       count(DISTINCT user_id)                                                   AS visitors,
       count(DISTINCT session_id)                                                AS sessions,
       count(*) FILTER (WHERE event_type = 'search')                             AS searches,
       count(*) FILTER (WHERE event_type = 'search' AND result_count = 0)        AS zero_result_searches,
       count(*) FILTER (WHERE event_type = 'impression')                         AS impressions,
       count(*) FILTER (WHERE event_type = 'click')                              AS clicks,
       count(*) FILTER (WHERE event_type = 'add_to_cart')                        AS carts,
       count(*) FILTER (WHERE event_type = 'purchase')                           AS purchases,
       count(DISTINCT user_id) FILTER (WHERE event_type = 'purchase')            AS buyers,
       count(DISTINCT metadata->>'order_id') FILTER (WHERE event_type = 'purchase')  AS orders,
       coalesce(sum(revenue) FILTER (WHERE event_type = 'purchase'), 0)::float   AS revenue,
       count(*) FILTER (WHERE event_type = 'rec_impression')                     AS rec_impressions,
       count(*) FILTER (WHERE event_type = 'rec_click')                          AS rec_clicks,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE event_type = 'search') AS p95_latency_ms
FROM events
GROUP BY 1;
-- @@
CREATE UNIQUE INDEX ix_mart_funnel_daily ON mart_funnel_daily (day);
