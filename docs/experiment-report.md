# Experiment report

Generated 2026-11-08 23:12 UTC by `scripts/export_report.py` from the live analysis endpoints. Every number below is computed from the event log; nothing is typed in by hand.

**What is real and what is simulated.** The catalog, queries and relevance judgments are the public WANDS dataset (Wayfair). Shopper behaviour is simulated: 20,000 personas with latent taste, a position-biased click model whose relevance signal is the WANDS grade, and cart/purchase rates calibrated to Retailrocket's real funnel. The A/B results therefore validate the *experimentation pipeline and methodology*; the real-data evidence for ranking quality is the offline evaluation at the end.

| Phase | Searches | Impressions | Clicks | Carts | Purchases | Revenue |
|---|---|---|---|---|---|---|
| warmup | 22,843 | 454,278 | 17,999 | 2,711 | 996 | $269,456 |
| experiment | 68,759 | 1,373,494 | 62,779 | 9,654 | 3,642 | $1,057,548 |
| bandit | 22,818 | 456,133 | 21,278 | 3,277 | 1,287 | $372,613 |
## Hybrid retrieval + personalized LTR vs. BM25 + popularity

`ranking_hybrid_ltr_v1` · status **completed** · 2026-10-12 to 2026-10-26 · 14 days

> Fusing semantic retrieval with BM25 and re-ranking with a LambdaRank model plus user affinity surfaces more relevant products, lifting search conversion and revenue per visitor without hurting CTR or zero-result rate.

**Sample ratio check:** control 7,056 · treatment 7,269 (χ² p = 0.075) → balanced

### treatment vs control (7,269 vs 7,056 users)

**Recommendation: Inconclusive, keep running**

treatment vs control: conversion rate 11.76% → 12.26% (+4.2% relative; 95% CI for the absolute difference -0.57% to 1.56%; p = 0.3628). Revenue per visitor $36.63 → $38.23 (+4.4%; Welch p = 0.5092; bootstrap 95% CI $-3.18 to $6.08). CUPED with pre-period revenue removed 0% of variance (adjusted p = 0.5079). Not significant at alpha = 0.05. The test has 7,056 users per arm vs 48,117 required to detect a 5% relative lift with 80% power; the smallest effect detectable right now is 12.9%. Estimated 81.5 more days at current traffic.

| Metric | Control | Treatment | Relative lift | 95% CI (abs.) | p-value | Test |
|---|---|---|---|---|---|---|
| Conversion rate (buyers / assigned users) (primary) | 11.76% | 12.26% | +4.2% | -0.57% to 1.56% | 0.3628 | two proportion ztest |
| Search CTR (clicks / impressions) | 4.42% | 4.61% | **+4.3%** | 0.09% to 0.29% | 0.0004 | delta method ztest |
| Add-to-cart rate (carts / clicks) | 15.38% | 15.55% | +1.1% | -0.62% to 0.96% | 0.6717 | delta method ztest |
| Revenue per assigned user | $36.63 | $38.23 | +4.4% | $-3.15 to $6.35 | 0.5092 | welch ttest |
| Average order value | $286.21 | $291.59 | +1.9% | $-20.37 to $31.12 | 0.6823 | delta method ztest |
| Zero-result rate (guardrail) | 0.06% | 0.00% | **-100.0%** | -0.10% to -0.03% | 0.0009 | delta method ztest |
| Searchers with no click (guardrail) | 22.29% | 20.70% | **-7.1%** | -2.93% to -0.24% | 0.0206 | two proportion ztest |

Revenue robustness: bootstrap 95% CI for the RPV difference $-3.18 to $6.08; CUPED (pre-period revenue) θ = -0.005, variance reduction 0%, adjusted p = 0.5079.
Power: 7,056 users per arm of 48,117 required to detect a 5% relative lift at 80% power; smallest detectable lift now 12.9%; always-valid (mSPRT) p = 1.0000.

## A/A sanity check (layered on the ranking test)

`aa_sanity_check` · status **completed** · 2026-10-12 to 2026-10-26 · 14 days

> Two identically treated random halves should show no significant difference on any metric. Used to validate the assignment hash and the statistics engine.

**Sample ratio check:** a1 7,160 · a2 7,165 (χ² p = 0.967) → balanced

### a2 vs a1 (7,165 vs 7,160 users)

**Recommendation: Inconclusive, keep running**

