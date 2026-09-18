> 원본: docs/deliverables/03-second-experiment-report.md (원본 기준)

# 산출물 문서 ③ — 2차 실험 보고서

## 범위와 판정 기준

1차 파일럿에서 확인된 결함을 대상으로 가설을 세우고 수정한 뒤, 저장된 2차 산출물과 로그로 재검증한 결과를 정리한다. 수치가 없는 사람 검수 점수나 주관적인 시각 품질 평가는 이 보고서에 포함하지 않는다.

## 1차·2차 비교 요약

| 실험 | 1차 관찰 | 2차 관찰 | 현재 결론 |
|---|---|---|---|
| A. 컷아웃 마스크 | `ceramic` 3.2%, `textile` 26.2% 보존; 2건 손실 | `ceramic` 64.1%, `textile` 96.8%; 6건 전건 `OK` | 연결성 기반 마스크와 fallback이 보존 게이트를 통과시킴 |
| B. 제품 유형별 씬 분기 | 목걸이(`cma-109609`)가 `metal` 분기로 가서 사이드보드 씬을 받음 | 6건 중 6건 기대 분기 일치, 오분류 0건 | 장신구 전용 분기와 키워드 보강이 의도한 매핑을 회복함 |
| C. 이미지 파라미터 | 9셀 모두 서버 로그 `steps=4`, SHA-256도 동일 | JSON edit 경로에서 `steps` 반영; `strength`는 여전히 무반영 | steps 손잡이는 연결됐지만 품질 개선 A/B는 아직 유효하지 않음 |

## 실험 A — 컷아웃 마스크

### 문제

1차 파일럿 `generated/evaluation/pilot-20260909-191344`에서 밝은 제품 내부가 배경으로 판정됐다. `ceramic`(`cma-122443`) 보존율은 3.2%(요약 지시의 약 3%), `textile`(`cma-102980`)은 26.2%(약 26%)였다. 두 값 모두 컷아웃 제품 보존 게이트의 실패 사례다.

### 가설

색거리 임계값만으로 배경을 분리하면 외부 배경과 색이 비슷한 제품 내부까지 배경으로 지워진다. 배경은 이미지 테두리에서 연결된 영역으로만 정의해야 한다.

### 조치

`src/detail_page_ai/source_photos.py`의 컷아웃 경로에 다음 원칙을 적용했다.

- 이미지 테두리에서 4-이웃으로 연결된 영역만 배경으로 취급
- 마스크가 파편화되거나 신뢰할 수 없으면 `None`을 반환하고 원본으로 fallback
- 후속 수정에서 연결된 그림자에 대한 억제 로직을 추가

### 결과

최종 재실행 `generated/evaluation/pilot-20260909-224737`의 컷아웃 게이트 결과는 다음과 같다.

| 케이스 | 1차 보존율 | 2차 보존율 | 2차 판정 |
|---|---:|---:|---|
| `ceramic` / `cma-122443` | 3.2% | 64.1% | `OK` |
| `textile` / `cma-102980` | 26.2% | 96.8% | `OK` |
| 나머지 4건 | 100.0% | 100.0% | `OK` |

전체 6건이 성공했고, 컷아웃 게이트 요약은 `OK: 6`, 부분 손실 `0`, 심각 손실 `0`, 종료 코드 `0`이었다.

### 남은 한계

보존율은 자동 픽셀 지표이며 사람 검수 점수가 아니다. `review_sheet.csv`의 사실성·명료성·상품성·시각품질 칸은 비어 있으므로, 이 결과만으로 시각적 품질 향상을 주장할 수 없다. 또한 보존율은 제품 영역 기준으로 정규화된 지표이므로 전체 캔버스 점유율과 같은 의미가 아니다.

## 실험 B — 제품 유형별 씬 분기

### 문제

금·보석 목걸이(`jewelry`, `cma-109609`)가 장신구 전용 분기 없이 `metal` 분기로 배정되어 사이드보드 기반 씬을 받았다.

### 가설

`_product_scene_direction`에 장신구 분기가 없어서 금속 관련 키워드를 가진 목걸이가 일반 금속 제품 분기로 흘러간다고 보았다.

