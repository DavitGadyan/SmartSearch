# Deployment

## Local

```sh
cp .env.example .env
make setup   # infra → install → migrate → data → warm-up → train → experiments → marts → eval → report
make photos  # optional, once: representative product photos (3.3 GB download, kept under data/, never committed)
make api     # http://localhost:8000/docs
make web     # http://localhost:3000 · console /admin · MLflow http://localhost:5001
```

Fully containerised: `docker compose --profile app up --build` (API runs migrations on start; run the data pipeline
once from the host). Ports: Postgres 5435, Redis 6379, MLflow 5001 (5432 and 5000 are usually taken by a local
Postgres and macOS AirPlay).

## Console access

The console (`/admin`) is behind one shared keyword. `frontend/middleware.ts` checks a signed, 12-hour cookie and
redirects to `/admin/login`; `app/api/admin/login` issues it after a constant-time compare with `ADMIN_PASSWORD`.
Admin API calls go through `app/api/admin/[...path]`, a same-origin proxy that adds the API's `X-API-Key` from the
server-side `ADMIN_API_KEY`, so the key never reaches the browser. Both variables are server-only: locally in
`frontend/.env.local` (Next.js does not read the repository root `.env`), in compose under `web.environment`, on
Vercel as project secrets. Changing the keyword signs everyone out.

## Frontend on Vercel

`frontend/vercel.json` is ready. Set `NEXT_PUBLIC_API_URL`, `ADMIN_API_KEY` (same value as the API) and
`ADMIN_PASSWORD`, then `vercel --prod` from `frontend/`. Product photos are served by the API (`/static/photos`) and
rewritten to `/img/photos/*` on the web origin, so the image optimiser caches them.

## API on Railway

1. Project with PostgreSQL (`CREATE EXTENSION vector;`) and Redis plugins.
2. Deploy `backend/` (Dockerfile). Variables: `DATABASE_URL` (`postgresql+asyncpg://` scheme), `REDIS_URL`,
   `ADMIN_API_KEY`, `CORS_ORIGINS='["https://<vercel-domain>"]'`, `DATA_DIR=/data`, optional `ANTHROPIC_API_KEY`,
   `MLFLOW_TRACKING_URI` (unreachable → file store fallback).
3. Volume at `/data`; seed it once (`railway run make data warmup train experiments marts photos`) or bake
   `data/artifacts` and `data/processed/photos` into the image. Memory: ~1.5 GB for catalog, embeddings and BM25 indexes.

## Caching

- API: gzip above 1 kB; `Cache-Control` on product detail and global rails (60 s, stale-while-revalidate 5 min),
  per-product rails (60 s, no revalidation so impressions are not logged in the background), personal rail (private,
  30 s); in-process TTL caches for rails (60 s global, 10 min per product) and console analyses (60 s, cleared when an
  experiment changes status or receives simulated traffic).
- Web: TanStack Query persists product pages and global rails in `localStorage` for an hour; product pages are
  prefetched on card hover; above-the-fold photos load with priority; `/img/*` carries a one-day browser cache.

## Operations

- Ranker served from `ranking_models.is_champion`; `make train` registers a new version and promotes it when its
  cross-validated NDCG@10 is at least as good or the feature set changed.
- `make marts` refreshes product stats and all materialized views; the API reloads stats on restart.
- Experiments: `POST /experiments`, `PATCH /experiments/{key}/status`; one running experiment per surface.
- `make photos` is idempotent: it resumes downloads, skips photos already extracted and only fills `image_url` where
  it is empty, so generated photos keep precedence. Restart the API afterwards.
