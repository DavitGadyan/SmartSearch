# ADR 0001: pgvector plus an in-memory matrix instead of a dedicated vector database

**Status:** accepted

## Context
Semantic retrieval needs nearest-neighbour search over ~43k product embeddings (512-d). Options: Qdrant/Weaviate as a
separate service, pgvector in the existing Postgres, or a NumPy matrix in the API process.

## Decision
Postgres + pgvector (HNSW) is the system of record; an L2-normalised NumPy matrix serves requests. 43k × 512 float32
is 88 MB; a full dot product takes ~5 ms on a laptop CPU.

## Consequences
- One fewer service to run and monitor.
- Semantic scores exist for every candidate, which the LTR needs for BM25-only candidates; an ANN service would need
  extra round trips.
- Beyond ~1-2M products, switch serving to the pgvector HNSW index or an ANN service behind the same `SemanticIndex`
  interface.
