# Phase 4 — 평가·운영

과정의 **산출물 제출 목록(생성형 AI)** 을 기준으로 **이미 있는 문서**를 배치했습니다. 이 Phase 를 위해 새로 쓴 문서는 없습니다.

- **성격** — `상시`: 현재 상태를 설명하며 갱신합니다 / `시점`: 날짜가 붙은 당시 기록이라 고치지 않습니다 / `보관`: 대체·폐기된 이력입니다

## 제출 산출물과 해당 문서

| # | 제출 산출물 | 해당 문서 |
| --- | --- | --- |
| 4-1 | AI 기능 평가 보고서: 정량 평가 + 정성 평가 + 비교표 | [`submission/01`](submission/01-ai-evaluation-report.md) (2절 정량, 3절 정성, 4절 비교표), 근거는 [`evaluation/`](evaluation/) |
| 4-2 | AI 안전성 검증 보고서: 할루시네이션·Prompt Injection·편향 검증 | [`submission/02`](submission/02-ai-safety-report.md), 근거는 [`evaluation/ai-safety-report-2026-09-21.md`](evaluation/ai-safety-report-2026-09-21.md) |
| 4-3 | 모델 카드 및 운영 가이드 | [`submission/03`](submission/03-model-card-and-operations.md), 배포·운영 가이드는 [`operations/`](operations/), 인프라 전달은 [`infra-handoffs/`](infra-handoffs/) |

## 폴더 구성

| 폴더 | 담긴 것 |
| --- | --- |
| [`submission/`](submission/) | 제출본 3종과 제출 원칙·미검증 항목 안내 |
| [`evaluation/`](evaluation/) | 평가·안전성 검증 기록과 근거 데이터(JSON·이미지) |
| [`operations/`](operations/) | 배포·운영 가이드 |
| [`infra-handoffs/`](infra-handoffs/) | 인프라팀과 주고받은 전달 기록 |

### 제출본 3종

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`submission/01-ai-evaluation-report.md`](submission/01-ai-evaluation-report.md) | 60건 종단 실행과 사진·레이아웃·테스트·BE 연동을 수치와 정성 근거로 평가 | 시점 |
| [`submission/02-ai-safety-report.md`](submission/02-ai-safety-report.md) | 할루시네이션·Prompt Injection·편향 검증 105건의 결과와 자동 사실성 방어의 한계 | 시점 |
| [`submission/03-model-card-and-operations.md`](submission/03-model-card-and-operations.md) | 텍스트·이미지·누끼·로컬 모델 카드와 L40S 단일 파드 배포·PVC·프로브·운영 가이드 | 시점 |
| [`submission/README.md`](submission/README.md) | Phase 4 평가·안전성·모델 카드 3종의 제출 원칙, 미검증 항목, 핵심 수치 안내 | 상시 |

### 평가·검증 기록

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`evaluation/ai-safety-report-2026-09-21.md`](evaluation/ai-safety-report-2026-09-21.md) | 할루시네이션·Prompt Injection·편향을 105건 실측으로 검증한 2026-09-21 시점 기록 | 시점 |
| [`evaluation/celadon-run-2026-09-23.md`](evaluation/celadon-run-2026-09-23.md) | 청자 분청 찻잔에서 생성컷 미사용과 PNG·react_document 사진 구성 불일치를 재현한 기록 | 시점 |
| [`evaluation/cutout-ground-truth.md`](evaluation/cutout-ground-truth.md) | 누끼 ground-truth 기준 시점 기록 | 시점 |
| [`evaluation/cutout-regression-baseline.md`](evaluation/cutout-regression-baseline.md) | 누끼 회귀 기준선 시점 기록 | 시점 |
| [`evaluation/full60-runs.md`](evaluation/full60-runs.md) | 60건 전체 평가 실행 시점 기록 | 시점 |
| [`evaluation/generated-photo-usage-2026-09-23.md`](evaluation/generated-photo-usage-2026-09-23.md) | 합죽선 매화선 두 실행에서 gallery 계획은 추가됐지만 생성컷 소비가 되지 않은 현상과 원인 기록 | 시점 |

### 배포·운영 가이드

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`operations/aws-deploy-inventory.md`](operations/aws-deploy-inventory.md) | EKS 반입 대상의 통합 이미지·모델 S3→PVC·단일 PVC·Secret·ConfigMap·GPU·프로브·CI 목록 | 상시 |
| [`operations/aws-deployment.md`](operations/aws-deployment.md) | 로컬 MLX 파이프라인을 AWS 환경으로 이관하고 1건 end-to-end 품질 게이트를 확인하는 운영 가이드 | 상시 |
| [`operations/aws-migration-checklist.md`](operations/aws-migration-checklist.md) | AWS 이관에 필요한 준비물·차단 조건·확인 방법을 정리한 실무 체크리스트 | 상시 |
| [`operations/eks-workload-spec.md`](operations/eks-workload-spec.md) | EKS 인프라팀 요청에 대한 AI 저장소 workload·자원·검증 상태 답변 | 상시 |
| [`operations/local-llm.md`](operations/local-llm.md) | Mac 로컬 MLX Serve 기반 상세페이지 LLM 실행 경로와 출력 규칙 | 상시 |
| [`operations/security-response-2026-09-30.md`](operations/security-response-2026-09-30.md) | 사이버 보안팀 보안조치요구서(SAST F-1·F-3·F-4·F-7, SCA 21건)에 대한 확인 근거·조치·재검 결과 회신 | 시점 |
| [`operations/server-memory-estimate.md`](operations/server-memory-estimate.md) | Apple Silicon 로컬 MLX 통합 메모리 예상과 서버 메모리 문서 참조 | 상시 |
| [`operations/sglang-serving-research.md`](operations/sglang-serving-research.md) | AWS g6e.xlarge 한 장의 L40S에서 텍스트·확산 SGLang 2프로세스를 공존시키기 위한 운영 조사 | 시점 |
| [`operations/ubuntu-deployment.md`](operations/ubuntu-deployment.md) | Ubuntu g6e.xlarge에서 detail-page-ai와 SGLang 2개 추론 서버를 Docker Compose로 배포하는 가이드 | 상시 |

### 인프라 전달 기록

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`infra-handoffs/ecr-review-2026-09-17.md`](infra-handoffs/ecr-review-2026-09-17.md) | ECR 이미지 분리·태그·OIDC에 대한 동의와 레포 이름·CI·빌드 용량의 차단 사항 | 시점 |
| [`infra-handoffs/infra-handoff-2026-09-21.md`](infra-handoffs/infra-handoff-2026-09-21.md) | GitHub Actions 변수·ECR push 결과와 챗봇 모델 질문, 자원 요청을 인프라팀에 회신 | 시점 |
| [`infra-handoffs/infra-handoff-2026-09-22.md`](infra-handoffs/infra-handoff-2026-09-22.md) | CodeBuild·ECR 이름 변경·모델 S3 준비·GPU 검증의 적용 결과와 IAM 차단 보고 | 시점 |
| [`infra-handoffs/infra-handoff-2026-09-23.md`](infra-handoffs/infra-handoff-2026-09-23.md) | 모델 3종 S3 업로드 경로·SHA256SUMS 해시·검증 결과와 GPU 미검증 상태 회신 | 시점 |
| [`infra-handoffs/infra-handoff-2026-09-23b.md`](infra-handoffs/infra-handoff-2026-09-23b.md) | Stage 실기동 오류 회신 — 상세페이지 텍스트 서버 캐시 예산 실패 원인(동시 기동)과 수정, 챗봇 LLM 회신 항목·모델명 불일치 | 시점 |
