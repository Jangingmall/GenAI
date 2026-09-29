# Round 10 · BE/FE 인터페이스 영향 — 생성 사진 '참고용' 라벨 계약

| 항목 | 값 |
| --- | --- |
| 차수 | 10 |
| 파일럿 디렉터리 | `generated/evaluation/full60-20260910-204433` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-164008` (9차) |
| 이미지 재생성 | 예 (케이스별 Flux 이미지 생성 60건, 3시간 52분) |
| 기록 시각 | 2026-09-11 |

## BE 계약 변화

### 1) 생성 사진 선택 인자

`src/detail_page_ai/react_document_builder.py`의 `build_react_document_from_draft()`가 다음 keyword-only 선택 인자를 받도록 바뀌었다.

```python
build_react_document_from_draft(
    draft,
    *,
    generated_photos: list[GeneratedPhotoMetadataDto] | None = None,
)
```

빌더는 `generated_photos` 중 `product_generated=True`인 사진만 label 전달 대상으로 선택했다. 기존 호출자가 인자를 생략하면 기존과 같은 기본 경로를 사용했다.

### 2) `react_document` figcaption 노드

생성 사진의 `figure` children에 `figcaption` element node가 추가됐다. 노드 ID는 `...-reference-label`, 텍스트 노드는 `...-reference-label-text` suffix를 사용했고 label 값은 `AI 생성 활용 장면(참고용)` 또는 `AI 생성 디테일(참고용)`이었다. 원본 사진의 metadata label은 이 노드에 들어가지 않았다.

### 3) 파이프라인 전달 순서

`pipeline.py`는 사진 metadata를 만든 뒤 `generated_photos=photo_metadata`를 넘겨 React 문서를 만들었다. 관리자 확인 결과 실제 케이스에는 생성 컷 5개에 figcaption이 생겼고 원본 컷 3개에는 label이 없었다.

## FE가 소비하는 계약

- `page_plan`의 블록 어휘, `PageBlockVariant`, `layout_id`와 기존 DTO field 구조는 10차 라벨 수정의 대상이 아니었다.
- FE가 받는 `react_document.json`은 기존 image node를 유지하면서 생성 사진에만 optional `figcaption` child가 추가된 형태였다.
- `web/detail_page.css`에는 `.generated-photo-reference`와 `.generated-photo-label` 표시 규칙이 추가됐고 기존 시맨틱 토큰을 사용했다.
- FE 컴포넌트 구현, 프런트 통합, 소비 화면 변경은 이 차수 범위가 아니었고 수행하지 않았다.

## 하위 호환성 여부

기존 `build_react_document_from_draft(draft)` 호출은 선택 인자를 생략할 수 있어 하위 호환이 유지됐다. 기존 원본 사진 figure에는 label child가 추가되지 않았고, 생성 사진 figure에만 figcaption child가 추가됐다. 따라서 계약 변경은 생성 사진 metadata가 전달되는 경우의 optional child 확장이었으며, FE 구현 변경은 수행하지 않았다.

## 계약 게이트 결과

`scripts/check_reference_label.py`에서 같은 `analysis-cma-102980`은 수정 전 React 문서 label 누락으로 FAIL(종료 코드 1), 수정 후 PASS(종료 코드 0)였다. 60건 전체 실행에서는 라벨 계약이 60/60 PASS로 기록됐다.

