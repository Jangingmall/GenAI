# Round 10 · 구현 체크포인트 — '참고용' 라벨 계약 수정과 60건 평가 1차

| 항목 | 값 |
| --- | --- |
| 차수 | 10 |
| 파일럿 디렉터리 | `generated/evaluation/full60-20260910-204433` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-164008` (9차) |
| 이미지 재생성 | 예 (케이스별 Flux 이미지 생성 60건, 3시간 52분) |
| 기록 시각 | 2026-09-11 |

## 변경 파일

### 1) React 문서 빌더의 생성 사진 라벨 전달

- **파일**: `src/detail_page_ai/react_document_builder.py`
- **위치**: `_image_figures()`와 `_media_group()` 주변, `build_react_document_from_draft()`
- **내용**: `build_react_document_from_draft(draft, *, generated_photos=None)`에 keyword-only 선택 인자를 추가했다. `product_generated=True`인 `GeneratedPhotoMetadataDto`만 `photo_id → label` 맵으로 만들었고, 해당 사진의 `figure` 아래에 `figcaption`과 `...-reference-label`/`...-reference-label-text` 노드를 추가했다. 원본 사진의 label은 맵에 넣지 않았다.

### 2) 파이프라인의 문서 생성 시점과 호출 인자 이동

- **파일**: `src/detail_page_ai/pipeline.py`
- **위치**: `DetailPagePipeline.run()`의 기존 196행 부근 호출을 사진 메타데이터 생성 뒤 298행 부근으로 이동했고, 복구 경로에서 `record.request.detail_page.photos`를 `generated_photos`로 전달했다.
- **내용**: React 문서가 사진 메타데이터가 만들어진 뒤 생성되도록 순서를 바꿨다. `pipeline.py:539`의 완료 draft 편집 재빌드 경로는 생성 사진이 존재할 수 없는 경로로 확인되어 그대로 두었다.

### 3) HTML의 생성 사진 figcaption

- **파일**: `src/detail_page_ai/html_renderer.py`
- **위치**: `_image_tag()`, `_block_image()`, `_render_page_block()`, `build_detail_page_html()`
- **내용**: 생성 사진의 label을 HTML `figure` 안 `figcaption.generated-photo-label`로 전달했다. 실제 케이스 확인에서 생성 컷 5장에는 figcaption이 생겼고, 원본 컷 3장에는 라벨이 생기지 않았다.

### 4) 기존 시맨틱 토큰을 사용하는 표시 스타일

- **파일**: `web/detail_page.css`
- **위치**: `.generated-photo-reference`, `.generated-photo-label`
- **내용**: 라벨 표시용 CSS를 추가했고 기존 시맨틱 토큰 `--fill-neutral-impact`, `--font-white`를 사용했다. FE 컴포넌트 구현이나 프런트 통합은 수행하지 않았다.

### 5) 60건 평가 러너와 실행 메타데이터

- **파일**: `scripts/run_eval_pilot.py`
- **위치**: `select_pilot_cases()`, `print_dry_run()`, `_write_run_index()`, `run_pilot()`, `main()`
- **내용**: `--all`, `--limit`, `--resume`를 추가하고, 케이스 완료·건너뛰기마다 `run_index.json`을 임시 파일 후 `replace`로 원자 갱신하도록 확장했다. 상위 메타데이터에 `configured_image_model`, 실제 실행 모드의 `image_model`, `image_provider`, `image_generated_cases`를 기록했다.

### 6) 라벨 품질 게이트와 테스트

- **추가 파일**: `scripts/check_reference_label.py`, `tests/test_eval_runner_cli.py`, `tests/test_reference_label_gate.py`
- **수정 파일**: `tests/test_html_renderer.py`, `tests/test_react_document.py`
- **내용**: React 문서와 HTML에서 생성 사진의 `참고용` 라벨이 존재하고 원본 사진에는 오표기되지 않는지 검사하는 게이트와 러너 CLI·라벨 계약 테스트를 추가했다.

## 코드상 체크포인트

- 커밋 기준은 `c1d413f`였다.
- `source_photos.py:793`, `:834`가 만든 생성 사진 label이 `react_document_builder.py:224-232`까지 전달되는 경로가 추가됐다.
- 기존 `build_react_document_from_draft(draft)` 호출은 keyword 인자를 생략해도 동작하는 하위 호환 경로로 남았다.
- 60건 실행의 `run_index.json`에는 `image_generated_cases: 60`, `image_model: mlx-community/flux2-klein-9b-4bit`, `configured_image_model: mlx-community/flux2-klein-9b-4bit`, `image_provider: mlx`가 기록됐다.

## 테스트 통과 수

- 변경 전 기준 312 passed에서 10차 변경 후 328 passed로 늘었다.
- 추가된 러너 CLI·라벨 계약 테스트와 기존 HTML/React 테스트가 포함된 상태로 328 passed가 기록됐다.

## 새 산출물

- `scripts/check_reference_label.py`
- `tests/test_eval_runner_cli.py`
- `tests/test_reference_label_gate.py`
- `run_index.json`의 증분 기록 및 이미지 실행 메타데이터 필드

