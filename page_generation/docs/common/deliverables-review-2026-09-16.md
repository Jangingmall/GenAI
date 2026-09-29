# 전체 산출물 검수 — 최종 판정

> 이 문서는 2026-09-16 시점 기록이다. 이후 상태가 바뀌어도 이 문서는 고치지 않는다.
> 워커 보고서 원본 4개(`codex.md`, `agy.md`, `agy2.md`, `agy-2.md`)는 `.orchestration/`에 로컬로만 남으며 저장소에는 이 판정 문서만 남는다.

- 검수일: 2026-09-16
- 방식: 워커 3인이 겹치지 않는 파일 범위를 검수하고, 관리자가 모든 지적을 코드·문서에서 재확인해 등급을 확정했다.
- 워커 보고 원본: `codex.md`(계약·아키텍처 4건), `agy.md`(운영·배포 11건), `agy2.md`(5종 산출물·차수 기록 6건), `agy-2.md`(미검수 영역 10건)
- 관리자 직접 검수: 테스트 실행, 레이아웃 카탈로그 종수, 문서→파일 경로 무결성 21건, 시크릿 스캔, health 라우트 인증

## 판정 요약

| 등급 | 건수 | 의미 |
| --- | ---: | --- |
| 치명 | 4 | 다른 팀이 문서대로 구현·구성하면 실패한다 |
| 불일치 | 6 | 문서와 코드/문서 간 사실 차이 |
| 사소 | 6 | 표기·정리 문제 |
| 기록만 | 4 | 시점 기록이라 수정하지 않고 남긴다 |
| 반려 | 5 | 워커 지적이나 관리자가 기각 |

---

## 치명 4건

### C-1. BE/FE 명세의 허용 `asset_mode` 목록에 `source_original` 누락
- `docs/phase3/api/be-fe-ai-integration-spec.md:486-494` 는 `source`, `source_crop`, `source_composite`, `generated_scene`, `generated_view` 만 열거한다.
- 실제 `AssetMode` 에는 `source_original` 이 있고(`src/detail_page_ai/models.py:22-30`), **hero 가 실제로 이 값을 내보낸다**(`src/detail_page_ai/source_photos.py:1065-1083`).
- 상품 BE 가 이 문서대로 검증기를 만들면 **모든 hero 자산이 거부된다.** `docs/phase3/api/ai-dto-contract.md:113-115` 도 같은 누락이 있다.
- 아키텍처 문서는 올바르게 적고 있어(`docs/common/ai-architecture-and-safety.md:148`) 계약 문서만 뒤처졌다.

### C-2. React JSON 계약의 전달 경로에 존재하지 않는 `status.` 래퍼
- `docs/phase3/api/react-json-output-contract.md:19-21` 은 `status.draft.react_document`, `status.result.detail_page.react_document` 로 적는다. `docs/phase2/ai-architecture-design.md:284-285` 도 같다.
- 실제 상태 DTO 는 `status` 가 **문자열 필드**이고 `draft` / `result` 가 최상위에 있다(`src/detail_page_ai/ai_dto.py:84-95`).
- 실제 경로는 `draft.react_document`, `result.detail_page.react_document` 다. FE 가 문서대로 구현하면 문자열을 객체처럼 탐색한다.

### C-3. EKS PVC 용량을 "최소 20Gi" 로 안내
- `docs/phase4/operations/aws-migration-checklist.md:140`.
- 모델 가중치만 약 30GB 다(`docs/phase4/operations/eks-workload-spec.md:83`). 20Gi 로 만들면 최초 기동 중 디스크 풀로 CrashLoopBackOff 가 된다.
- 같은 저장소의 `eks-workload-spec.md:128` 은 100Gi 를 권장해 **문서끼리 모순**이다.

### C-4. 산출물 색인의 미해결 목록이 사실과 다름
- `docs/phase3/originals/03-second-experiment-report.md:175` "60건 전체 평가는 수행하지 않았고" → 10차에 60/60 수행됐다(`round-10/03-experiment-report.md:45`, `docs/phase4/evaluation/full60-runs.md:15`).
- `:176` "생성 자산의 `참고용` 라벨 … 미수정으로 남긴 배포 차단 조건" → 12차에 관리자 결정으로 표시와 게이트 자체가 제거됐다(`round-12/01-implementation-checkpoint.md:43`).
- 이 문서는 12차 행까지 갱신된 **살아 있는 색인**이므로 시점 기록 예외에 해당하지 않는다.

---

## 불일치 6건

