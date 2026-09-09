# 04. 추론 API 구성

작성 기준: 2026-09-09 코드 대조

이 서비스에서 API는 성격이 다른 두 층이다. 서비스 API는 Product BE/FE와 작업을 주고받고, 모델 추론 API는 서비스가 텍스트·비전·이미지 모델을 호출하는 내부 경계다.

| 층 | 구현 | 포트·인증 | 역할 |
|---|---|---|---|
| 서비스 API | src/detail_page_ai/app.py — FastAPI app | 8000; /api/v1/ai/...는 legacy demo 설정에 의해 열리고, /internal/v1/ai/...는 X-AI-Internal-Token 필요 | 작업 접수, draft·상태·승인 결과, BE 전달 |
| 모델 추론 API | MLX Serve; src/local_detail_page_ai/clients.py의 MlxServeChatClient, MlxServeImageClient | 기본 http://127.0.0.1:11234; OpenAI 호환 JSON | 서비스 API가 위임하는 텍스트·비전 분석과 Flux 생성·편집 |

서비스 API가 모델 추론 API의 클라이언트다. 모델 서버가 Product BE/FE 계약을 직접 제공하지 않는다.

## 1. 서비스 API: 포트 8000

src/detail_page_ai/app.py의 run 심볼은 uvicorn으로 detail_page_ai.app:app을 0.0.0.0:8000에 바인딩한다.

### 1.1 Product BE 내부 API

X-AI-Internal-Token은 src/detail_page_ai/app.py의 _require_internal_auth 심볼이 검사한다. 토큰이 없으면 503, 잘못된 토큰이면 401이다.

| 메서드·경로 | 심볼 | 입력 | 결과 |
|---|---|---|---|
| POST /internal/v1/ai/detail-page-jobs | create_internal_detail_page_job | multipart product_image, JSON 문자열 metadata, 선택적 product_images, 선택적 Idempotency-Key | 202, AiToProductBeAcceptedResponseDto 형태의 QUEUED 작업 |
| GET /internal/v1/ai/detail-page-jobs/{job_id} | get_internal_detail_page_job | X-AI-Internal-Token | AiToProductBeStatusResponseDto |
| PUT /internal/v1/ai/detail-page-jobs/{job_id}/draft | save_internal_detail_page_draft | JSON ProductBeToAiSaveDraftRequestDto | draft projection |
| POST /internal/v1/ai/detail-page-renders | approve_internal_detail_page | multipart metadata, 선택적 이미지, 선택적 Idempotency-Key | AiToProductBeApprovedResponseDto |

내부 job 생성 metadata는 src/detail_page_ai/ai_dto.py의 ProductBeToAiCreateJobRequestDto다.

    {
      "product_id": "<product id>",
      "source_asset_id": "<optional source asset id>",
      "request_id": "<optional request id>",
      "idempotency_key": "<idempotency key>",
      "template_id": "default-long-detail-page",
      "locale": "ko-KR",
      "user_hints": {
        "product_name": "<optional>",
        "making_method": "<optional>",
        "care_guide": "<optional>"
      },
      "options": {
        "aspect_ratio": "1:4",
        "image_size": "2K",
        "output_mime_type": "image/png"
      }
    }

accepted 응답의 필드 구조는 src/detail_page_ai/ai_dto.py의 AiToProductBeAcceptedResponseDto에서 확인된다. 아래 값은 실제 호출 결과가 아니다.

    {
      "product_id": "<runtime value>",
      "job_id": "<runtime value>",
      "request_id": "<runtime value>",
      "status": "QUEUED",
      "status_url": "<runtime value>",
      "created_at": "<datetime>"
    }

최종 승인 metadata는 ProductBeToAiApproveDraftRequestDto다. job metadata에 draft_id, draft, options를 추가하며, draft는 ApprovedDraftDto의 product_name, summary, hero_headline, hero_description, usage_scene, features, keywords, layout_id, page_plan 필드를 가진다.

### 1.2 Legacy/public API projection

