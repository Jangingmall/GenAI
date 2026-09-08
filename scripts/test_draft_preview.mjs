import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const projectRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const mimeTypes = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "text/javascript",
  ".jpg": "image/jpeg",
  ".png": "image/png",
};
const server = createServer(async (request, response) => {
  try {
    const requestPath = decodeURIComponent(
      new URL(request.url, "http://127.0.0.1").pathname
    );
    const filePath = resolve(projectRoot, `.${requestPath}`);
    if (!filePath.startsWith(projectRoot)) throw new Error("unsafe path");
    const data = await readFile(filePath);
    response.writeHead(200, {
      "content-type": mimeTypes[extname(filePath)] || "application/octet-stream",
    });
    response.end(data);
  } catch {
    response.writeHead(404);
    response.end("not found");
  }
});

await new Promise((resolveServer) => server.listen(4174, "127.0.0.1", resolveServer));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  let approvalRequestBody = "";
  await page.route("http://127.0.0.1:4174/api/v1/ai/detail-page-jobs/job-json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "DRAFT_READY",
        draft: {
          draft_id: "job-json",
          generation_id: "generation-json",
          version: 1,
          preview: {
            source_asset_id: "source-json",
            source_sha256: "source-hash",
            mime_type: "image/jpeg",
            image_url: "/generated/samples/live_najeon_box/photos/01-hero.jpg",
          },
          product: {
            product_type: "나전함",
            display_name: "나전함",
            summary: "JSON으로 전달된 초안",
            keywords: ["나전"],
            features: [],
            warnings: [],
          },
          draft: {
            product_name: "JSON 전달 나전함",
            summary: "JSON으로 전달된 초안",
            hero_headline: "문양의 깊이",
            hero_description: "이미지에서 확인되는 특징입니다.",
            usage_scene: "서재 선반 위",
            features: [],
            keywords: ["나전"],
            layout_id: "editorial-split",
          },
        },
      }),
    });
  });
  await page.route("http://127.0.0.1:8000/api/v1/ai/detail-page-renders", async (route) => {
    approvalRequestBody = route.request().postData() || "";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "COMPLETED",
        backend_delivery_pending: false,
        result: {
          generation_id: "generation-approved",
          detail_page: {
            mime_type: "image/png",
            image_base64: "iVBORw0KGgo=",
          },
        },
      }),
    });
  });
  await page.goto("http://127.0.0.1:4174/web/ai_draft_preview.html?job_id=job-json");
  await page.waitForFunction(() =>
    document.querySelector("#preview-frame")?.classList.contains("is-ready")
  );
  if (!(await page.locator("#preview-frame").evaluate((node) => node.classList.contains("preview-frame")))) {
    throw new Error("preview frame sizing class is missing");
  }
  const initial = await page.frameLocator("#preview-frame").locator("h1").innerText();
  if (initial !== "JSON 전달 나전함") {
    throw new Error(`unexpected initial title: ${initial}`);
  }
  const previewImage = await page.frameLocator("#preview-frame").locator("img").first().getAttribute("src");
  if (!previewImage?.includes("live_najeon_box/photos/01-hero.jpg")) {
    throw new Error(`structured preview asset was not used: ${previewImage}`);
  }
  await page.locator("#hero-headline").fill("장인의 시간이 머무는 문양");
  await page.waitForTimeout(300);
  const updated = await page.frameLocator("#preview-frame").locator(".intro-band h2").innerText();
  if (updated !== "장인의 시간이 머무는 문양") {
    throw new Error(`preview did not update: ${updated}`);
  }
  await page.setViewportSize({ width: 691, height: 1000 });
  const narrowPreview = await page.locator("#preview-frame").evaluate((node) => {
    const rect = node.getBoundingClientRect();
    const wrap = node.parentElement;
    return {
      renderedWidth: rect.width,
      frameWidth: getComputedStyle(node).width,
      transform: getComputedStyle(node).transform,
      scrollable: wrap.scrollWidth > wrap.clientWidth,
    };
  });
  if (narrowPreview.renderedWidth < 600 || narrowPreview.frameWidth !== "774px" || !narrowPreview.transform.startsWith("matrix(") || !narrowPreview.scrollable) {
    throw new Error(`narrow preview sizing is incorrect: ${JSON.stringify(narrowPreview)}`);
  }
  const recommendedLayout = await page.frameLocator("#preview-frame").locator("main").getAttribute("class");
  if (recommendedLayout !== "detail-page detail-page--editorial-split") {
    throw new Error(`AI-recommended layout missing: ${recommendedLayout}`);
  }
  await page.locator("#approve-button").click();
  await page.waitForFunction(() => document.querySelector("#approve-button")?.innerText === "PNG 생성 완료");
  if (!(await page.locator("#png-download").isVisible())) {
    throw new Error("PNG download link is not visible");
  }
  const approvalText = await page.locator("#approve-button").innerText();
  if (approvalText !== "PNG 생성 완료") {
    throw new Error(`approval completion state missing: ${approvalText}`);
  }
  if (!approvalRequestBody.includes('"layout_id":"editorial-split"') || !approvalRequestBody.includes("장인의 시간이 머무는 문양")) {
    throw new Error("approved draft payload is missing current edits");
  }
  await page.screenshot({ path: "generated/previews/ai_draft_preview.png", fullPage: true });
} finally {
  await browser.close();
  await new Promise((resolveServer) => server.close(resolveServer));
}
