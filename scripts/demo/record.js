/* Records the SmartSearch demo as one Playwright video per scene (1920x1080 webm).
   Usage: node record.js [sceneName ...]   (no args = all scenes). Output: ./raw/<scene>.webm */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const WEB = "http://localhost:3000";
const KEYWORD = process.env.ADMIN_PASSWORD || "smartsearch";
const RAW = path.join(__dirname, "raw");
const W = 1920, H = 1080;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// a visible cursor: Playwright videos do not show the real one
const CURSOR = `
(() => {
  const st = document.createElement('style'); st.textContent = 'nextjs-portal{display:none!important}';
  (document.head || document.documentElement).appendChild(st);
  const c = document.createElement('div');
  c.id = '__cursor';
  Object.assign(c.style, { position: 'fixed', zIndex: 2147483647, width: '18px', height: '18px', borderRadius: '50%',
    background: 'rgba(17,17,17,.85)', boxShadow: '0 0 0 3px rgba(255,255,255,.9), 0 4px 14px rgba(0,0,0,.25)',
    pointerEvents: 'none', left: '-50px', top: '-50px', transform: 'translate(-50%,-50%)', transition: 'transform 120ms ease' });
  const add = () => document.body && document.body.appendChild(c);
  document.body ? add() : document.addEventListener('DOMContentLoaded', add);
  window.addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  window.addEventListener('mousedown', () => { c.style.transform = 'translate(-50%,-50%) scale(.6)'; }, true);
  window.addEventListener('mouseup', () => { c.style.transform = 'translate(-50%,-50%) scale(1)'; }, true);
})();`;

async function glide(page, x, y, steps = 24) {
  const start = (await page.evaluate(() => { const c = document.getElementById('__cursor'); return c ? [parseFloat(c.style.left) || 0, parseFloat(c.style.top) || 0] : [0, 0]; }));
  for (let i = 1; i <= steps; i++) {
    const t = i / steps, e = 1 - Math.pow(1 - t, 3);
    await page.mouse.move(start[0] + (x - start[0]) * e, start[1] + (y - start[1]) * e);
    await sleep(16);
  }
}
async function clickAt(page, selector, opts = {}) {
  const el = page.locator(selector).first();
  await el.waitFor({ state: "visible", timeout: 30000 });
  await el.scrollIntoViewIfNeeded();
  // keep the target clear of the sticky header
  const box0 = await el.boundingBox();
  if (box0 && box0.y < 120) { await page.evaluate((dy) => window.scrollBy(0, dy), box0.y - 160); await sleep(350); }
  const b = await el.boundingBox();
  await glide(page, b.x + b.width / 2, b.y + b.height / 2);
  await sleep(250);
  await el.click(opts).catch(() => el.click({ ...opts, force: true }));
}
async function scrollTo(page, y, ms = 1400) {
  await page.evaluate(([y, ms]) => new Promise((res) => {
    const y0 = window.scrollY, t0 = performance.now();
    const step = (t) => { const p = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - p, 3); window.scrollTo(0, y0 + (y - y0) * e); p < 1 ? requestAnimationFrame(step) : res(); };
    requestAnimationFrame(step);
  }), [y, ms]);
}
async function type(page, selector, text) {
  await clickAt(page, selector);
  await page.locator(selector).first().pressSequentially(text, { delay: 55 });
}

/** Console cookie without showing the login page (the console scene shows it on purpose). */
async function login(page) {
  await page.context().request.post(WEB + "/api/admin/login", { data: { password: KEYWORD } });
}