| # | 위치 | 내용 |
| --- | --- | --- |
| I-1 | `docs/phase3/api/be-fe-ai-integration-spec.md:104` | 허용 태그 예시에 `h1` 포함. 코드 allowlist 는 `h2` 부터다(`src/detail_page_ai/react_document.py:231-257`). `react-json-output-contract.md:88-94` 에는 `h1` 이 없어 문서끼리도 갈린다 |
| I-2 | `aws-deployment.md:13,346`, `aws-migration-checklist.md:13,213` | 단위 테스트 **353개**로 적혀 있다. 실제 **358개**(probe 테스트 5건 추가분 미반영) |
| I-3 | `aws-deployment.md:106,136,290`, `aws-migration-checklist.md:170` | 헬스체크를 "없는 작업 조회 404" 방식으로 안내하고 "전용 200 엔드포인트가 필요하다"고 적는다. `GET /health` 200 이 이미 구현됐다(`src/detail_page_ai/app.py:158`) |
| I-4 | `.env.example:39` | 주석 머리글이 `[기본값: black-forest-labs/FLUX.2-klein-4B]`. 실제 값은 46행 `circulus/FLUX.2-klein-9B-bnb-4bit` |
| I-5 | `docs/phase4/operations/ubuntu-deployment.md` 전체 | "GPU 에서 한 번도 실행되지 않았다" 면책 문구가 **한 곳도 없다.** 형제 문서 3개(aws-deployment, aws-migration-checklist, eks-workload-spec)에는 모두 있다. 운영자가 가장 먼저 따라가는 문서라 누락이 크다 |
| I-6 | `docs/phase3/originals/02-error-analysis.md:249` | 사건 7 제목이 "(배포 차단 조건 5, 미수정)". 라벨 요구 자체가 제거돼 더 이상 열린 차단 조건이 아니다 |

---

## 사소 6건

| # | 위치 | 내용 |
| --- | --- | --- |
| T-1 | `.env.example:31` | `0.50 (약 24.0 GiB)`. 실제는 44.7 × 0.5 = **22.35 GiB**. 48GB 를 10진으로 오인 |
| T-2 | `aws-deployment.md:163` | "가중치 하한 합계 32.55 GiB" 는 용어 오류. 순수 가중치 합은 29.8 GiB, 32.55 는 정적 선점 + 이미지 가중치다 |
| T-3 | `pyproject.toml` | `pythonpath = ["src"]` 만 있어 `uv run pytest` 는 수집 실패 2건(`tests/test_attached_detail_page.py`, `tests/test_eval_runner_cli.py` 가 `scripts` 를 import). README 가 안내하는 `python -m pytest` 로는 358 통과 |
| T-4 | `scripts/build_review_page.py` | 1,871줄, 저장소 전체 참조 **0회**. `build_review_artifact.py` 로 대체됐고 문서도 새 도구만 안내한다 |
| T-5 | `docs/phase3/api/ai-fe-io-spec.md:104-114,164-169` | `/health`, `/health/ready` 가 API 경로 목록에 없다 |
| T-6 | `web/ai_input.*`, `web/ai_draft_preview.*` (6개) | FastAPI 가 서빙하지 않고 Playwright 테스트에서만 쓰는데 `Dockerfile:34`, `sglang/Dockerfile:86` 에서 이미지에 번들된다 |

---

## 기록만 남긴 것 (시점 기록, 수정하지 않음)

1. 차수 로그 10개에 권고·향후 계획 문장이 있다(round-02/06/07/08/09/11). 로그 규칙 위반이지만 차수 기록은 고치지 않는다.
2. `round-11` 안에서 "깨끗한 컷아웃"이 12건(`01:54,58`, `02:69`)과 13건(`03:71,86`)으로 갈린다. 12 는 품질 기준, 13 은 개정 게이트 OK 수로 보이나 문서가 분모를 구분하지 않았다.
3. `round-10/03:53` "OK 55건" 과 `docs/phase4/evaluation/full60-runs.md:25` "게이트 OK 3" 은 게이트 개정 전후 값이다. round-10 이 "당시 게이트 기록"이라고 명시해 모순은 아니다. `full60-runs.md` 표에 게이트 버전 표기가 없는 점만 기록한다.
4. `docs/phase4/operations/sglang-serving-research.md:148` 의 "두 모델 공존 시 여유분 ~24 GiB" 는 산수 오류다(실제 12.2~14.9 GiB). 2026-09-14 조사 시점 기록이라 고치지 않는다.

---

## 관리자가 기각한 워커 지적 5건

### R-1 ~ R-3. 인프라팀 문서에서 불리한 사실을 지우라는 제안 — **전면 반려**
`agy-2.md` 는 다음 셋을 "치명"으로 올리며 표현을 바꾸라고 제안했다.
- `eks-workload-spec.md:7` 의 "Dockerfile 을 아직 빌드하지 않았다" → 협업 지향 문장으로 정제
- `:153` 의 FLUX Non-Commercial License 고지 → 대외 문서에서 분리
- `:142` 의 "원격 저장소가 없다" → 객관화된 표현으로 교체

