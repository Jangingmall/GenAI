# 보안조치요구서 회신 — 생성형 AI 팀 (2026-09-30)

- 수신: 사이버 보안팀 · 발신: 생성형 AI 팀
- 근거: 「미담 GenAI팀 보안조치요구서」(점검 기준일 2026-09-30, 대외비)
- 대상: `page_generation`(상세페이지 생성) · `chat_bot`(챗봇) 코드와 Python 의존성
- 확인 기준: page_generation 작업 저장소 `deploy/ubuntu`, GenAI `main` `505a68e`, infra `main`, BE `develop`

> 성격: 시점 기록. 요구서 원문은 대외비라 이 저장소에 넣지 않았다.

---

## 요약

| 항목 | 판정 (재확인) | 조치 | 담당 | 일정 | 적용 환경 |
| --- | --- | --- | --- | --- | --- |
| SAST F-1 인증 의존성 | **외부 노출 없음** | 테스트 2건 추가 (라우트 전수 · 비인증 요청) | 상세페이지 / 챗봇 담당 | 2026-09-30 완료 | 저장소. 코드 동작 변경 없음 |
| SAST F-3 경로 처리 | **경로 탈출 불가** | 테스트 5건 추가 | 상세페이지 | 2026-09-30 완료 | 저장소. 코드 동작 변경 없음 |
| SAST F-4 객체 인가 | **BE 가 소유자 확인, AI 는 BE 에서만 도달** | 없음 (근거 회신) | 상세페이지 / 챗봇 담당 | 2026-09-30 | — |
| SAST F-7 innerHTML | **XSS 불가 (기존 이스케이프 확인)** | `innerHTML` 제거 → DOM API, 브라우저 검증 추가 | 상세페이지 | 2026-09-30 완료 | 로컬 개발 화면만 (배포 이미지에 없음) |
| SCA 21건 | 버전 매칭 확인 | **Pillow 12.3.0 · rembg 2.0.85 · pytest 9.1.1 로 올림** | 상세페이지 | 2026-09-30 저장소 반영 | 새 page-generation 이미지 발행 후 Stage 교체 시 |

---

## SAST F-1 — FastAPI 인증 의존성 (라우트 16개)

### page_generation (10개)

| 라우트 | 인증 | 비인증 요청 결과 |
| --- | --- | --- |
| `GET /health`, `GET /health/ready` | 없음 (의도) | 200 — 상태 문자열만 반환, 데이터 없음 |
| `POST /internal/v1/ai/detail-page-jobs` 외 내부 3개 | `X-AI-Internal-Token` 헤더 (`hmac.compare_digest`) | 토큰 없음·틀림 **401**, 서버에 토큰 미설정 시 **503** (닫힌 상태로 실패) |
| `POST/GET/PUT /api/v1/ai/...` 4개 (FE 직접 호출용 데모) | `ENABLE_LEGACY_DEMO_API` 스위치 | 기본값 꺼짐 → **404**. Stage 매니페스트에 이 값 없음 |

- 증빙 테스트: `tests/test_ai_internal_app.py`
  - `test_every_route_is_health_internal_or_a_disabled_demo_route` — 헬스를 뺀 모든 라우트가 내부 토큰 또는 데모 스위치를 거치는지 전수 검사. 인증 없는 라우트가 새로 생기면 CI 에서 실패한다
  - `test_unauthenticated_requests_are_refused` — 실제 HTTP 요청으로 데모 404, 내부 401 확인
  - 기존 `test_internal_routes_reject_wrong_token`(401), `test_internal_routes_fail_closed_when_token_is_not_configured`(503)

### chat_bot (6개)

`/ai/health`, `/ai/ready`, `POST/PUT/DELETE /ai/products`, `POST /ai/chat` — **앱 수준 인증은 없다.** 외부 노출은 네트워크로 막혀 있다.

### 네트워크 격리 증거 (infra `main`)

- `ai` 네임스페이스 `default-deny-ingress` — 모든 유입 차단이 기본
- `allow-backend-ingress` — `ai-sglang`·`ai-ollama` 파드로는 **`app` 네임스페이스의 `backend` 파드에서 TCP 8000 만** 허용
- 두 서비스 모두 `type: ClusterIP`, AI 서비스를 가리키는 Ingress·HTTPRoute 없음

→ 두 서비스 모두 **BE 경유 전용**이다. 챗봇 라우트에 내부 토큰을 두는 심층 방어는 챗봇 담당에게 권고로 전달한다.

- 남은 확인: Stage 에서 BE 가 아닌 파드로부터의 실제 접근 차단 시험은 클러스터 권한이 없어 하지 못했다 — 인프라팀 확인 요청

## SAST F-3 — 경로 처리 후보 3건

| 위치 | 입력 흐름 | 파일 접근 전 검증 | 재검 |
| --- | --- | --- | --- |
| `src/detail_page_ai/assets.py` (로컬 자산 저장소 `get`) | 자산 ID → 메타데이터 → 저장 위치 | ID 는 `^[0-9a-f]{64}$`(sha256) 만 허용, 저장 위치를 `resolve()` 해 저장소 루트 안인지 확인, 읽은 뒤 sha256 재검증 | 기존 `store.get("../secret")` 거부 + **신규: 메타데이터를 루트 밖으로 조작해도 거부** |
| `src/detail_page_ai/html_renderer.py` (`_load_section_assets`) | 우리 렌더러(Node)가 임시 폴더에 쓴 manifest 의 파일명 | 읽기 전에 `Path(filename).name == filename` (경로 구분자·절대경로 차단) | **신규 4건:** `../secret.png`, `/etc/passwd`, `sub/section.png` 거부. `..` 는 이름 검사를 통과하지만 폴더를 읽다 실패해 거부 |
| `scripts/dataset/setup_real_eval_dataset.py:191` | 우리가 만든 평가셋 manifest 의 `image_path` (`images/cma-<미술관 숫자 ID>.jpg`) | 이동 대상은 `Path(...).name` 으로 파일명만 사용 | 개발용 1회성 스크립트. 배포 이미지·서비스 경로에 없음. 외부 입력 없음 |