/api/v1/ai/... 라우트는 src/detail_page_ai/app.py의 _require_legacy_demo_api dependency를 사용한다. src/detail_page_ai/config.py의 ENABLE_LEGACY_DEMO_API 기본값은 false이므로 기본 서비스 구성에서는 이 층이 404로 닫혀 있고 Product BE 내부 API를 사용한다.

| 메서드·경로 | 심볼 | 입력·결과 |
|---|---|---|
| POST /api/v1/ai/detail-page-jobs | create_detail_page_job | multipart product_image, 선택적 product_images, product_name, making_method, care_guide, request_id, template_id, locale, JSON 문자열 options; 202 AiFeJobAcceptedResponseDto |
| GET /api/v1/ai/detail-page-jobs/{job_id} | get_detail_page_job | AiFeJobStatusResponseDto |
| PUT /api/v1/ai/detail-page-jobs/{job_id}/draft | save_detail_page_draft | JSON draft; AiFeDraftResponseDto |
| POST /api/v1/ai/detail-page-renders | approve_detail_page | multipart product_image, JSON 문자열 draft, 선택적 product_images, request_id, options; AiFeApprovedResponseDto |

public 응답 필드는 src/detail_page_ai/fe_dto.py의 AiFeJobAcceptedResponseDto, AiFeJobStatusResponseDto, AiFeDraftResponseDto, AiFeApprovedResponseDto가 정의한다. 상태 응답은 job_id, request_id, status, progress와 선택적 draft, result, error, updated_at을 가진다. 결과의 result에는 generation_id, product, detail_page가 들어가며 실행 가능한 HTML/CSS가 아니라 구조화 JSON과 asset metadata다.

## 2. MLX Serve 클라이언트

모델 클라이언트와 transport는 src/local_detail_page_ai/clients.py에 있다. 기본 텍스트 모델은 ddalcu/Qwen3.8-27B-MLX-Serve-4bit, 이미지 모델은 mlx-community/flux2-klein-9b-4bit다.

### 2.1 공통 transport

JsonTransport protocol은 다음 메서드를 요구한다.

    post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]

UrllibJsonTransport.post는 JSON을 UTF-8로 직렬화해 Content-Type: application/json으로 POST한다. HTTP/URL/timeout 오류는 LocalModelError로 감싸고, 응답을 JSON으로 파싱한 뒤 최상위가 객체인지 확인한다.

테스트에서는 tests/test_local_llm.py의 FakeJsonTransport가 이 protocol을 스텁한다. post 호출의 URL·payload·timeout을 calls에 저장하고 미리 준비한 dict를 반환하므로 모델 서버에 접속하지 않고 실제 payload를 검증한다.

### 2.2 MlxServeChatClient: 텍스트·비전 분석

심볼: src/local_detail_page_ai/clients.py — MlxServeChatClient

- 기본 URL은 http://127.0.0.1:11234다.
- 기본 모델은 ddalcu/Qwen3.8-27B-MLX-Serve-4bit다.
- 기본 timeout은 300초, max_tokens는 4096이다.
- 이미지가 없으면 messages[0].content는 prompt 문자열이다.
- 이미지가 있으면 content는 text part와 image_url part 배열이고, 이미지는 data:<mime>;base64,<bytes> data URL이다.
- endpoint는 {base_url}/v1/chat/completions다.
- stream은 false, temperature은 0, response_format은 {"type":"json_object"}다.
- json_schema 인자는 이 client에서 직접 전송하지 않는다. LocalProductAnalyzer가 prompt에 schema 텍스트를 넣고, 응답은 ProductProfileDto로 Pydantic 검증한다. 즉 서버에 깊은 JSON Schema를 보내는 방식이 아니라 JSON object 모드 + prompt schema + DTO 검증의 조합이다.

