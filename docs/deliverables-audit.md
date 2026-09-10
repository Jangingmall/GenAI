# 산출물 점검 결과

점검일: 2026-09-09. 코드·문서 정적 대조, 평가 데이터 경로/SHA-256 검증, 로컬 모델 smoke test와 6건 파일럿 실행 결과 기준.
실제 상품 BE 공개 배포, 권리 담당자 승인, 정량 평가와 사람 2인 검수까지 완료했다는 의미는 아니다.

| 산출물 | 최신 판정 | 조치 / 남은 조건 |
|---|---|---|
| BE/FE 통합 인터페이스 | 부분 충족 | 내부 구현 경로와 공개 계약 제안을 구분했고, draft·최종 결과·BE 적재에 제한형 `react_document`를 구현했다. 공개 URL·인증·실제 BE 흐름 합의가 남아 있다. |
| React JSON FE 출력 | 구현 충족(연동 대기) | `schemaVersion: 2.0`, 허용 태그·props·트리 검증, `imageId` 자산 참조, camelCase 직렬화, FE/BE 전달·로컬 `react_document.json` 저장을 구현했다. FE 컴포넌트 renderer와 상품 BE 저장 schema 연동 검증이 남아 있다. |
| 수집 계획·라이선스 점검 | 부분 충족 | CMA Open Access 실물 60점 snapshot과 CC0 표시·hash를 확보했다. 직접 제공 자산의 권리 증빙과 사람 검수는 미완료다. |
| 정제 전략 | 부분 충족 | 원본 보존·중복·split·provenance·격리 전략과 dataset validation을 반영했다. 라벨 gold 승인은 남아 있다. |
| 영역별 평가셋 50~200건 | 부분 충족 | `cma_real_v1`은 분석 60·렌더링 준비 60건이다. 이 중 6건 파일럿의 실제 모델 실행은 완료했지만 60건 전체 실행과 API·상태·안전 전용 50건 이상 평가는 아직 없다. |
| 평가 지표 정의 | 부분 충족 | 분모·N/A·실패·사람 검수·로컬 모델/생성 자산 기준과 6건 파일럿 실측 결과를 정리했다. 컷아웃 보존율·씬 분기 회귀 gate를 추가했으며 60건 전체와 사람 검수는 미완료다. |
| AI 아키텍처 다이어그램 | 충족(로컬 기준) | Qwen3.8 27B + Flux2 Klein 9B 기본 구조와 4B 임시 검증 endpoint를 분리해 기록했다. 운영 확장은 별도 검증 대상이다. |
| 안전성 정책 초안 | 부분 충족·배포 차단 조건 5 미해결 | 원본 보존 자산과 `GENERATED` 참고 자산을 구분했지만, 6건 최종 렌더에 생성 참고 컷의 `참고용` 표시가 없어 게시 gate를 충족하지 못했다. 사람 검수와 라벨 렌더 수정이 남아 있다. |

## 최신 실행 증거

| 항목 | 결과 |
|---|---|
| Python 회귀 테스트 | `236 passed`, Pillow deprecation warning 140건 |
| 실제 평가 데이터 | `cma_real_v1`: 60개 실물, 6개 카테고리 각 10개, 분석/렌더링 JSONL 각 60건. 파일·decode·hash·라이선스 표시 검증은 통과했으며 60건 전체 모델 실행과 사람 라벨 검수는 pending |
| 기본 로컬 모델 설정 | 텍스트·비전·한국어 카피 `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`, 이미지 `mlx-community/flux2-klein-9b-4bit`, `PROMPT_VERSION=local-mlx-qwen-flux-v1` |
| 1차 파일럿 평가 | 6건 전건 성공. React schema validity, tree safety, alias serialization 각 6/6 PASS, imageId 해석 48/48 PASS, 원본 SHA-256 일치 6/6 PASS, executable field 누출 0건 |
| 파일럿 후속 회귀 gate | 기존 파일럿에서 컷아웃 제품 소실 2건(textile 0.2624, ceramic 0.0324)이 확인되어 `scripts/check_cutout_fidelity.py`와 `scripts/check_scene_direction_coverage.py`를 추가했다. 상세 수치와 기록은 [1차 파일럿 평가 보고서](evaluation/pilot-report-2026-09-09.md)에 있다. |
| 숨의잔 4B smoke | 10섹션, 774×4,341, Flux 생성 참고 컷 5장, 원본 역할 3장은 fallback |
| 부채 4B smoke | 10섹션, 774×4,202, Flux 생성 참고 컷 5장, 원본 역할 3장은 `VERIFIED` |
| Flux2 Klein 4B endpoint | 전용 로컬 11235의 `/v1/images/generations`가 `200`과 `b64_json`을 반환 |

