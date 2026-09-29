# Phase 2 — 설계·데이터

과정의 **산출물 제출 목록(생성형 AI)** 을 기준으로 **이미 있는 문서**를 배치했습니다. 이 Phase 를 위해 새로 쓴 문서는 없습니다.

- **성격** — `상시`: 현재 상태를 설명하며 갱신합니다 / `시점`: 날짜가 붙은 당시 기록이라 고치지 않습니다 / `보관`: 대체·폐기된 이력입니다

## 제출 산출물과 해당 문서

| # | 제출 산출물 | 해당 문서 |
| --- | --- | --- |
| 2-1 | AI 통합 영역 2개 최종 선정 문서 + BE/FE 통합 인터페이스 명세 | 영역 선정만 다룬 별도 문서는 없습니다. 영역 1(분석·카피)·영역 2(이미지·렌더링) 구분은 [Phase 3 체크포인트 1절](../phase3/submission/01-implementation-checkpoint.md), 인터페이스 명세는 [Phase 3 `api/`](../phase3/api/) 에 있습니다 |
| 2-2 | 데이터 수집 계획·라이선스 점검 문서 + 정제 전략 | [`collection-license-cleaning-plan.md`](collection-license-cleaning-plan.md) |
| 2-3 | 평가 데이터셋 (영역별 50~200건) + 평가 지표 정의서 | 데이터셋은 docs 밖 [`data/evaluation/`](../../data/evaluation/) ([데이터셋 카드](../../data/evaluation/dataset-card.md)), 지표는 [`metrics-definition.md`](metrics-definition.md)·[`human-review-guide.md`](human-review-guide.md) |
| 2-4 | AI 아키텍처 다이어그램 + 안전성 정책 초안 | [`ai-architecture-design.md`](ai-architecture-design.md), 다이어그램 [`ai-architecture.excalidraw`](ai-architecture.excalidraw)·[`runtime-architecture.html`](runtime-architecture.html), 정책 [`ai-evaluation-and-safety-policy.md`](ai-evaluation-and-safety-policy.md) |

> 아키텍처와 안전성 정책을 합친 운영 기준 [`ai-architecture-and-safety.md`](../common/ai-architecture-and-safety.md) 는 여러 Phase 에 걸쳐 [`common/`](../common/) 에 두었습니다.

## 이 폴더의 문서

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`ai-architecture-design.md`](ai-architecture-design.md) | 상세페이지 AI의 모델 구성·서빙 구조·저장·재시도·확장 설계 | 상시 |
| [`ai-evaluation-and-safety-policy.md`](ai-evaluation-and-safety-policy.md) | 평가 방법·release gate·사람 검수·안전성 정책 초안 | 상시 |
| [`collection-license-cleaning-plan.md`](collection-license-cleaning-plan.md) | CMA 실물 데이터 수집·권리 표시·라이선스 확인·정제 전략 | 상시 |
| [`human-review-guide.md`](human-review-guide.md) | 4대 평가 축의 1~5점 척도와 2인 독립 검수·합의 절차 가이드 | 상시 |
| [`metrics-definition.md`](metrics-definition.md) | 사실성·명료성·상품성·시각품질 4대 축의 평가 지표와 통계 정의 | 상시 |
