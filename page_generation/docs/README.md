# 문서 안내

상세페이지 생성 AI 의 문서를 과정의 **Phase 1~4 산출물 제출 목록(생성형 AI)** 에 맞춰 폴더별로 나눴습니다.
각 Phase 폴더의 `README.md` 가 그 Phase 의 제출 산출물과 해당 문서를 안내합니다.

- **성격** — `상시`: 현재 상태를 설명하며 갱신합니다 / `시점`: 날짜가 붙은 당시 기록이라 고치지 않습니다 / `보관`: 대체·폐기된 이력입니다
- 한 문서는 한 곳에만 두었습니다. 여러 Phase 에 걸치는 문서는 `common/`, 제출 대상이 아닌 문서는 `internal/` 에 있습니다

## 폴더 구조

```
docs/
├── phase1/        기획 — 초기 설계서
├── phase2/        설계·데이터 — 아키텍처·데이터 계획·평가 지표·안전성 정책
├── phase3/        구현·실험 — 제출본 5종, API 계약, 실행 기록, BE 협의, 1~13차 실험
├── phase4/        평가·운영 — 제출본 3종, 평가 기록, 배포·운영 가이드, 인프라 전달
├── common/        여러 Phase 공통
└── internal/      Phase 에 넣지 않은 문서 (보관·내부 작업 기록)
```

## Phase별 제출 산출물

| Phase | 제출 산출물 | 해당 문서 |
| --- | --- | --- |
| [Phase 1 — 기획](phase1/README.md) | 1-1 AI 관점 비교 분석 보고서 | 없음 |
| | 1-2 AI 통합 영역 2개+ 후보 도출 문서 | 없음 |
| | 1-3 AI·데이터·UX 차별화 전략 문서 | 없음 |
| [Phase 2 — 설계·데이터](phase2/README.md) | 2-1 AI 통합 영역 2개 최종 선정 + BE/FE 통합 인터페이스 명세 | 선정 문서 없음 · 명세는 Phase 3 `api/` |
| | 2-2 데이터 수집 계획·라이선스 점검 + 정제 전략 | `phase2/collection-license-cleaning-plan.md` |
| | 2-3 평가 데이터셋 + 평가 지표 정의서 | `data/evaluation/` · `phase2/metrics-definition.md` |
| | 2-4 AI 아키텍처 다이어그램 + 안전성 정책 초안 | `phase2/ai-architecture-design.md` 외 |
| [Phase 3 — 구현·실험](phase3/README.md) | 3-1 AI 영역 1·2 1차 구현 코드·체크포인트 | `phase3/submission/01` |
| | 3-2 에러 분석 + 2차 실험 보고서 | `phase3/submission/02`·`03` |
| | 3-3 추론 API 구성 코드 + BE/FE 통합 인터페이스 명세서 | `phase3/submission/04`·`05` |
| [Phase 4 — 평가·운영](phase4/README.md) | 4-1 AI 기능 평가 보고서 | `phase4/submission/01` |
| | 4-2 AI 안전성 검증 보고서 | `phase4/submission/02` |
| | 4-3 모델 카드 및 운영 가이드 | `phase4/submission/03` |

## 여러 Phase 공통

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`common/ai-architecture-and-safety.md`](common/ai-architecture-and-safety.md) | 로컬·서버 모델 경계, 데이터 흐름, 평가 지표와 안전성 정책을 합친 운영 기준 | 상시 |
| [`common/deliverables-audit.md`](common/deliverables-audit.md) | 산출물의 충족 여부·수정 사항·남은 작업 점검 결과 | 시점 |
| [`common/deliverables-review-2026-09-16.md`](common/deliverables-review-2026-09-16.md) | 2026-09-16 산출물 검토 시점 기록 | 시점 |

## Phase 에 넣지 않은 문서

