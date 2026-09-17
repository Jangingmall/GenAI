# Round 01 · Experiment Report — validation 계획 보존

| 항목 | 값 |
| --- | --- |
| 차수 | 01 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-102346` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260909-224737` (baseline) |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 문제

baseline에서 6건 중 5건이 같은 시퀀스를 냈다. 충분한 모델 계획을 validation이 다시 채우거나 재배열하는지 확인해야 했다.

## 가설

중간 블록이 6개 이상인 모델 계획을 보존하면 validation이 선택 차이를 지우지 않아 수렴 지표가 낮아질 것이라고 가정했다.

## 실험 설계

`src/detail_page_ai/validation.py:ensure_editorial_page_plan`에서 충분한 계획을 그대로 보존하고, 빈약한 계획의 안전 바닥만 유지했다. 모델, 입력 6건, 이미지 생성 조건은 고정했다.

## 실행 명령

- 파일럿 생성기는 `scripts/run_eval_pilot.py`였다. 저장된 `run_index.json`에는 전체 CLI 인자가 보존되어 있지 않다.
- 구성 측정: `.venv/bin/python scripts/check_plan_diversity.py generated/evaluation/pilot-20260910-102346`
- 컷아웃 측정: `.venv/bin/python scripts/check_cutout_fidelity.py generated/evaluation/pilot-20260910-102346 --role hero`

## 측정 수치

아래의 유효 공통 블록은 `hero`와 `closing`을 제외한 종수다. 당시 구 기준은 평균 Jaccard `<=60%`, 전체 공통 블록 `<=4종`, 완전 일치 `0쌍`이었다.

| 지표 | 실측값 |
|---|---:|
| 평균 Jaccard | 96.3% |
| 유효 공통 블록 | 6종 |
| 완전 일치 쌍 | 10쌍 |
| 고유 시퀀스 | 2종/6건 |
| 최빈 반복 | 5회 |
| 길이 분포 | 8블록 1건, 9블록 5건 |
| 파일럿 성공 | 6/6 |
| 컷아웃 게이트 | OK 6건, 부분 손실 0, 심각 손실 0 |
| 소요 시간 | 28.2분 |

## 판정

구 기준을 통과하지 못했다. 평균 Jaccard와 완전 일치 쌍이 기준을 크게 넘었고, 유효 공통 블록 6종도 전체 공통 블록 상한 4종을 넘는다.

## 그 차수가 입증하거나 반증한 것

validation 패딩 제거는 평균 96.7%→96.3%, 유효 공통 7종→6종으로 미세한 변화를 만들었다. 그러나 최빈 반복 5회와 완전 일치 10쌍은 그대로였다. 따라서 패딩 제거만으로 구성 수렴이 풀린다는 가설은 반증됐다.

## 남은 한계

프롬프트에 남은 순서 각인과 선택·생략 조건 부재를 검증하지 않았다. 컷아웃 게이트는 전건 통과했지만 사람 검수 점수는 없었다.
