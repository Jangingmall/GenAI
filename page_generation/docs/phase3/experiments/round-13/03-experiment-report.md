# Round 13 · 실험 리포트 — 생성컷 자리 확보와 다양성 귀무모형 재정의

| 항목 | 값 |
| --- | --- |
| 차수 | 13 |
| 파일럿 디렉터리 | `generated/attached/fan-set-usage-scene` |
| 직전 차수 기준 | `generated/evaluation/full60-v2-20260911-110752` (60건 실측) |
| 이미지 재생성 | 예 (부채 세트 1건, FLUX 생성컷 5장) |
| 기록 시각 | 2026-09-18 |
| 텍스트 모델 | `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` (MLX Serve `127.0.0.1:11234`) |
| 이미지 모델 | `mlx-community/flux2-klein-9b-4bit` (같은 포트, 2단계 교체) |

## 1. 문제

이미지 생성을 켜고 부채 세트를 돌려도 생성된 라이프스타일 컷이 상세페이지에
쓰이지 않았다. 생성컷 사용 0장이었다.

## 2. 실험 A — 모델은 코드가 지정한 시퀀스를 따르는가

### 가설

모델이 제시된 레이아웃 원형을 무시한다면, 후보를 1개로 강제해도 따르지 않을 것이다.

### 방법

`build_analysis_prompt(..., archetypes=[원형 하나], image_generation_enabled=True)`
로 프롬프트를 만들고 부채 이미지로 3회 호출했다. 후보가 1개면
`_format_selected_layout_instruction` 이 "Code-selected layout plan" 분기를 탄다.
프로젝트 소스는 수정하지 않았다.

### 결과

| 원형 | 완전 일치 | `usage_scene` 포함 | 누락 | 추가 |
| --- | --- | --- | --- | --- |
| `texture-macro-led` | True | True | 없음 | 없음 |
| `set-lineup-first` | True | True | 없음 | 없음 |
| `maker-process-led` | True | True | 없음 | 없음 |

3회 모두 코드가 지정한 시퀀스와 모델의 `page_plan` 이 완전히 일치했다. 카탈로그
원본(`assets/references/detail-page-layouts.json`)과 직접 대조해 확인했다.

### 판정

**가설은 기각됐다.** 모델은 지시를 따른다. 뒤이어 실제 실행의 후보군을 올바른
조건으로 재계산한 결과, 모델은 4종 후보에서도 `single-angle-color` 를 골라 그
시퀀스를 그대로 따르고 있었다([`02-error-analysis.md`](02-error-analysis.md) 1절).

진짜 원인은 `single-angle-color` 에 `usage_scene` 블록이 없다는 것이었다.

## 3. 실험 B — 후보 풀을 제한했을 때의 다양성 대가

### 방법

실험 A에서 `page_plan` 이 원형 시퀀스와 정확히 일치함을 확인했으므로, 모델을
호출하지 않고 원형 배정만으로 다양성을 정확히 시뮬레이션할 수 있다. 60건 평가셋의
실제 이미지 sha256 로 원형을 배정하고 `scripts/check_plan_diversity.py` 에 넣었다.
운영에서는 BE 가 항상 장인 힌트를 보내므로 힌트가 있는 조건으로 뒀다.

### 결과

| | 평균 집합 일치도 | 유효 공통 블록 | `usage_scene` 포함 |
| --- | --- | --- | --- |
| 전체 풀 (25종) | 55.5% | 0종 | 35 / 60 |
| **usage 풀 (16종)** | **60.9%** | **1종** | **60 / 60** |
| 기준 | ≤ 64.9% | ≤ 4종 | — |

후보 풀을 제한하면 상품 간 구성이 그만큼 비슷해진다. 평균 집합 일치도가 5.4%p
올라가지만 기준 안에 남는다.

참고로 강제 없이 뽑으면 카탈로그 25종 중 16종이 `usage_scene` 을 포함하므로
자연 포함률은 60건 기준 35건(58%)이었다. 생성컷을 항상 쓰려면 제한이 필요하다.

## 4. 실험 C — 완전 일치 쌍 귀무모형

### 방법

카탈로그에서 **복원추출**로 N건을 뽑는 시뮬레이션을 2000회(seed 42) 돌려 완전
일치 쌍 수의 평균과 p95 를 구했다. 우리 실행 결과는 유도에 넣지 않았다.

### 결과 — 배치 크기에 따른 기대값 (후보 25종)

