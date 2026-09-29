# 평가 지표 정의서

상태: 2026-09-09 갱신 (초안). 아래 수치는 측정된 성능이 아닌 제안 목표다.
현재 데이터는 실제 공개 이미지 `cma_real_v1`과 기존 통합 fixture를 분리해 관리한다.
2026-09-09에 `cma_real_v1` 6개 카테고리 각 1건(총 6건) 파일럿 실행을 완료했다 ([파일럿 보고서](../phase3/runs/pilot-report-2026-09-09.md), 2026-09-09).
이후 10차에서 같은 입력군의 60건 모델 실행을 60/60건 완료했다 ([10차 실험 보고서](../phase3/experiments/round-10/03-experiment-report.md), 2026-09-11).
자세한 파일럿 실행 기록과 결함 분석은 [2026-09-09 파일럿 평가 1차 실행 결과 보고서](../phase3/runs/pilot-report-2026-09-09.md)를 참고한다.
2026-09-08에 기록된 4B 생성 2건은 pipeline smoke test이며 정량 평가 결과가 아니다 ([로컬 생성 테스트 기록](../phase3/runs/local-generation-test-report.md), 2026-09-08).
FE 구조 출력은 제한형 `react_document` JSON AST를 기준으로 평가하고, `page_plan`은 모델·편집·하위 호환 입력으로만 집계한다.

## 1. 영역과 집계

| 영역 | 1차 목표 | 현재 데이터·실행 상태 | 판정 |
|---|---:|---:|---|
| 분석·카피 | 60 | `cma_real_v1` 분석 입력 60; 파일럿 6건 완료 ([파일럿 보고서](../phase3/runs/pilot-report-2026-09-09.md), 2026-09-09); 10차에서 60건 전수 실행 ([10차 실험 보고서](../phase3/experiments/round-10/03-experiment-report.md), 2026-09-11) | 모델 실행 60/60건 완료 ([10차 실험 보고서](../phase3/experiments/round-10/03-experiment-report.md), 2026-09-11) |
| 이미지·렌더링 | 60 | `cma_real_v1` 렌더링 입력 60; 파일럿 6건 완료 ([파일럿 보고서](../phase3/runs/pilot-report-2026-09-09.md), 2026-09-09); 10차에서 이미지 생성 포함 60건 전수 실행 ([10차 실험 보고서](../phase3/experiments/round-10/03-experiment-report.md), 2026-09-11) | 모델 실행 60/60건 완료 ([10차 실험 보고서](../phase3/experiments/round-10/03-experiment-report.md), 2026-09-11) |
| API·상태·안전 | 60 | 기존 fixture 60(초안 42/저장 9/승인 9); 전용 set 없음 | 전용 50건 미확보 |

구조 출력 계약은 모든 영역의 공통 자동 gate로 적용한다. `react_document`의 유효성은 별도
신규 상품 수를 늘리는 지표가 아니라 각 실행 결과의 출력 계약 검사로 집계한다.

영역별 건수는 고유 입력/요청 시퀀스 기준이다. 동일 사례의 여러 지표 측정은 사례 수를 늘리지 않는다.
기존 3개 상품 반복 fixture를 독립 상품 60건으로 보고하지 않는다. `cma_real_v1`은
60개 실물 object로 구성된 별도 평가 입력이며, 6개 카테고리 각 10건이다.
`cma_real_v1`의 모델 실행은 10차에 60/60건 완료됐다 ([10차 실험 보고서](../phase3/experiments/round-10/03-experiment-report.md), 2026-09-11).
권리 최종 확인은 마지막 데이터 점검에서 대기 상태로 기록됐으며, 이후 승인 근거는 확인 필요다 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08).
사람 정답 라벨도 당시 승인 대기였고, 이후 완료 근거는 확인 필요다 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08).
사람 검수 점수는 수집되지 않았으므로, 60건 실행 성공을 사람 평가 성능이나 게시 승인으로 해석하지 않는다 ([Phase 4 기능 평가](../phase4/submission/01-ai-evaluation-report.md), 2026-09-22).

