# 문서 안내

프로젝트 문서는 목적별로 나눠 관리합니다.

> 2026-09-08 최신 구현 기준: FE 구조 출력의 canonical contract는 제한형 `react_document` JSON AST입니다. `page_plan`은 편집·하위 호환 필드이고, HTML/CSS는 승인 후 PNG를 만드는 내부 renderer 경로로만 취급합니다.

## API

- [산출물 점검 결과](deliverables-audit.md): 충족 여부·수정 사항·남은 작업
- [BE/FE 통합 인터페이스](api/be-fe-ai-integration-spec.md): 구현 대조 정정 및 공개 계약 제안
- [데이터 수집·라이선스·정제 계획](data/collection-license-cleaning-plan.md)
- [평가 지표 정의서](evaluation/metrics-definition.md)
- [실제 공개 이미지 평가셋](../data/evaluation/cma_real_v1/README.md): CC0 표시 기반 실물 60점, 분석/렌더링 각 60건, 실행·검수 안내

- [`api/ai-dto-contract.md`](api/ai-dto-contract.md): 상품 BE↔AI 방향별 DTO 및 이미지·메타데이터 전달 계약
- [`api/ai-fe-io-spec.md`](api/ai-fe-io-spec.md): 상품 BE가 FE와 AI 사이를 연결하는 입출력 명세
- [`api/react-json-output-contract.md`](api/react-json-output-contract.md): FE용 `react_document` schema v2.0·렌더링·보안·버전 계약
- [`../src/detail_page_ai/react_document.py`](../src/detail_page_ai/react_document.py): FE가 소비하는 제한형 React JSON AST DTO 구현
- [`../src/detail_page_ai/react_document_builder.py`](../src/detail_page_ai/react_document_builder.py): 승인 draft → React JSON AST 결정적 조립기

## 아키텍처

- [`architecture/ai-architecture-and-safety.md`](architecture/ai-architecture-and-safety.md): 모델·데이터 흐름·서빙 구조·평가 지표·안전성 정책 초안
- [`architecture/ai-architecture-design.md`](architecture/ai-architecture-design.md): 모델·데이터 흐름·서빙 구조 중심의 아키텍처 설계
- [`architecture/ai-evaluation-and-safety-policy.md`](architecture/ai-evaluation-and-safety-policy.md): 평가 지표·release gate·안전성 정책 초안

## 운영·모델

- [`operations/local-llm.md`](operations/local-llm.md): 로컬 LLM 실행 경로
- [`operations/local-generation-test-report.md`](operations/local-generation-test-report.md): Gemma + Flux2 Klein 4B 실제 생성 테스트 기록
- [`operations/server-memory-estimate.md`](operations/server-memory-estimate.md): 서버 메모리 예상
- [`operations/sglang-vllm-fit.md`](operations/sglang-vllm-fit.md): SGLang·vLLM 적용 검토

## 참고 자료

- [`references/product-photography.md`](references/product-photography.md): 제품 사진 생성·구도 기준
- [`superpowers/specs/`](superpowers/specs/): 설계 문서
- [`superpowers/plans/`](superpowers/plans/): 구현 계획 및 작업 기록
