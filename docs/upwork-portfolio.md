# Upwork portfolio item · SmartSearch

Copy-ready text for the Upwork portfolio form, in the order the form asks for it. Screenshots are in `docs/portfolio/` (1440×900, retina). The demo
video is `docs/demo/smartsearch-demo.mp4` (Upwork takes a YouTube or Vimeo link, so upload it there first).

## Title (70 characters max)

Ecommerce Search, Ranking & A/B Testing Engine · Python, LightGBM, Next.js

Alternative: SmartSearch: hybrid search, learning to rank, A/B tests and an AI shopping agent

## Role

Data Scientist / ML Engineer, end to end: data, retrieval, ranking model, experimentation statistics, recommender
systems, API, storefront and merchant console.

## Description (paste as is, 533 of 600 characters)

SmartSearch is an ecommerce search engine I built end to end. Shoppers search 42,994 real products, a learned ranker orders the results, every change is proven with an A/B test, and an AI assistant can shop and check out for them.

Key results
• Ranking quality (NDCG@10): 0.688 → 0.722
• Online A/B test: CTR +4.3% (p = 0.0004), conversion +4.2%
• Cold-start exploration slot: add-to-cart +12% (p = 0.001)
• Data: 233k human relevance grades, 20k shoppers, 2.6M events
• Stack: Python, LightGBM, FastAPI, PostgreSQL, Next.js, Claude

## Skills tags

Machine Learning · Learning to Rank · Information Retrieval · Recommender Systems · A/B Testing · Statistics ·
Python · FastAPI · PostgreSQL · LightGBM · Next.js · TypeScript · LLM Agents · Data Science

## Project steps (Upwork "Add a step": image + title + description, each under 300 characters)

1. **01-home.png · A storefront built for measurement.** Every search, click, cart and purchase is logged with the
   shopper, the ranking strategy and the experiment arm, so any change can be read in conversion later. The rails
   under the hero are live recommendation surfaces, not static content.

2. **02-rails.png · Recommendations that explain themselves.** "Picked for you" blends co-occurrence neighbours of
   recent items, content neighbours and the shopper's affinity profile; new visitors fall back to trending.
   Each rail logs impressions and clicks so it can be judged by CTR and attributed conversion.

3. **03-search-explain.png · Why this ranking?** Hybrid retrieval returns 200 keyword and 200 semantic candidates,
   fused by reciprocal rank fusion, then LightGBM LambdaRank orders them. The drawer shows the ranker score, the
   bounded personalization term and the top feature contributions, so relevance is debuggable, not a black box.

4. **04-product.png · Three kinds of recommendation on one page.** Similar items come from the embedding space,
   Bought together from co-purchase item-item similarity, Goes with it from a product knowledge graph. Products with a
   photo are shown first among the top candidates; scores are never changed by display rules.

5. **05-assistant.png · An agent that can only sell what the store has.** The Claude assistant calls the store's own
   search, recommendation and graph tools and may only present products a tool returned. It extracts budget and
   constraints, explains each pick, and adds to the cart when asked; greetings get a reply, not a search.

6. **06-checkout-acp.png · Agentic Commerce Protocol checkout.** The cart prices and completes orders through the
   merchant endpoints an external AI agent would use: checkout session, shipping options, delegated payment token,
   completion. The same path serves the storefront and the assistant.

7. **07-console-overview.png · Merchant console.** KPIs count up from live marts: revenue, revenue per visitor,
   conversion, CTR, zero-result rate, with period-over-period deltas, the search funnel and a revenue-at-stake detector
   that ranks where the funnel leaks. Access is behind a keyword; the API key never reaches the browser.

8. **08-experiments.png · Every change is a test.** Ranking tests, an A/A sanity check, the exploration slot, a
   contextual bandit against the fixed ranker, and UI tests created from the console sit in one list with their
   status and verdict. One running experiment per surface keeps assignments clean.

9. **09-experiment-detail.png · What changed, then the result.** The detail page previews both arms, then reports
   control → treatment, confidence interval, p-value and the H0 verdict in plain language. Statistics live under
   "Details": SRM check, CUPED, multiple-comparison correction, power and the required sample size.

10. **10-experiment-result.png · An honest verdict.** Conversion +4.2% at p = 0.36 with 7k users per arm is not
    evidence; a 5% minimum detectable effect needs about 48k per arm, so the engine says "keep running". The
    secondary metrics that did move (CTR +4.3%, p = 0.0004) are shown next to it.

11. **11-experiment-builder.png · An A/B test from one sentence.** "Make the add-to-cart button green and call it
    Add to bag" becomes two arms with live previews, a sample-size plan from the live baseline, a deployment to half
    of the shoppers and a reject / fail-to-reject verdict. Simulated traffic and assumed effects are labelled.

12. **12-ranking-quality.png · Offline quality next to online results.** NDCG@10, MRR and Recall@50 by strategy
    from 5-fold cross-validation with 95% confidence intervals on the lift, next to the champion ranker's feature
    importance from the MLflow registry. Offline wins still have to survive the A/B test to ship.

13. **13-shoppers.png · Segments and cohorts.** Conversion and revenue by persona segment, weekly retention cohorts
    and recommendation performance by rail, so personalization can be checked for who it helps and who it hurts.

## Links

- Repository: https://github.com/DavitGadyan/SmartSearch
- Demo video: upload `docs/demo/smartsearch-demo.mp4` to YouTube or Vimeo and paste the link in the Upwork
  "Add video" field; `smartsearch-demo-720p.mp4` is the smaller upload, `smartsearch-demo-preview.gif` a 24-second
  loop for a README or a message.
