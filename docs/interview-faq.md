# Interview FAQ

Common questions about search, ranking, personalization and experimentation, answered in general terms and then
with what this project does. Numbers come from [experiment-report.md](experiment-report.md).

### What is the difference between search, ranking and personalization?

Search retrieves candidates that match the query. Ranking orders them. Personalization changes the order for a
particular shopper.

Here: BM25 and semantic retrieval produce the candidates, LightGBM LambdaRank orders them, and an affinity boost
re-weights brands, categories and price bands the shopper has engaged with. The persona switcher in the storefront
shows the same query ranked differently for different shoppers.

### BM25 versus semantic search?

BM25 scores word overlap, so it is precise on exact terms and blind to synonyms. Semantic search embeds query and
products as vectors, so it matches meaning ("shoes for long runs" → marathon shoes) at the cost of precision on
specific terms. Production systems combine both.

Here: both run on every query and are fused with reciprocal rank fusion. Hybrid retrieval lifts NDCG@10 from 0.688
(BM25) to 0.705 on human judgments, and from 0.584 to 0.729 against a BM25 + popularity baseline on unseen queries.

### What is learning to rank?

Instead of hand-tuned weights, a model learns from labelled examples which features make a result rank higher.
LambdaRank / LambdaMART optimise a ranking metric such as NDCG directly, grouped by query.

Here: LightGBM LambdaRank with 23 features (retrieval scores and ranks, class match, title overlap, price and its
z-score within the class, rating, reviews, stock, popularity, 30-day CTR, cart and conversion rates). Labels are the
WANDS grades Exact / Partial / Irrelevant with gains 3 / 1 / 0. Hybrid retrieval adds +0.017 NDCG@10 over BM25 (95% CI
0.006 to 0.029) and the re-ranker about +0.016 more, 0.722 in total. Personalization is a separate bounded boost, not a
ranker feature. Each result exposes its feature contributions in the "Why this ranking?" drawer.

### Why NDCG?

Position matters: a relevant item at rank 1 is worth more than at rank 10. NDCG discounts by position, handles
graded relevance, and is normalised so queries with few relevant items compare fairly. MRR, Precision@K and
Recall@K cover the first hit, the top-K quality and the retrieval depth.

Here: NDCG@10 and MRR, 5-fold cross-validation over 479 queries with paired bootstrap confidence intervals. A single
96-query split flipped the LTR verdict between runs, which is why the headline number is cross-validated.

### How do you avoid leakage when evaluating a ranker?

Behavioral features such as popularity encode past clicks on the very queries being evaluated.

Here: after the experiments had run, control NDCG@10 moved from 0.58 to 0.71 with no code change. The fix: freeze
behavioral features at the end of the warm-up period, which never searched test queries, and report a content-only
protocol first. The [case study](case-study.md) documents both numbers.

### How do you handle a new user, or a new product?

New users have no history: fall back to the unpersonalized ranker, popularity and context (query, category,
price). New products have no clicks: give them controlled exposure and learn fast.

Here: cold users receive the unpersonalized ranking (affinities are learned only from a shopper's own events, with
recency decay). Cold products (under 50 impressions) compete for one exploration slot at position 5 via Thompson
sampling on their click posterior. The slot was A/B tested: neutral on conversion and revenue, and it gives cold
products impressions.

### A search engine returns relevant results but conversion is low. What do you do?

Diagnose before modelling: where in the funnel do shoppers drop, and for which queries? Then fix the cause, evaluate
offline, and confirm with an A/B test.

Here: the console's search analytics show CTR and conversion by query with a position-bias curve, and the
opportunity detector ranks revenue at stake: high-volume queries with low conversion, zero-result queries,
high-impression low-CTR products and out-of-stock demand. Each item carries a suggested action.

### How do you keep recommendations from repeating the same products?

Add diversity constraints (brand or category caps, maximal marginal relevance), reserve exploration slots, and
measure coverage and intra-list similarity alongside CTR.

Here: the exploration slot is the only diversity mechanism implemented. Catalog coverage of the recommendation rails
is reported in the console; brand caps and MMR are the next step.

### How do you know a new ranking model is actually better?