a2 vs a1: conversion rate 12.51% → 11.51% (-8.0% relative; 95% CI for the absolute difference -2.06% to 0.07%; p = 0.0658). Revenue per visitor $38.87 → $36.02 (-7.3%; Welch p = 0.2397; bootstrap 95% CI $-7.55 to $1.93). CUPED with pre-period revenue removed 0% of variance (adjusted p = 0.2399). Not significant at alpha = 0.05. The test has 7,160 users per arm vs 44,834 required to detect a 5% relative lift with 80% power; the smallest effect detectable right now is 12.4%. Estimated 73.7 more days at current traffic.

| Metric | Control | Treatment | Relative lift | 95% CI (abs.) | p-value | Test |
|---|---|---|---|---|---|---|
| Conversion rate (buyers / assigned users) (primary) | 12.51% | 11.51% | -8.0% | -2.06% to 0.07% | 0.0658 | two proportion ztest |
| Search CTR (clicks / impressions) | 4.53% | 4.51% | -0.6% | -0.13% to 0.08% | 0.6357 | delta method ztest |
| Add-to-cart rate (carts / clicks) | 15.46% | 15.48% | +0.1% | -0.77% to 0.81% | 0.9579 | delta method ztest |
| Revenue per assigned user | $38.87 | $36.02 | -7.3% | $-7.60 to $1.90 | 0.2397 | welch ttest |
| Average order value | $287.77 | $290.28 | +0.9% | $-23.28 to $28.28 | 0.8491 | delta method ztest |
| Zero-result rate (guardrail) | 0.03% | 0.03% | -14.2% | -0.04% to 0.03% | 0.8005 | delta method ztest |
| Searchers with no click (guardrail) | 21.42% | 21.55% | +0.6% | -1.22% to 1.47% | 0.8559 | two proportion ztest |

Revenue robustness: bootstrap 95% CI for the RPV difference $-7.55 to $1.93; CUPED (pre-period revenue) θ = -0.005, variance reduction 0%, adjusted p = 0.2399.
Power: 7,160 users per arm of 44,834 required to detect a 5% relative lift at 80% power; smallest detectable lift now 12.4%; always-valid (mSPRT) p = 0.5810.

## Thompson-sampling exploration slot for cold-start products

`exploration_slot` · status **completed** · 2026-10-26 to 2026-11-02 · 7 days

> Reserving result position 5 for a Thompson-sampled cold product gives new items impressions without measurably hurting conversion or revenue per visitor.

**Sample ratio check:** off 4,899 · on 4,808 (χ² p = 0.356) → balanced

### on vs off (4,808 vs 4,899 users)

**Recommendation: Inconclusive, keep running**

on vs off: conversion rate 9.68% → 10.75% (+11.1% relative; 95% CI for the absolute difference -0.13% to 2.28%; p = 0.0796). Revenue per visitor $30.09 → $32.04 (+6.5%; Welch p = 0.4796; bootstrap 95% CI $-3.23 to $7.34). CUPED with pre-period revenue removed 0% of variance (adjusted p = 0.4741). Not significant at alpha = 0.05. The test has 4,808 users per arm vs 59,922 required to detect a 5% relative lift with 80% power; the smallest effect detectable right now is 17.5%. Estimated 78.6 more days at current traffic.

| Metric | Control | Treatment | Relative lift | 95% CI (abs.) | p-value | Test |
|---|---|---|---|---|---|---|
| Conversion rate (buyers / assigned users) (primary) | 9.68% | 10.75% | +11.1% | -0.13% to 2.28% | 0.0796 | two proportion ztest |
| Search CTR (clicks / impressions) | 4.57% | 4.60% | +0.7% | -0.11% to 0.17% | 0.6728 | delta method ztest |
| Add-to-cart rate (carts / clicks) | 14.61% | 16.36% | **+12.0%** | 0.70% to 2.80% | 0.0011 | delta method ztest |
| Revenue per assigned user | $30.09 | $32.04 | +6.5% | $-3.46 to $7.36 | 0.4796 | welch ttest |
| Average order value | $297.19 | $280.59 | -5.6% | $-52.22 to $19.02 | 0.3610 | delta method ztest |
| Zero-result rate (guardrail) | 0.00% | 0.00% | n/a | 0.00% to 0.00% | 1.0000 | delta method ztest |
| Searchers with no click (guardrail) | 24.68% | 24.23% | -1.8% | -2.16% to 1.26% | 0.6076 | two proportion ztest |

