# 문서 안내

프로젝트 문서는 목적별로 나눠 관리합니다.

> 2026-09-17 현재 구현 기준: FE 구조 출력의 정본은 제한형 `react_document` JSON AST이며, `page_plan`은 모델·편집·하위 호환 입력 필드입니다.
> 서버 추론은 SGLang 단일 엔진으로 텍스트 서버(`30000`)와 이미지 확산 서버(`30001`)를 띄우며, Mac 로컬 개발은 MLX Serve를 사용합니다.
> 서버 GPU에서는 아직 한 번도 실행하지 않았습니다. `hero`는 촬영 원본을 그대로 쓰는 `source_original`, 누끼는 rembg 경로를 사용하며 생성 사진의 별도 참고용 표시는 제거되었습니다.

> 2026-09-23 추가: `gallery` 블록의 사진은 모델이 아니라 **코드가 확정합니다.** 생성 디테일컷이 있으면 `page_plan`의 `photo_ids`를 무시하고 `detail`~`detail-05`로 덮어쓰며, PNG 렌더러와 `react_document` 빌더가 같은 규칙을 씁니다.
> 따라서 갤러리에 실제로 들어간 사진은 `page_plan`이 아니라 `react_document`의 `imageId` 참조로 판단합니다.

## API

- [`api/ai-dto-contract.md`](api/ai-dto-contract.md): BE↔AI 방향별 DTO와 이미지 provenance·메타데이터 전달 계약
- [`api/ai-fe-io-spec.md`](api/ai-fe-io-spec.md): BE·FE·AI 사이의 운영 및 로컬 직접 API 입출력 명세
- [`api/ai-product-content-generation-agreement.md`](api/ai-product-content-generation-agreement.md): 현재 활성 계약으로 사용하지 않는 이전 `/ai/products`·HTML block 계약 폐기 안내
- [`api/be-fe-ai-integration-spec.md`](api/be-fe-ai-integration-spec.md): BE 공개 제안과 AI 내부/직접 API의 BE·FE 연동 계약
- [`api/react-json-output-contract.md`](api/react-json-output-contract.md): FE용 `react_document` schema v2.0의 구조·렌더링·보안 계약
- [`../src/detail_page_ai/react_document.py`](../src/detail_page_ai/react_document.py): FE가 소비하는 제한형 React JSON AST DTO 구현
- [`../src/detail_page_ai/react_document_builder.py`](../src/detail_page_ai/react_document_builder.py): 승인 draft에서 React JSON AST를 결정적으로 조립하는 builder

## BE·인프라 전달 문서

> 아래 문서는 특정 팀과 주고받은 시점 기록입니다. 이후 구현이나 운영 결정이 바뀌어도 당시 요청·근거를 고치지 않습니다.