제출 대상이 아닌 문서입니다. 삭제하지 않고 이력으로 남겨 둡니다.

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`internal/ai-product-content-generation-agreement.md`](internal/ai-product-content-generation-agreement.md) | 현재 활성 계약으로 사용하지 않는 이전 `/ai/products`·HTML block 계약 폐기 안내 | 보관 |
| [`internal/be-ai-integration-negotiation.md`](internal/be-ai-integration-negotiation.md) | BE·AI·챗봇 사이의 연동 불일치, 생성 이미지·경로·인증 합의 쟁점과 제안 | 보관 |
| [`internal/be-request-2026-09-17.md`](internal/be-request-2026-09-17.md) | 세 서비스 실측에서 찾은 BE↔AI 통신·비동기·인증·AWS 배포 문제와 요청 목록 | 보관 |
| [`internal/orchestration.md`](internal/orchestration.md) | cmux 기반 Claude Code 오케스트레이터와 CLI 워커의 멀티 에이전트 운영 규약 | 상시 |
| [`internal/plans/2026-08-26-image-detail-page-ai-fe-be.md`](internal/plans/2026-08-26-image-detail-page-ai-fe-be.md) | 제품 전체 이미지 생성 중심 초기 AI-FE/AI-BE 구현 계획 보관본 | 보관 |
| [`internal/plans/2026-08-27-source-preserving-detail-page-implementation.md`](internal/plans/2026-08-27-source-preserving-detail-page-implementation.md) | 원본 제품 보존형 상세페이지 구현 계획 | 시점 |
| [`internal/plans/2026-08-31-detail-page-flow-hardening.md`](internal/plans/2026-08-31-detail-page-flow-hardening.md) | draft-to-PNG 흐름과 승인 전후 renderer를 hardening하는 구현 계획 | 시점 |
| [`internal/plans/2026-08-31-fe-be-ai-be-fe-implementation.md`](internal/plans/2026-08-31-fe-be-ai-be-fe-implementation.md) | Product BE 게이트웨이·multipart·상태 계약 구현 계획 | 시점 |
| [`internal/plans/2026-09-10-round-01-05-documentation.md`](internal/plans/2026-09-10-round-01-05-documentation.md) | Round 01~05 실험 산출물 문서화와 색인 복원 계획 | 시점 |
| [`internal/product-photography.md`](internal/product-photography.md) | 스튜디오·라이프스타일·packshot 등 제품 사진 제작 기준 | 보관 |
| [`internal/refactoring/cleanup-diagnosis-agy.md`](internal/refactoring/cleanup-diagnosis-agy.md) | 코드 정리 후보를 실제 문제 유발 여부로 판정한 교차 진단 보고서 | 시점 |
| [`internal/refactoring/cleanup-diagnosis-codex.md`](internal/refactoring/cleanup-diagnosis-codex.md) | 코드 정리 필요성·유지비·호출 관계를 교차 검증한 진단 | 시점 |
| [`internal/refactoring/diagnosis-agy.md`](internal/refactoring/diagnosis-agy.md) | src 패키지 책임 경계와 규모를 점검한 구조 리팩터링 진단서 | 시점 |
| [`internal/refactoring/diagnosis-codex.md`](internal/refactoring/diagnosis-codex.md) | 순수 구조 변경을 전제로 한 책임 경계·호출 관계 교차 진단 | 시점 |
| [`internal/refactoring/refactoring-plan.md`](internal/refactoring/refactoring-plan.md) | 구조 리팩터링 작업의 확정 실행 계획과 현재 보류 사유 | 보관 |
| [`internal/sglang-vllm-fit.md`](internal/sglang-vllm-fit.md) | SGLang 확정 전 로컬 MLX Serve·SGLang·vLLM 적용을 검토한 당시 기록 | 보관 |

## 현재 구현 기준

> 2026-09-17 현재 구현 기준: FE 구조 출력의 정본은 제한형 `react_document` JSON AST이며, `page_plan`은 모델·편집·하위 호환 입력 필드입니다.
> 서버 추론은 SGLang 단일 엔진으로 텍스트 서버(`30000`)와 이미지 확산 서버(`30001`)를 띄우며, Mac 로컬 개발은 MLX Serve를 사용합니다.
> 서버 GPU에서는 아직 한 번도 실행하지 않았습니다. `hero`는 촬영 원본을 그대로 쓰는 `source_original`, 누끼는 rembg 경로를 사용하며 생성 사진의 별도 참고용 표시는 제거되었습니다.

> 2026-09-23 추가: `gallery` 블록의 사진은 모델이 아니라 **코드가 확정합니다.** 생성 디테일컷이 있으면 `page_plan`의 `photo_ids`를 무시하고 `detail`~`detail-05`로 덮어쓰며, PNG 렌더러와 `react_document` 빌더가 같은 규칙을 씁니다.
> 따라서 갤러리에 실제로 들어간 사진은 `page_plan`이 아니라 `react_document`의 `imageId` 참조로 판단합니다.