- 증빙 테스트: `tests/test_assets.py::test_record_pointing_outside_store_is_refused`, `tests/test_html_renderer.py::test_section_manifest_cannot_read_outside_sections_dir` (4개 경우)

## SAST F-4 — 세션·작업 객체 인가

| 위치 | AI 쪽 | 소유자 확인 위치 (BE `develop`) |
| --- | --- | --- |
| `detail_page_ai/app.py` `GET /api/v1/ai/detail-page-jobs/{job_id}` | 데모 라우트 — 기본값 꺼짐(404). 내부 조회는 내부 토큰 필요 | `GenerationService.poll` → `verifyOwner(product, requesterId)` 후에만 AI 에 조회 |
| `chat_bot/app/main.py` `/ai/chat` `session_id` | 요청의 세션 ID 로 세션을 찾음 (앱 수준 확인 없음) | `ChatService.sendMessage` → `verifyOwner(session, memberId)` 후에만 AI 에 전달. 세션 ID 는 BE 가 발급한 UUID |

AI 서비스는 BE 파드에서만 도달하므로(F-1 네트워크 격리) 타 계정이 AI 에 직접 요청할 경로가 없다.

- 남은 확인: 타 계정 교차 요청 시험은 BE 공개 API 대상이며 Stage 계정이 필요하다 — BE 팀·보안팀 DAST 결과로 확인 요청

## SAST F-7 — `web/ai_draft_preview.js:177` innerHTML

- **데이터 흐름:** AI 초안 API 가 준 특징 제목·설명(모델 출력) 또는 판매자가 편집창에 입력한 값 → 편집 입력칸
- **기존 상태:** 두 값 모두 `escapeHtml`(`& < > " '` 5종 치환)을 거친 뒤 `innerHTML` 에 들어가 속성·본문 어디서도 HTML 로 해석되지 않았다
- **배포 여부:** 이 파일은 로컬 개발용 미리보기 화면이다. 배포 이미지는 `web/detail_page.html`·`detail_page.css` 만 복사한다(`deploy/sglang/Dockerfile`)
- **조치:** 177번 줄을 `createElement`·`textContent`·`value` 로 바꿔 파일의 `innerHTML` 사용을 0 건으로 만들었다
- **브라우저 검증:** `scripts/browser/test_draft_preview.mjs` 에 공격 문자열 ``"><img src=x onerror="window.__xss=1">`` 을 초안 특징에 넣고 편집창 입력까지 하는 검사를 추가했다. 스크립트 실행 없음 · 편집창·미리보기에 `img` 생성 없음 · 원문 그대로 유지. **수정 전 코드와 수정 후 코드 모두 통과**해 기존에도 취약하지 않았음을 확인했다

## SCA — Python 의존성 21건

| 패키지 | 이전 | 조치 후 | 수정 버전 (OSV 기준) | 우리 사용 경로와 발동 조건 |
| --- | --- | --- | --- | --- |
| Pillow (18건) | 11.3.0 | **12.3.0** | 12.1.1 ~ 12.3.0 | 사용자 이미지는 MIME `image/png`·`jpeg`·`webp` 만 받고 파일 서명을 먼저 대조한다. PSD·FITS·McIdas·PDF·폰트·JPEG2000 등 해당 코덱은 도달하지 않는다. 다만 합성에서 `paste`·`crop` 을 쓰므로(CVE-2026-59199 계열) 업그레이드로 해소 |
| rembg (2건) | 2.0.69 | **2.0.85** | 2.0.75 | CVE-2026-40086 은 사용자 지정 모델 경로, GHSA-55v6-g8pm-pw4c 는 rembg 서버 모드의 SSRF·CORS. 우리는 고정 모델명(`birefnet-general`)으로 라이브러리만 호출해 발동하지 않지만 올렸다 |
| pytest (1건) | 8.4.2 (개발용) | **9.1.1** | 9.0.2 초과 | 개발 의존성. 배포 이미지는 `uv sync --no-dev` 라 포함되지 않는다 |

- 챗봇: pytest 는 이미 9.1.1 이고, Pillow 는 `sentence-transformers` 를 통해 빌드 시 최신이 설치된다. 2026-09-30 발행 이미지(`505a68e`) 빌드 로그에서 **Pillow 12.3.0** 을 확인했다
- 딸려서 빠진 패키지: `opencv-python-headless`(rembg 2.0.85 가 더 이상 요구하지 않음). 우리 코드는 사용하지 않는다
- Pillow 14 에서 제거 예정인 `Image.getdata()` 7곳을 `get_flattened_data()` 로 바꿨다

### 호환성 재검

| 확인 | 결과 |
| --- | --- |
| 전체 테스트 | 460 passed |
| 누끼 결과 동일성 (birefnet-general, 사진 7장) | 업그레이드 전후 마스크 **7장 모두 픽셀 차이 0** |
| 브라우저 테스트 (초안 편집·미리보기·승인) | 통과 |
| 린트 (변경 파일) | 새 경고 없음 |

- 재스캔: 보안팀 스캐너로 새 `uv.lock` 기준 재스캔을 요청한다

## 반영 일정

1. 저장소 반영 — 2026-09-30 (본 회신과 같은 변경)
2. GenAI `main` 머지 후 CI 가 새 page-generation 이미지를 발행
3. 인프라팀이 Stage 이미지를 교체하면 Stage 에 적용된다
