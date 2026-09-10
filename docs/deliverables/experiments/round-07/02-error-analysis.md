# Round 07 · 에러 분석 — 원형 variant 전달 경로 개방

| 항목 | 값 |
| --- | --- |
| 차수 | 07 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-153208` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-145007` (6차) |
| 이미지 재생성 | 아니오 (--image-provider none, AI 이미지 생성 없음) |
| 기록 시각 | 2026-09-10 |

## 1. 사건 A: 폐기된 선행 실행 중단 (`--no-product-photos` 오용)

### 1) 증상
구조 다양성 전용의 빠른 측정을 위해 이미지 생성을 끄려다, 첫 시도 실행(`pilot-20260910-152852`)이 중단되어 `run_index.json`조차 남지 않았다 (디렉터리가 비어 있음).

### 2) 증거
`generated/evaluation/pilot-20260910-152852` 디렉터리에 미완료 상태의 로그와 누락된 요약 파일이 남음.

### 3) 원인
오케스트레이터가 CLI 옵션 `--no-product-photos`를 "AI 이미지 생성 생략"으로 오인하여 사용했다. 그러나 이 플래그는 생성 모델뿐만 아니라 원본 상품 사진 메타데이터까지 완전히 제외시켜 파이프라인 전제 조건을 깨뜨렸다.

### 4) 조치
해당 실행을 폐기하고, 원본 상품 사진은 보존하면서 AI 생성 모델만 끄는 올바른 옵션인 `--image-provider none`을 사용하여 `pilot-20260910-153208`을 재실행했다.

### 5) 재발 방지
구조 전용 실행 시에는 반드시 `--image-provider none` 플래그만을 사용하도록 표준화했다.

---

## 2. 사건 B: ProductProfileDto 키워드 수 초과로 1건 실패 (성공 5/6)

### 1) 증상
채택된 실행 `pilot-20260910-153208`에서 6건 중 1건(`analysis-cma-122443`)이 실패하여 최종 `run_index.json`에 5건 성공, 1건 실패가 기록되었다.

### 2) 증거
- `generated/evaluation/pilot-20260910-153208/run_index.json`: `total: 6, completed: 5, failed: 1`
- 로그: `LocalModelError: Local vision model response does not match ProductProfileDto`.
- 근본 원인은 로컬 텍스트 모델이 `keywords`를 9개 반환하여 `src/detail_page_ai/dto.py:167`의 `max_length=8`을 위반한 Pydantic `too_long` 검증 실패였다. 이는 사건 A의 `--no-product-photos`와는 완전히 무관한 텍스트 생성 모델의 제약 위반이다.

### 3) 조치
Pydantic 검증 에러 로그를 확인하고, 성공한 5건의 산출물만을 대상으로 `check_plan_diversity.py` 구조 측정을 수행했다.

### 4) 재발 방지
텍스트 모델의 간헐적 리스트 길이 초과에 대비해 Pydantic 검증 전 상위 8개로 자동 truncate하는 방어 로직 검토가 필요하다.

---

## 3. 사건 C: photos/ 부재로 인한 컷아웃 지표 산출 불가 및 메타데이터 함정

### 1) 증상
`check_cutout_fidelity.py` 실행 시 `[FAIL] MISSING_OUTPUT 6건`이 발생하여 컷아웃 지표가 산출되지 않았다.

### 2) 증거
`pilot-20260910-153208`의 각 케이스별 `photos/` 디렉터리가 **전 케이스 0장**으로 비어 있다.

### 3) 원인 및 메타데이터 함정
- `--image-provider none`으로 실행되어 AI 이미지 생성이 수행되지 않았으며, 6차 자산을 복사해 온 것이 아니라 이미지가 아예 없다.
- **메타데이터 함정**: `run_index.json`의 최상위 `image_model` 필드는 CLI 기본 설정값이라 전 차수 `mlx-community/flux2-klein-9b-4bit`로 표시되지만, 실제로 무엇이 돌았는지는 반드시 **케이스별 `image_model`**을 봐야 한다. 7차의 케이스별 `image_model`은 `none`이다.

### 4) 조치
Round 07은 컷아웃 지표를 산출할 수 없는 실행이므로, 컷아웃 충실도 성과를 이 차수 것으로 인용해서는 안 된다는 사실을 명시했다.

---

## 4. 이월 중인 미해결 결함
- **구조 다양성 수렴 미해결**: variant 전달 경로를 열었으나 평균 Jaccard 유사도는 72.4%로 5차·6차와 동일하게 유지되었다.
- **사람 검수 점수 부재**: 8종 variant의 조화로움에 대한 평가 점수는 없으며 집계 수치만 존재한다.
