import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE_URL;
const CODE = process.env.ACCESS_CODE;
const OUT = process.env.OUT_DIR;
const CLAIM = process.env.CLAIM ?? "LongAlign improves long-context performance by up to 30% but hurts performance on short, generic tasks.";
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL ?? "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
let n = 0;
const shot = async (name) => {
  n += 1;
  const file = `${OUT}/${String(n).padStart(2, "0")}-${name}.png`;
  await page.screenshot({ path: file, fullPage: true });
  console.log("screenshot", file);
};
const log = (...a) => console.log("step:", ...a);

try {
  await page.goto(BASE, { waitUntil: "networkidle" });
  await shot("home");
  await page.getByTestId("claim-input").fill(CLAIM);
  await shot("claim-entered");
  await page.getByTestId("decompose-button").click();
  const gate = page.getByTestId("access-code-input");
  const gated = await gate.waitFor({ timeout: 10000 }).then(() => true, () => false);
  if (gated) {
    await shot("access-code-prompt");
    await gate.fill(CODE ?? "");
    await page.getByTestId("access-code-submit").click();
  } else {
    log("no access-code prompt (server has no FC_ACCESS_CODE)");
  }
  await page.getByTestId("statement-row").first().waitFor({ timeout: 120000 });
  log("statements", await page.getByTestId("statement-row").count());
  await shot("statements-proposed");
  await page.getByTestId("approve-button").click();
  await page.getByTestId("progress").waitFor({ timeout: 60000 });
  await shot("verifying");
  await page.getByTestId("result-overall").waitFor({ timeout: 240000 });
  log("overall", (await page.getByTestId("result-overall").innerText()).replace(/\s+/g, " "));
  const quotes = await page.getByTestId("evidence-quote").count();
  log("quotes", quotes);
  if (quotes === 0) throw new Error("the result shows no evidence quotes");
  log("revised", await page.getByTestId("revised-banner").count(), "needs-attention", await page.getByTestId("needs-attention").count());
  await shot("result");
  await page.getByTestId("review-panel").scrollIntoViewIfNeeded();
  await shot("review-panel");
  await page.getByTestId("view-trace").click();
  await page.getByTestId("span-row").first().waitFor({ timeout: 30000 });
  log("spans", await page.getByTestId("span-row").count());
  await shot("trace-timeline");
  const toggles = page.getByTestId("span-toggle");
  const rows = page.getByTestId("span-row");
  const texts = await rows.allInnerTexts();
  const pick = (re) => texts.findIndex((t) => re.test(t));
  for (const required of [/claim/, /decompose/, /approval/, /retrieve/, /verify/, /finalize/, /review/, /final_message/]) {
    if (pick(required) < 0) throw new Error(`the trace has no ${required} span`);
  }
  for (const [label, re] of [["decompose", /decompose/i], ["retrieve", /retrieve/i], ["verify", /verify/i], ["review-gpt", /review/i], ["final-message", /final_message/i]]) {
    const i = pick(re);
    if (i >= 0) {
      await toggles.nth(i).click();
      await rows.nth(i).scrollIntoViewIfNeeded();
      await shot(`trace-span-${label}`);
      await toggles.nth(i).click();
    }
  }
  await page.goto(`${BASE}/traces`, { waitUntil: "networkidle" });
  await page.getByTestId("run-row").first().waitFor({ timeout: 15000 });
  await shot("traces-list");
  await page.goto(`${BASE}/abstracts`, { waitUntil: "networkidle" });
  await page.getByTestId("doc-search").fill("lost in the middle");
  await page.keyboard.press("Enter");
  await page.getByTestId("doc-row").first().waitFor({ timeout: 15000 });
  await shot("abstracts-search");
  await page.getByTestId("doc-row").first().getByRole("link").first().click();
  await page.getByTestId("doc-abstract").waitFor({ timeout: 15000 });
  await shot("abstract-detail");
  console.log("E2E OK");
} catch (e) {
  await shot("failure");
  console.log("E2E FAILED:", e.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
