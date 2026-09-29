# Round 13 · 구현 체크포인트 — 생성컷 자리 확보와 다양성 기준선 정정

| 항목 | 값 |
| --- | --- |
| 차수 | 13 |
| 파일럿 디렉터리 | `generated/attached/fan-set-usage-scene` |
| 직전 차수 기준 | `generated/evaluation/full60-v2-20260911-110752` (60건 실측) |
| 이미지 재생성 | 예 (부채 세트 1건, FLUX 생성컷 5장) |
| 기록 시각 | 2026-09-18 |

## 1. 차수 종료 상태

13차의 커밋 범위는 `dd628a2..ce24d62` 다. 두 변경 모두 채택했다.

| 커밋 | 내용 | 판정 |
| --- | --- | --- |
| `ac34b19` | 이미지 생성이 켜지면 레이아웃 원형 후보를 `usage_scene` 자리가 있는 것으로 제한 | 채택 (관리자 육안 승인) |
| `ce24d62` | 다양성 기준선을 복원추출·실제 배치 크기로 정정 | 채택 |

테스트는 387개에서 **394개**로 늘었고 전부 통과한다.

## 2. 변경 1 — 생성컷이 놓일 자리

`src/detail_page_ai/layout_archetypes.py` 의 `select_layout_archetypes` 가
`image_generation_enabled` 일 때 후보 풀을 `sequence` 에 `usage_scene` 이 있는
원형으로 제한한다. 걸러서 후보가 남지 않으면 기존 후보를 그대로 쓴다.

9차에서 정한 "모델이 상품 관찰값(`product_type`·`craft_type`·`observations`)을
후보의 `when`·`avoid_when` 과 대조해 스스로 고른다"는 설계는 **그대로 둔다.**
바뀐 것은 후보군의 구성뿐이며, 모델이 무엇을 고르든 생성컷이 놓일 자리가 있게 된다.

`image_generation_enabled` 는 `factory.py` → `LocalProductAnalyzer` →
프롬프트·원형 선택으로 배선했다.

## 3. 변경 2 — 다양성 기준선

`scripts/check_plan_diversity.py` 의 `simulate_catalog_baseline` 이 비복원
추출(`rng.sample`)로 귀무모형을 만들고 있었다. 실제 파이프라인은 상품마다
독립적으로 원형을 고르는 복원 추출이므로 모델이 과정과 달랐다. 자세한 것은
[`02-error-analysis.md`](02-error-analysis.md) 3절에 있다.

- 기준선을 **실제 배치 크기 N 만큼 복원추출**하도록 바꿨다.
- 같은 시뮬레이션에서 완전 일치 쌍 분포를 모아 **p95** 를 기준으로 유도한다.
  `DEFAULT_MAX_IDENTICAL_PAIRS = 1` 은 `--max-identical-pairs` 로 명시했을 때만
  쓰는 오버라이드로 남겼다.
- `--candidate-pool-size` 를 추가했다. 실행 조건에 따라 후보 풀이 좁아지는 경우
  (장인 힌트가 없으면 `statement` 원형이 빠져 15종)를 위한 것이고, 미지정이면
  카탈로그 전체를 쓴다.

## 4. 채택 근거

### 변경 1

부채 세트를 같은 원본·같은 장인 입력으로 다시 돌렸다.

| | 변경 전 | 변경 후 |
| --- | --- | --- |
| 모델이 고른 원형 | `single-angle-color` | `process-evidence-deep` |
| 블록 수 | 8 | 10 |
| `usage_scene` | 없음 | 있음 (`photo_id: lifestyle`) |
| 생성컷 사용 | 0장 | 5장 |
| 페이지 | 774 × 3724 | 774 × 5043 |

관리자가 전후 비교 페이지를 육안으로 확인하고 승인했다.

### 변경 2

게이트를 느슨하게 만든 것이 아님을 대조군으로 확인했다. 60건을 전부 같은
레이아웃으로 채운 입력은 **1770쌍 · 평균 집합 일치도 100%** 로 여전히 걸린다.

## 5. 남긴 것

- `scale_reference` 블록이 요청하는 `photo_id: scale` 사진이 존재하지 않아
  렌더 시 `hero` 로 대체된다. 경고 로그를 남기므로 조용히 넘어가지는 않는다.
  다만 `page_plan` 에는 `photo_id: "scale"` 이 그대로 남아 `photos` 배열에 없는
  사진을 가리킨다. 정본인 `react_document` 에는 이 참조가 없다. `scale` 컷을
  만들지, `page_plan` 에도 대체 결과를 반영할지 정해야 한다
  ([`05-be-fe-interface.md`](05-be-fe-interface.md) 4절).
- `--candidate-pool-size` 는 카탈로그의 **앞에서부터 N종**을 잘라 쓴다. 완전 일치
  쌍은 풀 크기에만 의존하므로 영향이 없지만, 평균 집합 일치도 기준선은 어느 N종이
  뽑히느냐에 따라 조금 달라진다(25종 56.3% / 15종 54.9%). 카탈로그가 계열별로
  묶여 있지 않아 계통적 편향은 없다고 보았다.
- `generated/attached/fan-set-usage-scene/result_summary.json` 은 정상이지만,
  이전 차수의 `fan-set-111842/result_summary.json` 은 중간에 잘려 있어 파싱되지
  않는다. 원인은 확인하지 않았다.