const scenes = {
  async home(page) {
    await page.goto(WEB + "/");
    await page.locator(".glass-clear").first().waitFor({ timeout: 30000 });
    await sleep(2200);
    await glide(page, 980, 420);
    await scrollTo(page, 620, 1600); await sleep(900);
    await clickAt(page, ".glass-clear >> nth=2", { trial: true }); await sleep(900);
    await scrollTo(page, 1320, 1600); await sleep(1400);
    await scrollTo(page, 0, 1200); await sleep(600);
  },
  async search(page) {
    await page.goto(WEB + "/");
    await page.locator(".glass-clear").first().waitFor({ timeout: 30000 });
    await sleep(600);
    await type(page, 'main input[aria-label="Search products"]', "mid-century walnut nightstand under 200");
    await sleep(1300);
    await page.keyboard.press("Enter");
    await page.locator(".glass-clear").first().waitFor({ timeout: 30000 });
    await sleep(2200);
    await clickAt(page, 'button[aria-label="Why this ranking?"] >> nth=1');
    await sleep(2800);
    await page.keyboard.press("Escape"); await sleep(500);
    await scrollTo(page, 760, 1500); await sleep(1200);
    await clickAt(page, 'label:has-text("Modern") input, label:has-text("Mid-Century") input', { trial: true }).catch(() => {});
    await sleep(600);
  },
  async product(page) {
    await page.goto(WEB + "/search?q=mid-century%20walnut%20nightstand%20under%20200");
    await page.locator(".glass-clear").first().waitFor({ timeout: 30000 });
    await sleep(800);
    await clickAt(page, ".glass-clear a >> nth=0");
    await page.getByText("Goes with it").waitFor({ timeout: 30000 });
    await sleep(2600);
    await scrollTo(page, 700, 1600); await sleep(1600);
    await scrollTo(page, 1400, 1600); await sleep(1400);
  },
  async assistant(page) {
    await page.goto(WEB + "/assistant");
    await sleep(900);
    await type(page, '[placeholder="What are you looking for?"]', "Something to make a small balcony cozy, under $300");
    await page.keyboard.press("Enter");
    await page.locator(".glass-clear").first().waitFor({ timeout: 90000 });
    await sleep(3200);
    await scrollTo(page, 500, 1200); await sleep(1000);
    await type(page, '[placeholder="What are you looking for?"]', "Add the first one to my cart");
    await page.keyboard.press("Enter");
    await page.locator("text=/added|in your cart|cart/i").last().waitFor({ timeout: 90000 }).catch(() => {});
    await sleep(2800);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await sleep(1200);
  },
  async checkout(page) {
    await page.goto(WEB + "/cart");
    if (!(await page.locator('button:has-text("Checkout")').count())) {
      // the assistant did not add anything: add two items from a search first
      await page.goto(WEB + "/search?q=outdoor%20patio%20umbrella");
      await page.locator(".glass-clear").first().waitFor({ timeout: 30000 }); await sleep(600);
      await clickAt(page, '.glass-clear button:not([aria-label]) >> nth=0'); await sleep(500);
      await clickAt(page, '.glass-clear button:not([aria-label]) >> nth=4'); await sleep(500);
      await page.goto(WEB + "/cart");
    }
    await page.locator('button:has-text("Checkout")').first().waitFor({ timeout: 30000 });
    await sleep(1400);
    await clickAt(page, 'button:has-text("Checkout")');
    await page.getByText("Shipping").waitFor({ timeout: 30000 });
    await sleep(900);
    await type(page, "#name", "Dana Morales");
    await sleep(400);
    await clickAt(page, 'label:has-text("Express")');
    await sleep(1200);
    await clickAt(page, 'button:has-text("Place order")');
    await page.getByText("Thank you").waitFor({ timeout: 60000 });
    await sleep(2600);
  },
  async console(page) {
    await page.goto(WEB + "/admin");
    await page.locator("#keyword").waitFor({ timeout: 30000 });
    await sleep(600);
    await type(page, "#keyword", KEYWORD);
    await page.keyboard.press("Enter");
    await page.getByText("Revenue per visitor").waitFor({ timeout: 60000 });
    await sleep(3200);
    await scrollTo(page, 520, 1600); await sleep(1600);
    await scrollTo(page, 1100, 1600); await sleep(1400);
  },
  async experiments(page) {
    await login(page);
    const req = page.context().request;
    const list = await (await req.get(WEB + "/api/admin/experiments")).json().catch(() => []);
    for (const e of Array.isArray(list) ? list : []) await req.get(WEB + `/api/admin/experiments/${e.key}/analysis`).catch(() => {});
    await page.goto(WEB + "/admin/experiments");
    await page.getByText("A/A").first().waitFor({ timeout: 60000 });
    await sleep(2400);
    await clickAt(page, 'a[href*="/admin/experiments/"]:not([href$="/new"]) >> nth=0');
    await page.getByText("primary metric").first().waitFor({ timeout: 90000 });
    await sleep(2600);
    await scrollTo(page, 650, 1600); await sleep(1800);
    await scrollTo(page, 1400, 1600); await sleep(1600);
  },
  async builder(page) {
    await login(page);
    await page.goto(WEB + "/admin/experiments/new");
    await page.locator('[aria-label="Message"]').waitFor({ timeout: 60000 });
    await sleep(1200);
    await type(page, '[aria-label="Message"]', "Make the add-to-cart button green and call it Add to bag");
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => Array.from(document.querySelectorAll("input")).some((i) => /bag/i.test(i.value)), null, { timeout: 150000 });
    await sleep(3500);
    await scrollTo(page, 500, 1600); await sleep(1800);
  },
};

(async () => {
  fs.mkdirSync(RAW, { recursive: true });
  const wanted = process.argv.slice(2);
  const names = wanted.length ? wanted : Object.keys(scenes);
  const browser = await chromium.launch();
  for (const name of names) {
    const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, recordVideo: { dir: RAW, size: { width: W, height: H } }, reducedMotion: "no-preference" });
    await ctx.addInitScript(CURSOR);
    const page = await ctx.newPage();
    const t0 = Date.now();
    try {
      await scenes[name](page);
    } catch (e) {
      console.error(`scene ${name} failed:`, e.message);
    }
    const video = page.video();
    await ctx.close();
    const out = path.join(RAW, `${name}.webm`);
    fs.renameSync(await video.path(), out);
    console.log(`${name}: ${((Date.now() - t0) / 1000).toFixed(1)}s -> ${out}`);
  }
  await browser.close();
})();
