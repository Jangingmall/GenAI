# Round 02 · Experiment Report — 프롬프트의 순서 신호 제거

| 항목 | 값 |
| --- | --- |
| 차수 | 02 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-111715` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-102346` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 문제

Round 01에서 최빈 시퀀스가 5회 반복됐다. 프롬프트의 Copy Map 나열 순서, 9블록 하한, 순차 레시피가 모델의 page-plan 순서를 반복해서 각인할 가능성이 남았다.

## 가설

세 순서 신호를 제거하면 최빈 시퀀스 빈도가 줄어들 것이라고 가정했다.

## 실험 설계

Copy Map을 block type 참조표로 바꾸고, page_plan 하한을 9에서 8로 낮추며, `Open`·`Follow`·`Include`·`Finish` 순차 레시피를 제거했다. 입력 6건과 모델 및 이미지 재생성 조건은 고정했다.

## 실행 명령

- 파일럿 생성기는 `scripts/run_eval_pilot.py`였다. 저장된 `run_index.json`에는 전체 CLI 인자가 보존되어 있지 않다.
- 구성 측정: `.venv/bin/python scripts/check_plan_diversity.py generated/evaluation/pilot-20260910-111715`
- 컷아웃 측정: `.venv/bin/python scripts/check_cutout_fidelity.py generated/evaluation/pilot-20260910-111715 --role hero`

## 측정 수치

유효 공통 블록은 `hero`와 `closing`을 제외한 종수다. 당시 구 기준은 평균 Jaccard `<=60%`, 전체 공통 블록 `<=4종`, 완전 일치 `0쌍`이었다.

| 지표 | 실측값 |
|---|---:|
| 평균 Jaccard | 93.3% |
| 유효 공통 블록 | 6종 |
| 완전 일치 쌍 | 10쌍 |
| 고유 시퀀스 | 3종/6건 |
| 최빈 반복 | 3회 |
| 길이 분포 | 9블록 6건 |
| 파일럿 성공 | 6/6 |
| 컷아웃 게이트 | OK 6건, 부분 손실 0, 심각 손실 0 |
| 소요 시간 | 27.8분 |

## 판정

구 기준 `FAIL`이었다. 최빈 반복은 5회에서 3회로 줄었지만 평균 Jaccard·유효 공통 블록·완전 일치 쌍이 기준을 만족하지 못했다.

## 그 차수가 입증하거나 반증한 것

순서 신호를 줄이면 최빈 시퀀스 빈도는 감소한다는 방향의 변화는 입증됐다. 그러나 블록 집합의 수렴까지 해소된다는 가설은 반증됐다.

## 남은 한계

선택·생략 조건이 없어 모델이 모든 블록을 후보로 두는 문제가 이월됐다. 하한을 8로 낮췄어도 실제 계획은 모두 9블록이었다. 사람 검수 점수는 없었다.
