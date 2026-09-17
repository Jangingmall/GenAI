# 문서 안내

프로젝트 문서는 목적별로 나눠 관리합니다.

> 2026-09-17 현재 구현 기준: FE 구조 출력의 정본은 제한형 `react_document` JSON AST이며, `page_plan`은 모델·편집·하위 호환 입력 필드입니다.
> 서버 추론은 SGLang 단일 엔진으로 텍스트 서버(`30000`)와 이미지 확산 서버(`30001`)를 띄우며, Mac 로컬 개발은 MLX Serve를 사용합니다.
> 서버 GPU에서는 아직 한 번도 실행하지 않았습니다. `hero`는 촬영 원본을 그대로 쓰는 `source_original`, 누끼는 rembg 경로를 사용하며 생성 사진의 별도 참고용 표시는 제거되었습니다.

## API

- [`api/ai-dto-contract.md`](api/ai-dto-contract.md): BE↔AI 방향별 DTO와 이미지 provenance·메타데이터 전달 계약
- [`api/ai-fe-io-spec.md`](api/ai-fe-io-spec.md): BE·FE·AI 사이의 운영 및 로컬 직접 API 입출력 명세
- [`api/ai-product-content-generation-agreement.md`](api/ai-product-content-generation-agreement.md): 현재 활성 계약으로 사용하지 않는 이전 `/ai/products`·HTML block 계약 폐기 안내
- [`api/be-fe-ai-integration-spec.md`](api/be-fe-ai-integration-spec.md): BE 공개 제안과 AI 내부/직접 API의 BE·FE 연동 계약
- [`api/react-json-output-contract.md`](api/react-json-output-contract.md): FE용 `react_document` schema v2.0의 구조·렌더링·보안 계약
- [`../src/detail_page_ai/react_document.py`](../src/detail_page_ai/react_document.py): FE가 소비하는 제한형 React JSON AST DTO 구현
- [`../src/detail_page_ai/react_document_builder.py`](../src/detail_page_ai/react_document_builder.py): 승인 draft에서 React JSON AST를 결정적으로 조립하는 builder

## 아키텍처

- [`architecture/ai-architecture-and-safety.md`](architecture/ai-architecture-and-safety.md): 로컬·서버 모델 경계, 데이터 흐름, 평가 지표와 안전성 정책을 합친 운영 기준
- [`architecture/ai-architecture-design.md`](architecture/ai-architecture-design.md): 상세페이지 AI의 모델 구성·서빙 구조·저장·재시도·확장 설계
- [`architecture/ai-evaluation-and-safety-policy.md`](architecture/ai-evaluation-and-safety-policy.md): 평가 방법·release gate·사람 검수·안전성 정책 초안

## 평가

> 아래 평가 문서는 날짜가 붙은 당시 실행·검토 사실을 보존하는 시점 기록입니다. 이후 구현이 바뀌어도 당시 기록은 고치지 않습니다.

- [`evaluation/ai-review-2026-09-10.md`](evaluation/ai-review-2026-09-10.md): 2026-09-10 AI 검토 시점 기록
- [`evaluation/deliverables-review-2026-09-16.md`](evaluation/deliverables-review-2026-09-16.md): 2026-09-16 산출물 검토 시점 기록
- [`evaluation/copy-analysis-2026-09-09.md`](evaluation/copy-analysis-2026-09-09.md): 파일럿 1차 6건 생성 카피의 사실 근거성 분석과 프롬프트 개선 후보 기록
- [`evaluation/cutout-ground-truth.md`](evaluation/cutout-ground-truth.md): 누끼 ground-truth 기준 시점 기록
- [`evaluation/cutout-regression-baseline.md`](evaluation/cutout-regression-baseline.md): 누끼 회귀 기준선 시점 기록
- [`evaluation/full60-runs.md`](evaluation/full60-runs.md): 60건 전체 평가 실행 시점 기록
- [`evaluation/human-review-guide.md`](evaluation/human-review-guide.md): 4대 평가 축의 1~5점 척도와 2인 독립 검수·합의 절차 가이드
- [`evaluation/metrics-definition.md`](evaluation/metrics-definition.md): 사실성·명료성·상품성·시각품질 4대 축의 평가 지표와 통계 정의
- [`evaluation/pilot-report-2026-09-09.md`](evaluation/pilot-report-2026-09-09.md): CMA real v1 카테고리별 6건 대상 1차 파일럿 실행 결과와 결함 분석 기록
- [`../data/evaluation/cma_real_v1/README.md`](../data/evaluation/cma_real_v1/README.md): CC0 표시 기반 실물 60건의 분석·렌더링 입력과 실행·검수 안내