**셋 다 반려한다.** 근거:
- 셋 다 **사실**이고, 모두 인프라팀의 의사결정을 바꾸는 정보다. 빌드 미검증은 배포 일정에, 라이선스는 컴플라이언스 승인에, 원격 부재는 이미지 발행 파이프라인 구성에 직접 영향을 준다.
- 워커가 든 이유는 "배포 반려를 부를 수 있다", "책임 공방을 유발할 수 있다"였다. 이는 **정확성이 아니라 우리 팀의 유불리를 기준으로 삼은 것**이고, 이 저장소의 "과장 금지" 원칙과 정면으로 어긋난다.
- 라이선스 고지를 빼는 것은 상대 팀이 법적 위험을 모르고 승인하게 만드는 일이라 특히 받아들일 수 없다.

### R-4. `agy2` "1~9차 컷아웃 6/6 OK 는 허위 통과" (치명) → **기각**
당시 게이트 버전의 판정을 그대로 적은 시점 기록이고, 그 판정이 폴백을 정상으로 오인했다는 사실은 11차 에러 분석(`round-11/02:20-26`)에 이미 기록돼 있다. 기록 체계가 의도대로 작동한 사례다.

### R-5. `agy` "ubuntu-deployment 가 healthy 를 단정" (치명) → **부분 기각**
149행은 `출력 예시` 라고 명시돼 있어 관측 주장이 아니다. 다만 같은 문서에 면책 문구가 전혀 없는 것은 사실이므로 I-5 로 낮춰 남겼다.

이와 함께 `sglang-serving-research.md` 의 `--revision` 누락·모델명 `qwen-vl` 지적도 조사 시점 기록이므로 기각했다.

---

## 이상 없음으로 확인된 것

- 차수 기록 완전성: round-01~12 각 5개 문서 **60개 전부 존재**, 로그 헤더 4요소 전부 있음
- 레이아웃 카탈로그 **25종** (`assets/references/detail-page-layouts.json`), 문서에 "20종" 오기 없음
- 인증: 내부 4개 라우트 모두 `X-AI-Internal-Token` 검증, `/health`·`/health/ready` 무인증 확인
- 계약 필드 철자: `product_generated`, `asset_mode`, `fidelity_status`, `react_document` 모두 코드와 일치
- 사람 평가 점수를 지어낸 문장 **0건**. AI 참고치는 참고치로 명시돼 있고, 12차의 `확인 필요` 표기는 수치를 만들지 않은 올바른 처리다
- 시크릿: 토큰·키 패턴 0건, `.env` 미존재·gitignore 등록, 노트북 출력 셀 없음
- 문서가 가리키는 파일 경로 21건 결손은 전부 "삭제됨"을 설명하는 참조이거나 미구현 제안 경로
- `scripts/` 22개 전부 문법·임포트 정상
- EKS(단일 컨테이너) 문서와 EC2 compose(3 컨테이너) 문서의 구조 차이는 대상이 달라서이지 모순이 아님
- `local-llm.md` 등 Mac 로컬 문서와 서버 문서의 MLX/SGLang 분리 정상

## 조치 결과

검수 후 실제 조치 결과와 아래 커밋의 변경 통계는 각 커밋에 대해 `git show --stat <해시>`로 직접 확인했다.

- `cdf33c4`: 치명 C-1~C-4, 불일치 I-1~I-6, 사소 T-1·T-2를 조치했다. `.env.example`을 포함한 문서 11개가 변경됐다. `git show --stat cdf33c4` 확인 결과 11개 파일 변경(486 insertions, 279 deletions)이다.
- `e0d98b6`: 사소 T-6에 따라 `Dockerfile`과 `sglang/Dockerfile`의 `web` COPY를 축소했다. `git show --stat e0d98b6` 확인 결과 `Dockerfile`, `sglang/Dockerfile`, `sglang/entrypoint.sh` 3개 파일 변경(237 insertions, 4 deletions)이다.
- `ecebfd1`: 사소 T-3(pytest pythonpath)와 T-4(`scripts/build_review_page.py` 1,871줄 삭제)를 조치했다. `git show --stat ecebfd1` 확인 결과 `pyproject.toml`, `scripts/build_review_page.py`, `scripts/orchestration/workers.tsv` 3개 파일 변경(4 insertions, 1,875 deletions)이다.
- 검수 중 추가로 발견한 `docs/phase3/api/be-fe-ai-integration-spec.md:104`의 diff 아티팩트(`+ ` 불릿)는 되돌렸으며, 이 수정은 `cdf33c4`에 포함돼 있다.
- 시점 기록 4건은 고치지 않았다. 차수 로그와 조사 시점의 수치를 후속 상태와 섞지 않고 당시 검수 결과를 보존해야 하기 때문이다.
- 검수 시점 이후 기준 `python -m pytest -q`와 `uv run pytest -q`는 모두 **358 passed**였다.
