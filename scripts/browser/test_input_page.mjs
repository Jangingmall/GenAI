import assert from "node:assert/strict";
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";

const htmlPath = fileURLToPath(new URL("../../web/ai_input.html", import.meta.url));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const requests = [];
  await page.route("**/api/v1/ai/detail-page-jobs", async (route) => {
    requests.push(route.request());
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "job-test",
        request_id: "request-test",
        status: "QUEUED",
        status_url: "/api/v1/ai/detail-page-jobs/job-test",
        created_at: "2026-08-28T00:00:00Z",
      }),
    });
  });

  await page.goto(`file://${htmlPath}`);
  await page.screenshot({ path: "generated/previews/ai_input_page.png", fullPage: true });
  await page.locator("#detail-page-form").evaluate((element) => {
    element.dataset.apiUrl = "http://127.0.0.1:8000/api/v1/ai/detail-page-jobs";
  });
  assert.equal(await page.locator(".upload-card").count(), 1);
  assert.equal(await page.locator("#product-image-input").count(), 1);
  assert.equal(await page.locator("#product-name").count(), 1);
  assert.equal(await page.locator("#making-method").count(), 1);
  assert.equal(await page.locator("#care-guide").count(), 1);

  const files = [
    { name: "primary.png", mimeType: "image/png", buffer: Buffer.from("primary") },
    { name: "side.png", mimeType: "image/png", buffer: Buffer.from("side") },
  ];
  await page.locator("#product-image-input").setInputFiles(files);
  await page.locator("#product-name").fill("나전 보관함");
  await page.locator("#making-method").fill("표면에 장식 문양을 더해 제작했습니다.");
  await page.locator("#care-guide").fill("마른 천으로 닦아 주세요.");
  const requestPromise = page.waitForRequest("**/api/v1/ai/detail-page-jobs");
  await page.locator("#create-button").click();
  const submittedRequest = await requestPromise;

  assert.equal(requests.length, 1);
  const body = (await submittedRequest.postDataBuffer()).toString();
  assert.match(body, /name="product_image"/);
  assert.match(body, /name="product_images"/);
  assert.match(body, /name="product_name"/);
  assert.match(body, /나전 보관함/);
  assert.match(body, /표면에 장식 문양을 더해 제작했습니다/);
  assert.match(body, /마른 천으로 닦아 주세요/);
  await page.waitForFunction(() => document.querySelector("#submit-status")?.textContent.includes("접수"));
  assert.match(await page.locator("#submit-status").innerText(), /접수/);
} finally {
  await browser.close();
}
