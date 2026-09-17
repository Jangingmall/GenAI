# 로컬 LLM 상세페이지 경로

> 이 문서는 Mac 로컬 개발 구성이며 서버 운영 구성은 [`ubuntu-deployment.md`](ubuntu-deployment.md)입니다.

FastAPI 서비스와 CLI runner 모두 같은 로컬 모델 경로를 사용합니다. 로컬 runner도 운영과 같은 원본 보존 규칙을 사용하며, 제품 전체를 Stable Diffusion·ComfyUI·FLUX로 다시 생성하지 않습니다.

> 2026-09-16 현재 출력 기준: FE에는 `react_document` 제한형 JSON AST를 제공하고, HTML/CSS는 승인 후 PNG를 만드는 내부 renderer에서만 사용합니다. `page_plan`은 AST 조립 전의 모델·편집·하위 호환 DTO입니다.

## 구성

- 이미지 분석 및 한국어 상품 카피: 로컬 Ollama vision API (`/api/chat`) 또는 MLX Serve OpenAI API (`/v1/chat/completions`)
- 제품 사진: 원본 RGB 컷아웃, 실제 원본 crop, 결정적 Pillow 합성
- 배경·연출: 기본은 중립 단색 배경, MLX 모드에서는 Flux2가 활용 장면과 디테일 컷을 생성
- FE 구조 출력: `react_document` 제한형 JSON AST + `imageId` 자산 참조
- 최종 상세페이지 이미지: 내부 HTML/CSS + Playwright
- 백엔드: 외부 적재 없이 실제 BE DTO 조립 경로만 검증

기본 로컬 경로는 MLX Serve의 `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` 분석·비전 모델과
`mlx-community/flux2-klein-9b-4bit` 이미지 모델입니다. 두 모델은 `http://127.0.0.1:11234`에서
같은 MLX Serve 인스턴스로 요청합니다.

현재 MLX Serve 모델 저장소에서 확인되는 모델은 다음과 같습니다.

- `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`
- `mlx-community/flux2-klein-9b-4bit`
- `Runpod/FLUX.2-klein-4B-mflux-4bit` (비교 테스트용)

## 실행 준비

```bash
"/Applications/MLX Core.app/Contents/MacOS/mlx-serve" serve \
  --model ~/.mlx-serve/models/ddalcu/Qwen3.8-27B-MLX-Serve-4bit \
  --host 127.0.0.1 \
  --port 11234
```

MLX Serve가 `http://127.0.0.1:11234`에서 실행 중이면 다음 명령만으로 두 모델을 사용합니다.

```bash
PYTHONPATH=src .venv/bin/python scripts/runtime/run_local_detail_page.py \
  --image assets/samples/images-2.jpeg \
  --output-dir generated/runs/images_2_qwen27b_flux2 \
  --text-provider mlx \
  --text-url http://127.0.0.1:11234 \
  --text-model ddalcu/Qwen3.8-27B-MLX-Serve-4bit \
  --image-provider mlx \
  --image-url http://127.0.0.1:11234 \
  --image-model mlx-community/flux2-klein-9b-4bit
```

Ollama를 별도 검증 경로로 사용할 때만 `--text-provider ollama`,
`--text-url http://127.0.0.1:11434`, `--text-model gemma3:12b`,
`--image-provider none`을 명시합니다.

`hero`는 촬영 원본 그대로(`asset_mode=source_original`, `fidelity_status=VERIFIED`) 유지합니다.
`packshot`·대표 `detail`은 rembg(`birefnet-general`, `rembg==2.0.69`) 누끼·원본 crop/합성
경로를 사용하며, 누끼 실패 시 `source`/`FALLBACK`으로 대체합니다. Flux2가 만든
`lifestyle`·추가 `detail-02`~`detail-05`는 생성 자산으로 메타데이터에 `GENERATED` 및
`product_generated=true`를 표시하고, 별도 화면 '참고용' 표시는 붙이지 않으며 상품 사실의
근거가 아닌 연출 슬롯에서만 사용합니다.

## 실행

