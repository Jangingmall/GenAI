# Round 12 · 구현 체크포인트 — hero 원본 고정·rembg 누끼 채택·참고용 표시 제거·합성 반려

| 항목 | 값 |
| --- | --- |
| 차수 | 12 |
| 파일럿 디렉터리 | `generated/attached/najeon-hero-030813`, `generated/attached/petal-rembg-000846`, `generated/cutout-compare/`, `generated/composite-check/{nacre,petals}` |
| 직전 차수 기준 | `generated/evaluation/full60-20260910-204433` (11차 되돌림 후 기준) |
| 이미지 재생성 | 예 (나전칠기·꽃잎 적용 결과와 합성 시도; 활용 장면 Flux 생성 유지) |
| 기록 시각 | 2026-09-14 |

## 1. 차수 종료 상태

12차의 커밋 범위는 `cf8a4b1..cfd60bb`였다. `492e776`의 hero 원본 고정과 `cfd60bb`의 rembg 누끼·생성 사진 라벨 제거·워커 등록부 수정은 채택되었다. 누끼와 생성 배경을 합성하는 변경은 커밋하지 않았고, 검증 뒤 되돌렸다.

| 작업 묶음 | 판정 | 차수 종료 상태 |
| --- | --- | --- |
| hero 원본 고정 (`492e776`) | 채택 | `hero`가 `source_original`·`VERIFIED`·`product_generated=False`로 전달됨 |
| rembg 누끼 및 의존성 고정 (`cfd60bb`) | 채택 | rembg `2.0.69`, Pillow `11.3.0` 고정; `birefnet-general` 사용 |
| 생성 사진의 '참고용' 표시 제거 (`cfd60bb`) | 채택 | `react_document`의 `...-reference-label` 노드와 렌더 오버레이 제거 |
| 누끼+생성배경 합성 시도 | 반려 | 미커밋 3파일을 `cfd60bb` 상태로 되돌리고 prompt v4 복귀 |

최종 테스트 통과 수는 **348 passed**였다. 추이는 `349 → 351 → 348 → (합성 시도 350) → 348`이었다.

## 2. 채택된 구현 변경

### 1) hero 원본 고정

- **파일·위치**: `src/detail_page_ai/models.py:22-30`의 `AssetMode`·`FidelityStatus`, `src/detail_page_ai/source_photos.py:1017-1080`의 `_source_original()`·`_source_hero()`, `src/detail_page_ai/source_photos.py:505-574`의 `ProductFidelityValidator.validate()`.
- 기존 `asset_mode="source"`·`fidelity_status="FALLBACK"`가 누끼 실패를 뜻하는 경로와 hero 정책을 분리하기 위해 `asset_mode="source_original"`을 추가했다.
- hero는 원본 바이트를 그대로 사용하고 `fidelity_status="VERIFIED"`, label `원본 보존 대표 이미지`, `product_generated=False`를 기록한다.
- BE 전달 필터는 `source_original`이면서 `photo_id=="hero"`이고 `fidelity_status=="VERIFIED"`인 경우만 통과시킨다.
- `generated/attached/hero-check`에서 원본과 픽셀 차이의 bbox가 `None`으로 확인되었고, 적용 결과 `generated/attached/najeon-hero-030813`은 1060×1060 jpg 원본이었다.

### 2) rembg 누끼 채택

- **파일·위치**: `src/detail_page_ai/source_photos.py:399-502`의 `RembgCutoutExtractor`, `src/detail_page_ai/source_photos.py:662-683`의 `SourcePreservingProductPhotoGenerator` 초기화 경로, `pyproject.toml:5-13`, `uv.lock`.
- `birefnet-general`을 1024px 분할 모델로 사용하고, 세션을 지연 생성한 뒤 1회 생성 세션을 재사용하도록 했다.
- `session_factory`와 `segmenter`를 주입할 수 있게 하여 테스트에서 실모델과 네트워크를 사용하지 않았다.
- 알파 8 미만 값은 전경에서 제외하고, 전경 비율이 0.5% 미만 또는 99.5% 초과이면 `None`을 반환해 기존 폴백 경로로 넘긴다.
- `SolidBackgroundCutoutExtractor`는 학습 증강·비교 기준선 용도로 남겼다.
- 최종 잠금 버전은 rembg `2.0.69`, Pillow `11.3.0`, NumPy `2.5.3`, onnxruntime `1.29.0`이다.

### 3) '참고용' 표시 제거

- **파일·위치**: `src/detail_page_ai/react_document_builder.py`의 `_image_figures()`·`_media_group()`·블록 생성 경로, `src/detail_page_ai/html_renderer.py`의 `_image_tag()`·`_block_image()`·`_render_page_block()`·`build_detail_page_html()`.
- `react_document_builder.py`에서 생성 사진 label 전달에만 사용되던 `generated_photos` 인자와 `...-reference-label` figcaption 노드를 제거했다. `pipeline.py`의 관련 호출부 2곳도 함께 정리했다.
- `html_renderer.py`의 figure/figcaption 오버레이와 `web/detail_page.css`의 표시 규칙을 제거했다.
- `scripts/check_reference_label.py`와 `tests/test_reference_label_gate.py`를 삭제했다.
- 생성 사진 label 문자열은 `AI 생성 활용 장면(참고용)`에서 `AI 생성 활용 장면`, `AI 생성 디테일(참고용)`에서 `AI 생성 디테일`로 바꾸었다. 생성 여부를 구분하는 `product_generated` 플래그는 유지했다.
- 계약 문서와 AWS 운영 문서도 현재 동작에 맞게 갱신했다.

### 4) 워커 등록부 수정

- **파일**: `scripts/orchestration/workers.tsv`.
- 재시작 뒤 실제 배치인 codex `tts003`, agy `tts004`, agy2 `tts005`, codex3 `tts006`, codex2 `tts007`을 가리키도록 등록부를 수정했다.

## 3. 반려된 구현 시도

### 누끼+생성배경 lifestyle 기본 경로

- **시도한 파일**: `src/detail_page_ai/source_photos.py`, `src/detail_page_ai/prompts.py`, `tests/test_source_photos.py`.
- lifestyle 기본 경로를 생성 배경과 누끼의 `source_composite`로 바꾸고, 실패 시 Flux 편집과 단색 합성을 순서대로 사용하려 했다.
- 배경 prompt 버전을 `background-v4-jewelry-coverage`에서 `background-v5-front-facing-composite`로 바꾸었다.
- 합성 확인 산출물은 `generated/composite-check/nacre`와 `generated/composite-check/petals`에 보존했다.
- 오케스트레이터가 제시한 소견을 관리자가 보고 선택지 2를 결정한 뒤 위 3파일을 `cfd60bb`로 되돌렸고, 최종 활용 장면 경로와 prompt v4를 유지했다.

## 4. 차수 산출물

- `generated/attached/najeon-023918`: 데모 스크립트 오용 결과로 무효.
- `generated/attached/najeon-real-024039`: 실제 파이프라인의 나전칠기 첫 결과.
- `generated/attached/najeon-hero-030813`: hero 원본 적용 결과.
- `generated/attached/hero-check`: hero 원본 검증 결과.
- `generated/attached/petal-220947`: rembg 적용 전 꽃잎 결과.
- `generated/attached/petal-rembg-000846`: 현재 채택 파이프라인의 꽃잎 결과.
- `generated/cutout-compare/`: 기존 추출기와 rembg의 62케이스 비교 결과.
- `generated/composite-check/{nacre,petals}`: 반려된 합성 시도 결과.

