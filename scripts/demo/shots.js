/* Portfolio screenshots at 1440x900 (retina) with deterministic waits.
   Usage: node shots.js <outDir>            all steps
          STEPS=8,12,13 node shots.js <outDir>   only those step numbers */
const { chromium } = require("playwright");
const path = require("path");
const WEB = "http://localhost:3000";
const KEYWORD = process.env.ADMIN_PASSWORD || "smartsearch";
const OUT = process.argv[2] || path.join(__dirname, "shots");
const ONLY = process.env.STEPS ? new Set(process.env.STEPS.split(",").map(Number)) : null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  await ctx.addInitScript(() => { const st = document.createElement("style"); st.textContent = "nextjs-portal{display:none!important}"; (document.head || document.documentElement).appendChild(st); });
  const page = await ctx.newPage();
  const shot = (name) => page.screenshot({ path: path.join(OUT, name), type: "png" });
  const cards = async (ms = 1500) => { await page.locator(".glass-clear").first().waitFor({ timeout: 90000 }); await sleep(ms); };
  const text = async (t, ms = 1800) => { await page.getByText(t).first().waitFor({ timeout: 90000 }); await sleep(ms); };
  const loaded = async (ms = 1200) => { await page.waitForFunction(() => document.querySelectorAll(".shimmer").length === 0, null, { timeout: 90000 }).catch(() => {}); await sleep(ms); };
  const login = async () => { await ctx.request.post(WEB + "/api/admin/login", { data: { password: KEYWORD } }); };

  const steps = {
    1: async () => { await page.goto(WEB + "/"); await cards(2500); await shot("01-home.png"); },
    2: async () => { await page.goto(WEB + "/"); await cards(1200); await page.evaluate(() => window.scrollTo(0, 640)); await sleep(1800); await shot("02-rails.png"); },
    3: async () => { await page.goto(WEB + "/search?q=mid-century%20walnut%20nightstand%20under%20200"); await cards(1500); await page.locator('button[aria-label="Why this ranking?"]').nth(1).click(); await sleep(1500); await shot("03-search-explain.png"); },
    4: async () => { await page.goto(WEB + "/product/4847"); await text("Goes with it", 2500); await shot("04-product.png"); },
    5: async () => { await page.goto(WEB + "/assistant"); await sleep(800); const box = page.locator('[placeholder="What are you looking for?"]'); await box.fill("Something to make a small balcony cozy, under $300"); await box.press("Enter"); await page.locator(".glass-clear").first().waitFor({ timeout: 120000 }); await sleep(2500); await shot("05-assistant.png"); },
    6: async () => {
      await page.goto(WEB + "/search?q=outdoor%20patio%20umbrella"); await cards(800);
      await page.locator(".glass-clear button:not([aria-label])").nth(0).click(); await sleep(300);
      await page.locator(".glass-clear button:not([aria-label])").nth(4).click(); await sleep(300);
      await page.goto(WEB + "/cart"); await text("Checkout", 800);
      await page.locator('button:has-text("Checkout")').click();
      await page.locator("#name").waitFor({ timeout: 30000 }); await page.locator("#name").fill("Dana Morales");
      await page.locator('label:has-text("Express")').click(); await sleep(900); await shot("06-checkout-acp.png");
    },
    7: async () => { await login(); await page.goto(WEB + "/admin"); await text("Revenue per visitor", 3500); await shot("07-console-overview.png"); },
    8: async () => { await login(); await page.goto(WEB + "/admin/experiments"); await text("A/A", 500); await loaded(2500); await shot("08-experiments.png"); },
    9: async () => { await login(); await page.goto(WEB + "/admin/experiments/ranking_hybrid_ltr_v1"); await text("primary metric", 2500); await shot("09-experiment-detail.png"); await page.evaluate(() => window.scrollTo(0, 560)); await sleep(1500); await shot("10-experiment-result.png"); },
    11: async () => {
      await login(); await page.goto(WEB + "/admin/experiments/new"); await page.locator('[aria-label="Message"]').waitFor({ timeout: 60000 }); await sleep(800);
      await page.locator('[aria-label="Message"]').fill("Make the add-to-cart button green and call it Add to bag"); await page.locator('[aria-label="Message"]').press("Enter");
      await page.waitForFunction(() => Array.from(document.querySelectorAll("input")).some((i) => /bag/i.test(i.value)), null, { timeout: 150000 }); await sleep(3000); await shot("11-experiment-builder.png");
    },
    12: async () => { await login(); await page.goto(WEB + "/admin/search"); await text("Ranking quality", 500); await loaded(1500); await page.getByText("Ranking quality").first().scrollIntoViewIfNeeded(); await page.evaluate(() => window.scrollBy(0, -90)); await sleep(1500); await shot("12-ranking-quality.png"); },
    13: async () => { await login(); await page.goto(WEB + "/admin/shoppers"); await page.locator("table tbody tr").first().waitFor({ timeout: 90000 }).catch(() => {}); await loaded(3000); await shot("13-shoppers.png"); },
  };
  for (const [n, fn] of Object.entries(steps)) {
    if (ONLY && !ONLY.has(Number(n))) continue;
    try { await fn(); console.log("step", n, "ok"); } catch (e) { console.error("step", n, "failed:", e.message.split("\n")[0]); }
  }
  await browser.close();
  console.log("done ->", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
