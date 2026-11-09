-- One row per assigned user per experiment: the correct denominator for every experiment metric
-- (users who never clicked or bought are kept with zeros). Window = [assignment, experiment end).
-- pre_* columns summarise the pre-period (CUPED covariates).
DROP MATERIALIZED VIEW IF EXISTS mart_experiment_user;
-- @@
CREATE MATERIALIZED VIEW mart_experiment_user AS
WITH a AS (
    SELECT ea.experiment_key, ea.user_id, ea.variant, ea.assigned_at, e.start_at, e.end_at,
           coalesce((e.config->>'pre_period_days')::int, 7) AS pre_days
    FROM experiment_assignments ea
    JOIN experiments e ON e.key = ea.experiment_key
),
post AS (
    SELECT a.experiment_key, a.user_id, a.variant, a.assigned_at,
           count(*)        FILTER (WHERE ev.event_type = 'search')                               AS searches,
           count(*)        FILTER (WHERE ev.event_type = 'search' AND ev.result_count = 0)       AS zero_result_searches,
           count(*)        FILTER (WHERE ev.event_type = 'impression')                           AS impressions,
           count(*)        FILTER (WHERE ev.event_type = 'click')                                AS clicks,
           count(*)        FILTER (WHERE ev.event_type = 'add_to_cart')                          AS carts,
           count(*)        FILTER (WHERE ev.event_type = 'purchase')                             AS purchases,
           coalesce(sum(ev.revenue) FILTER (WHERE ev.event_type = 'purchase'), 0)::float          AS revenue,
           count(DISTINCT ev.session_id) FILTER (WHERE ev.event_type = 'search')                 AS search_sessions,
           count(DISTINCT ev.session_id) FILTER (WHERE ev.event_type = 'click')                  AS click_sessions,
           count(DISTINCT ev.metadata->>'order_id') FILTER (WHERE ev.event_type = 'purchase')        AS orders
    FROM a
    LEFT JOIN events ev ON ev.user_id = a.user_id AND ev.ts >= a.assigned_at AND ev.ts < COALESCE(a.end_at, now() + interval '1 day')
    GROUP BY 1, 2, 3, 4
),
pre AS (
    SELECT a.experiment_key, a.user_id,
           coalesce(sum(ev.revenue) FILTER (WHERE ev.event_type = 'purchase'), 0)::float AS pre_revenue,
           count(*) FILTER (WHERE ev.event_type = 'purchase')                            AS pre_purchases,
           count(*) FILTER (WHERE ev.event_type = 'search')                              AS pre_searches,
           count(*) FILTER (WHERE ev.event_type = 'click')                               AS pre_clicks
    FROM a
    LEFT JOIN events ev ON ev.user_id = a.user_id
                       AND ev.ts <  a.start_at
                       AND ev.ts >= a.start_at - make_interval(days => a.pre_days)
    GROUP BY 1, 2
)
SELECT post.*, pre.pre_revenue, pre.pre_purchases, pre.pre_searches, pre.pre_clicks,
       (post.purchases > 0)::int AS converted,
       (post.clicks > 0)::int    AS clicked,
       (post.carts > 0)::int     AS carted
FROM post
JOIN pre USING (experiment_key, user_id);
-- @@
CREATE UNIQUE INDEX ix_mart_experiment_user ON mart_experiment_user (experiment_key, user_id);
-- @@
DROP MATERIALIZED VIEW IF EXISTS mart_experiment_daily;
-- @@
CREATE MATERIALIZED VIEW mart_experiment_daily AS
WITH days AS (
    SELECT ea.experiment_key, ea.variant, date_trunc('day', ea.assigned_at)::date AS day, count(*) AS new_users
    FROM experiment_assignments ea GROUP BY 1, 2, 3
),
ev AS (
    SELECT ea.experiment_key, ea.variant, date_trunc('day', e.ts)::date AS day,
           count(*) FILTER (WHERE e.event_type = 'search')     AS searches,
           count(*) FILTER (WHERE e.event_type = 'impression') AS impressions,
           count(*) FILTER (WHERE e.event_type = 'click')      AS clicks,
           count(*) FILTER (WHERE e.event_type = 'add_to_cart') AS carts,
           count(*) FILTER (WHERE e.event_type = 'purchase')   AS purchases,
           count(DISTINCT e.user_id) FILTER (WHERE e.event_type = 'purchase') AS buyers,
           coalesce(sum(e.revenue) FILTER (WHERE e.event_type = 'purchase'), 0)::float AS revenue
    FROM experiment_assignments ea
    JOIN experiments x ON x.key = ea.experiment_key
    JOIN events e ON e.user_id = ea.user_id AND e.ts >= ea.assigned_at AND e.ts < COALESCE(x.end_at, now() + interval '1 day')
    GROUP BY 1, 2, 3
)
SELECT coalesce(d.experiment_key, ev.experiment_key) AS experiment_key,
       coalesce(d.variant, ev.variant)               AS variant,
       coalesce(d.day, ev.day)                       AS day,
       coalesce(d.new_users, 0) AS new_users,
       coalesce(ev.searches, 0) AS searches, coalesce(ev.impressions, 0) AS impressions, coalesce(ev.clicks, 0) AS clicks,
       coalesce(ev.carts, 0) AS carts, coalesce(ev.purchases, 0) AS purchases, coalesce(ev.buyers, 0) AS buyers, coalesce(ev.revenue, 0) AS revenue
FROM days d
FULL OUTER JOIN ev ON ev.experiment_key = d.experiment_key AND ev.variant = d.variant AND ev.day = d.day;
