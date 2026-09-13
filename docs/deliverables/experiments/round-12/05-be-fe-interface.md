# Round 12 · BE/FE 인터페이스 영향 — `source_original` 도입과 생성 라벨 제거

| 항목 | 값 |
| --- | --- |
| 차수 | 12 |
| 파일럿 디렉터리 | `generated/attached/najeon-hero-030813`, `generated/attached/petal-rembg-000846`, `generated/cutout-compare/`, `generated/composite-check/{nacre,petals}` |
| 직전 차수 기준 | `generated/evaluation/full60-20260910-204433` (11차 되돌림 후 기준) |
| 이미지 재생성 | 예 (나전칠기·꽃잎 적용 결과와 합성 시도; 활용 장면 Flux 생성 유지) |
| 기록 시각 | 2026-09-14 |

## 1. BE 에셋 계약 변화

### `asset_mode=source_original` 추가

hero 원본을 누끼 실패 폴백과 구별하기 위해 `asset_mode`에 `source_original`을 추가했다.

| 필드 | hero 계약 |
| --- | --- |
| `photo_id` | `hero` |
| `asset_mode` | `source_original` |
| `fidelity_status` | `VERIFIED` |
| label | `원본 보존 대표 이미지` |
| `product_generated` | `False` |

BE 전달 필터는 `source_original`을 `photo_id=="hero"`이고 `fidelity_status=="VERIFIED"`인 경우에만 통과시킨다. 기존 `source`·`source_crop`·`source_composite`와 생성 자산의 구분에는 `product_generated`를 계속 사용한다.

### 현재 확인된 사진 역할

`generated/attached/petal-rembg-000846`에서는 다음 역할과 계약이 확인되었다.

| 역할 | `asset_mode` | 생성 여부 |
| --- | --- | --- |
| `hero` | `source_original` | `product_generated=False` |
| `packshot` | `source_composite` | `product_generated=False` |
| `detail` | `source_crop` | `product_generated=False` |
| `lifestyle` | `generated_scene` | `product_generated=True` |
| `detail-02`~`detail-05` | `generated_view` | `product_generated=True` |

## 2. `react_document` 계약 변화

- `src/detail_page_ai/react_document_builder.py`에서 figure children에 붙이던 `...-reference-label` figcaption 노드와 해당 text 노드를 제거했다.
- 위 노드에 label을 전달하기 위해 사용하던 `generated_photos` 인자를 제거했으며 `pipeline.py` 호출부 2곳도 함께 정리했다.
- 생성 사진 label 문자열은 `AI 생성 활용 장면`, `AI 생성 디테일`로 유지한다. 현재 표시 계약은 별도 figcaption 노드가 아니라 `product_generated` 플래그로 생성 여부를 구분하는 방식이다.
- 최종 확인 결과 산출물에서 제거된 '참고용' 표시 문자열은 0회였다.

## 3. HTML 렌더 계약 변화

`src/detail_page_ai/html_renderer.py`에서 figure/figcaption 오버레이 전달을 제거했고, `web/detail_page.css`의 관련 표시 규칙도 제거했다. FE 구현이나 프런트 통합은 이번 차수 범위에 포함하지 않았고, BE가 넘기는 계약 변화만 기록했다.

## 4. 변경되지 않은 계약

`page_plan` 블록 어휘, `PageBlockVariant`, `layout_id`는 이번 차수 변경 항목으로 기록되지 않았다. 레이아웃을 소비하는 기존 계약은 유지하고 사진 provenance와 표시 노드만 바꾸었다.

## 5. 하위 호환 영향

하위 호환 영향은 제한적이다. 기존 사진 모드와 `product_generated` 필드는 유지되고, 새 `source_original`은 hero와 `VERIFIED` 조건에만 사용된다. 따라서 에셋 생성 여부를 `product_generated`로 읽는 소비자는 기존 구분 방식을 계속 사용할 수 있다.

`react_document`에서 `...-reference-label` 노드나 정확한 '참고용' 문자열을 직접 찾던 소비자에게는 해당 presentation 노드와 문자열이 사라지는 계약 변화가 있다. FE 렌더러 구현과 통합 작업은 이 기록의 범위가 아니다.