## 데이터·라이선스

- [`data/collection-license-cleaning-plan.md`](data/collection-license-cleaning-plan.md): CMA 실물 데이터 수집·권리 표시·라이선스 확인·정제 전략

## 운영·모델

- [`operations/aws-deployment.md`](operations/aws-deployment.md): 로컬 MLX 파이프라인을 AWS 환경으로 이관하고 1건 end-to-end 품질 게이트를 확인하는 운영 가이드
- [`operations/aws-migration-checklist.md`](operations/aws-migration-checklist.md): AWS 이관에 필요한 준비물·차단 조건·확인 방법을 정리한 실무 체크리스트
- [`operations/eks-workload-spec.md`](operations/eks-workload-spec.md): EKS 인프라팀 요청에 대한 AI 저장소 workload·자원·검증 상태 답변
- [`operations/local-generation-test-report.md`](operations/local-generation-test-report.md): 로컬 상세페이지 생성 smoke test 구성·실행 결과와 미완료 정량 평가 상태
- [`operations/local-llm.md`](operations/local-llm.md): Mac 로컬 MLX Serve 기반 상세페이지 LLM 실행 경로와 출력 규칙
- [`operations/orchestration.md`](operations/orchestration.md): cmux 기반 Claude Code 오케스트레이터와 CLI 워커의 멀티 에이전트 운영 규약
- [`operations/server-memory-estimate.md`](operations/server-memory-estimate.md): Apple Silicon 로컬 MLX 통합 메모리 예상과 서버 메모리 문서 참조
- [`operations/sglang-serving-research.md`](operations/sglang-serving-research.md): AWS g6e.xlarge 한 장의 L40S에서 텍스트·확산 SGLang 2프로세스를 공존시키기 위한 운영 조사
- [`operations/sglang-vllm-fit.md`](operations/sglang-vllm-fit.md): SGLang 확정 전 로컬 MLX Serve·SGLang·vLLM 적용을 검토한 당시 기록
- [`operations/ubuntu-deployment.md`](operations/ubuntu-deployment.md): Ubuntu g6e.xlarge에서 detail-page-ai와 SGLang 2개 추론 서버를 Docker Compose로 배포하는 가이드

## 산출물

- [`deliverables-audit.md`](deliverables-audit.md): 산출물의 충족 여부·수정 사항·남은 작업 점검 결과
- [`deliverables/01-implementation-checkpoint.md`](deliverables/01-implementation-checkpoint.md): AI 영역 1·2의 1차 구현 체크포인트와 근거 산출물 기준
- [`deliverables/02-error-analysis.md`](deliverables/02-error-analysis.md): 상세페이지 AI 시스템 개발·평가 과정의 에러 분석 보고서
- [`deliverables/03-second-experiment-report.md`](deliverables/03-second-experiment-report.md): 1차 파일럿 결함을 수정한 2차 실험과 재검증 결과
- [`deliverables/04-inference-api.md`](deliverables/04-inference-api.md): 서비스 API와 텍스트·비전·이미지 모델 추론 API의 층별 구성
- [`deliverables/05-be-fe-interface.md`](deliverables/05-be-fe-interface.md): BE/FE 통합 인터페이스 정본 문서를 가리키는 canonical link stub

