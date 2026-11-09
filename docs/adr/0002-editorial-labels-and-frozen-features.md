# ADR 0002: train the ranker on editorial labels; freeze behavioral features at the warm-up cutoff

**Status:** accepted

## Context
Two label sources: WANDS human judgments (480 queries, 233k graded pairs) and the simulated event log. Real search
teams train on clicks; here clicks are generated *from* the WANDS grades.

## Decision
Train LambdaRank on editorial grades. Use behavioral data only as features, frozen at the end of the warm-up period
(which searched train/val queries only) for training and offline evaluation. Evaluate with 5-fold cross-validation
over all judged queries, with paired bootstrap CIs.

## Rationale
- A click-trained model would learn the simulator back. Circular, so offline numbers would be meaningless.
- Editorial labels have no position bias; no IPW is needed for the ranker.
- Freezing fixed a leak we measured: after the experiment phase ran on all queries, popularity encoded test-query
  relevance and the control's NDCG@10 moved from 0.58 to 0.71.
- A single 96-query test split flipped the LTR-vs-RRF verdict between runs; CV did not.

## Consequences
- Personalization cannot be a model feature (no user signal in labels); it is an explicit additive boost.
- With real click logs the next step is a click model with inverse-propensity weighting.
