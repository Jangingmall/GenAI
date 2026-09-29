# Round 13 · BE/FE 인터페이스 영향 — 스키마 변경 없음, 나오는 값의 분포가 달라짐

| 항목 | 값 |
| --- | --- |
| 차수 | 13 |
| 파일럿 디렉터리 | `generated/attached/fan-set-usage-scene` |
| 직전 차수 기준 | `generated/evaluation/full60-v2-20260911-110752` (60건 실측) |
| 이미지 재생성 | 예 (부채 세트 1건, FLUX 생성컷 5장) |
| 기록 시각 | 2026-09-18 |

## 1. 계약 변경 여부

**DTO·필드·타입 변경이 없다.** BE 가 코드를 고칠 일은 없다.

| 항목 | 13차 |
| --- | --- |
| `page_plan` 블록 타입 목록 | 변경 없음 (`usage_scene` 은 기존 화이트리스트에 이미 있었다) |
| `photo_id` 목록 | 변경 없음 (`lifestyle` 은 기존 목록에 있었다) |
| `asset_mode` · `fidelity_status` · `product_generated` | 변경 없음 |
| `react_document` 스키마 | 변경 없음 |
| 콜백 페이로드 | 변경 없음 |

## 2. 달라지는 것 — 값의 분포

이미지 생성을 켠 경로에서 **`usage_scene` 블록이 거의 항상 포함된다.** 60건
평가셋 기준 35건에서 60건으로 올라간다.

BE·FE 가 확인할 점은 다음 두 가지다.

### `page_plan` 이 길어질 수 있다

부채 세트 기준 8블록에서 10블록으로 늘었고, 렌더 높이가 3724px 에서 5043px 로
늘었다. `page_plan` 의 상한은 기존과 같은 **14블록**이다(`dto.py` 의
`max_length=14`). 상한 자체는 변하지 않았으므로 고정 크기를 가정한 구현이 없다면
영향이 없다.

### `usage_scene` 블록은 생성 사진을 가리킨다

`usage_scene` 은 `photo_id: lifestyle` 을 쓰고, 그 사진은 이미지 생성이 켜져
있으면 다음과 같이 나온다.

```
asset_mode       generated_scene
fidelity_status  GENERATED
product_generated true
```

**판매자에게 "이 컷은 생성물"이라고 표시해야 하는 사진이다.** 표시 근거가 되는
필드는 이미 내려가고 있으므로 FE 가 새로 받을 값은 없다.

## 3. 사진 출처 — 부채 세트 실행 기준

| photo_id | asset_mode | fidelity_status | product_generated |
| --- | --- | --- | --- |
| `hero` | `source_original` | VERIFIED | false |
| `packshot` | `source` | FALLBACK | false |
| `detail` | `source_crop` | VERIFIED | false |
| `lifestyle` | `generated_scene` | GENERATED | **true** |
| `detail-02` | `generated_view` | GENERATED | **true** |
| `detail-03` | `generated_view` | GENERATED | **true** |
| `detail-04` | `generated_view` | GENERATED | **true** |
| `detail-05` | `generated_view` | GENERATED | **true** |

`hero` 는 원본 픽셀을 그대로 보존한다(`source_original`). 12차에서 정한 원칙이
유지된다.

## 4. 알려진 틈 — `scale` 사진이 없다

새 레이아웃에서 `scale_reference` 블록이 선택될 수 있는데, 이 블록이 요청하는
`photo_id: scale` 사진을 파이프라인이 만들지 않는다. 현재는 `hero` 로 대체되고
경고를 남긴다.

```
photo_id 'scale' requested by scale_reference block is unavailable;
using default photo_id 'hero'
```

**`page_plan` 에는 존재하지 않는 사진을 가리키는 참조가 남는다.** 부채 세트 실행
산출물을 확인한 결과다.

```
page_plan 의 scale_reference : photo_id = "scale"
photos 배열                  : hero, packshot, detail, lifestyle,
                               detail-02 ~ detail-05   ← scale 없음
```

정본인 `react_document` 에는 이 문제가 없다. 대체가 `react_document` 를 만들기
전에 일어나므로 `scale` 참조가 남지 않는다(산출물 전체를 검색해 확인했다).

따라서 **`react_document` 를 쓰는 경로는 안전하고, `page_plan` 의 `photo_id` 를
직접 읽어 사진을 찾는 구현만 깨진다.** `page_plan` 은 하위 호환용 필드이므로
BE·FE 가 이미 `react_document` 를 쓰고 있다면 영향이 없다. 쓰고 있지 않다면
`photo_id` 를 `photos` 배열에서 찾지 못하는 경우를 처리해야 한다.

`scale` 컷을 실제로 만들지, 아니면 `page_plan` 에도 대체 결과를 반영할지는 아직
정하지 않았다. 둘 중 하나로 정리해야 할 항목이다.

## 5. BE 에 요청할 것

없다. 이번 차수는 우리 쪽 레이아웃 선택과 평가 도구만 바뀌었다.

이전 차수에서 올린 미해결 항목(BE-9 콜백 경로 정본, BE-11 콜백 시점과 승인 주체,
BE-12 이미지 URL 리다이렉트)은 그대로 회신 대기 중이다.
