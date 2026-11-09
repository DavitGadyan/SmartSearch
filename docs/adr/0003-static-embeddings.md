# ADR 0003: static embeddings (model2vec) instead of a transformer encoder

**Status:** accepted

## Context
Semantic retrieval needs query and product embeddings. Sentence-transformers needs torch; fastembed needs
onnxruntime. Neither ships wheels for x86_64 macOS on current versions, and both make containers heavy.

## Decision
`model2vec` static embeddings (`minishlab/potion-retrieval-32M`, 512-d): pure NumPy, ~130 MB, thousands of texts per
second on CPU. Model name and dimension are configuration (`EMBEDDING_MODEL`, `EMBEDDING_DIM`).

## Consequences
- Lower semantic quality than a transformer encoder; mitigated because retrieval is fused with BM25 and re-ranked.
- Portable everywhere (dev laptop, CI, slim images). Swapping in a transformer encoder is a one-class change in
  `ml/retrieval/embedder.py` plus a re-embed.
