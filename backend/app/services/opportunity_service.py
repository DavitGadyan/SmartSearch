"""Merchant-intelligence opportunity detector: rule-based scans over the marts, ranked by estimated revenue at stake."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics_service import _rows, window


async def detect(db: AsyncSession, days: int = 28, limit: int = 40) -> dict:
    start, end = await window(db, days)
    p = {"s": start, "e": end}
    site = (
        await _rows(
            db,
            "SELECT sum(purchases) AS purchases, sum(searches) AS searches, sum(revenue) AS revenue, sum(clicks) AS clicks, sum(impressions) AS impressions, sum(carts) AS carts FROM mart_funnel_daily WHERE day BETWEEN :s AND :e",
            **p,
        )
    )[0]
    conv = (site["purchases"] or 0) / (site["searches"] or 1)
    ctr = (site["clicks"] or 0) / (site["impressions"] or 1)
    cart_rate = (site["carts"] or 0) / (site["clicks"] or 1)
    aov = (site["revenue"] or 0) / (site["purchases"] or 1)
    opps: list[dict] = []

    for r in await _rows(
        db,
        """
        SELECT query, sum(searches) AS searches, sum(purchases) AS purchases, sum(clicks) AS clicks, sum(impressions) AS impressions, sum(revenue) AS revenue
        FROM mart_search_terms_daily WHERE day BETWEEN :s AND :e GROUP BY query HAVING sum(searches) >= 80""",
        **p,
    ):
        q_conv = r["purchases"] / r["searches"]
        q_ctr = r["clicks"] / (r["impressions"] or 1)
        if q_conv < 0.5 * conv:
            gap = (conv - q_conv) * r["searches"] * aov
            opps.append(
                dict(
                    type="low_conversion_query",
                    severity="high" if gap > 2000 else "medium",
                    title=f'"{r["query"]}" converts at {q_conv:.2%} vs {conv:.2%} site-wide',
                    detail=f"{int(r['searches'])} searches, CTR {q_ctr:.1%}, {int(r['purchases'])} purchases in {days} days.",
                    entity=r["query"],
                    impact=round(gap, 0),
                    actions=[
                        "Inspect top results for relevance and price fit",
                        "Add synonyms / fix query understanding",
                        "Run a ranking A/B test on this query class",
                    ],
                )
            )
        elif q_ctr > 1.3 * ctr and r["clicks"] and (r["purchases"] / r["clicks"]) < 0.5 * conv / ctr:
            opps.append(
                dict(
                    type="high_ctr_low_conversion_query",
                    severity="medium",
                    title=f'"{r["query"]}": shoppers click ({q_ctr:.1%} CTR) but do not buy',
                    detail="Titles attract clicks but the product pages disappoint - likely a title/attribute or price-expectation mismatch.",
                    entity=r["query"],
                    impact=round(0.3 * r["clicks"] * conv / ctr * aov, 0),
                    actions=[
                        "Review attribute completeness for the clicked products",
                        "Check price distribution vs query intent",
                        "Enrich attributes (material, dimensions) with the LLM pipeline",
                    ],
                )
            )

    for r in await _rows(
        db,
        "SELECT query, sum(zero_result_searches) AS zero, sum(searches) AS searches FROM mart_search_terms_daily WHERE day BETWEEN :s AND :e GROUP BY query HAVING sum(zero_result_searches) >= 3 ORDER BY 2 DESC LIMIT 20",
        **p,
    ):
        opps.append(
            dict(
                type="zero_results_query",
                severity="high" if r["zero"] > 20 else "medium",
                title=f'"{r["query"]}" returned no results {int(r["zero"])} times',
                detail=f"{r['zero'] / r['searches']:.0%} of its {int(r['searches'])} searches came back empty.",
                entity=r["query"],
                impact=round(r["zero"] * conv * aov, 0),
                actions=[
                    "Add synonyms or spelling variants",
                    "Check catalog coverage (merchandising gap)",
                    "Fall back to semantic retrieval for this query",
                ],
            )
        )

    for r in await _rows(
        db,
        """
        SELECT m.product_id, p.name, p.product_class, p.in_stock, p.price::float AS price, sum(m.impressions) AS impressions, sum(m.clicks) AS clicks, sum(m.purchases) AS purchases, avg(m.avg_impression_position) AS pos
        FROM mart_product_daily m JOIN products p ON p.id = m.product_id WHERE m.day BETWEEN :s AND :e GROUP BY 1, 2, 3, 4, 5 HAVING sum(m.impressions) >= 150 ORDER BY impressions DESC LIMIT 400""",
        **p,
    ):
        p_ctr = r["clicks"] / r["impressions"]
        if not r["in_stock"] and r["clicks"] >= 5:
            opps.append(
                dict(
                    type="out_of_stock_demand",
                    severity="high",
                    title=f"Out of stock but in demand: {r['name'][:60]}",
                    detail=f"{int(r['impressions'])} impressions and {int(r['clicks'])} clicks while unavailable ({r['product_class']}).",
                    entity=r["product_id"],
                    impact=round(r["clicks"] * cart_rate * 0.34 * r["price"], 0),
                    actions=[
                        "Restock or set a back-in-stock notification",
                        "Demote further in ranking until available",
                        "Recommend in-stock alternatives on the product page",
                    ],
                )
            )
        elif p_ctr < 0.4 * ctr and r["pos"] and r["pos"] <= 6:
            opps.append(
                dict(
                    type="low_ctr_product",
                    severity="medium",
                    title=f"Shown high, rarely clicked: {r['name'][:60]}",
                    detail=f"Avg position {r['pos']:.1f}, CTR {p_ctr:.1%} vs {ctr:.1%} site-wide over {int(r['impressions'])} impressions.",
                    entity=r["product_id"],
                    impact=round((ctr - p_ctr) * r["impressions"] * cart_rate * 0.34 * r["price"], 0),
                    actions=[
                        "Improve title / primary image",
                        "Check price vs category",
                        "Let the ranker demote it (CTR feature) or bury it for the affected queries",
                    ],
                )
            )

    cold = (
        await _rows(
            db,
            "SELECT count(*) AS n FROM products p LEFT JOIN product_stats s ON s.product_id = p.id WHERE p.is_new AND p.in_stock AND coalesce(s.impressions_30d, 0) = 0",
        )
    )[0]["n"]
    if cold:
        opps.append(
            dict(
                type="cold_start_inventory",
                severity="low",
                title=f"{cold:,} new in-stock products have never been shown",
                detail="New items have no behavioral signal, so popularity-aware ranking never surfaces them.",
                entity=None,
                impact=None,
                actions=[
                    "Keep the Thompson-sampling exploration slot experiment running",
                    "Seed with content-based similarity to proven sellers",
                ],
            )
        )

    opps.sort(key=lambda o: -(o["impact"] or 0))
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "site": {"conversion_per_search": conv, "ctr": ctr, "cart_rate": cart_rate, "aov": aov},
        "count": len(opps),
        "opportunities": opps[:limit],
    }
