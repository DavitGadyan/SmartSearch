-- Rolling behavioral aggregates per product (ranking features). Rates are Bayesian-smoothed with weak priors so
-- a product with 1 click out of 1 impression does not get CTR = 1.0. :as_of lets us compute "as of" a past date.
WITH agg AS (
    SELECT
        product_id,
        count(*) FILTER (WHERE event_type = 'impression' AND ts >= CAST(:as_of AS timestamptz) - interval '7 days')  AS impressions_7d,
        count(*) FILTER (WHERE event_type = 'click'      AND ts >= CAST(:as_of AS timestamptz) - interval '7 days')  AS clicks_7d,
        count(*) FILTER (WHERE event_type = 'impression')                                                    AS impressions_30d,
        count(*) FILTER (WHERE event_type = 'click')                                                         AS clicks_30d,
        count(*) FILTER (WHERE event_type = 'add_to_cart')                                                   AS carts_30d,
        count(*) FILTER (WHERE event_type = 'purchase')                                                      AS purchases_30d,
        coalesce(sum(revenue) FILTER (WHERE event_type = 'purchase'), 0)                                     AS revenue_30d
    FROM events
    WHERE product_id IS NOT NULL
      AND ts >  CAST(:as_of AS timestamptz) - interval '30 days'
      AND ts <= CAST(:as_of AS timestamptz)
    GROUP BY product_id
),
reset AS (
    UPDATE product_stats SET impressions_7d = 0, clicks_7d = 0, impressions_30d = 0, clicks_30d = 0, carts_30d = 0,
                             purchases_30d = 0, revenue_30d = 0, ctr_30d = 0, cart_rate_30d = 0, conversion_30d = 0, popularity = 0
    WHERE product_id NOT IN (SELECT product_id FROM agg)
)
UPDATE product_stats ps SET
    impressions_7d  = a.impressions_7d,
    clicks_7d       = a.clicks_7d,
    impressions_30d = a.impressions_30d,
    clicks_30d      = a.clicks_30d,
    carts_30d       = a.carts_30d,
    purchases_30d   = a.purchases_30d,
    revenue_30d     = a.revenue_30d,
    ctr_30d         = (a.clicks_30d + 0.5)    / (a.impressions_30d + 20.0),
    cart_rate_30d   = (a.carts_30d + 0.2)     / (a.clicks_30d + 10.0),
    conversion_30d  = (a.purchases_30d + 0.1) / (a.clicks_30d + 10.0),
    popularity      = ln(1 + a.clicks_30d + 3 * a.carts_30d + 10 * a.purchases_30d),
    updated_at      = now()
FROM agg a
WHERE a.product_id = ps.product_id;