### 조치

`src/detail_page_ai/prompts.py`에 장신구 전용 씬 분기를 추가하고, 장신구·금속함 등 키워드가 서로 다른 분기로 해석되도록 키워드 커버리지를 보강했다.

### 결과

최종 재실행 `pilot-20260909-224737`에 대해 씬 분기 게이트가 6건을 모두 기대 분기와 일치시켰다.

| 카테고리 | 기대 분기 | 실제 분기 | 판정 |
|---|---|---|---|
| textile | `textile` | `textile` | 일치 |
| box | `box` | `box` | 일치 |
| metalware | `metal` | `metal` | 일치 |
| ceramic | `ceramic` | `ceramic` | 일치 |
| jewelry | `jewelry` | `jewelry` | 일치 |
| furniture | `wood` | `wood` | 일치 |

기대 분기 일치 6건, 오분류 0건, 기본값 fallback 0건이며 `scripts/check_scene_direction_coverage.py` 종료 코드는 `0`이었다.

### 남은 한계

검증 범위는 현재 카테고리당 1건인 6건 파일럿이다. 더 넓은 상품명·관찰값 분포에서의 커버리지는 별도 평가가 필요하다. 씬 분기 일치는 상품 이미지의 시각적 품질이나 매출 효과를 측정하지 않는다.

## 실험 C — 이미지 생성 파라미터

### 문제

`steps`를 높이면 품질을 개선할 수 있는지 확인하려고 `steps` 4/8/16과 `strength` 0.25/0.50/0.75의 9셀 실험을 수행했다. 그러나 `generated/experiments/image-steps-ab-20260909-223049/`의 9장 출력이 모두 같은 SHA-256으로 저장됐고, 서버 로그도 모두 `steps=4`였다. 즉 두 파라미터 모두 실제 edit 요청에 반영되지 않았다.

### 가설

MLX Core 26.9.1의 multipart `/v1/images/edits` 어댑터가 내부 `mode: "edit"` JSON으로 변환하는 과정에서 `steps`와 `strength`를 전달하지 않는 것으로 추정했다.

### 조치

`src/local_detail_page_ai/clients.py`의 `MlxServeImageClient.edit()`를 multipart endpoint 대신 JSON `/v1/images/generations`의 `mode: "edit"` 경로로 전환했다. 참조 이미지는 base64로 보내고, `steps`는 정수, `strength`는 실수로 JSON에 넣도록 했다.

### 결과

수정 전 9셀의 SHA-256은 모두 다음 값으로 동일했다.

`e1b213380ceda0c545bb24e1dac0d4cb5bfc385f4958751bf71b2de163dbd617`

수정 후 같은 프롬프트와 참조 이미지로 확인한 값은 다음과 같다.

| 설정 | 서버 로그 steps | 소요시간 | SHA-256 |
|---|---:|---:|---|
| `steps=4`, `strength=0.25` | 4 | 34.184초 | `e1b213380ced…` |
| `steps=8`, `strength=0.25` | 8 | 83.888초 | `9c1ec01d2aa47fffa39a56e6f712bacb51df0c61e9bbd1860cfb8a0c9be80a11` |
| `steps=4`, `strength=0.75` | 4 | 58.586초 | `e1b213380ced…` |

따라서 JSON edit 경로에서는 `steps`가 실제로 반영됐고, `steps=4`와 `steps=8`의 출력 바이트가 달랐다. 반면 동일한 `steps=4`에서 `strength=0.25`와 `0.75`는 같은 결과였으며, 현재 FLUX.2 in-context edit 모드는 `strength`를 의도적으로 사용하지 않는다.

### 남은 한계

파라미터가 연결된 뒤의 유효한 품질 A/B, 즉 사람 검수나 사전 정의된 품질 지표로 `steps=4`와 `steps=8`을 비교한 실험은 아직 수행하지 않았다. 따라서 8스텝이 더 낫다고 결론 내릴 근거가 없다. `strength`는 현재 모델 edit 모드에서 지원되지 않으므로 숫자형으로 전송하는 것만으로 활성화되지 않는다.

