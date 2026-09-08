import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [, , inputArgument, outputArgument, sectionsFlag, sectionsArgument] = process.argv;

if (!inputArgument || !outputArgument) {
  console.error(
    "Usage: node scripts/render_detail_page.mjs <input.html> <output.png> [--sections <directory>]",
  );
  process.exit(1);
}
if ((sectionsFlag && sectionsFlag !== "--sections") || (sectionsFlag === "--sections" && !sectionsArgument)) {
  console.error(
    "Usage: node scripts/render_detail_page.mjs <input.html> <output.png> [--sections <directory>]",
  );
  process.exit(1);
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 774, height: 1000 },
    deviceScaleFactor: 1,
  });
  await page.goto(pathToFileURL(resolve(inputArgument)).href, {
    waitUntil: "load",
  });
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready;
    const images = [...document.images];
    await Promise.all(
      images.map((image) =>
        image.complete
          ? Promise.resolve()
          : new Promise((resolve) => {
              image.addEventListener("load", resolve, { once: true });
              image.addEventListener("error", resolve, { once: true });
            }),
      ),
    );
  });
  await page.screenshot({
    path: resolve(outputArgument),
    fullPage: true,
    type: "png",
  });
  let sectionCount = 0;
  if (sectionsArgument) {
    const sectionsDirectory = resolve(sectionsArgument);
    await mkdir(sectionsDirectory, { recursive: true });
    const sectionLocator = page.locator("[data-section]");
    sectionCount = await sectionLocator.count();
    const sections = [];
    for (let index = 0; index < sectionCount; index += 1) {
      const section = sectionLocator.nth(index);
      const sectionId = (await section.getAttribute("data-section")) || `section-${index + 1}`;
      const label = (await section.getAttribute("data-section-title")) || sectionId;
      const safeId = sectionId.replace(/[^a-zA-Z0-9_-]+/g, "-");
      const filename = `${String(index + 1).padStart(2, "0")}-${safeId}.png`;
      const outputPath = join(sectionsDirectory, filename);
      await section.screenshot({ path: outputPath, type: "png" });
      const box = await section.boundingBox();
      sections.push({
        order: index + 1,
        section_id: sectionId,
        label,
        file: filename,
        width: box ? Math.round(box.width) : null,
        height: box ? Math.round(box.height) : null,
      });
    }
    await writeFile(
      join(sectionsDirectory, "manifest.json"),
      JSON.stringify({ sections }, null, 2),
      "utf8",
    );
  }
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    height: document.documentElement.scrollHeight,
  }));
  console.log(JSON.stringify({ ...dimensions, section_count: sectionCount }));
} finally {
  await browser.close();
}
