# Metrics glossary

## North star and metric tree

```
Revenue per visitor (RPV) = conversion rate × average order value
├── Search engagement:  search CTR, no-click rate, zero-result rate, avg click position
├── Purchase funnel:    click → add-to-cart rate → purchase rate
├── Order economics:    AOV, units per order
└── Guardrails:         p95 search latency, zero-result rate, no-click rate
```

CTR is not the north star: a ranker can earn clicks with attractive but irrelevant items without selling more.
Experiments decide on conversion and RPV; CTR is diagnostic.

## Online metrics

| Metric | Definition | Unit | Test |
|---|---|---|---|
| Conversion rate | users with ≥1 purchase / assigned users | user | two-proportion z-test, Newcombe CI |
| Revenue per visitor | Σ revenue / assigned users (zero-purchase users included) | user | Welch t-test; bootstrap CI; CUPED |
| Purchases per visitor | Σ purchases / assigned users | user | Welch t-test |
| AOV | Σ revenue / Σ purchases | user (ratio) | delta-method z-test |
| Search CTR | Σ clicks / Σ impressions | user (ratio) | delta-method z-test |
| Add-to-cart rate | Σ carts / Σ clicks | user (ratio) | delta-method z-test |
| Zero-result rate | zero-result searches / searches | user (ratio) | delta-method z-test (guardrail) |
| No-click rate | searchers with no click / searchers | user | two-proportion z-test (guardrail) |

Ratio metrics use the delta method because the randomisation unit (user) differs from the analysis unit
(impression, click); per-user numerator and denominator are correlated and naive binomial tests understate variance.

## Offline metrics

Graded relevance from WANDS: Exact = 2, Partial = 1, Irrelevant = 0; unjudged = 0 (Cranfield assumption).

| Metric | Meaning |
|---|---|
| NDCG@k | discounted gain of the top k vs. the ideal ordering; gain 2^grade − 1, so Exact counts 3× Partial |
| MRR | 1 / rank of the first relevant (grade ≥ 1) item |
| P@10 | share of relevant items in the top 10 |
| Recall@50 | share of judged-relevant items in the top 50 (retrieval coverage) |
| MAP@10 | mean average precision at 10 |

Offline metrics show whether the ranker orders judged items well; online metrics show whether shoppers buy more.

## Validity checks

| Check | Catches |
|---|---|
| Sample ratio mismatch (χ², p < 0.001) | broken assignment, bots, logging loss in one arm |
| Power / MDE | whether "not significant" means "no effect" or "too few users" |
| A/A test | false positives from the pipeline itself |
| CUPED | variance from heterogeneous users (pre-period revenue covariate) |
| Benjamini-Hochberg | multiple comparisons across secondary metrics |
| mSPRT always-valid p | peeking before the planned sample size |

## Off-policy evaluation (bandit)

Logged tuples (x, a, p, r): context, action taken, logging propensity, reward. For a target policy π:

| Estimator | Formula | Notes |
|---|---|---|
| IPS | mean of π(a\|x)/p · r | unbiased, high variance when π differs from logging |
| SNIPS | Σ w r / Σ w with w = π(a\|x)/p | trades a little bias for much lower variance |
| Doubly robust | mean of Σ_a π(a\|x) q̂(x,a) + w (r − q̂(x,a)) | unbiased if either the propensities or the reward model q̂ are right |
| ESS | (Σ w)² / Σ w² | effective sample size after weighting; low ESS = don't trust the estimate |

Weights are clipped at 50. Reward models are fit on a held-out half of the logs so DR is not evaluated on its own training data.