### 2026-09-08 당시 smoke test 기록 ([로컬 생성 테스트 기록](../phase3/runs/local-generation-test-report.md), 2026-09-08)

최근 `Gemma 12B + Flux2 Klein 4B` 조합으로 2건을 실행했다. `숨의잔`은 10섹션·774×4,341,
부채는 10섹션·774×4,202로 생성됐으며 각각 Flux 생성 참고 컷 5장을 포함한다. 이 두 건은
모델 비교·정량 metric의 분모가 아니라 endpoint, provenance, fallback 동작을 확인한 기록이다.
자세한 파일과 판정은 [로컬 생성 테스트 기록](../phase3/runs/local-generation-test-report.md)을 따른다.

## 2. 지표 정의

| 지표 | 분자 / 분모 또는 측정 구간 | 초기 목표 |
|---|---|---|
| 상품 분류 정확도 | 검수 라벨과 일치한 상품 / 검수 완료 상품 | ≥90% |
| 공예 precision | 맞게 공예로 분류한 상품 / 공예로 예측한 상품 | ≥95% |
| 근거 주장 precision | 근거가 확인된 주장 / 검수한 전체 사실 주장 | ≥95% |
| 미확인 주장률 | 근거 없는 주장 / 검수한 전체 사실 주장 | ≤2% |
| 입력 유지율 | 의미가 보존된 입력 사실 / 제공된 유효 입력 사실 | 100% |
| 입력 provenance 기록률 | 이미지 관찰·`user_hints` 근거가 연결된 적용 사실 / 적용 사실 전체 | ≥95% |
| 원본 hash 일치율 | 일치 source 자산 / 전체 source 자산 | 100% |
| crop 일치율 | 원본 정수 crop과 decode 픽셀이 같은 자산 / source_crop 자산 | 100% |
| 합성 fidelity | 선언된 변환 검증 통과 자산 / source_composite 자산<br>*(주의: 선언된 변환 적용 여부만 보며 마스크 품질을 보지 않으므로, 컷아웃 원본 보존율과 함께 봐야 한다.)* | 100% |
| 컷아웃 원본 보존율 | 산출물 비배경(ink) 픽셀 비율 / 원본 비배경 픽셀 비율 (`scripts/check_cutout_fidelity.py`) | 건당 >0.6 (OK 판정, 심각 손실 <0.25 0건) |
| 씬 분기 적합률 | 기대 분기와 일치한 케이스 / 판정한 케이스 (`scripts/check_scene_direction_coverage.py`) | 100% (오분류 0건) |
| 거절 자산 누출률 | renderer/응답/적재에 유입된 거절 자산 / 주입한 거절 자산 | 0% |
| 섹션 완전율 | 필수 순서·블록·링크를 충족한 출력 / 렌더 평가 출력 | 100% |
| React schema validity | `ReactDetailPageDocumentDto` 검증을 통과한 문서 / `react_document` 생성 문서 | 100% |
| React tree safety | 허용 태그·부모/자식 관계·고유 ID·깊이/노드 제한을 모두 통과한 문서 / 생성 문서 | 100% |
| React alias serialization | FE 계약의 camelCase 키(`schemaVersion`, `canvasWidth`, `imageId` 등)가 보존된 JSON / 직렬화 JSON | 100% |
| image reference resolution | 모든 `img.props.imageId`가 photos/asset manifest에 해석되는 이미지 참조 / 전체 이미지 참조 | 100% |
| executable field leakage | HTML/JSX/script/event/raw CSS/`dangerouslySetInnerHTML` 필드가 유입된 문서 / 전체 문서 | 0% |
| 생성 참고 표시율 | 라벨·provenance가 있는 참고 자산 / 생성 참고 자산 | 100% |
| 멱등 재사용률 | 결과 ID 동일·추가 생성 없는 순차 재전송 / 순차 재전송 시험 | 100% |
| 저장 무생성률 | 모델·PNG 호출 0인 저장 / 저장 시험 | 100% |
| 인젝션 방어율 | 정책 변경·비밀 노출 없는 사례 / 공격 사례 | 100% |
| 작업 성공률 | 기한 내 재시도 후 성공 / 정상 유효 입력 작업 | ≥99%, 운영 목표 |
| BE 적재 성공률 | 기한 내 ACK 확인 / 적재 대상 generation | ≥99.5%, 운영 목표 |
| 지연 p50/p95 | 초안 접수→DRAFT_READY; 승인 접수→PNG 각각 측정 | 부하 측정 후 확정 |
| 완료당 비용 | 실패·재시도 포함 총 비용 / 완료 작업 수 | 예산 승인 후 확정 |

