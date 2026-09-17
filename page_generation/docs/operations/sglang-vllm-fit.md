# 로컬 MLX Serve 서빙 운영 검토 (SGLang 확정 전 기록)

작성일: 2026-09-08  
대상 서비스: 이미지 입력 → 상품 특징 분석 → `react_document` 조립·검증 → HTML/CSS 상세페이지 렌더링 → AI-FE/AI-BE DTO 전달

> **상태 (2026-09-16): 당시 로컬 MLX Serve 검토 기록.** 이 문서의 검토 결론은 현재 서버 운영
> 기준으로 사용하지 않습니다. 현행 운영 경로는 [Ubuntu 배포 가이드](ubuntu-deployment.md)의
> SGLang 2프로세스 구성으로 대체되었습니다: `sglang-text`(포트 `30000`, `qwen-text`,
> `cyankiwi/Qwen3.8-27B-AWQ-INT4`)와 `sglang-image`(포트 `30001`, `flux-klein`,
> `circulus/FLUX.2-klein-9B-bnb-4bit`)가 Ubuntu `g6e.xlarge`의 L40S 48GB를 공유합니다.
> Mac 로컬 개발 경로로서의 MLX Serve(`127.0.0.1:11234`) 설정은 여전히
> [로컬 LLM 경로](local-llm.md)를 참고합니다. 서버 GPU 실행·두 모델 동시 적재는 아직 검증하지 않았습니다.

이 문서의 본문은 2026-09-08 당시 로컬 전용 서빙 경로를 검토한 내용이다. 외부 모델 API나
외부 검색 API를 운영 경로에 포함하지 않는다는 원칙은 유지되지만, 운영 provider는 현재
SGLang으로 확정되었다.

## 1. 당시 검토 결론 (현재 서버 운영 기준 아님)

- 당시 검토에서는 추론 provider를 `local` 하나로 제한했다.
- 텍스트·이미지 분석과 한국어 카피 생성은 로컬 Gemma 모델이 담당한다.
- 배경·활용 장면·디테일 참고 컷은 로컬 Flux 모델이 담당한다.
- 현재 사진 정책은 `hero` 촬영 원본 그대로(`source_original`, `VERIFIED`)와 rembg 기반 `packshot`/대표 `detail`을 구분하며, 누끼 실패 시 `source`/`FALLBACK`으로 대체한다.
- Flux는 제품 원본을 다시 그리는 최종 상품 사진 생성기가 아니라, 제품 없는 배경과 연출 참고 컷 생성기로 제한한다.
- 제품 분석은 입력 이미지와 BE가 전달한 `user_hints`만 사용한다. 확인되지 않은 사실은 빈 값으로 둔다.

당시 검토의 로컬 개발 환경 예시는 다음과 같다.

```dotenv
ANALYSIS_PROVIDER=local
LOCAL_TEXT_PROVIDER=mlx
LOCAL_TEXT_URL=http://127.0.0.1:11234
LOCAL_TEXT_MODEL=mlx-community/gemma-4-12b-it-4bit
LOCAL_IMAGE_PROVIDER=mlx
LOCAL_IMAGE_URL=http://127.0.0.1:11234
LOCAL_IMAGE_MODEL=mlx-community/flux2-klein-9b-4bit
BACKGROUND_PROVIDER=mlx
PRODUCT_PHOTO_GENERATION=source
```

## 2. 데이터 흐름과 토폴로지

```text
FE
 │  원본 상품 이미지 + 선택적 상품 힌트
 ▼
AI API / 작업 서비스
 ├─ 로컬 Gemma
 │    이미지 + user_hints → ProductProfileDto JSON
 │
 ├─ 원본 보존 사진 합성기
 │    원본 RGB + 마스크 → hero / packshot / 대표 detail
 │
 ├─ 로컬 Flux (선택)
 │    제품 없는 배경·활용 장면·디테일 참고 컷 생성
 │
 ├─ React JSON builder + validator
 │    → `react_document` (FE projection/BE metadata)
 └─ HTML/CSS + Playwright
      → 상세페이지 PNG 및 섹션 PNG
      → AI-FE DTO / AI-BE DTO
```

당시 기본 개발 구성에서는 FastAPI/CLI와 MLX Serve를 같은 장비에서 실행했다. 운영 규모가
커지면 API/worker와 MLX Serve를 별도 로컬 장비로 분리하되, 모델 서버는 로컬망에만
바인딩한다. 제품 원본은 외부 서비스로 전송하지 않는다.

## 3. 로컬 서버 계약

### 텍스트·비전 분석

`MlxServeChatClient`가 다음 OpenAI 호환 요청을 보낸다.

```text
POST {LOCAL_TEXT_URL}/v1/chat/completions
model: mlx-community/gemma-4-12b-it-4bit
content: text prompt + image_url data URL
response_format: {"type":"json_object"}
```

응답의 `choices[0].message.content`를 JSON으로 파싱한 뒤
`ProductProfileDto.model_validate()`로 다시 검증한다. JSON이 아니거나 필수 구조가
맞지 않으면 제한된 재시도 후 작업을 실패 상태로 저장한다.

### 이미지 생성

배경·연출 참고 컷은 `MlxServeImageClient`가 사용한다.

```text
POST {LOCAL_IMAGE_URL}/v1/images/generations
model: mlx-community/flux2-klein-9b-4bit
response_format: b64_json
size: 1024x1024
```

원본을 참고해야 하는 `detail-02`~`detail-05` 보조 컷은 다음 편집 계약을 사용한다.

