# Case study: building and measuring a search ranking change end to end

## The question

Does fusing semantic retrieval with keyword search, re-ranking with a learned model and personalizing per shopper
sell more than classic BM25 + popularity? Answering it needs three things most portfolio projects skip: a ranker
evaluated on human judgments without leakage, an experiment engine that computes its own verdict, and an honest
account of what is real and what is simulated.

## What is real, what is simulated

| Layer | Source |
|---|---|
| Catalog (42,994 products), 480 queries, 233k graded relevance judgments | WANDS (Wayfair), public |
| Prices, brands, stock, "new" flags | synthesized, deterministic, flagged in `attributes._synthetic` |
| Funnel calibration (view → cart → purchase) | Retailrocket clickstream (2.7M events), public |
| Shoppers, clicks, carts, purchases | simulated: 20k personas, position-biased click model driven by WANDS grades |
| Product photos | 166 generated with Higgsfield (SOUL v2) from name, class and attributes (prompts in `manifest.json`); 17,396 representative photos from the Amazon Berkeley Objects dataset, each the most similar Amazon listing by text embedding (similarity ≥ 0.5, at most 3 products per photo); both labelled on the product page; the remaining 25k products show category tiles |
| Checkout | Agentic Commerce Protocol merchant endpoints with a mock payment provider; orders are real rows in the same event log |

Everything downstream (events, marts, experiment analyses, dashboards) runs on that event log through the same code
a real deployment would use.

## Offline: does the ranker rank better?

Three strategies on held-out WANDS queries (NDCG@10, graded relevance, gain 2^g − 1). Clean protocol: 5-fold CV
over 479 judged queries, ranker retrained per fold, behavioral features zeroed so no click can leak:

| Strategy | NDCG@10 | lift vs A (95% CI) |
|---|---|---|
| A · BM25 (+ popularity, zero here) | 0.688 | baseline |
| B · Hybrid retrieval (RRF) | 0.705 | +0.017 [0.006, 0.029] |
| C · Hybrid + LambdaRank, content features | 0.722 | +0.034 [0.022, 0.045] |

- **Hybrid retrieval** is a modest but significant gain over pure BM25, and a large one over the realistic classic
  baseline: on the 96 test queries never searched during warm-up, BM25 *with* a popularity boost scores 0.584
  against 0.729 for RRF. Popularity learned from other queries pushes popular-but-irrelevant items up.
- **The re-ranker** adds about +0.016 over RRF with content features (significant). With behavioral features the
  full-feature CV shows +0.040 more, but part of that is leakage (popularity on train/val folds), and the production
  model is at parity with RRF on the clean test split (0.711 vs 0.729, CI spans zero).

Two methodology lessons came out of getting those numbers right:

1. **Leakage through popularity.** After the experiment phase had run on all queries, product popularity encoded
   test-query clicks and the control's NDCG@10 moved from 0.58 to 0.71 with no code change. Fix: freeze behavioral
   features at the end of warm-up (which only ever searched train/val queries) for training and evaluation.
2. **A single 96-query split is not enough.** The LTR-vs-RRF verdict flipped sign between runs on the fixed test
   split. 5-fold cross-validation with paired bootstrap CIs made the estimate stable, and showed that part of the
   full-feature CV lift (+0.04) was itself leakage through popularity on train/val folds. The report shows both.

Why the re-ranker adds little here: 330 training queries, labels that only cover what Wayfair's own engine surfaced,
and retrieval ranks that already carry most of the signal. With real click logs the next step is a click model
with inverse-propensity weighting (position is logged for exactly this), and a personalizer trained on user signal.

## Online: do shoppers buy more?

Experiment `ranking_hybrid_ltr_v1`, 14 simulated days, 50/50 hash assignment, every assigned user in the denominator:

| Metric | Control | Treatment | Lift | p |
|---|---|---|---|---|
| Conversion rate (primary) | 11.76% | 12.26% | +4.2% | 0.36 |
| Revenue per visitor | $36.63 | $38.23 | +4.4% | 0.51 (bootstrap CI −$3.2 to +$6.1) |
| Search CTR | 4.42% | 4.61% | +4.3% | 0.0004 |
| No-click rate (guardrail) | 22.3% | 20.7% | −7.1% | 0.02 |
| Zero-result rate (guardrail) | 0.06% | 0.00% | −100% | 0.0009 |

The decision engine's verdict is **keep running**: engagement guardrails are significantly better, conversion and
revenue point the same way but are far from significant, and 7k users per arm is a fraction of the 48k required to
detect a 5% lift at 80% power (smallest detectable lift today: 13%). Sample-ratio check balanced (χ² p = 0.08).

The layered **A/A test** finds no significant difference at the 5% level on any metric. Its primary metric lands at
p = 0.07, a useful reminder that one A/A test in fifteen will sit near the threshold by chance. The
**exploration-slot test** (Thompson sampling at position 5) lifts add-to-cart rate by 12% (p = 0.001) with conversion
+11% at p = 0.08: promising, not proven.

Honest caveats: simulated behaviour makes the A/B outcome partly a property of the click model, so these numbers
validate the pipeline and the statistics, not the business case. CUPED removed ~0% variance because simulated
shoppers rarely have pre-period purchases; on real traffic with repeat customers it typically removes 20-50%.

## Learning the policy instead of picking it

The A/B test picks one ranker for everyone. A contextual bandit can pick per request. From the 68.8k logged searches
of the A/B phases (known 50/50 propensities) the LinTS policy was trained offline and evaluated off-policy:

| Policy | SNIPS | Doubly robust | ESS |
|---|---|---|---|
| Logged traffic (A/B weights) | 8.89% | | |
| Fixed treatment ranker | 8.96% | 8.95% | 17.4k |
| Fixed control (BM25 + popularity) | 8.87% | 8.87% | 11.3k |
| LinTS greedy | 9.30% | 9.72% | 10.3k |

IPS alone would have said the opposite (5.5%): the policy often chooses actions the logs rarely contain, so most
importance weights are zero and plain IPS is biased low. SNIPS and DR correct for that; the ESS column says how much
data actually supports each estimate. The policy was then put into a real A/B test rather than shipped on OPE, and
the live read disagrees with the estimate: conversion 11.28% → 10.58% (−6.2%, p = 0.27), CTR −3.6% (p = 0.02), with
4.7k users per arm. Verdict: keep running, and treat the off-policy lift as unconfirmed. That gap is the point of
the exercise: OPE ranks candidate policies, the A/B test decides.

## Typed decisions as infrastructure

Microsoft-Decision-1 answers fixed-option questions with calibrated probabilities instead of text, at ~1/50 of the
cost of a generative call. It sits in three places: query-intent classification (which category?), assistant routing
(a plain product query goes straight to search, no LLM turn), and a relevance judge over the assistant's final picks.
Because every decision point has a local fallback, the system runs without credentials, and because the judge is
scored against WANDS human grades, the fallback's weakness is measured, not hidden: 46% accuracy, Spearman 0.45. That
is the bar a hosted decision model has to clear before it is trusted to drop products.

## What I would do next with real data

1. Train the ranker on clicks with IPW and compare to the editorial-label model offline and online.
2. Replace the affinity boost with a learned personalizer (session embeddings) and test it as its own experiment.
3. Switch the exploration slot from Thompson sampling on CTR to a revenue-aware bandit.
4. Run the experiment for the full required sample, then a holdback to measure long-term effects.
