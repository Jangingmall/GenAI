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

## 가설이 빗나간 지점

실험 C는 처음에 “steps를 올리면 품질이 오르는가?”라는 질문으로 시작했지만, 1차 결과가 보여준 직접적인 문제는 품질 차이가 아니라 **실험 손잡이가 연결되지 않았다는 것**이었다. 먼저 endpoint가 파라미터를 실제로 반영하는지 확인해야 했고, 그 결과 `steps`만 JSON edit 경로에서 살아났다. `strength`는 전송 타입을 고치는 문제로 남지 않고, 현재 FLUX.2 in-context edit 모드가 지원하지 않는 기능이라는 결론에 도달했다.

## 근거 파일

- 1차 파일럿: `generated/evaluation/pilot-20260909-191344/run_index.json` 및 해당 `analysis-*/result_summary.json`
- 최종 파일럿: `generated/evaluation/pilot-20260909-224737/run_index.json`
- 최종 게이트 실행 기록: `.orchestration/tasks/20260909-224712-agy.md`
- 이미지 파라미터 실험: `generated/experiments/image-steps-ab-20260909-223049/results.json`
- 클라이언트 edit 경로: `src/local_detail_page_ai/clients.py`