분모 0은 N/A로 기록한다. 실패·timeout은 결과표에서 제거하지 않고 실패 수와 검열된 지연을 별도 보고한다.
동시 승인 멱등성은 순차 재전송과 별도 측정하며 현재 보장된 것으로 간주하지 않는다.
GENERATED 자산에는 원본 crop 픽셀 동일 지표를 적용하지 않고 사람의 형태·색·구성품 검수를 적용한다.
합성 fidelity는 선언된 변환이 그대로 적용됐는지만 검증하며 마스크 자체의 품질(제품 누끼 정확도)을 보지 않는다. 따라서 마스크 결함으로 인한 제품 본체 소실 여부는 '컷아웃 원본 보존율' 지표와 함께 교차 검증해야 한다.

## 3. 사람 검수와 통계

사실성·명료성·상품성·시각 품질을 각각 1~5점 평가한다.
1은 사용 불가, 3은 상당한 수정 필요, 5는 수정 없이 사용 가능한 수준이다. 평균 목표는 4.0 이상.
검수자 2인의 독립 점수, 의견 차이와 합의 결과를 보존한다. 미검수는 정답으로 사용하지 않는다.
상품별 macro 평균과 전체 micro 평균, 표본 수, 비율의 95% Wilson 구간을 함께 보고한다.
기존 3개 상품 반복 fixture와 현재 60개 공개 이미지 입력만으로 운영 99~99.5% 신뢰성을 입증할 수 없다.

## 4. 결과 저장과 배포 판정

실행별 run_id, case_id, dataset_hash/version, code_revision, provider/model, prompt_version,
started_at, ended_at, retry_count, result_path/hash, `react_document` schema/hash 또는
`react_document.json` 경로, metric numerator/denominator/value,
error_code, reviewer/review_status를 저장한다. 키·원본 본문은 로그에 남기지 않는다.

P0/P1 위반 1건, 거절 자산 누출, 승인 전 게시, 근거 없는 핵심 인증/진품성 주장은 배포 차단 조건이다.
평균 점수로 상쇄하지 않는다. 성능 수치 목표와 배포 판정은 담당자의 승인을 받아 확정한다.

## 5. 남은 데이터 작업

`cma_real_v1`의 최종 권리 확인은 마지막 데이터 점검에서 대기 상태로 기록됐으며, 이후 완료 근거는 확인 필요다 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08).
사람 정답 라벨 승인도 당시 대기 상태였으며, 이후 완료 근거는 확인 필요다 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08).
모델 실행은 10차에서 60/60건 완료됐고 결과는 Phase 4 기능 평가 보고서에 정리됐다 ([10차 실험 보고서](../phase3/experiments/round-10/03-experiment-report.md), 2026-09-11; [Phase 4 기능 평가](../phase4/submission/01-ai-evaluation-report.md), 2026-09-22).
사람 검수 점수는 수집되지 않았다 ([Phase 4 기능 평가](../phase4/submission/01-ai-evaluation-report.md), 2026-09-22).
API·상태·안전 영역은 별도 고유 요청 50건 이상을 추가해야 한다 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08).
기존 [60건 fixture](../../data/evaluation/detail_page_eval_60.jsonl)는
스키마·회귀 준비에 사용하고, 공개 이미지 [CMA real v1](../../data/evaluation/cma_real_v1/README.md)은
분석·렌더링 평가 입력으로 사용한다.
