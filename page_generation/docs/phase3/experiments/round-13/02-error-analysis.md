# Round 13 · 에러 분석 — 잘못된 진단, 효과 없는 수정, 잘못 정의된 기준선

| 항목 | 값 |
| --- | --- |
| 차수 | 13 |
| 파일럿 디렉터리 | `generated/attached/fan-set-usage-scene` |
| 직전 차수 기준 | `generated/evaluation/full60-v2-20260911-110752` (60건 실측) |
| 이미지 재생성 | 예 (부채 세트 1건, FLUX 생성컷 5장) |
| 기록 시각 | 2026-09-18 |

이번 차수의 사고 세 건은 모두 **측정 대상과 측정 도구가 어긋난** 경우였다.
증상이 아니라 측정을 먼저 의심했어야 했다.

## 1. 사건 1: 후보군을 다른 조건으로 재계산해 놓고 "모델이 지시를 어긴다"고 진단했다

### 관측

부채 세트 실행에서 `usage_scene` 이 뽑히지 않아 원인을 조사했다. 모델이 낸
`page_plan` 을 "제시된 원형 4종"과 대조했더니 어느 것과도 일치하지 않았다.

```
제시된 원형 4종: material-color-scale, component-assembly,
                color-system-led, silhouette-proof
모델 출력: hero, statement, palette, wide_image,
          feature_grid, recommendation, notice, closing
일치: 없음
```

여기서 "프롬프트에 `Do not add, substitute, or reorder page_plan blocks` 라고
적혀 있는데도 모델이 지키지 않는다"고 판단했고, "레이아웃 시퀀스를 코드가 확정하고
모델은 내용만 채우게 하자"는 설계 변경을 제안했다.

### 실제

**제시된 원형 4종을 내가 잘못 계산했다.** 진단 스크립트는 `user_hints=None` 으로
후보를 다시 뽑았는데, 실제 실행에는 장인 힌트(제품명·제작과정·관리법)가 있었다.
`select_layout_archetypes` 는 `making_method` 유무로 `statement` 계열 원형을
거르므로 두 조건의 후보군이 다르다.

| 조건 | 후보 4종 |
| --- | --- |
| 힌트 없음 (내가 비교한 것) | `material-color-scale`, `component-assembly`, `color-system-led`, `silhouette-proof` |
| **힌트 있음 (실제 실행)** | **`single-angle-color`**, `multi-angle-form`, `texture-macro-led`, `scale-and-care` |

모델이 낸 순서는 `single-angle-color` 의 시퀀스와 **완전히 일치했다.** 모델은
처음부터 지시를 지키고 있었다. 진짜 원인은 그 원형에 `usage_scene` 블록이 아예
없다는 것이었다.

### 교훈

파이프라인의 어떤 단계를 재현해 비교할 때는 **그 실행에 실제로 들어간 입력**으로
재현해야 한다. 함수 기본값으로 다시 부르면 다른 분기를 타고, 그 결과를 실제
출력과 대조하면 없는 문제를 만들어낸다.

이 진단을 근거로 관리자에게 설계 변경을 제안했고 승인까지 받았다. 구현 직전에
후보군을 다시 확인해 바로잡았으나, 승인 요청 전에 확인했어야 했다.

## 2. 사건 2: 원인이 아닌 곳을 고쳤다

사건 1의 잘못된 진단과 별개로, "후보 4종 중 `usage_scene` 원형이 하나도 없으면
하나를 교체한다"는 로직을 먼저 넣었다.

```python
if (image_generation_enabled and selected and usage_candidates
        and not any("usage_scene" in item.get("sequence", []) for item in selected)):
    selected[rng.randrange(len(selected))] = rng.choice(usage_candidates)
```

이 로직은 부채 실행에 아무 효과가 없었다. 실제 후보군에는 이미 `usage_scene` 을
가진 `texture-macro-led` 가 들어 있었고, 모델이 그것을 고르지 않았을 뿐이다.
**"후보에 하나는 있게 한다"와 "무엇을 골라도 자리가 있다"는 다른 요구사항이다.**

채택한 수정은 교체가 아니라 풀 자체를 거르는 것이고, 코드 줄 수도 더 적다.

## 3. 사건 3: 귀무모형이 실제 과정과 달랐다

### 관측

완전 일치 쌍 게이트가 60건 배치에서 어떤 설계로도 통과하지 못했다. 현행 운영
상태를 같은 도구로 재도 99쌍이 나와 기준(1쌍 이하)에 한참 못 미쳤다.

### 원인

`simulate_catalog_baseline` 이 `rng.sample(layout_sets, effective_k)` 로 **비복원
추출**을 했다. 시뮬레이션 배치 안에 같은 원형이 두 번 나올 수 없으므로 완전 일치
쌍의 기대값이 구조적으로 0 이었다. 그 위에 얹힌 고정 기준 1쌍은 모델에서 유도된
값이 아니라 손으로 정한 값이었다.

두 번째 문제는 `effective_k = min(sample_size, len(layout_sets))` 였다. 60건
배치에서 기준선은 25건만 시뮬레이션했다 — **60개 상품이 25종에서 서로 겹치지 않게
뽑히는, 일어날 수 없는 상황**을 모델링하고 있었다.

실제 파이프라인은 상품마다 독립적으로 원형을 고르는 복원 추출이다.

주목할 점은 코드 주석이 이 문제를 이미 알고 있었다는 것이다.

> With replacement across 25 archetypes, expected similarity rises to ~65.4%
> (+1.4%p) due to the birthday problem.

복원추출의 효과를 알면서도 모델을 고치는 대신 임계값에 여유폭을 더해 덮었다.

### 영향

9차 기록의 "완전 일치 0쌍" 은 **6건짜리 파일럿** 결과였다. 올바른 귀무모형에서
N=6 의 기대값은 0.60쌍이므로 0쌍은 자연스러운 값이고, 이것을 60건 배치에 그대로
적용하면 항상 실패한다. 9차의 결론 자체가 틀린 것은 아니지만, **그 수치가 배치
크기에 의존한다는 사실이 기록되지 않았다.**

### 교훈

게이트가 모든 설계에서 실패하면 설계가 아니라 게이트를 의심한다. 그리고 귀무모형은
**실제로 데이터를 만들어낸 과정과 같아야** 한다. 과정이 다르면 임계값에 여유폭을
더해도 맞춰지지 않는다.

기준을 고칠 때는 우리 결과를 보고 맞추지 않도록, 임계값 유도에 우리 실행 결과가
들어가지 못하게 못 박고 작업을 배분했다. 유도된 값은 독립적으로 계산한 귀무모형
참고값과 자릿수까지 일치했다([`03-experiment-report.md`](03-experiment-report.md) 4절).
