-- Weekly acquisition cohorts (first activity week) × weeks since acquisition → active users and buyers.
DROP MATERIALIZED VIEW IF EXISTS mart_cohort_retention;
-- @@
CREATE MATERIALIZED VIEW mart_cohort_retention AS
WITH first_seen AS (
    SELECT user_id, date_trunc('week', min(ts))::date AS cohort_week FROM events GROUP BY user_id
),
activity AS (
    SELECT e.user_id, date_trunc('week', e.ts)::date AS week,
           bool_or(e.event_type = 'purchase') AS bought
    FROM events e GROUP BY 1, 2
)
SELECT f.cohort_week,
       (a.week - f.cohort_week) / 7                    AS weeks_since,
       count(DISTINCT a.user_id)                        AS active_users,
       count(DISTINCT a.user_id) FILTER (WHERE a.bought) AS buyers,
       (SELECT count(*) FROM first_seen f2 WHERE f2.cohort_week = f.cohort_week) AS cohort_size
FROM first_seen f
JOIN activity a ON a.user_id = f.user_id
GROUP BY 1, 2;