```bash
PYTHONPATH=src .venv/bin/python scripts/runtime/run_local_detail_page.py \
  --image assets/samples/najeon-box.jpeg \
  --output-dir generated/samples/local_najeon_box \
  --text-provider ollama \
  --text-url http://127.0.0.1:11434 \
  --text-model gemma3:12b \
  --image-provider none
```

생성 결과:

```text
generated/samples/local_najeon_box/
├── detail_page.png
├── react_document.json
├── photos/
├── sections/
└── result_summary.json
```

`photos/`에는 `hero`·`packshot`·`detail` 원본 자산, `lifestyle` 제공 사진 또는
`lifestyle-02` 프롬프트 편집 `generated_scene`, 그리고 제공 사진으로 채우지 못한 역할과
보조 생성에 쓰이는 `detail-02`·`detail-05` 디테일 `generated_view`가 저장될 수 있습니다.
제공 사진 수와 무관하게 보조 생성 컷이 붙으며, `detail-02`는 각도, `detail-03`은 표면
매크로, `detail-04`는 실제 사용 상황, `detail-05`는 에디토리얼 배치입니다. 생성 실패 시
원본 크롭으로 대체됩니다.
`alternate`는 기본 역할을 넘는 제공 사진을 한 장도 버리지 않고 보존하는 슬롯이며, 생성 여부는
`product_generated` 플래그로 구분하고 최종 상품 근거가 아닌 연출 이미지로 취급합니다.

`react_document.json`은 `schemaVersion: "2.0"`, `canvasWidth`, `root[]`를 갖는 JSON AST다.
문서에는 실제 URL·HTML·JSX·이벤트 핸들러를 넣지 않으며 `img.props.imageId`를 `photos/` 또는
BE asset manifest와 연결한다. 서버가 허용 tag·부모/자식 관계·고유 ID·깊이/노드 수를
검증한 뒤 저장한다.

상품 분석만 확인하고 역할별 원본 보존 컷도 만들지 않으려면 다음 옵션을 사용합니다.

```bash
PYTHONPATH=src .venv/bin/python scripts/runtime/run_local_detail_page.py \
  --image assets/samples/najeon-box.jpeg \
  --no-product-photos
```

로컬 Qwen 분석은 외부 검색 API를 호출하지 않습니다. 분석 입력은 원본
이미지와 BE가 전달한 `user_hints`이며, `ProductProfileDto.observations`에는 이미지에서
확인한 색·형태·구성 정보만 기록합니다. 검색이 필요한 최신 정보는 생성 전에 BE가
검수해 `user_hints`로 전달해야 합니다.

## Flux2 Klein 4B 임시 테스트

`Runpod/FLUX.2-klein-4B-mflux-4bit`는 기본 모델을 대체하지 않는 메모리 절약형 비교
프로파일이다. 기본 11234 서버에 4B를 직접 지정하면 image modality 오류가 발생할 수 있으므로,
테스트할 때는 기존 서버를 유지한 채 전용 MLX Serve를 11235에 기동한다.

```bash
"/Applications/MLX Core.app/Contents/MacOS/mlx-serve" serve \
  --model ~/.mlx-serve/models/Runpod/FLUX.2-klein-4B-mflux-4bit \
  --host 127.0.0.1 \
  --port 11235
```

그 다음 텍스트는 11234의 Qwen3.8 27B, 이미지는 11235의 4B를 지정한다.

```bash
PYTHONPATH=.:src .venv/bin/python scripts/runtime/run_local_detail_page.py \
  --image /path/to/product.jpg \
  --output-dir generated/runs/flux2_klein_4b_test \
  --text-provider mlx \
  --text-url http://127.0.0.1:11234 \
  --text-model ddalcu/Qwen3.8-27B-MLX-Serve-4bit \
  --image-provider mlx \
  --image-url http://127.0.0.1:11235 \
  --image-model Runpod/FLUX.2-klein-4B-mflux-4bit
```

직접 endpoint 점검은 `POST /v1/images/generations` 응답의 `200`과 `data[0].b64_json`을
확인한다. 테스트 결과는 [로컬 생성 테스트 기록](local-generation-test-report.md)을 따르며,
4B 생성 컷은 `GENERATED` 생성 자산이므로 원본 상품 근거·대표 상품 사진으로 승인하지 않는다.
