/* Visits every route once so the dev server has compiled them (and the API caches are warm) before recording. */
const { chromium } = require("playwright");
const WEB = "http://localhost:3000";
const KEYWORD = process.env.ADMIN_PASSWORD || "smartsearch";
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await ctx.newPage();
  const go = async (url, text) => { const t = Date.now(); await page.goto(url); if (text) await page.getByText(text).first().waitFor({ timeout: 90000 }).catch(() => {}); console.log(`${url.replace(WEB, "")} ${Date.now() - t} ms`); };
  await go(WEB + "/", "Trending");
  await go(WEB + "/search?q=mid-century%20walnut%20nightstand%20under%20200", "results for");
  await go(WEB + "/product/4847", "Goes with it");
  await go(WEB + "/assistant", "Assistant");
  await go(WEB + "/cart", "cart");
  await go(WEB + "/admin/login", "Keyword");
  await page.locator("#keyword").fill(KEYWORD); await page.locator("#keyword").press("Enter");
  await page.getByText("Revenue per visitor").first().waitFor({ timeout: 90000 });
  await go(WEB + "/admin/experiments", "A/A");
  await go(WEB + "/admin/experiments/ranking_hybrid_ltr_v1", "What changed");
  await go(WEB + "/admin/experiments/new", "New experiment");
  await go(WEB + "/admin/search", "NDCG");
  await go(WEB + "/admin/shoppers", "");
  await browser.close();
})();
