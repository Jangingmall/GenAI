# Phase 3 — 구현·실험

과정의 **산출물 제출 목록(생성형 AI)** 을 기준으로 **이미 있는 문서**를 배치했습니다. 이 Phase 를 위해 새로 쓴 문서는 없습니다.

- **성격** — `상시`: 현재 상태를 설명하며 갱신합니다 / `시점`: 날짜가 붙은 당시 기록이라 고치지 않습니다 / `보관`: 대체·폐기된 이력입니다

## 제출 산출물과 해당 문서

| # | 제출 산출물 | 해당 문서 |
| --- | --- | --- |
| 3-1 | AI 영역 1·2 1차 구현 코드·체크포인트 | [`submission/01`](submission/01-implementation-checkpoint.md), 코드는 [`src/`](../../src/) |
| 3-2 | 에러 분석 + 2차 실험 보고서 (개선 가설·결과) | [`submission/02`](submission/02-error-analysis.md), [`submission/03`](submission/03-second-experiment-report.md), 근거는 [`experiments/`](experiments/)·[`runs/`](runs/) |
| 3-3 | 추론 API 구성 코드 + BE/FE 통합 인터페이스 명세서 | [`submission/04`](submission/04-inference-api.md), [`submission/05`](submission/05-be-fe-interface.md), 정본 계약은 [`api/`](api/), BE 협의는 [`be-handoffs/`](be-handoffs/) |

## 폴더 구성

| 폴더 | 담긴 것 |
| --- | --- |
| [`submission/`](submission/) | 제출본 5종과 구성 안내 |
| [`originals/`](originals/) | 제출본의 원본 |
| [`api/`](api/) | BE·FE·AI 연동 정본 계약 (현재 계약) |
| [`runs/`](runs/) | 구현 중 실행·연동 테스트 기록과 원시 로그 |
| [`be-handoffs/`](be-handoffs/) | BE 와 주고받은 협의·전달 기록 |
| [`experiments/`](experiments/) | 1~13차 실험 기록 (차수마다 5종) |

### 제출본 5종

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`submission/01-implementation-checkpoint.md`](submission/01-implementation-checkpoint.md) | 분석·카피와 이미지·렌더링 영역의 1차 구현 상태, 파일럿 실측, 품질 게이트 체크포인트 | 시점 |
| [`submission/02-error-analysis.md`](submission/02-error-analysis.md) | 파일럿·다양성 고도화 과정의 11개 장애를 증상·원인·조치·재발 방지로 분석 | 시점 |
| [`submission/03-second-experiment-report.md`](submission/03-second-experiment-report.md) | 컷아웃·씬 분기·이미지 파라미터·1~12차 다양성 실험의 수정 전후 결과와 한계 | 시점 |
| [`submission/04-inference-api.md`](submission/04-inference-api.md) | FastAPI 서비스 API와 MLX 텍스트·비전·이미지 추론 클라이언트의 요청·응답·설정 계약 | 시점 |
| [`submission/05-be-fe-interface.md`](submission/05-be-fe-interface.md) | BE·FE·AI 작업·승인·react_document·오류·멱등성 계약을 가리키는 정본 인터페이스 산출물 | 시점 |
| [`submission/README.md`](submission/README.md) | Phase 3 제출 산출물 5종의 구성·원본 위치·문서별 역할 안내 | 상시 |

### 제출본의 원본

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`originals/01-implementation-checkpoint.md`](originals/01-implementation-checkpoint.md) | AI 영역 1·2의 1차 구현 체크포인트와 근거 산출물 기준 | 시점 |
| [`originals/02-error-analysis.md`](originals/02-error-analysis.md) | 상세페이지 AI 시스템 개발·평가 과정의 에러 분석 보고서 | 시점 |
| [`originals/03-second-experiment-report.md`](originals/03-second-experiment-report.md) | 1차 파일럿 결함을 수정한 2차 실험과 재검증 결과 | 시점 |
| [`originals/04-inference-api.md`](originals/04-inference-api.md) | 서비스 API와 텍스트·비전·이미지 모델 추론 API의 층별 구성 | 시점 |
| [`originals/05-be-fe-interface.md`](originals/05-be-fe-interface.md) | BE/FE 통합 인터페이스 정본 문서를 가리키는 canonical link stub | 상시 |