- [`api/ai-worklist-2026-09-17.md`](api/ai-worklist-2026-09-17.md): BE 협의 결과를 바탕으로 상세페이지 AI가 맡을 수정·계약 대응 작업과 차단 항목
- [`api/be-ai-integration-negotiation.md`](api/be-ai-integration-negotiation.md): BE·AI·챗봇 사이의 연동 불일치, 생성 이미지·경로·인증 합의 쟁점과 제안
- [`api/be-handoff-2026-09-17.md`](api/be-handoff-2026-09-17.md): HTTP/1.1·비동기·라우팅·재시도·AWS 주소 등 BE 코드·설정 수정 요청과 근거
- [`api/be-handoff-2026-09-18.md`](api/be-handoff-2026-09-18.md): BE 1차 반영 후 재연동 결과를 바탕으로 남은 계약·운영 결정과 수정 요청
- [`api/be-request-2026-09-17.md`](api/be-request-2026-09-17.md): 세 서비스 실측에서 찾은 BE↔AI 통신·비동기·인증·AWS 배포 문제와 요청 목록
- [`api/be-request-2026-09-18-e2e.md`](api/be-request-2026-09-18-e2e.md): 실제 BE 컨테이너 E2E에서 확인된 승인 흐름·generation ID·multipart·상태 반영 요청
- [`api/open-decisions-2026-09-17.md`](api/open-decisions-2026-09-17.md): POST /ai/products 응답, 생성 이미지 전달, 내부 인증, 경로 의미·타임아웃에 대한 공동 결정 항목
- [`operations/be-handoff-2026-09-18b.md`](operations/be-handoff-2026-09-18b.md): status_url 응답 스키마·콜백 경로·데드라인 스케줄러에 대한 BE 전달 회신
- [`operations/be-handoff-2026-09-21.md`](operations/be-handoff-2026-09-21.md): BE 경유 첫 연동에서 통과한 구간과 S3 설정·오류 응답·승인 시점 관련 요청
- [`operations/be-handoff-2026-09-22.md`](operations/be-handoff-2026-09-22.md): BE-11 승인·콜백 시점 문제와 31분 데드라인을 비교하고 선택지·결정을 요청한 문서
- [`operations/ecr-review-2026-09-17.md`](operations/ecr-review-2026-09-17.md): ECR 이미지 분리·태그·OIDC에 대한 동의와 레포 이름·CI·빌드 용량의 차단 사항
- [`operations/infra-handoff-2026-09-21.md`](operations/infra-handoff-2026-09-21.md): GitHub Actions 변수·ECR push 결과와 챗봇 모델 질문, 자원 요청을 인프라팀에 회신
- [`operations/infra-handoff-2026-09-22.md`](operations/infra-handoff-2026-09-22.md): CodeBuild·ECR 이름 변경·모델 S3 준비·GPU 검증의 적용 결과와 IAM 차단 보고
- [`operations/infra-handoff-2026-09-23.md`](operations/infra-handoff-2026-09-23.md): 모델 3종 S3 업로드 경로·SHA256SUMS 해시·검증 결과와 GPU 미검증 상태 회신
- [`operations/infra-handoff-2026-09-23b.md`](operations/infra-handoff-2026-09-23b.md): Stage 실기동 오류 회신 — 상세페이지 텍스트 서버 캐시 예산 실패 원인(동시 기동)과 수정, 챗봇 LLM 회신 항목·모델명 불일치

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
- [`evaluation/ai-safety-report-2026-09-21.md`](evaluation/ai-safety-report-2026-09-21.md): 할루시네이션·Prompt Injection·편향을 105건 실측으로 검증한 2026-09-21 시점 기록
- [`evaluation/be-ai-integration-test-2026-09-21.md`](evaluation/be-ai-integration-test-2026-09-21.md): BE를 거친 상세페이지 E2E에서 작업 제출·DRAFT_READY·콜백 경로를 확인하고 S3 설정에서 막힌 2026-09-21 기록
- [`evaluation/be-integration-test-2026-09-17.md`](evaluation/be-integration-test-2026-09-17.md): BE·AI 양방향 HTTP 연동 실패 원인과 2차 실측 정정을 남긴 2026-09-17 기록
- [`evaluation/celadon-run-2026-09-23.md`](evaluation/celadon-run-2026-09-23.md): 청자 분청 찻잔에서 생성컷 미사용과 PNG·react_document 사진 구성 불일치를 재현한 기록
- [`evaluation/container-integration-test-2026-09-17.md`](evaluation/container-integration-test-2026-09-17.md): Ubuntu 컨테이너에서 이미지 빌드·비루트·헬스체크·BE 연동 상태를 확인한 기록
- [`evaluation/generated-photo-usage-2026-09-23.md`](evaluation/generated-photo-usage-2026-09-23.md): 합죽선 매화선 두 실행에서 gallery 계획은 추가됐지만 생성컷 소비가 되지 않은 현상과 원인 기록
- [`evaluation/logs/README.md`](evaluation/logs/README.md): 2026-09-17 세 서비스 로컬 연동의 원시 로그 파일 구성과 흐름별 결과 안내
- [`evaluation/pipeline-run-2026-09-17.md`](evaluation/pipeline-run-2026-09-17.md): 상세페이지 접수부터 분석·승인·렌더까지 이미지 생성 경로를 포함해 끝까지 실행한 기록
- [`evaluation/reintegration-test-2026-09-18.md`](evaluation/reintegration-test-2026-09-18.md): BE 수정 후 컨테이너 4개를 재연동해 202 응답·DRAFT_READY·콜백·COMPLETED를 확인하고 남은 문제를 기록
- [`evaluation/three-service-integration-test-2026-09-17.md`](evaluation/three-service-integration-test-2026-09-17.md): BE·챗봇·상세페이지를 함께 기동해 HTTP/2 업그레이드·경로·상품 ID·env 문제를 실측한 기록