## 실험 기록

> 아래 실험 기록은 각 차수 당시의 구현·에러·추론 API·BE/FE 영향 사실을 보존하는 시점 기록입니다. 이후 구현이 바뀌어도 수정하지 않습니다.

- [`deliverables/experiments/`](deliverables/experiments/): Round 01~12, 총 12차 × 5종(구현 체크포인트·에러 분석·실험 리포트·추론 API·BE/FE 인터페이스) 60개 기록

## 리팩터링

> 아래 진단·계획 문서는 작성 당시 코드 상태와 판정을 남긴 시점 기록입니다. 이후 구현이 바뀌어도 원문은 수정하지 않습니다.

- [`refactoring/cleanup-diagnosis-agy.md`](refactoring/cleanup-diagnosis-agy.md): 코드 정리 후보를 실제 문제 유발 여부로 판정한 교차 진단 보고서
- [`refactoring/cleanup-diagnosis-codex.md`](refactoring/cleanup-diagnosis-codex.md): 코드 정리 필요성·유지비·호출 관계를 교차 검증한 진단
- [`refactoring/diagnosis-agy.md`](refactoring/diagnosis-agy.md): src 패키지 책임 경계와 규모를 점검한 구조 리팩터링 진단서
- [`refactoring/diagnosis-codex.md`](refactoring/diagnosis-codex.md): 순수 구조 변경을 전제로 한 책임 경계·호출 관계 교차 진단
- [`refactoring/refactoring-plan.md`](refactoring/refactoring-plan.md): 구조 리팩터링 작업의 확정 실행 계획과 현재 보류 사유

## 참고 자료·설계 이력

- [`references/product-photography.md`](references/product-photography.md): 스튜디오·라이프스타일·packshot 등 제품 사진 제작 기준
- [`superpowers/plans/2026-08-26-image-detail-page-ai-fe-be.md`](superpowers/plans/2026-08-26-image-detail-page-ai-fe-be.md): 제품 전체 이미지 생성 중심 초기 AI-FE/AI-BE 구현 계획 보관본
- [`superpowers/plans/2026-08-27-source-preserving-detail-page-implementation.md`](superpowers/plans/2026-08-27-source-preserving-detail-page-implementation.md): 원본 제품 보존형 상세페이지 구현 계획
- [`superpowers/plans/2026-08-31-detail-page-flow-hardening.md`](superpowers/plans/2026-08-31-detail-page-flow-hardening.md): draft-to-PNG 흐름과 승인 전후 renderer를 hardening하는 구현 계획
- [`superpowers/plans/2026-08-31-fe-be-ai-be-fe-implementation.md`](superpowers/plans/2026-08-31-fe-be-ai-be-fe-implementation.md): Product BE 게이트웨이·multipart·상태 계약 구현 계획
- [`superpowers/plans/2026-09-10-round-01-05-documentation.md`](superpowers/plans/2026-09-10-round-01-05-documentation.md): Round 01~05 실험 산출물 문서화와 색인 복원 계획
- [`superpowers/specs/2026-08-26-image-driven-detail-page-design.md`](superpowers/specs/2026-08-26-image-driven-detail-page-design.md): 제품 전체 이미지 생성 중심 초기 설계 보관본
- [`superpowers/specs/2026-08-27-source-preserving-detail-page-design.md`](superpowers/specs/2026-08-27-source-preserving-detail-page-design.md): 원본 제품 보존형 상세페이지 생성 시스템 설계

## 노트북

- [`../notebooks/colab_sglang_smoke_test.ipynb`](../notebooks/colab_sglang_smoke_test.ipynb): 저장소 clone 없이 Colab에서 SGLang 텍스트·이미지 OpenAI 호환 요청을 확인하는 GPU smoke test 노트북
