const draft = {
  layout_id: "adaptive",
  product_name: "화조문양 문양 나전함",
  summary: "검은 칠면 위에 화조와 덩굴 문양을 더해 완성한 다층 구조의 나전 보관함입니다.",
  hero_headline: "어두운 칠 위에 피어난 문양",
  hero_description: "검은 바탕 위로 이어지는 화조와 덩굴 문양이 차분한 깊이와 섬세한 리듬을 전합니다.",
  usage_scene: "서재, 거실 선반, 침실 협탁 위에 두고 작은 소품을 정돈하는 장면을 상상해 보세요.",
  features: [
    { title: "촘촘한 형태와 깊은 문양", description: "겹겹이 쌓인 구조와 반복되는 문양이 단정한 입체감을 만듭니다." },
    { title: "빛에 따라 달라지는 장식감", description: "검은 바탕 위 장식 요소가 빛의 방향에 따라 다른 표정을 보여 줍니다." },
    { title: "담백한 직사각형 실루엣", description: "수직으로 쌓인 비례와 평평한 면이 공간에 안정적인 균형을 더합니다." },
  ],
  page_plan: [
    { section_id: "hero", block_type: "hero", eyebrow: "OBJECT TEA ART", title: "차잔을 넘어", body: "테이블에 남는 형상", variant: "paper", photo_id: "hero" },
    { section_id: "core-value", block_type: "statement", eyebrow: "CORE VALUE", title: "오브젝트형 실루엣과 4가지 메탈 컬러", body: "서로 다른 표면과 형태가 한 장면 안에서 리듬을 만듭니다.", variant: "dark" },
    { section_id: "features", block_type: "feature_grid", eyebrow: "VISIBLE DETAILS", title: "형태와 표면을 읽는 방법", body: "원본 이미지에서 확인되는 요소를 중심으로 구성했습니다.", variant: "paper" },
    { section_id: "detail-01", block_type: "detail_split", eyebrow: "METAL DETAIL", title: "촘촘한 형태와 깊은 문양", body: "겹겹이 쌓인 구조와 반복되는 문양이 단정한 입체감을 만듭니다.", variant: "image-left", photo_id: "detail" },
    { section_id: "detail-02", block_type: "detail_split", eyebrow: "SILHOUETTE", title: "빛에 따라 달라지는 장식감", body: "검은 바탕 위 장식 요소가 빛의 방향에 따라 다른 표정을 보여 줍니다.", variant: "image-right", photo_id: "detail" },
    { section_id: "usage-scene", block_type: "usage_scene", eyebrow: "PREMIUM TEA TIME", title: "차를 내는 순간, 한 장면으로 정리됩니다.", body: "서재, 거실 선반, 침실 협탁 위에 두고 작은 소품을 정돈하는 장면을 상상해 보세요.", variant: "dark", photo_id: "lifestyle" },
    { section_id: "gallery", block_type: "gallery", eyebrow: "PRODUCT GALLERY", title: "4가지 표면의 인상", body: "각기 다른 색과 형태를 가까이에서 살펴보세요.", variant: "paper" },
    { section_id: "recommendation", block_type: "recommendation", eyebrow: "RECOMMENDED SCENE", title: "이런 자리에 더 잘 어울립니다.", body: "제품의 표면과 실루엣이 돋보이는 장면을 제안합니다.", variant: "sand", items: [{ label: "공유 테이블", value: "차를 함께 내는 자리" }, { label: "작은 선반", value: "빛이 머무는 공간" }, { label: "차분한 협탁", value: "하루의 물건을 정리하는 자리" }] },
    { section_id: "info", block_type: "info_table", eyebrow: "PRODUCT INFORMATION", title: "주문 전 확인할 기본 정보", body: "이미지에서 확인되는 범위만 정리했습니다.", variant: "paper", items: [{ label: "제품 유형", value: "나전 보관함" }, { label: "표면", value: "검은 칠면과 장식 문양" }, { label: "정확한 규격", value: "별도 확인 필요" }] },
    { section_id: "notice", block_type: "notice", eyebrow: "IMAGE-BASED NOTE", title: "확인되지 않은 정보는 따로 확인해 주세요.", body: "최종 승인 전 문구를 검토할 수 있습니다.", variant: "dark" },
    { section_id: "closing", block_type: "closing", eyebrow: "OBJECT STORY", title: "차를 내는 시간에, 오브제의 인상을 더합니다.", body: "제품의 형태와 표면에서 발견한 이야기를 담았습니다.", variant: "paper" },
  ],
};