## Appendix A · Long form (GitHub, LinkedIn, a cover letter; too long for the Upwork field)

**The problem.** Ecommerce search teams need to prove that a ranking change makes shoppers buy more, not just that it
scores better offline. SmartSearch is a complete, inspectable version of that loop: retrieve, rank, personalize,
record behaviour, test, decide, and let an AI agent buy.

**What I built**

- Hybrid retrieval: BM25 (bm25s) and 512-dimensional static embeddings (model2vec) fused with reciprocal rank fusion. +0.017 NDCG@10 over BM25 alone (95% CI 0.006 to 0.029); on 96 unseen queries 0.584 → 0.729.
- Learning to rank: LightGBM LambdaRank trained on 233k human grades with 23 features (retrieval scores, class match, price z-score, rating, stock, 30-day CTR / cart / conversion rates). 5-fold cross-validated NDCG@10 0.722 vs 0.688 for the baseline. Every result exposes its feature contributions in a "Why this ranking?" drawer.
- Leakage-safe evaluation: behavioural features frozen at the warm-up cutoff; before the fix one split moved the baseline from 0.58 to 0.71 purely from leaked behaviour.
- Personalization: an additive affinity boost bounded to [−1, 1] from brand, category, style, material, colour and price-fit history, cached in Redis, switchable and testable on its own.
- Recommendations: embedding neighbours, co-purchase item-item similarity, knowledge-graph complements (co-purchase, co-view, category edges, Louvain communities) and a blended "Picked for you" rail; a Thompson-sampling exploration slot for cold products (+12% add-to-cart rate, p = 0.001).
- Experimentation engine: sticky salted-hash assignment, two-proportion z-tests, Welch and bootstrap for revenue per visitor, delta method for ratios, CUPED, Benjamini–Hochberg, mSPRT sequential testing, sample-ratio check, power and MDE, automatic ship / keep running / reject verdicts. An A/A test validates the machinery.
- Policy learning: a linear Thompson-sampling contextual bandit chooses the ranker per request; evaluated off-policy (IPS, SNIPS, doubly robust) and then live, where the +4% estimate did not confirm (−6.2%, p = 0.27), reported honestly.
- Agentic commerce: a Claude tool-use assistant that only recommends what the store's APIs returned, adds to the cart and checks out through the merchant side of the Agentic Commerce Protocol (checkout sessions, delegated payment).
- Merchant console behind a password: KPIs and funnel, search terms with position-bias curve, ranking quality, experiment reports with hypothesis verdicts, and a console assistant that drafts both arms of a storefront change, plans the sample size, deploys it to half of the shoppers and reports reject / fail to reject H0.
- Simulation: 20k shopper personas, 2.6M events over 35 days from a position-biased click model calibrated on a real retail clickstream; prices and shopper behaviour are labelled as simulated everywhere.
- Engineering: FastAPI + SQLAlchemy async, PostgreSQL + pgvector, Redis, MLflow model registry, Alembic, 48 backend tests, Next.js 15 storefront and console with persisted query cache, 17,562 product photos (CC BY dataset matched by text similarity, plus generated ones), CI.

**Key numbers**

| Metric | Value |
|---|---|
| Catalog / relevance grades | 42,994 products · 233k human judgments · 479 evaluated queries |
| Offline NDCG@10 | 0.688 (BM25) → 0.705 (hybrid) → 0.722 (hybrid + LambdaRank), 5-fold CV |
| Online, 7k users per arm | conversion +4.2% (p = 0.36, underpowered), CTR +4.3% (p = 0.0004), no-click rate −7.1% (p = 0.02) |
| Required sample for a 5% lift | ≈ 48k users per arm at 80% power |
| Exploration slot | add-to-cart rate +12% (p = 0.001) |
| Simulated traffic | 20k shoppers · 2.6M events · 35 days |

**Stack.** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL + pgvector, Redis, LightGBM, bm25s, model2vec, scipy /
statsmodels, MLflow, Next.js 15, React 19, Tailwind, TanStack Query, Anthropic Claude (Sonnet for the assistant,
Haiku for bulk jobs), Playwright, Docker.

## Appendix B · Recruiter questions this project answers

- **Search vs ranking vs personalization?** Retrieval finds candidates (BM25 + embeddings), the ranker orders them
  (LambdaRank, 23 features), personalization re-orders per shopper (bounded affinity boost). Each is its own
  switchable strategy, so each can be A/B tested alone.
- **Why NDCG@10?** Position matters and grades are graded. It is reported with MRR, Precision@10, Recall@50, MAP@10,
  bootstrap intervals and a per-query win rate.
- **How do you avoid leakage?** Behavioural features frozen at the warm-up cutoff and zeroed for the headline; 5-fold
  cross-validation, not one split.
- **How do you know a ranker is better online?** Sticky 50/50 assignment, SRM check, z-test on conversion, Welch and
  bootstrap on revenue, CUPED, Benjamini–Hochberg, guardrails, power and MDE, then a verdict. An A/A test proves the
  machinery does not invent lifts.
- **Cold start?** New shoppers get a zero boost and trending items; new products get a Thompson-sampling exploration
  slot (position 5, Beta(1 + clicks, 1 + impressions − clicks)).
- **Why a bandit after A/B?** To pick the ranker per request; evaluated off-policy with IPS / SNIPS / doubly robust,
  then tested live, where the estimate did not confirm.
- **Can an AI agent buy?** Yes, over the Agentic Commerce Protocol, the same endpoints the cart uses.
