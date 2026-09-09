import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { chromium } from "playwright";

const projectRoot = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const mimeTypes = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript" };
const server = createServer(async (request, response) => {
  try {
    const requestPath = decodeURIComponent(new URL(request.url, "http://127.0.0.1").pathname);
    const filePath = resolve(projectRoot, `.${requestPath}`);
    if (!filePath.startsWith(projectRoot)) throw new Error("unsafe path");
    const data = await readFile(filePath);
    response.writeHead(200, { "content-type": mimeTypes[extname(filePath)] || "text/plain" });
    response.end(data);
  } catch {
    response.writeHead(404);
    response.end("not found");
  }
});

await new Promise((resolveServer) => server.listen(4175, "127.0.0.1", resolveServer));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  let savedBody = "";
  await page.route("**/api/v1/ai/detail-page-jobs/remote-job", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "DRAFT_READY",
        draft: {
          draft_id: "remote-job",
          generation_id: "analysis-remote",
          html: '<img src="data:image/png;base64,iVBORw0KGgo=">',
          source_mime_type: "image/png",
          source_sha256: "source-hash",
          product: { product_type: "나전함", display_name: "서버 초안", summary: "서버에서 받은 초안", keywords: [], features: [], warnings: [] },
          draft: {
            layout_id: "editorial-split",
            product_name: "서버 초안",
            product_type: "나전함",
            summary: "서버에서 받은 초안",
            hero_headline: "서버 헤드라인",
            hero_description: "서버 설명",
            usage_scene: "선반 위",
            features: [],
            keywords: [],
          },
        },
      }),
    });
  });
  await page.route("**/api/v1/ai/detail-page-jobs/remote-job/draft", async (route) => {
    savedBody = route.request().postData() || "";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        draft_id: "remote-job",
        generation_id: "analysis-remote",
        html: '<img src="data:image/png;base64,iVBORw0KGgo=">',
        source_mime_type: "image/png",
        source_sha256: "source-hash",
        product: { product_type: "나전함", display_name: "수정 서버 초안", summary: "수정", keywords: [], features: [], warnings: [] },
        draft: { layout_id: "editorial-split", product_name: "수정 서버 초안", product_type: "나전함", summary: "수정", hero_headline: "수정", hero_description: "수정", usage_scene: "선반", features: [], keywords: [] },
      }),
    });
  });
  await page.route("http://127.0.0.1:8000/api/v1/ai/detail-page-renders", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "COMPLETED", result: { detail_page: { mime_type: "image/png", image_base64: "iVBORw0KGgo=" } } }),
    });
  });

  await page.goto("http://127.0.0.1:4175/web/ai_draft_preview.html?job_id=remote-job");
  await page.waitForFunction(() => document.querySelector("#preview-frame")?.classList.contains("is-ready"));
  assert.equal(await page.locator("#product-name").inputValue(), "서버 초안");
  await page.locator("#product-name").fill("수정 서버 초안");
  await page.locator("#save-draft").click();
  await page.waitForFunction(() => document.querySelector("#save-status")?.textContent.includes("저장 완료"));
  assert.match(savedBody, /수정 서버 초안/);
} finally {
  await browser.close();
  await new Promise((resolveServer) => server.close(resolveServer));
}
