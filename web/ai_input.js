const MAX_IMAGES = 12;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const MAX_TOTAL_BYTES = 120 * 1024 * 1024;
const ACCEPTED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

const form = document.querySelector("#detail-page-form");
const dropZone = document.querySelector("#drop-zone");
const fileInput = document.querySelector("#product-image-input");
const chooseImages = document.querySelector("#choose-images");
const imageList = document.querySelector("#image-list");
const imageCount = document.querySelector("#image-count");
const imageError = document.querySelector("#image-error");
const submitButton = document.querySelector("#create-button");
const submitStatus = document.querySelector("#submit-status");
const files = [];

function setImageError(message = "") {
  imageError.textContent = message;
}

function setSubmitStatus(message = "", isError = false) {
  submitStatus.textContent = message;
  submitStatus.classList.toggle("is-error", isError);
}

function makeId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
}

function isDuplicate(file) {
  return files.some((entry) => (
    entry.file.name === file.name &&
    entry.file.size === file.size &&
    entry.file.lastModified === file.lastModified
  ));
}

function addFiles(selectedFiles) {
  setImageError();
  const rejected = [];
  for (const file of Array.from(selectedFiles)) {
    if (!ACCEPTED_TYPES.has(file.type)) {
      rejected.push(`${file.name}: JPG, PNG, WEBP만 올릴 수 있습니다.`);
      continue;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      rejected.push(`${file.name}: 한 장에 10MB까지 올릴 수 있습니다.`);
      continue;
    }
    if (isDuplicate(file)) continue;
    if (files.reduce((total, entry) => total + entry.file.size, 0) + file.size > MAX_TOTAL_BYTES) {
      rejected.push("전체 사진 용량은 120MB까지 올릴 수 있습니다.");
      break;
    }
    if (files.length >= MAX_IMAGES) {
      rejected.push(`사진은 최대 ${MAX_IMAGES}장까지 올릴 수 있습니다.`);
      break;
    }
    files.push({ id: makeId(), file });
  }
  renderFiles();
  if (rejected.length) setImageError(rejected[0]);
}

function renderFiles() {
  imageList.replaceChildren();
  for (const [index, entry] of files.entries()) {
    const item = document.createElement("div");
    item.className = "image-item";
    item.dataset.fileId = entry.id;

    const image = document.createElement("img");
    image.alt = index === 0 ? "대표 원본 이미지" : `추가 원본 이미지 ${index}`;
    image.src = URL.createObjectURL(entry.file);
    image.addEventListener("load", () => URL.revokeObjectURL(image.src), { once: true });

    const badge = document.createElement("span");
    badge.className = "image-item__badge";
    badge.textContent = index === 0 ? "대표" : `${index + 1}`;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "image-item__remove";
    remove.setAttribute("aria-label", `${index + 1}번째 사진 삭제`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      const entryIndex = files.findIndex((candidate) => candidate.id === entry.id);
      if (entryIndex >= 0) files.splice(entryIndex, 1);
      renderFiles();
    });

    item.append(image, badge, remove);
    imageList.append(item);
  }
  imageCount.textContent = files.length
    ? `${files.length}장 선택됨 · 첫 번째 사진이 대표 사진입니다.`
    : "아직 사진이 없습니다.";
}

function clearFieldError(field) {
  field.classList.remove("is-invalid");
  const error = document.querySelector(`[data-error-for="${field.id}"]`);
  if (error) error.textContent = "";
}

function validateForm() {
  let valid = true;
  setImageError();
  if (!files.length) {
    setImageError("대표 사진을 한 장 이상 올려 주세요.");
    valid = false;
  }
  for (const field of [document.querySelector("#product-name"), document.querySelector("#making-method")]) {
    const error = document.querySelector(`[data-error-for="${field.id}"]`);
    if (!field.value.trim()) {
      field.classList.add("is-invalid");
      error.textContent = "필수 입력 항목입니다.";
      valid = false;
    } else {
      clearFieldError(field);
    }
  }
  return valid;
}

function buildRequestBody() {
  const body = new FormData();
  body.append("product_image", files[0].file, files[0].file.name);
  for (const entry of files.slice(1)) {
    body.append("product_images", entry.file, entry.file.name);
  }
  body.append("product_name", document.querySelector("#product-name").value.trim());
  body.append("making_method", document.querySelector("#making-method").value.trim());
  body.append("care_guide", document.querySelector("#care-guide").value.trim());
  body.append("template_id", "default-long-detail-page");
  body.append("locale", "ko-KR");
  body.append("options", JSON.stringify({
    aspect_ratio: "1:4",
    image_size: "2K",
    output_mime_type: "image/png",
  }));
  return body;
}

chooseImages.addEventListener("click", (event) => {
  event.stopPropagation();
  fileInput.click();
});
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
fileInput.addEventListener("change", () => {
  addFiles(fileInput.files);
  fileInput.value = "";
});
for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
  });
}
dropZone.addEventListener("drop", (event) => addFiles(event.dataTransfer.files));

for (const field of document.querySelectorAll("input, textarea")) {
  field.addEventListener("input", () => clearFieldError(field));
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setSubmitStatus();
  if (!validateForm()) return;

  submitButton.disabled = true;
  submitButton.textContent = "초안 접수 중...";
  try {
    const response = await fetch(form.dataset.apiUrl, {
      method: "POST",
      body: buildRequestBody(),
    });
    if (!response.ok) throw new Error("request failed");
    const accepted = await response.json();
    const previewUrl = form.dataset.previewUrl || "/web/ai_draft_preview.html";
    const previewHref = `${previewUrl}?job_id=${encodeURIComponent(accepted.job_id)}`;
    try {
      sessionStorage.setItem(
        `ai-detail-job:${accepted.job_id}`,
        JSON.stringify({ statusUrl: accepted.status_url, accepted }),
      );
    } catch {
      // The status URL is also carried in the query string fallback below.
    }
    const link = document.createElement("a");
    link.href = previewHref;
    link.textContent = "초안 확인·수정하기";
    link.target = "_blank";
    link.rel = "noreferrer";
    submitStatus.replaceChildren(document.createTextNode("초안 생성을 접수했습니다. "), link);
  } catch {
    setSubmitStatus("접수에 실패했습니다. 잠시 후 다시 시도해 주세요.", true);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "초안 만들기";
  }
});

renderFiles();