Revenue robustness: bootstrap 95% CI for the RPV difference $-3.23 to $7.34; CUPED (pre-period revenue) θ = 0.014, variance reduction 0%, adjusted p = 0.4741.
Power: 4,808 users per arm of 59,922 required to detect a 5% relative lift at 80% power; smallest detectable lift now 17.5%; always-valid (mSPRT) p = 0.7070.

## Contextual-bandit policy vs. fixed treatment ranker

`bandit_policy_v1` · status **running** · 2026-11-02 to 2026-11-09 · 6 days

> A LinTS policy that picks the ranking strategy per request from query intent, constraints, shopper history, segment and device (trained off-policy on the earlier experiments, learning online from purchases) converts at least as well as the fixed treatment ranker.

**Sample ratio check:** fixed 4,707 · bandit 4,822 (χ² p = 0.239) → balanced

### bandit vs fixed (4,822 vs 4,707 users)

**Recommendation: Inconclusive, keep running**

bandit vs fixed: conversion rate 11.28% → 10.58% (-6.2% relative; 95% CI for the absolute difference -1.96% to 0.55%; p = 0.2703). Revenue per visitor $34.76 → $31.12 (-10.5%; Welch p = 0.2007; bootstrap 95% CI $-9.16 to $1.92). CUPED with pre-period revenue removed 0% of variance (adjusted p = 0.2011). Not significant at alpha = 0.05. The test has 4,707 users per arm vs 50,454 required to detect a 5% relative lift with 80% power; the smallest effect detectable right now is 16.2%. Estimated 58.3 more days at current traffic.

| Metric | Control | Treatment | Relative lift | 95% CI (abs.) | p-value | Test |
|---|---|---|---|---|---|---|
| Conversion rate (buyers / assigned users) (primary) | 11.28% | 10.58% | -6.2% | -1.96% to 0.55% | 0.2703 | two proportion ztest |
| Search CTR (clicks / impressions) | 4.75% | 4.58% | **-3.6%** | -0.31% to -0.03% | 0.0176 | delta method ztest |
| Add-to-cart rate (carts / clicks) | 15.92% | 15.22% | -4.4% | -1.77% to 0.37% | 0.1996 | delta method ztest |
| Revenue per assigned user | $34.76 | $31.12 | -10.5% | $-9.21 to $1.94 | 0.2007 | welch ttest |
| Average order value | $285.56 | $278.95 | -2.3% | $-41.24 to $28.03 | 0.7085 | delta method ztest |
| Zero-result rate (guardrail) | 0.00% | 0.00% | n/a | 0.00% to 0.00% | 1.0000 | delta method ztest |
| Searchers with no click (guardrail) | 23.58% | 24.74% | +4.9% | -0.56% to 2.88% | 0.1865 | two proportion ztest |

Revenue robustness: bootstrap 95% CI for the RPV difference $-9.16 to $1.92; CUPED (pre-period revenue) θ = -0.001, variance reduction 0%, adjusted p = 0.2011.
Power: 4,707 users per arm of 50,454 required to detect a 5% relative lift at 80% power; smallest detectable lift now 16.2%; always-valid (mSPRT) p = 1.0000.

## Offline ranking evaluation (WANDS human judgments)

Protocol: 5-fold cross-validation over 479 judged queries, ranker retrained per fold (300 rounds), content features only (behavioral features zeroed). Behavioral features frozen at 2026-10-12 (end of warm-up, before any test query was searched).

| Strategy | NDCG@10 | NDCG@20 | MRR | P@10 | Recall@50 | MAP@10 | NDCG@10 lift vs A | 95% CI | Win rate |
|---|---|---|---|---|---|---|---|---|---|
| A · BM25 + popularity | 0.6881 | 0.6860 | 0.8844 | 0.815 | 0.2520 | 0.7704 | baseline |  |  |
| B · Hybrid retrieval (RRF) | 0.7052 | 0.7015 | 0.9179 | 0.847 | 0.2506 | 0.8144 | +0.0171 | [0.006, 0.029] | 35% |
| C · Hybrid + LambdaRank | 0.7216 | 0.7213 | 0.9310 | 0.861 | 0.2585 | 0.8319 | +0.0335 | [0.022, 0.045] | 40% |

Champion `ltr_v3` on the fixed 96-query test split: A NDCG@10 0.5843, B NDCG@10 0.7288, C NDCG@10 0.7106.