## 실험 D — 섹션 구성 다양화 1~12차 전체 색인

앞의 실험 A·B·C 본문은 유지했다. 섹션 구성 다양화 실험은 차수마다 다섯 종류의 로그로 분리했으며, 아래 표는 전체 색인이다. 각 차수의 구현 체크포인트·에러 분석·실험 리포트·추론 API 영향·BE/FE 인터페이스 영향은 링크된 다섯 문서에 각각 기록했다.

### 정본 수치와 판정 기준

- 1~7차 당시 절대 기준: 평균 Jaccard `<=60%`, 전체 공통 블록 `<=4종`, 완전 일치 `0쌍`.
- 8~9차 기준: 카탈로그 비복원 추출 평균 `+10%p`, 유효 공통 블록 `<=4종`, 완전 일치 `<=1쌍`.
- 개정 전 카탈로그 기준선은 63.9%, 개정 후 지정 시뮬레이션은 54.4%였다. 현재 스크립트 기준선은 54.52%, 6건 임계값은 64.52%다.
- 6차와 9차는 케이스별 `image_model=mlx-community/flux2-klein-9b-4bit`로 실제 이미지를 생성했다. 7차와 8차는 6차 자산을 복사한 실행이 아니라 `--image-provider none`으로 AI 이미지 생성을 끈 실행이었다.
- 7차는 케이스별 `image_model=none`이고 `photos/`가 전 케이스 0장이었다. 8차도 케이스별 `image_model=none`이며 남은 사진은 모두 `product_generated=false`인 원본 파생 컷이었다. `run_index.json` 최상위 `image_model`은 설정값이므로 실제 실행 여부의 근거로 쓰지 않았다.

### 1~12차 요약 표

| 차수 | 바꾼 것 | 파일럿 디렉터리 | 평균 Jaccard | 유효 공통 블록 | 완전 일치 쌍 | 판정 |
|---:|---|---|---:|---:|---:|---|
| 1 | validation 블록 패딩 제거 | `generated/evaluation/pilot-20260910-102346` | 96.3% | 6종 | 10쌍 | 구 기준 FAIL (6/6, 이미지 실제 생성) |
| 2 | 프롬프트 순서 각인 3곳 제거 | `generated/evaluation/pilot-20260910-111715` | 93.3% | 6종 | 10쌍 | 구 기준 FAIL (6/6, 이미지 실제 생성) |
| 3 | 블록별 선택·생략 조건 추가 | `generated/evaluation/pilot-20260910-115722` | 78.3% | 4종 | 2쌍 | 구 기준 FAIL (6/6, 이미지 실제 생성) |
| 4 | 원형 4종을 예시로 제시 | `generated/evaluation/pilot-20260910-123917` | 79.8% | 4종 | 3쌍 | 구 기준 FAIL (6/6, 이미지 실제 생성) |
| 5 | 구성을 코드가 결정, 모델은 카피 작성 | `generated/evaluation/pilot-20260910-135605` | 72.4% | 4종 | 1쌍 | 구 기준 FAIL (6/6, 이미지 실제 생성) |
| 6 | variant 고정 배정 해제·CSS 4종 구현 | `generated/evaluation/pilot-20260910-145007` | 72.4% | 4종 | 1쌍 | 구 기준 FAIL (6/6, Flux 실제 생성) |
| 7 | variant 전달 경로 개방 | `generated/evaluation/pilot-20260910-153208` | 72.4% | 4종 | 1쌍 | 구 기준 FAIL (5/6, `--image-provider none`, 사진 0장) |
| 8 | 카탈로그와 판정 기준 재설계 | `generated/evaluation/pilot-20260910-161310` | 66.0% | 1종 | 2쌍 | 새 기준 FAIL (6/6, `--image-provider none`, 원본 파생 컷) |
| **9** | **근거 기반 후보 원형 선택** | `generated/evaluation/pilot-20260910-164008` | **52.3%** | **0종** | **0쌍** | **새 기준 PASS (6/6, Flux 실제 생성)** |
| **10** | **'참고용' 라벨 계약 수정 + 60건 전체 평가 1차** | `generated/evaluation/full60-20260910-204433` | **52.3%** | **0종** | **0쌍** | **60/60 성공 · 라벨 60/60 PASS · 다양성 6건 표본 PASS · 컷아웃 OK 55/부분손실 5** |
| 11 | 컷아웃 게이트 보강(채택)·추출기 수정(되돌림) | `generated/evaluation/full60-v2-20260911-110752` | 52.3% | 0종 | 0쌍 | **되돌림** (지표 PASS 60/60·수행률 40%이나 육안 판정으로 추출기 되돌림 `162863d`, 게이트 채택 `696dd15`) |
| 12 | hero 원본 고정·rembg 누끼 채택·'참고용' 표시 제거·누끼+생성배경 합성 시도(반려) | `generated/attached/najeon-hero-030813`, `generated/attached/petal-rembg-000846`, `generated/cutout-compare/`, `generated/composite-check/{nacre,petals}` | 확인 필요 | 확인 필요 | 확인 필요 | **rembg 채택·hero `source_original`·합성 반려·348 passed** |