```text
POST {LOCAL_IMAGE_URL}/v1/images/edits
multipart: image + model + prompt + output_format=png
```

생성 결과는 `data[0].b64_json`에서 디코드한다. 결과 검증에 실패하면 원본 크롭으로
대체하고, 생성 결과를 최종 제품 사실의 근거로 사용하지 않는다.

## 4. 실행 기준 (당시 로컬 검토)

당시 로컬 검토에서는 MLX Serve를 기본 모델로 시작했다.

```bash
"/Applications/MLX Core.app/Contents/MacOS/mlx-serve" serve \
  --model ~/.mlx-serve/models/mlx-community/gemma-4-12b-it-4bit \
  --host 127.0.0.1 \
  --port 11234
```

상세페이지 생성 CLI는 동일한 로컬 endpoint를 사용한다.

```bash
PYTHONPATH=src .venv/bin/python scripts/runtime/run_local_detail_page.py \
  --image assets/samples/najeon-box.jpeg \
  --output-dir generated/runs/local_gemma_flux \
  --text-provider mlx \
  --text-url http://127.0.0.1:11234 \
  --text-model mlx-community/gemma-4-12b-it-4bit \
  --image-provider mlx \
  --image-url http://127.0.0.1:11234 \
  --image-model mlx-community/flux2-klein-9b-4bit
```

텍스트 추론만 별도로 점검할 때는 로컬 Ollama를 선택할 수 있다. 이 경우에도 외부 호출은
없으며, 이미지 생성은 `--image-provider none`으로 둔다. 서비스 기본값을 바꾸지는 않는다.

## 5. 안전한 생성 규칙 (로컬·서버 공통 원칙)

- 단일 입력 이미지에 없는 후면·측면·내부 구조를 사실처럼 만들지 않는다.
- `visual_facts`는 이미지에서 직접 확인한 내용만 기록한다.
- `user_hints`는 BE가 제공한 사실 후보이며, 모델이 새로운 출처나 수치를 덧붙이지 않는다.
- 크기·재료·제작자·연대·인증·관리법은 근거가 없으면 `null` 또는 빈 배열로 둔다.
- Flux 생성 컷은 `GENERATED`와 `product_generated=true`로 구분하고, 화면에 별도 '참고용' 표시를 붙이지 않으며 상품 대표 이미지·상품 사실의 증거로 사용하지 않는다.
- 원본 이미지와 모델 요청 본문은 로그에 남기지 않거나 민감 데이터로 마스킹한다.
- 모델 서버 포트는 `127.0.0.1` 또는 사설망에만 노출하고, API 계층에서 MIME·크기·timeout을 검증한다.

## 6. 메모리·동시성 기준 (당시 로컬 검토 추정)

당시 로컬 검토에서는 다음 순서로 시작하도록 제안했다.

1. Gemma 분석 동시성 1
2. 원본 합성 및 HTML 캡처는 분석과 겹치지 않도록 작업 단위로 조절
3. Flux 생성은 별도 단계로 실행하고 실패 시 원본 크롭으로 대체
4. 통합 메모리·swap·처리시간 p95를 측정한 뒤 동시성을 2로 올림

대략적인 시작 추정치는 API/worker와 렌더러 2~6GB, Gemma 12B 4-bit 8~14GB,
Flux2 Klein 9B 4-bit 8~16GB다. 모델과 런타임이 동시에 상주하면 32GB 이상부터
검증하고, 최종 수치는 MLX Serve 로그와 장비 모니터링으로 확정한다.

## 7. 점검 체크리스트

- [ ] `ANALYSIS_PROVIDER`가 `local`이 아닌 값이면 설정 검증이 실패하는가
- [ ] 프로세스 환경에 외부 API 키가 있어도 로컬 pipeline이 이를 읽지 않는가
- [ ] `ProductProfileDto`가 이미지와 `user_hints`만으로 생성되는가
- [ ] 분석 결과가 JSON/Pydantic 검증을 통과한 뒤에만 렌더링되는가
- [ ] `react_document`가 schema v2.0, 허용 tag/tree, 고유 ID, 깊이/노드, safe URL, `imageId` 검증을 통과하는가
- [ ] React JSON 외부 키가 camelCase이고 raw HTML/JSX/CSS/script/event handler가 없는가
- [ ] 대표 제품 사진에 원본 픽셀 보존 검증이 적용되는가
- [ ] Flux 실패 시 원본 크롭 fallback이 동작하는가
- [ ] MLX Serve timeout·5xx·잘못된 JSON이 안전한 실패 상태로 남는가
- [ ] 원본 이미지·base64·프롬프트가 로그와 오류 응답에 노출되지 않는가
- [ ] 동시성 1/2에서 메모리 peak와 p95 지연시간을 기록했는가

## 8. 변경 보류 항목

SGLang 외 다른 서빙 런타임이나 외부 모델 provider로의 전환은 현재 구성에 포함하지 않는다. 필요할
때에도 먼저 동일 평가셋으로 사실 정확도, 구조화 출력 성공률, 원본 보존율, p95 지연시간을
비교하고 별도 설계·승인을 거친다. 이 문서의 당시 기준은 로컬 Gemma + Flux였으며,
2026-09-16 현재 서버 운영 기준은 SGLang 텍스트·이미지 2프로세스다. 현재 Mac 로컬 개발
모델·환경변수는 [로컬 LLM 경로](local-llm.md), 서버 운영 모델·포트·기동 절차는
[Ubuntu 배포 가이드](ubuntu-deployment.md)를 따른다.