코드상 요청 모양은 다음과 같다. prompt와 base64 값은 실행 시 생성되는 값이다.

    POST http://127.0.0.1:11234/v1/chat/completions
    Content-Type: application/json

    {
      "model": "ddalcu/Qwen3.8-27B-MLX-Serve-4bit",
      "messages": [
        {
          "role": "user",
          "content": [
            {"type": "text", "text": "<prompt including JSON Schema>"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<base64>"}}
          ]
        }
      ],
      "stream": false,
      "temperature": 0,
      "max_tokens": 4096,
      "response_format": {"type": "json_object"}
    }

image가 없으면 content는 배열이 아니라 prompt 문자열이다. client가 읽는 응답 구조는 choices[0].message.content이며, content는 문자열 또는 text를 가진 블록 배열일 수 있다. 실제 모델 응답 본문은 모델 호출을 하지 않았으므로 기록하지 않는다.

### 2.3 MlxServeImageClient: 이미지 생성

심볼: src/local_detail_page_ai/clients.py — MlxServeImageClient.generate

생성은 {base_url}/v1/images/generations로 JSON POST한다. width/height 인자는 현재 MLX Serve가 지원하는 정사각형 크기를 사용하므로 payload에서는 1024x1024로 고정된다. 동시 작업 브리프가 지정한 최종 steps 기본값은 4다.

    {
      "model": "mlx-community/flux2-klein-9b-4bit",
      "prompt": "<background or scene prompt>",
      "negative_prompt": "<negative prompt, possibly empty>",
      "n": 1,
      "size": "1024x1024",
      "response_format": "b64_json",
      "steps": 4
    }

client는 응답의 data[0].b64_json을 strict base64 decode해 bytes로 반환한다. data, 첫 항목, b64_json이 없거나 base64가 아니면 LocalModelError다. 실제 base64 응답 값은 확인하지 않았다.

### 2.4 MlxServeImageClient: 이미지 편집

심볼: src/local_detail_page_ai/clients.py — MlxServeImageClient.edit

편집도 최종적으로는 /v1/images/generations의 JSON mode: "edit" 경로를 사용한다.

이 선택에는 호환성 경위가 있다. MLX Core 26.9.1에서 multipart /v1/images/edits 요청은 내부적으로 mode: "edit" JSON으로 변환되지만 steps와 strength를 전달하지 않는다. 그래서 현재 client는 multipart 경로를 사용하지 않고, 참조 이미지를 base64 JSON 필드로 싣는 직접 JSON 경로를 사용한다. 이렇게 해야 steps와 strength가 JSON 숫자로 payload에 남는다. 코드 주석에 따르면 현재 FLUX.2 in-context edit 모드는 strength를 받지만 의도적으로 무시할 수 있다. 전송되는 값과 모델이 실제로 반영하는지는 구분해야 한다.

    POST http://127.0.0.1:11234/v1/images/generations
    Content-Type: application/json

    {
      "model": "mlx-community/flux2-klein-9b-4bit",
      "prompt": "<edit prompt>",
      "size": "1024x1024",
      "mode": "edit",
      "steps": 4,
      "strength": 0.22,
      "image": "<base64 source image>"
    }

edit 함수 기본 strength는 0.30이다. 실제 파이프라인의 src/local_detail_page_ai/runner.py 심볼 MlxServeUsageSceneGenerator.generate와 MlxServeDetailViewGenerator.generate는 0.22를 전달한다.

### 2.5 대체 provider: OllamaChatClient

심볼: src/local_detail_page_ai/clients.py — OllamaChatClient

Ollama는 운영 기본 경로가 아니다. src/detail_page_ai/config.py의 LOCAL_TEXT_PROVIDER 기본값은 mlx이고, src/local_detail_page_ai/factory.py의 build_service와 src/local_detail_page_ai/runner.py의 build_local_pipeline가 값이 ollama일 때만 이 client를 선택한다.

Ollama 기본 URL은 http://127.0.0.1:11434, 기본 모델은 gemma3:12b, timeout은 180초다. native non-streaming endpoint /api/chat에 다음 JSON을 보낸다.

    {
      "model": "gemma3:12b",
      "messages": [
        {
          "role": "user",
          "content": "<prompt>",
          "images": ["<base64 image, image를 준 경우>"]
        }
      ],
      "stream": false,
      "format": "json",
      "options": {"temperature": 0}
    }

응답에서 message.content 문자열을 꺼내 JSON object로 파싱한다. Ollama의 깊은 Pydantic grammar schema 호환성 문제 때문에 client는 JSON mode를 사용하고, 최종 형식 검증은 LocalProductAnalyzer의 ProductProfileDto validation이 담당한다.

## 3. 추론 관련 설정 계약

src/detail_page_ai/config.py의 Settings와 .env.example을 대조한 결과다. 아래 기본값은 환경변수가 없을 때 Settings가 사용하는 값이다. .env.example에 명시된 값은 실행 시 기본값을 override할 수 있다.

| 환경변수 | Settings 기본값 | .env.example 값 | 의미 |
|---|---|---|---|
| ANALYSIS_PROVIDER | local | local | 분석 provider를 local-only로 제한한다. |
| LOCAL_TEXT_PROVIDER | mlx | mlx | 텍스트·비전 provider. mlx 또는 ollama; 운영 기본은 MLX다. |
| LOCAL_TEXT_URL | http://127.0.0.1:11234 | 동일 | 텍스트 모델 서버 base URL. |
| LOCAL_TEXT_MODEL | ddalcu/Qwen3.8-27B-MLX-Serve-4bit | 동일 | chat client에 전달할 모델 ID. |
| LOCAL_TEXT_TIMEOUT | 300.0초 | 300 | 텍스트 요청 timeout. |
| LOCAL_IMAGE_PROVIDER | mlx | mlx | 이미지 provider. none이면 이미지 생성기를 연결하지 않는다. |
| LOCAL_IMAGE_URL | http://127.0.0.1:11234 | 동일 | 이미지 모델 서버 base URL. |
| LOCAL_IMAGE_MODEL | mlx-community/flux2-klein-9b-4bit | 동일 | Flux image client에 전달할 모델 ID. |
| LOCAL_IMAGE_TIMEOUT | 300.0초 | 300 | 이미지 생성·편집 timeout. |
| BACKGROUND_PROVIDER | mlx | mlx | 제품 없는 배경·활용 장면·detail view provider. none이면 background generator가 없다. |
| PROMPT_VERSION | local-mlx-qwen-flux-v1 | detail-page-source-safe-v2 | 산출물 provenance prompt 버전. .env.example의 명시값이 코드 기본값을 override한다. |

추론과 직접 관련 없는 ASSET_STORE_DIR, SQLITE_PATH 등 상태 설정은 표에서 제외했다.

## 4. 어댑터와 파이프라인 연결

### 4.1 분석 경계

src/detail_page_ai/ports.py의 ProductAnalyzer protocol은 analyze(image, mime_type, user_hints)만 요구한다. src/local_detail_page_ai/adapters.py의 LocalProductAnalyzer는 StructuredJsonChatClient를 주입받고 다음 순서로 연결한다.

1. ProductProfileDto.model_json_schema()를 만든다.
2. build_analysis_prompt와 creator hints, JSON Schema를 하나의 prompt로 구성한다.
3. 주입된 chat client의 generate_json을 호출한다.
4. payload를 normalize한 뒤 ProductProfileDto로 검증한다.

상위 pipeline은 MLX인지 Ollama인지 알지 않고 ProductAnalyzer만 본다.

### 4.2 이미지 생성 경계

src/detail_page_ai/ports.py의 ProductPhotoGenerator는 source image와 profile, options를 받아 ProductPhotoSet을 반환한다. src/local_detail_page_ai/runner.py의 build_local_pipeline은 다음 구현을 구성한다.

- MlxServeBackgroundGenerator → MlxServeImageClient.generate: 제품 없는 배경판.
- MlxServeUsageSceneGenerator → MlxServeImageClient.edit: lifestyle용 원본 참조 사용 장면. role이 lifestyle이 아니면 거부한다.
- MlxServeDetailViewGenerator → MlxServeImageClient.edit: detail-02부터 detail-05까지 생성 detail view.
- SourcePreservingProductPhotoGenerator → ProductPhotoGenerator: 원본 제품 사진 보존·합성 및 fidelity validation.
- HtmlDetailPageRenderer → DetailPageRenderer: 최종 PNG와 section PNG 렌더링.

실서비스 조립은 src/local_detail_page_ai/factory.py의 build_service가 담당한다. Settings의 provider, URL, model, timeout을 읽어 client를 만들고 LocalProductAnalyzer, photo generator, renderer, DetailPagePipeline, repository/outbox를 연결한다. GenerationMetadataDto에는 provider, analysis model, image model, prompt version도 기록한다.

이 client/adapter 경계가 CUDA 이관 교체 지점이다. vLLM·diffusers 서버가 동일한 상위 계약을 제공하도록 새 client 또는 endpoint adapter를 만들면 ProductAnalyzer, ProductPhotoGenerator, DetailPagePipeline, FastAPI 라우트는 바뀌지 않는다. 핵심 조건은 텍스트 chat JSON, 이미지 generation JSON, 이미지 edit JSON 및 data[0].b64_json 응답 계약을 맞추는 것이다.

## 5. 엔드포인트별 요청·응답 구조 요약

아래 예시는 코드에서 읽은 필드 구조다. <...>는 실행 시 값이고, 모델 서버나 서비스에 실제 요청해 얻은 응답 본문이 아니다.

| 엔드포인트 | 요청 핵심 | client가 읽는 응답 |
|---|---|---|
| MLX POST /v1/chat/completions | OpenAI chat JSON; text 또는 text+data URL image, response_format=json_object, max_tokens=4096 | choices[0].message.content; 문자열 또는 text block list를 JSON object로 파싱 |
| MLX POST /v1/images/generations 생성 | model, prompt, negative prompt, n=1, size=1024x1024, response_format=b64_json, steps=4 | data[0].b64_json → bytes |
| MLX POST /v1/images/generations 편집 | model, prompt, mode=edit, steps=4, strength, base64 image | data[0].b64_json → bytes |
| Ollama POST /api/chat | model, messages, base64 images, stream=false, format=json | message.content → JSON object |
| Service POST /internal/v1/ai/detail-page-jobs | multipart image + metadata JSON, internal token | product_id, job_id, request_id, status=QUEUED, status_url, created_at |
| Service GET /internal/v1/ai/detail-page-jobs/{job_id} | internal token | status, progress, optional draft/result/error, updated_at |
| Service PUT /internal/v1/ai/detail-page-jobs/{job_id}/draft | JSON draft + optional version | draft response projection |
| Service POST /internal/v1/ai/detail-page-renders | multipart approval metadata + optional image, internal token | final result, status, backend pending flag, warning, BE ACK |

응답의 실제 job ID, timestamps, generated image bytes, base64 문자열은 이 문서 작성 중 모델 호출을 하지 않았기 때문에 기록하지 않았다.

## 6. 코드 근거와 운영상 주의

- 서비스 API route와 인증: src/detail_page_ai/app.py — create_internal_detail_page_job, get_internal_detail_page_job, save_internal_detail_page_draft, approve_internal_detail_page, _require_internal_auth.
- MLX chat/image payload와 response decoder: src/local_detail_page_ai/clients.py — MlxServeChatClient, MlxServeImageClient, _decode_image_response.
- JSON transport injection: src/local_detail_page_ai/clients.py — JsonTransport, UrllibJsonTransport; test stub: tests/test_local_llm.py — FakeJsonTransport.
- provider 조립: src/local_detail_page_ai/factory.py — build_service; local CLI 조립: src/local_detail_page_ai/runner.py — build_local_pipeline.
- 상위 교체 경계: src/detail_page_ai/ports.py — ProductAnalyzer, ProductPhotoGenerator, DetailPageRenderer.
- 설정 source of truth: src/detail_page_ai/config.py — Settings; 예시 override: .env.example.