표의 `유효 공통 블록`은 `hero`·`closing`을 제외한 종수다.

### 차수별 5종 문서 링크

| 차수 | 구현 체크포인트 | 에러 분석 | 실험 리포트 | 추론 API | BE/FE 인터페이스 |
|---:|---|---|---|---|---|
| 1 | [문서](../experiments/round-01/01-implementation-checkpoint.md) | [문서](../experiments/round-01/02-error-analysis.md) | [문서](../experiments/round-01/03-experiment-report.md) | [문서](../experiments/round-01/04-inference-api.md) | [문서](../experiments/round-01/05-be-fe-interface.md) |
| 2 | [문서](../experiments/round-02/01-implementation-checkpoint.md) | [문서](../experiments/round-02/02-error-analysis.md) | [문서](../experiments/round-02/03-experiment-report.md) | [문서](../experiments/round-02/04-inference-api.md) | [문서](../experiments/round-02/05-be-fe-interface.md) |
| 3 | [문서](../experiments/round-03/01-implementation-checkpoint.md) | [문서](../experiments/round-03/02-error-analysis.md) | [문서](../experiments/round-03/03-experiment-report.md) | [문서](../experiments/round-03/04-inference-api.md) | [문서](../experiments/round-03/05-be-fe-interface.md) |
| 4 | [문서](../experiments/round-04/01-implementation-checkpoint.md) | [문서](../experiments/round-04/02-error-analysis.md) | [문서](../experiments/round-04/03-experiment-report.md) | [문서](../experiments/round-04/04-inference-api.md) | [문서](../experiments/round-04/05-be-fe-interface.md) |
| 5 | [문서](../experiments/round-05/01-implementation-checkpoint.md) | [문서](../experiments/round-05/02-error-analysis.md) | [문서](../experiments/round-05/03-experiment-report.md) | [문서](../experiments/round-05/04-inference-api.md) | [문서](../experiments/round-05/05-be-fe-interface.md) |
| 6 | [문서](../experiments/round-06/01-implementation-checkpoint.md) | [문서](../experiments/round-06/02-error-analysis.md) | [문서](../experiments/round-06/03-experiment-report.md) | [문서](../experiments/round-06/04-inference-api.md) | [문서](../experiments/round-06/05-be-fe-interface.md) |
| 7 | [문서](../experiments/round-07/01-implementation-checkpoint.md) | [문서](../experiments/round-07/02-error-analysis.md) | [문서](../experiments/round-07/03-experiment-report.md) | [문서](../experiments/round-07/04-inference-api.md) | [문서](../experiments/round-07/05-be-fe-interface.md) |
| 8 | [문서](../experiments/round-08/01-implementation-checkpoint.md) | [문서](../experiments/round-08/02-error-analysis.md) | [문서](../experiments/round-08/03-experiment-report.md) | [문서](../experiments/round-08/04-inference-api.md) | [문서](../experiments/round-08/05-be-fe-interface.md) |
| 9 | [문서](../experiments/round-09/01-implementation-checkpoint.md) | [문서](../experiments/round-09/02-error-analysis.md) | [문서](../experiments/round-09/03-experiment-report.md) | [문서](../experiments/round-09/04-inference-api.md) | [문서](../experiments/round-09/05-be-fe-interface.md) |
| 10 | [문서](../experiments/round-10/01-implementation-checkpoint.md) | [문서](../experiments/round-10/02-error-analysis.md) | [문서](../experiments/round-10/03-experiment-report.md) | [문서](../experiments/round-10/04-inference-api.md) | [문서](../experiments/round-10/05-be-fe-interface.md) |
| 11 | [문서](../experiments/round-11/01-implementation-checkpoint.md) | [문서](../experiments/round-11/02-error-analysis.md) | [문서](../experiments/round-11/03-experiment-report.md) | [문서](../experiments/round-11/04-inference-api.md) | [문서](../experiments/round-11/05-be-fe-interface.md) |
| 12 | [문서](../experiments/round-12/01-implementation-checkpoint.md) | [문서](../experiments/round-12/02-error-analysis.md) | [문서](../experiments/round-12/03-experiment-report.md) | [문서](../experiments/round-12/04-inference-api.md) | [문서](../experiments/round-12/05-be-fe-interface.md) |

