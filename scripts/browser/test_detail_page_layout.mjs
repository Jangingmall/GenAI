import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const directory = await mkdtemp(join(tmpdir(), "detail-layout-test-"));
let browser;
try {
  execFileSync(process.env.EVAL_PYTHON || resolve(".venv/bin/python"), [
    "tests/build_detail_page_visual_fixtures.py", directory,
  ]);
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 774, height: 1000 } });
  const failures = [];
  for (const name of ["editorial-split", "image-first", "catalog-grid", "adaptive", "najeon", "tea"]) {
    await page.goto(pathToFileURL(join(directory, `${name}.html`)).href);
    await page.evaluate(() => document.fonts.ready);
    const result = await page.evaluate(() => {
      const main = document.querySelector("main").getBoundingClientRect();
      // display:none empty paragraphs have a zero rect outside their section;
      // they are not visible overflow and must not fail the geometry check.
      const text = [...document.querySelectorAll("h1,h2,h3,p,th,td,li")]
        .filter(el => el.getClientRects().length > 0);
      const overflow = text.filter(el => {
        const box = el.getBoundingClientRect();
        const section = el.closest("section")?.getBoundingClientRect();
        return el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1 ||
          box.left < main.left - 1 || box.right > main.right + 1 ||
          (section && (box.top < section.top - 1 || box.bottom > section.bottom + 1));
      }).map(el => `${el.tagName}:${el.textContent.slice(0, 20)}`);
      return {
        width: main.width, documentWidth: document.documentElement.scrollWidth, overflow,
        heroFit: getComputedStyle(document.querySelector(".product-image--hero")).objectFit,
        minBody: Math.min(...[...document.querySelectorAll("section p, section td")]
          .map(el => parseFloat(getComputedStyle(el).fontSize))),
        galleryImages: [...document.querySelectorAll(".gallery-section img")].map(el => el.src),
        galleryPositions: [...document.querySelectorAll(".gallery-section img")].map(el => getComputedStyle(el).objectPosition),
        decoded: [...document.images].every(el => el.complete && el.naturalWidth > 0),
        featureHeadingWidth: document.querySelector(".feature-grid .section-heading")?.getBoundingClientRect().width,
        paletteDisplay: document.querySelector(".palette-section") ? getComputedStyle(document.querySelector(".palette-section")).display : null,
        closingPadding: parseFloat(getComputedStyle(document.querySelector(".closing-section")).paddingTop),
        fullBleedGaps: [...document.querySelectorAll(".detail-page--adaptive .usage-section.block--full-bleed")].map(el => {
          const section = el.getBoundingClientRect();
          const image = el.querySelector("img").getBoundingClientRect();
          return Math.max(Math.abs(image.top - section.top), Math.abs(image.bottom - section.bottom));
        }),
      };
    });
    try {
      assert.equal(result.heroFit, "contain", `${name}: hero crops original`);
      assert.equal(result.documentWidth, 774, `${name}: document overflow`);
      assert.equal(result.width, 774, `${name}: export width changed`);
      assert.deepEqual(result.overflow, [], `${name}: clipped/overflowing copy`);
      assert.ok(result.minBody >= 15, `${name}: body copy too small`);
      assert.equal(result.galleryImages.length, 1, `${name}: duplicated single source`);
      assert.ok(result.galleryPositions.every(position => position === "50% 50%"), `${name}: gallery image not centered`);
      assert.ok(result.decoded, `${name}: broken image`);
      assert.ok(result.featureHeadingWidth >= 600, `${name}: feature heading occupies a card cell`);
      assert.ok(result.closingPadding >= 30, `${name}: closing copy touches edges`);
      if (result.paletteDisplay) assert.equal(result.paletteDisplay, "grid", `${name}: palette lacks layout`);
      assert.ok(result.fullBleedGaps.every(gap => gap <= 1), `${name}: full-bleed image leaves blank bands`);
      console.log(`PASS ${name}`);
    } catch (error) {
      failures.push(error.message);
      console.error(`FAIL ${name}`, JSON.stringify(result, (key, value) => key === "galleryImages" ? value.length : value));
    }
  }
  assert.deepEqual(failures, []);
} finally {
  await browser?.close();
  await rm(directory, { recursive: true, force: true });
}
