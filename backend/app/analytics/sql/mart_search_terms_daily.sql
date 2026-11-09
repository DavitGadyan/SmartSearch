-- Query-level performance per day. Attribution: clicks/carts/purchases carry the query that produced them.
DROP MATERIALIZED VIEW IF EXISTS mart_search_terms_daily;
-- @@
CREATE MATERIALIZED VIEW mart_search_terms_daily AS
SELECT date_trunc('day', ts)::date                                            AS day,
       lower(query)                                                            AS query,
       count(*) FILTER (WHERE event_type = 'search')                           AS searches,
       count(*) FILTER (WHERE event_type = 'search' AND result_count = 0)      AS zero_result_searches,
       count(DISTINCT user_id) FILTER (WHERE event_type = 'search')            AS searchers,
       count(*) FILTER (WHERE event_type = 'impression')                       AS impressions,
       count(*) FILTER (WHERE event_type = 'click')                            AS clicks,
       avg(position) FILTER (WHERE event_type = 'click')                       AS avg_click_position,
       count(*) FILTER (WHERE event_type = 'add_to_cart')                      AS carts,
       count(*) FILTER (WHERE event_type = 'purchase')                         AS purchases,
       coalesce(sum(revenue) FILTER (WHERE event_type = 'purchase'), 0)::float AS revenue
FROM events
WHERE query IS NOT NULL
GROUP BY 1, 2;
-- @@
CREATE INDEX ix_mart_search_terms_daily ON mart_search_terms_daily (day, query);