상세 실행 기록은 [로컬 생성 테스트 기록](operations/local-generation-test-report.md)과 [1차 파일럿 평가 보고서](evaluation/pilot-report-2026-09-09.md)에서 확인한다.
생성 참고 컷은 품질 smoke 증거이며 상품 사실·정량 평가의 gold label이 아니다.

## 근거와 중요 차이

- `src/detail_page_ai/app.py`: 로컬 Qwen/Flux adapter만 구성하며 외부 provider를 import하지 않는다.
- `src/detail_page_ai/react_document.py`·`react_document_builder.py`: 승인 draft에서 제한형 React JSON AST를 조립·검증한다. 모델 출력이 임의 HTML/JSX/CSS로 직접 전달되지 않는다.
- `src/detail_page_ai/backend_client.py`: AI→상품 BE metadata를 camelCase alias로 JSON 직렬화한다.
- `src/local_detail_page_ai/runner.py`: 로컬 실행 결과에 `react_document.json`을 저장한다.
- `src/detail_page_ai/source_photos.py`: `SolidBackgroundCutoutExtractor`가 테두리에서 4-이웃 flood fill로 연결된 배경만 마스킹하며, 추출 실패 시 원본 사진으로 fallback한다. `GENERATED` 참고 자산을 허용하지만 원본 hash 연결은 제품 형태 동일의 증명이 아니다.
- `src/local_detail_page_ai/adapters.py`: 이미지와 상품 BE `user_hints`만으로 `ProductProfileDto`를 생성한다.
- `data/evaluation/cma_real_v1/validation-report.json`: 60개 원본의 파일·hash·decode·license 표시 검증 결과.
- `data/evaluation/detail_page_eval_60.jsonl`: 3상품 기반 기존 통합 fixture(초안 42/저장 9/승인 9)이며 독립 성능셋이 아니다.

`cma_real_v1`과 기존 fixture를 합쳐서 독립 상품 120건 또는 상용 성능으로 보고하지 않는다.
미검수 라벨을 정답으로 확정하거나 crop을 독립 상품·새 촬영 구도로 세지 않는다.

## 완료를 위한 후속 조건

1. 권리 담당자: 직접 제공 원본의 내부 평가·학습·재배포 범위 증빙 확인.
2. 데이터/MD: CMA 레코드의 카테고리·시리즈·시각 사실 라벨을 2인 검수하고 dataset version 발행.
3. BE/FE: 공개 경로·인증·오류 envelope 합의 및 실제 사용자 흐름 검증.
4. 평가 담당자: `cma_real_v1` 전체 실행, numerator/denominator, 실패, 사람 점수 기록.
5. 운영 담당자: 4B를 기본 모델로 승격할지 9B 기본값을 유지할지 동일 조건 benchmark로 결정.
6. FE/BE: `react_document` schema v2.0 renderer·자산 manifest·저장/조회 호환성 검증과 `page_plan` 하위 호환 종료 시점을 합의.
7. 배포 gate: `generated_scene`/`generated_view`가 최종 고객 화면에 `참고용`으로 표시되는지 JSON·렌더 결과를 검증하고, 현재 6건의 표시 누락을 해소.

문서 수정으로 위 조건이 자동 충족되지는 않는다. 외부 상품 BE 배포와 사람 평가는 별도 실행이 필요하다.

## 문서

- [통합 인터페이스](api/be-fe-ai-integration-spec.md)
- [수집·라이선스·정제](data/collection-license-cleaning-plan.md)
- [평가 지표](evaluation/metrics-definition.md)
- [AI 아키텍처](architecture/ai-architecture-design.md)
- [안전성 정책](architecture/ai-evaluation-and-safety-policy.md)
- [최신 로컬 생성 테스트](operations/local-generation-test-report.md)