### 전체 결론

**원인이 셋으로 나뉘어 있었다.** 첫째, 카탈로그에 붙박이 블록이 많아 가능한 다양성의 상한을 만들었다. 둘째, 합격 기준이 카탈로그 도달 가능성을 확인하지 않은 채 정해졌고 `hero`·`closing`을 공통 블록으로 세어 측정도 왜곡했다. 셋째, 이미지 해시 하나로 원형을 추첨해 상품의 `when`·`avoid_when` 조건과 연결하지 않았다. 9차에서 후보와 상품 관찰값을 연결한 뒤 유효 공통 0종·완전 일치 0쌍이 됐다.

**합격 기준을 근거 없이 정한 것이 가장 오래 끈 오류였다.** 개정 전 카탈로그에서 이상적 추출 평균이 63.9%인데 절대 목표를 60%로 정했고, 고정 경계 블록까지 공통 수에 포함했다. 그 결과 1~7차의 개별 파이프라인 수정이 문제를 충분히 설명하지 못했다. 기준선을 카탈로그에서 계산하고 유효 공통 수를 분리한 것은 8차의 메타 수준 수정이었다.

최종 9차는 평균 Jaccard 52.3%, 유효 공통 0종, 완전 일치 0쌍으로 새 구조 기준을 통과했고, 컷아웃 게이트도 총 6건 `OK`, 부분 손실 0건, 심각 손실 0건이었다. 이 결과는 구조와 자동 컷아웃 지표에 대한 판정이며 사람 검수나 전반적인 상품성·시각 품질 승인을 뜻하지 않는다.

10~12차는 각각 다음과 같이 마무리됐다. 10차에는 60건 전체 평가를 수행했고 60/60 성공했다. 11차에는 게이트 보강을 채택했지만 추출기 수정은 되돌렸다. 12차에는 hero 원본 고정과 rembg 누끼를 채택했고, 누끼와 생성 배경의 합성 시도는 반려했다.

### 전체 미해결 이슈

- 사람 검수 점수는 존재하지 않는다.
- 60건 전체 평가는 10차에 수행되어 60/60 성공했다. 다만 표의 파일럿은 7차 성공 5건을 제외하면 차수별 6건이다.
- 생성 자산의 `참고용` 라벨 계약은 10차에 수정되어 라벨 게이트 60/60 PASS를 기록했고, 12차 관리자 결정으로 화면 표시 요구와 게이트가 제거됐다. 현재는 `product_generated=true`로 생성 자산을 구분하므로, 이 항목은 더 이상 열린 배포 차단 조건이 아니다.

### 근거

- `.orchestration/briefs/round-facts-verified.md`
- `generated/evaluation/pilot-20260910-102346`부터 `pilot-20260910-164008`까지의 저장된 파일럿 산출물
- `scripts/check_plan_diversity.py`, `scripts/check_cutout_fidelity.py`