Offline first (NDCG on held-out queries with confidence intervals), then an A/B test on business metrics with
guardrails. Check the split is fair (sample-ratio mismatch), use the right test per metric, correct for multiple
comparisons, and state the power before reading the result.

Here: the ranking test moved conversion 11.8% → 12.3% (+4.2%, p = 0.36), CTR +4.3% (p = 0.0004), no-click rate
−7.1% (p = 0.02), zero-result rate to zero; revenue per visitor +4.4% with a bootstrap CI that spans zero. SRM
χ² p = 0.08. CUPED on pre-period revenue, Benjamini-Hochberg on secondary metrics, mSPRT for sequential reads. The
engine's verdict is "keep running": 7k users per arm against 48k needed to detect a 5% lift at 80% power. The
layered A/A test has no significant metric at 5%.

### Why a bandit on top of A/B testing?

An A/B test picks one ranker for everyone. A contextual bandit picks per request and can be evaluated on logged data
before it touches traffic.

Here: linear Thompson sampling trained off-policy from 68.8k logged searches with known propensities. Plain IPS said
5.5% conversion, SNIPS 9.3% and doubly robust 9.7% against 8.96% for the fixed ranker, because the policy chooses
actions the logs rarely contain. The live A/B test then read −6.2% conversion (p = 0.27) and −3.6% CTR (p = 0.02):
the off-policy lift was not confirmed. Off-policy evaluation ranks candidates; the experiment decides.

### How does an AI agent buy from this store?

Through the Agentic Commerce Protocol (OpenAI and Stripe, 2025). The merchant exposes checkout sessions that an agent
creates, prices, completes and cancels, a product feed the agent searches, and delegated payment tokens with a
maximum amount and an expiry so the agent never holds card details.

Here: `/acp/checkout_sessions`, `/acp/feed.json` and a mock `/acp/agentic_commerce/delegate_payment` implement the
spec with idempotency keys, API versioning and the flat error object. The storefront cart and the in-store assistant
check out through the same endpoints; agent orders land in the same event log and experiments as human ones. Details
in [acp.md](acp.md).

### Can a merchant run their own test without engineers?

Yes. In the console, describe the change ("make the add-to-cart button green and call it Add to bag"). The
experimentation assistant drafts control (the current storefront) and treatment, plans the sample size for a 5%
relative lift at 80% power, and after an explicit yes deploys the test to half of the shoppers, runs simulated traffic
with the stated assumed effect, and reports: control and treatment conversion, lift, 95% CI, p, users per arm, and
whether H0 ("the change does not alter conversion") is rejected or not at α = 0.05. Shoppers only see their arm; all
test machinery stays in the console.

### What is real in this project and what is simulated?

Real: 42,994 products, 480 queries and 233k human relevance judgments (Wayfair WANDS), and funnel ratios from the
Retailrocket clickstream. Simulated: shoppers and all their behaviour, prices, brands and stock. The A/B outcome is
therefore partly a property of the click model; it validates the pipeline and the statistics, not a business case.

### Where this maps to a search and discovery data-science role

| Requirement | In this project |
|---|---|
| Design, run and analyze A/B tests | Experiment engine with SRM check, z-test, Welch, bootstrap, CUPED, mSPRT, power and MDE, automatic verdict; ranking, exploration-slot, bandit and A/A tests |
| Statistics and ML on business problems | LambdaRank re-ranker, contextual bandit with off-policy evaluation, relevance judge scored against human labels |
| Search, ranking and personalization | Hybrid retrieval, 23-feature ranker, affinity boost, per-result explanations, cross-validated NDCG, leakage found and fixed |
| Large-scale behavioral data | 2.6M events in PostgreSQL; SQL marts for funnel, search terms, products, experiments and cohorts |
| Model performance to business metrics | Offline lift and online conversion / revenue per visitor in one generated report; revenue-at-stake detector |
| Communication | Generated experiment report, case study with caveats, console with plain-language verdicts |
| SQL and Python | SQL marts in `backend/app/analytics/sql`; pandas, NumPy, scikit-learn, LightGBM, SciPy, statsmodels |