const imageUrl = "../generated/samples/live_najeon_box/photos/01-hero.jpg";
const editor = document.querySelector("#draft-editor");
const featureFields = document.querySelector("#feature-fields");
const frame = document.querySelector("#preview-frame");
const loading = document.querySelector("#preview-loading");
const draftState = document.querySelector("#draft-state");
const saveStatus = document.querySelector("#save-status");
const approveButton = document.querySelector("#approve-button");
const saveButton = document.querySelector("#save-draft");
const approvalResult = document.querySelector("#approval-result");
const pngDownload = document.querySelector("#png-download");
const approvalApiUrl = document.body.dataset.approvalApiUrl;
const draftSaveApiUrl = document.body.dataset.draftSaveApiUrl;
let pageCss = "";
let imageDataUri = "";
let renderTimer = null;
const jobId = new URLSearchParams(window.location.search).get("job_id");
let draftVersion = 1;
const layoutLabels = {
  adaptive: "제품 맞춤형 에디토리얼",
  "editorial-split": "에디토리얼 분할형",
  "image-first": "이미지 중심형",
  "catalog-grid": "카탈로그 그리드형",
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function imageTag(className, alt) {
  return `<img class="product-image ${className}" src="${imageDataUri}" alt="${escapeHtml(alt)}">`;
}

function featureCards(features) {
  return features.map((feature, index) => {
    const accent = ["jade", "red", "yellow"][index % 3];
    return `<article class="feature-card">
  <span class="feature-card__accent feature-card__accent--${accent}"></span>
  <h3>${escapeHtml(feature.title)}</h3>
  <p>${escapeHtml(feature.description)}</p>
</article>`;
  }).join("\n");
}

function splitSections(features, productName) {
  return features.map((feature, index) => {
    const side = index % 2 ? "split-section--reverse" : "";
    const position = ["center-top", "center-center", "center-bottom"][index % 3];
    return `<section class="split-section ${side}" data-section="detail-0${index + 1}" data-section-title="${escapeHtml(feature.title)}">
  <div class="split-section__media split-section__media--${position}">${imageTag("product-image--split", `${productName} 상세 이미지`)}</div>
  <div class="split-section__copy">
    <span class="eyebrow">DETAIL 0${index + 1}</span>
    <h2>${escapeHtml(feature.title)}</h2>
    <p>${escapeHtml(feature.description)}</p>
  </div>
</section>`;
  }).join("\n");
}

function gallery(productName) {
  const three = Array.from({ length: 3 }, (_, index) => imageTag(`crop-${index}`, `${productName} 디테일 이미지`)).join("\n");
  const two = Array.from({ length: 2 }, (_, index) => imageTag(`crop-${index + 3}`, `${productName} 디테일 이미지`)).join("\n");
  return { three, two };
}

const allowedBlockTypes = new Set([
  "hero", "statement", "feature_grid", "detail_split", "wide_image", "gallery",
  "usage_scene", "scale_reference", "palette", "recommendation", "info_table",
  "notice", "closing",
]);
const allowedVariants = new Set([
  "paper", "light", "sand", "dark", "image-left", "image-right", "full-bleed", "compact",
]);

function variantClass(variant) {
  return allowedVariants.has(variant) ? ` block--${variant}` : "";
}

function fallbackPlan() {
  return [
    { section_id: "hero", block_type: "hero", eyebrow: "IMAGE-BASED PRODUCT STORY", title: draft.product_name, body: draft.summary, variant: "paper", photo_id: "hero" },
    { section_id: "core-value", block_type: "statement", eyebrow: "CORE VALUE", title: draft.hero_headline, body: draft.hero_description, variant: "dark" },
    { section_id: "features", block_type: "feature_grid", eyebrow: "VISIBLE DETAILS", title: "가까이 볼수록 선명해지는 디테일", body: "원본 이미지에서 확인되는 요소를 중심으로 구성한 상세 컷입니다.", variant: "paper" },
    ...draft.features.map((feature, index) => ({ section_id: `detail-0${index + 1}`, block_type: "detail_split", eyebrow: `DETAIL 0${index + 1}`, title: feature.title, body: feature.description, variant: index % 2 ? "image-right" : "image-left", photo_id: "detail" })),
    { section_id: "wide-view", block_type: "wide_image", eyebrow: "WIDE VIEW", title: "전체 인상을 한눈에", body: "제품의 형태를 원본 그대로 살펴봅니다.", variant: "light", photo_id: "hero" },
    { section_id: "detail-cuts", block_type: "gallery", eyebrow: "DETAIL CUTS", title: "색과 문양의 작은 차이", body: "디테일을 가까이에서 비교해 보세요.", variant: "paper" },
    { section_id: "usage-scene", block_type: "usage_scene", eyebrow: "EVERYDAY SCENE", title: "일상에 더하는 하나의 포인트", body: draft.usage_scene, variant: "sand", photo_id: "lifestyle" },
    { section_id: "scale-reference", block_type: "scale_reference", eyebrow: "OBJECT ARRANGEMENT", title: "공간 속에서 살펴보는 균형", body: "실제 크기와 용도는 별도 확인이 필요합니다.", variant: "light", photo_id: "hero" },
    { section_id: "notice", block_type: "notice", eyebrow: "IMAGE-BASED NOTE", title: "이미지에서 확인되는 정보만 담았습니다.", body: "최종 승인 전 문구를 검토할 수 있습니다.", variant: "dark" },
    { section_id: "closing", block_type: "closing", eyebrow: "OBJECT STORY", title: "테이블 위에 남는 인상", body: "이미지에서 확인되는 특징을 중심으로 정리했습니다.", variant: "paper" },
  ];
}

function renderItems(items, fallback) {
  const values = items?.length ? items : fallback;
  return values.map((item, index) => `<article class="feature-card"><span class="feature-card__accent feature-card__accent--${["jade", "red", "yellow"][index % 3]}"></span><h3>${escapeHtml(item.label || item.title || "제품 특징")}</h3><p>${escapeHtml(item.value || item.description || "")}</p></article>`).join("\n");
}

function renderPlanBlock(block, index, productName) {
  if (!allowedBlockTypes.has(block.block_type)) return "";
  const sectionId = escapeHtml(block.section_id || `section-${index + 1}`);
  const eyebrow = escapeHtml(block.eyebrow || block.block_type.replaceAll("_", " ").toUpperCase());
  const title = escapeHtml(block.title || productName);
  const body = escapeHtml(block.body || "");
  const variant = variantClass(block.variant);
  if (block.block_type === "hero") return `<section class="hero${variant}" data-section="${sectionId}" data-section-title="상품 소개"><div class="hero__copy"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1><p>${body}</p></div><div class="hero__media">${imageTag("product-image--hero", `${productName} 대표 이미지`)}</div></section>`;
  if (block.block_type === "statement") return `<section class="intro-band${variant}" data-section="${sectionId}" data-section-title="핵심 메시지"><span class="section-number">${String(index + 1).padStart(2, "0")}</span><div><span class="eyebrow">${eyebrow}</span><h2>${title}</h2></div><p>${body}</p></section>`;
  if (block.block_type === "feature_grid") return `<section class="feature-grid${variant}" data-section="${sectionId}" data-section-title="제품 특징"><div class="section-heading section-heading--compact"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p></div>${renderItems(block.items, draft.features)}</section>`;
  if (block.block_type === "detail_split") return `<section class="split-section ${block.variant === "image-right" ? "split-section--reverse" : ""}${variant}" data-section="${sectionId}" data-section-title="${title}"><div class="split-section__media">${imageTag("product-image--split", `${productName} ${title} 상세 이미지`)}</div><div class="split-section__copy"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p></div></section>`;
  if (block.block_type === "wide_image") return `<section class="wide-section${variant}" data-section="${sectionId}" data-section-title="와이드 뷰"><div class="section-heading section-heading--compact"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p></div><div class="wide-section__media">${imageTag("product-image--wide", `${productName} 전체 이미지`)}</div></section>`;
  if (block.block_type === "gallery") { const galleries = gallery(productName); return `<section class="gallery-section${variant}" data-section="${sectionId}" data-section-title="상세 갤러리"><div class="section-heading section-heading--compact"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p></div><div class="detail-grid detail-grid--three">${galleries.three}</div><div class="detail-grid detail-grid--two">${galleries.two}</div></section>`; }
  if (block.block_type === "usage_scene") return `<section class="usage-section${variant}" data-section="${sectionId}" data-section-title="활용 장면"><div class="usage-section__copy"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p></div><div class="usage-section__media">${imageTag("product-image--usage", `${productName} 활용 이미지`)}</div></section>`;
  if (block.block_type === "scale_reference") return `<section class="scale-section${variant}" data-section="${sectionId}" data-section-title="크기 참고"><div class="section-heading section-heading--compact"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p></div><div class="scale-section__media">${imageTag("product-image--scale", `${productName} 크기 참고 이미지`)}</div></section>`;
  if (block.block_type === "palette") return `<section class="palette-section${variant}" data-section="${sectionId}" data-section-title="색과 표면"><div class="palette-section__copy"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p><ul>${(block.items || []).map((item, itemIndex) => `<li><span class="palette-swatch palette-swatch--${itemIndex % 4}"></span><strong>${escapeHtml(item.label || "표면")}</strong><span>${escapeHtml(item.value || item.description || "")}</span></li>`).join("")}</ul></div><div class="palette-section__media">${imageTag("product-image--palette", `${productName} 색상과 표면`)}</div></section>`;
  if (block.block_type === "recommendation") return `<section class="recommendation-section${variant}" data-section="${sectionId}" data-section-title="추천 연출"><div class="section-heading section-heading--compact"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p></div><div class="recommendation-grid">${(block.items || []).slice(0, 3).map((item, itemIndex) => `<article><span>${String(itemIndex + 1).padStart(2, "0")}</span><h3>${escapeHtml(item.label || "추천 장면")}</h3><p>${escapeHtml(item.value || item.description || "")}</p></article>`).join("")}</div></section>`;
  if (block.block_type === "info_table") return `<section class="info-section${variant}" data-section="${sectionId}" data-section-title="기본 정보"><div class="section-heading section-heading--compact"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p></div><table><tbody>${(block.items || []).map((item) => `<tr><th>${escapeHtml(item.label || "항목")}</th><td>${escapeHtml(item.value || item.description || "")}</td></tr>`).join("")}</tbody></table></section>`;
  if (block.block_type === "notice") return `<section class="notice-section${variant}" data-section="${sectionId}" data-section-title="안내"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p><ul><li>정확한 소재와 규격은 별도 확인이 필요합니다.</li><li>이미지에서 확인되지 않는 정보는 사실처럼 단정하지 않습니다.</li><li>최종 승인 전 문구를 검토할 수 있습니다.</li></ul></section>`;
  if (block.block_type === "closing") return `<section class="closing-section${variant}" data-section="${sectionId}" data-section-title="마무리"><span class="eyebrow">${eyebrow}</span><h2>${title}</h2><p>${body}</p></section>`;
  return "";
}

function renderPagePlan(productName) {
  const plan = Array.isArray(draft.page_plan) && draft.page_plan.length ? draft.page_plan : fallbackPlan();
  return plan.map((block, index) => renderPlanBlock(block, index, productName)).join("\n");
}

function buildPreviewHtml() {
  const productName = draft.product_name || "작품 이름";
  const hasAdaptivePlan = Array.isArray(draft.page_plan) && draft.page_plan.length > 0;
  const layoutClass = `detail-page--${hasAdaptivePlan ? "adaptive" : (layoutLabels[draft.layout_id] ? draft.layout_id : "editorial-split")}`;
  return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=774, initial-scale=1"><style>${pageCss}</style></head>
<body><main class="detail-page ${layoutClass}">
  <header class="topbar"><span class="topbar__label">PRODUCT DETAIL</span><span class="topbar__type">JSON DRAFT</span></header>
  ${renderPagePlan(productName)}
  <footer class="footer"><span>PRODUCT DETAIL</span><span>JSON DATA · LOCAL HTML PREVIEW · NOT PNG</span></footer>
</main></body></html>`;
}

function renderFeatureFields() {
  featureFields.replaceChildren();
  draft.features.forEach((feature, index) => {
    const wrapper = document.createElement("div");
    wrapper.className = "feature-field";
    wrapper.innerHTML = `<label for="feature-title-${index}"><span class="feature-field__number">0${index + 1}</span>특징 제목</label><input id="feature-title-${index}" type="text" maxlength="80" value="${escapeHtml(feature.title)}"><textarea id="feature-description-${index}" rows="2" maxlength="300" aria-label="특징 ${index + 1} 설명">${escapeHtml(feature.description)}</textarea>`;
    featureFields.append(wrapper);
    wrapper.querySelector("input").addEventListener("input", (event) => {
      draft.features[index].title = event.target.value;
      scheduleRender();
    });
    wrapper.querySelector("textarea").addEventListener("input", (event) => {
      draft.features[index].description = event.target.value;
      scheduleRender();
    });
  });
}

function fillEditor() {
  for (const field of editor.querySelectorAll("input:not([id^=feature-]), textarea")) {
    if (field.name in draft) field.value = draft[field.name];
  }
  renderFeatureFields();
}

function readEditor() {
  for (const field of editor.querySelectorAll("input:not([id^=feature-]), textarea")) {
    if (field.name in draft) draft[field.name] = field.value;
  }
}

function setDirtyStatus() {
  draftState.classList.remove("is-approved");
  draftState.querySelector(".draft-state__dot").nextSibling.textContent = " JSON 초안";
  saveStatus.textContent = "편집 중… JSON 데이터로 미리보기를 갱신하고 있습니다.";
}

function renderPreview() {
  readEditor();
  frame.srcdoc = buildPreviewHtml();
  frame.classList.add("is-ready");
  loading.hidden = true;
  saveStatus.textContent = "자동 저장됨 · JSON 데이터로 미리보기 갱신됨";
}

function scheduleRender() {
  setDirtyStatus();
  window.clearTimeout(renderTimer);
  renderTimer = window.setTimeout(renderPreview, 180);
}

function loadImageData() {
  return fetch(imageUrl)
    .then((response) => {
      if (!response.ok) throw new Error("sample image unavailable");
      return response.blob();
    })
    .then((blob) => new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    }));
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function loadDraftFromJob() {
  if (!jobId) return false;
  let statusUrl = `/api/v1/ai/detail-page-jobs/${encodeURIComponent(jobId)}`;
  try {
    const stored = sessionStorage.getItem(`ai-detail-job:${jobId}`);
    if (stored) statusUrl = JSON.parse(stored).statusUrl || statusUrl;
  } catch {
    // Use the deterministic status URL fallback.
  }
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const response = await fetch(statusUrl);
    if (!response.ok) throw new Error("초안 상태를 불러오지 못했습니다.");
    const payload = await response.json();
    if (payload.status === "FAILED") {
      throw new Error(payload.error?.message || "초안 생성에 실패했습니다.");
    }
    if (payload.draft) {
      Object.assign(draft, payload.draft.draft);
      draft.page_plan = payload.draft.draft.page_plan || [];
      draftVersion = payload.draft.version || 1;
      const preview = payload.draft.preview || {};
      if (preview.image_base64) {
        imageDataUri = `data:${preview.mime_type || "image/jpeg"};base64,${preview.image_base64}`;
      } else if (preview.image_url) {
        imageDataUri = preview.image_url;
      }
      document.querySelector("#layout-recommendation").textContent =
        `AI 추천 · ${layoutLabels[draft.layout_id] || "제품 맞춤형"}`;
      fillEditor();
      return true;
    }
    await wait(500);
  }
  throw new Error("초안 생성 시간이 초과되었습니다.");
}

editor.addEventListener("input", scheduleRender);
saveButton.addEventListener("click", async () => {
  readEditor();
  if (!jobId) {
    saveStatus.textContent = "초안 v03 저장됨 · PNG는 아직 생성하지 않았습니다.";
    return;
  }
  saveButton.disabled = true;
  saveStatus.textContent = "초안을 저장하고 있습니다…";
  try {
    const response = await fetch(`${draftSaveApiUrl}/${encodeURIComponent(jobId)}/draft`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft_id: jobId, version: draftVersion, draft }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "초안 저장에 실패했습니다.");
    if (payload.draft) Object.assign(draft, payload.draft);
    draftVersion = payload.version || draftVersion + 1;
    saveStatus.textContent = "초안 저장 완료 · PNG는 아직 생성하지 않았습니다.";
  } catch (error) {
    saveStatus.textContent = `초안 저장 실패 · ${error.message}`;
  } finally {
    saveButton.disabled = false;
  }
});
approveButton.addEventListener("click", () => {
  approveDraft();
});

async function approveDraft() {
  readEditor();
  draftState.classList.add("is-approved");
  draftState.querySelector(".draft-state__dot").nextSibling.textContent = " PNG 생성 중";
  approveButton.disabled = true;
  approveButton.textContent = "PNG 생성 중...";
  approvalResult.hidden = true;
  saveStatus.textContent = "승인 완료 · 현재 문구로 최종 PNG를 생성하고 있습니다.";

  try {
    const sourceResponse = await fetch(imageUrl);
    if (!sourceResponse.ok) throw new Error("원본 제품 이미지를 불러오지 못했습니다.");
    const sourceBlob = await sourceResponse.blob();
    const body = new FormData();
    body.append("product_image", sourceBlob, "sample-product.jpg");
    body.append("draft", JSON.stringify(draft));
    body.append("options", JSON.stringify({
      aspect_ratio: "1:4",
      image_size: "2K",
      output_mime_type: "image/png",
    }));
    const response = await fetch(approvalApiUrl, { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "PNG 생성 요청에 실패했습니다.");
    const detailPage = payload.result?.detail_page;
    const href = detailPage?.image_base64
      ? `data:${detailPage.mime_type || "image/png"};base64,${detailPage.image_base64}`
      : detailPage?.image_url;
    if (!href) throw new Error("생성된 PNG를 응답에서 찾지 못했습니다.");

    pngDownload.href = href;
    pngDownload.download = `${draft.product_name || "detail-page"}.png`;
    approvalResult.hidden = false;
    draftState.querySelector(".draft-state__dot").nextSibling.textContent = payload.backend_delivery_pending
      ? " PNG 생성 완료 · BE 저장 대기"
      : " PNG 생성 완료";
    approveButton.textContent = "PNG 생성 완료";
    saveStatus.textContent = payload.backend_delivery_pending
      ? "PNG는 준비됐고 BE 저장은 재시도 대기 중입니다."
      : "PNG 생성 완료 · FE 응답 및 BE 저장까지 처리했습니다.";
  } catch (error) {
    draftState.classList.remove("is-approved");
    draftState.querySelector(".draft-state__dot").nextSibling.textContent = " JSON 초안";
    approveButton.disabled = false;
    approveButton.textContent = "승인하고 PNG 생성";
    saveStatus.textContent = `PNG 생성 실패 · ${error.message}`;
  }
}

fillEditor();
const cssPromise = fetch("./detail_page.css").then((response) => response.text());
const assetPromise = jobId ? Promise.resolve("") : loadImageData();
Promise.all([cssPromise, assetPromise])
  .then(async ([css, image]) => {
    pageCss = css;
    imageDataUri = image;
    await loadDraftFromJob();
    renderPreview();
  })
  .catch((error) => {
  loading.textContent = "미리보기를 준비하지 못했습니다. 프로젝트 루트에서 페이지를 실행해 주세요.";
  saveStatus.textContent = error.message || "샘플 자산을 불러오지 못했습니다.";
});