## 데이터·라이선스

- [`data/collection-license-cleaning-plan.md`](data/collection-license-cleaning-plan.md): CMA 실물 데이터 수집·권리 표시·라이선스 확인·정제 전략

## 운영·모델

- [`operations/aws-deployment.md`](operations/aws-deployment.md): 로컬 MLX 파이프라인을 AWS 환경으로 이관하고 1건 end-to-end 품질 게이트를 확인하는 운영 가이드
- [`operations/aws-migration-checklist.md`](operations/aws-migration-checklist.md): AWS 이관에 필요한 준비물·차단 조건·확인 방법을 정리한 실무 체크리스트
- [`operations/eks-workload-spec.md`](operations/eks-workload-spec.md): EKS 인프라팀 요청에 대한 AI 저장소 workload·자원·검증 상태 답변
- [`operations/aws-deploy-inventory.md`](operations/aws-deploy-inventory.md): EKS 반입 대상의 통합 이미지·모델 S3→PVC·단일 PVC·Secret·ConfigMap·GPU·프로브·CI 목록
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

## Phase 산출물

- [`deliverables/phase3/01-implementation-checkpoint.md`](deliverables/phase3/01-implementation-checkpoint.md): 분석·카피와 이미지·렌더링 영역의 1차 구현 상태, 파일럿 실측, 품질 게이트 체크포인트
- [`deliverables/phase3/02-error-analysis.md`](deliverables/phase3/02-error-analysis.md): 파일럿·다양성 고도화 과정의 11개 장애를 증상·원인·조치·재발 방지로 분석
- [`deliverables/phase3/03-second-experiment-report.md`](deliverables/phase3/03-second-experiment-report.md): 컷아웃·씬 분기·이미지 파라미터·1~12차 다양성 실험의 수정 전후 결과와 한계
- [`deliverables/phase3/04-inference-api.md`](deliverables/phase3/04-inference-api.md): FastAPI 서비스 API와 MLX 텍스트·비전·이미지 추론 클라이언트의 요청·응답·설정 계약
- [`deliverables/phase3/05-be-fe-interface.md`](deliverables/phase3/05-be-fe-interface.md): BE·FE·AI 작업·승인·react_document·오류·멱등성 계약을 가리키는 정본 인터페이스 산출물
- [`deliverables/phase3/README.md`](deliverables/phase3/README.md): Phase 3 제출 산출물 5종의 구성·원본 위치·문서별 역할 안내
- [`deliverables/phase4/01-ai-evaluation-report.md`](deliverables/phase4/01-ai-evaluation-report.md): 60건 종단 실행과 사진·레이아웃·테스트·BE 연동을 수치와 정성 근거로 평가
- [`deliverables/phase4/02-ai-safety-report.md`](deliverables/phase4/02-ai-safety-report.md): 할루시네이션·Prompt Injection·편향 검증 105건의 결과와 자동 사실성 방어의 한계
- [`deliverables/phase4/03-model-card-and-operations.md`](deliverables/phase4/03-model-card-and-operations.md): 텍스트·이미지·누끼·로컬 모델 카드와 L40S 단일 파드 배포·PVC·프로브·운영 가이드
- [`deliverables/phase4/README.md`](deliverables/phase4/README.md): Phase 4 평가·안전성·모델 카드 3종의 제출 원칙, 미검증 항목, 핵심 수치 안내

## 실험 기록

> 아래 실험 기록은 각 차수 당시의 구현·에러·추론 API·BE/FE 영향 사실을 보존하는 시점 기록입니다. 이후 구현이 바뀌어도 수정하지 않습니다.

- [`deliverables/experiments/`](deliverables/experiments/): Round 01~13, 총 13차 × 5종(구현 체크포인트·에러 분석·실험 리포트·추론 API·BE/FE 인터페이스) 65개 기록

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