| N | 기대 평균 | p95 |
| ---: | ---: | ---: |
| 6 | 0.60쌍 | 2 |
| 10 | 1.81쌍 | 4 |
| 20 | 7.54쌍 | 12 |
| 60 | 70.71쌍 | 86 |

관리자와 워커가 독립적으로 계산한 값이 자릿수까지 일치했다.

기존 고정 기준 1쌍은 **N=6 에서만** 타당했다. 9차의 "완전 일치 0쌍" 은 6건
파일럿 결과이고, 그 기준을 60건에 적용하면 구조적으로 통과할 수 없다.

### 결과 — 후보 풀 크기의 영향 (N=60)

| 실행 조건 | 후보 풀 | 기대 | p95 | 관측 | 판정 |
| --- | ---: | ---: | ---: | ---: | --- |
| 변경 전 시뮬 (전체 풀) | 25종 | 70.7쌍 | 86 | 66쌍 | 통과 |
| **현행 운영 실측 (힌트 없음)** | **15종** | **117.8쌍** | **138** | **99쌍** | **통과** |
| 변경 후 시뮬 (usage 풀) | 16종 | 110.5쌍 | 129 | 102쌍 | 통과 |

**세 경우 모두 우연 기대치보다 낮다.** 우리 레이아웃은 카탈로그에서 무작위로
뽑는 것보다 오히려 덜 겹친다. "99쌍 미달" 은 전적으로 잘못 정의된 기준선이 만든
착시였다.

### 대조군 — 게이트가 약해지지 않았는지

60건을 전부 같은 6블록 레이아웃으로 채운 입력을 같은 도구에 넣었다.

```
평균 집합 일치도  100.0%  (기준 66.3% 이하)  미달
완전 일치 쌍      1770쌍  (기준 86쌍 이하)   미달
```

템플릿 붕괴는 여전히 확실히 걸린다.

## 5. 종단 재실행 — 부채 세트

변경을 적용하고 같은 원본·같은 장인 입력으로 다시 돌렸다.

| | 변경 전 | 변경 후 |
| --- | --- | --- |
| 모델이 고른 원형 | `single-angle-color` | `process-evidence-deep` |
| `page_plan` | hero → statement → palette → wide_image → feature_grid → recommendation → notice → closing | hero → statement → gallery → wide_image → detail_split → feature_grid → **usage_scene** → scale_reference → info_table → closing |
| 페이지 | 774 × 3724 | 774 × 5043 |

힌트가 제작 과정을 강조하므로 모델이 `process-evidence-deep` 을 고른 것은 근거에
맞는 선택이다. 9차의 "관찰값으로 고른다" 설계는 유지된다.

### 사진 출처

| photo_id | asset_mode | fidelity | product_generated |
| --- | --- | --- | --- |
| `hero` | `source_original` | VERIFIED | False |
| `packshot` | `source` | FALLBACK | False |
| `detail` | `source_crop` | VERIFIED | False |
| `lifestyle` | `generated_scene` | GENERATED | **True** |
| `detail-02` ~ `detail-05` | `generated_view` | GENERATED | **True** |

8장 중 5장이 생성물이고, `usage_scene` 블록이 `photo_id: lifestyle` 로 생성컷을
쓴다. `photo_generation_failures` 와 `unused_generated_photo_ids` 는 비어 있다.

### 육안 판정

관리자가 전후 비교 페이지에서 확인하고 승인했다. 자동 지표만으로 채택하지 않았다.

## 6. 남은 관찰

- 새 레이아웃의 `scale_reference` 가 `photo_id: scale` 을 요청했으나 그 사진이
  없어 렌더 시 `hero` 로 대체됐다. 지난 차수에 넣은 사진 해소 로직이 조용히
  넘어가지 않고 경고를 남긴 결과다. 대체는 `react_document` 를 만들기 전에
  일어나므로 정본에는 문제가 없지만, 하위 호환용 `page_plan` 에는
  `photo_id: "scale"` 이 그대로 남아 `photos` 배열에 없는 사진을 가리킨다.
- 평균 집합 일치도 임계값의 여유폭(+10.0%p)은 이번 차수에서 건드리지 않았다.
  귀무모형이 복원추출로 바뀌면서 기준선 자체가 54.5%에서 56.3%(25종)로 올라갔으므로,
  여유폭의 근거를 다시 볼 필요가 있다. 별도 안건으로 둔다.