### API·연동 계약

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`api/ai-dto-contract.md`](api/ai-dto-contract.md) | BE↔AI 방향별 DTO와 이미지 provenance·메타데이터 전달 계약 | 상시 |
| [`api/ai-fe-io-spec.md`](api/ai-fe-io-spec.md) | BE·FE·AI 사이의 운영 및 로컬 직접 API 입출력 명세 | 상시 |
| [`api/be-fe-ai-integration-spec.md`](api/be-fe-ai-integration-spec.md) | BE 공개 제안과 AI 내부/직접 API의 BE·FE 연동 계약 | 상시 |
| [`api/react-json-output-contract.md`](api/react-json-output-contract.md) | FE용 `react_document` schema v2.0의 구조·렌더링·보안 계약 | 상시 |

### 구현 중 실행·검토 기록

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`runs/ai-review-2026-09-10.md`](runs/ai-review-2026-09-10.md) | 2026-09-10 AI 검토 시점 기록 | 시점 |
| [`runs/be-ai-integration-test-2026-09-21.md`](runs/be-ai-integration-test-2026-09-21.md) | BE를 거친 상세페이지 E2E에서 작업 제출·DRAFT_READY·콜백 경로를 확인하고 S3 설정에서 막힌 2026-09-21 기록 | 시점 |
| [`runs/be-integration-test-2026-09-17.md`](runs/be-integration-test-2026-09-17.md) | BE·AI 양방향 HTTP 연동 실패 원인과 2차 실측 정정을 남긴 2026-09-17 기록 | 시점 |
| [`runs/container-integration-test-2026-09-17.md`](runs/container-integration-test-2026-09-17.md) | Ubuntu 컨테이너에서 이미지 빌드·비루트·헬스체크·BE 연동 상태를 확인한 기록 | 시점 |
| [`runs/copy-analysis-2026-09-09.md`](runs/copy-analysis-2026-09-09.md) | 파일럿 1차 6건 생성 카피의 사실 근거성 분석과 프롬프트 개선 후보 기록 | 시점 |
| [`runs/local-generation-test-report.md`](runs/local-generation-test-report.md) | 로컬 상세페이지 생성 smoke test 구성·실행 결과와 미완료 정량 평가 상태 | 시점 |
| [`runs/logs/README.md`](runs/logs/README.md) | 2026-09-17 세 서비스 로컬 연동의 원시 로그 파일 구성과 흐름별 결과 안내 | 시점 |
| [`runs/pilot-report-2026-09-09.md`](runs/pilot-report-2026-09-09.md) | CMA real v1 카테고리별 6건 대상 1차 파일럿 실행 결과와 결함 분석 기록 | 시점 |
| [`runs/pipeline-run-2026-09-17.md`](runs/pipeline-run-2026-09-17.md) | 상세페이지 접수부터 분석·승인·렌더까지 이미지 생성 경로를 포함해 끝까지 실행한 기록 | 시점 |
| [`runs/reintegration-test-2026-09-18.md`](runs/reintegration-test-2026-09-18.md) | BE 수정 후 컨테이너 4개를 재연동해 202 응답·DRAFT_READY·콜백·COMPLETED를 확인하고 남은 문제를 기록 | 시점 |
| [`runs/three-service-integration-test-2026-09-17.md`](runs/three-service-integration-test-2026-09-17.md) | BE·챗봇·상세페이지를 함께 기동해 HTTP/2 업그레이드·경로·상품 ID·env 문제를 실측한 기록 | 시점 |

### BE 협의·전달 기록

| 문서 | 내용 | 성격 |
| --- | --- | --- |
| [`be-handoffs/ai-worklist-2026-09-17.md`](be-handoffs/ai-worklist-2026-09-17.md) | BE 협의 결과를 바탕으로 상세페이지 AI가 맡을 수정·계약 대응 작업과 차단 항목 | 시점 |
| [`be-handoffs/be-handoff-2026-09-17.md`](be-handoffs/be-handoff-2026-09-17.md) | HTTP/1.1·비동기·라우팅·재시도·AWS 주소 등 BE 코드·설정 수정 요청과 근거 | 시점 |
| [`be-handoffs/be-handoff-2026-09-18.md`](be-handoffs/be-handoff-2026-09-18.md) | BE 1차 반영 후 재연동 결과를 바탕으로 남은 계약·운영 결정과 수정 요청 | 시점 |
| [`be-handoffs/be-handoff-2026-09-18b.md`](be-handoffs/be-handoff-2026-09-18b.md) | status_url 응답 스키마·콜백 경로·데드라인 스케줄러에 대한 BE 전달 회신 | 시점 |
| [`be-handoffs/be-handoff-2026-09-21.md`](be-handoffs/be-handoff-2026-09-21.md) | BE 경유 첫 연동에서 통과한 구간과 S3 설정·오류 응답·승인 시점 관련 요청 | 시점 |
| [`be-handoffs/be-handoff-2026-09-22.md`](be-handoffs/be-handoff-2026-09-22.md) | BE-11 승인·콜백 시점 문제와 31분 데드라인을 비교하고 선택지·결정을 요청한 문서 | 시점 |
| [`be-handoffs/be-handoff-2026-09-29.md`](be-handoffs/be-handoff-2026-09-29.md) | 승인 재요청 409·콜백 재시도 규칙·BE-11 정리와 승인 타임아웃 300초 확인을 BE 코드 대조로 전달한 문서 | 시점 |
| [`be-handoffs/be-request-2026-09-18-e2e.md`](be-handoffs/be-request-2026-09-18-e2e.md) | 실제 BE 컨테이너 E2E에서 확인된 승인 흐름·generation ID·multipart·상태 반영 요청 | 시점 |
| [`be-handoffs/open-decisions-2026-09-17.md`](be-handoffs/open-decisions-2026-09-17.md) | POST /ai/products 응답, 생성 이미지 전달, 내부 인증, 경로 의미·타임아웃에 대한 공동 결정 항목 | 시점 |

### 실험 기록 — 13차 × 5종

각 차수 폴더에 구현 체크포인트·에러 분석·실험 리포트·추론 API·BE/FE 인터페이스 5종이 있습니다. 모두 `시점` 기록입니다.

| 차수 | 내용 |
| --- | --- |
| [1차](experiments/round-01/) | validation 블록 패딩 제거 실험과 API·인터페이스 영향 |
| [2차](experiments/round-02/) | 프롬프트 순서 신호 제거 실험 |
| [3차](experiments/round-03/) | 블록별 근거·생략 조건 도입 실험 |
| [4차](experiments/round-04/) | 레이아웃 원형 예시 주입 실험 |
| [5차](experiments/round-05/) | 코드가 원형을 정하고 모델이 카피를 쓰는 실험 |
| [6차](experiments/round-06/) | variant 강제 배정 해제·CSS 4종 구현 |
| [7차](experiments/round-07/) | 원형 variant를 프롬프트로 전달 |
| [8차](experiments/round-08/) | 카탈로그 빈도와 다양성 합격 기준 수정 |
| [9차](experiments/round-09/) | 상품 근거로 원형 후보를 선택하는 실험 |
| [10차](experiments/round-10/) | 당시 생성컷 라벨 계약 수정과 60건 1차 실행 |
| [11차](experiments/round-11/) | 컷아웃 게이트 감사 채택·추출기 수정 되돌림 |
| [12차](experiments/round-12/) | hero 원본 고정·rembg 채택·화면 라벨 제거 |
| [13차](experiments/round-13/) | 생성컷 자리 확보·다양성 기준선 정정 |
