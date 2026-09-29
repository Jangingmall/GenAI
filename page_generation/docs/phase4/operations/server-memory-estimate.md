# Mac 로컬 통합 메모리 기준 산정

작성일: 2026-09-08

적용 범위: Apple Silicon Mac에서 실행하는 로컬 개발 구성(MLX Serve)입니다. Ubuntu 서버 운영의
NVIDIA L40S 48GB 메모리 예산은 이 문서에서 다시 계산하지 않으며, [SGLang 서빙 운영 조사](sglang-serving-research.md)와
[Ubuntu 배포 가이드](ubuntu-deployment.md)를 기준으로 확인합니다.

현재 구현은 제품 전체를 생성형 이미지 모델로 다시 그리지 않는다. 제품 사진은 원본 RGB와
알파 마스크를 Pillow로 합성하고, FE용 `react_document` AST는 in-process builder/validator로
조립·검증한다. HTML/CSS 페이지는 Playwright로 캡처한다. 모델 추론과
선택적 배경·연출 컷 생성은 로컬 MLX Serve의 Qwen과 Flux가 담당한다.

아래 수치는 실제 부하 테스트 전의 설계 추정치다. Apple Silicon에서는 CPU와 GPU가 통합
메모리를 공유하므로 모델별 resident memory와 swap 발생 여부를 장비에서 직접 측정해야 한다.

## 결론

| 구성 | 설계상 피크 범위 | 운영 판단 |
| --- | ---: | --- |
| API/worker + 원본 합성 + HTML 캡처 | 2~6GB | 8GB 이상에서 단일 작업부터 검증 |
| Qwen3.8 27B 4-bit MLX 추가 | 미측정 | 현재 로컬 기본 모델이며 장비에서 resident memory 측정 필요 |
| Flux2 Klein 9B 4-bit MLX 추가 | 8~16GB | 이미지 작업 시 별도 피크 측정 |
| Flux2 Klein 4B 4-bit MLX 추가 | 미측정 | 11235 전용 endpoint smoke test만 완료; 9B 추정치를 대체하지 않음 |
| Qwen과 Flux를 같은 로컬 서버에서 사용 | 미측정 | 두 모델 동시 상주 조건은 장비에서 별도 측정 |

모델 크기, 이미지 해상도, 컨텍스트 길이, HTML 높이, Chromium 프로세스 수, 동시 작업 수에
따라 실제 값은 크게 달라질 수 있다. 모델을 동시에 상주시키는지 요청 사이에 unload하는지도
반드시 같은 조건으로 비교한다.

## 프로세스별 예상치

### API·worker·원본 합성

| 항목 | 예상 메모리 |
| --- | ---: |
| FastAPI/작업 worker | 0.3~1GB |
| Pillow 원본·마스크·배경 버퍼 | 0.2~1GB |
| Playwright/Chromium HTML 캡처 | 0.5~2GB |
| SQLite·파일 캐시·안전 여유 | 1~2GB |
| **일반적인 피크** | **2~6GB** |

제품 사진 여러 장을 동시에 만들지 않고 작업 동시성을 1~2로 시작하면 메모리 경계를
관리하기 쉽다. 전체 PNG와 섹션 PNG를 메모리에 동시에 유지하지 말고 파일 기반 저장을
우선한다.

### Qwen3.8 27B 4-bit MLX

`LOCAL_TEXT_MODEL`의 `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` 가중치, 이미지 입력 버퍼, KV
cache를 포함한 값은 MLX Serve 로그와 macOS 메모리 측정값으로 확정한다. 이 문서에는 Qwen
27B에 대한 사전 peak 수치를 새로 산정하지 않으며, 긴 프롬프트와 동시 요청에서는 실제 값이
더 커질 수 있다.

### Flux2 Klein 9B 4-bit MLX

`LOCAL_IMAGE_MODEL`은 제품 원본을 다시 그리는 데 사용하지 않고, 제품 없는 배경 또는
연출 참고 컷 생성에만 사용한다. 생성 요청의 해상도와 단계 수가 커질수록 이미지 모델의
피크가 증가하므로, 생성 중 API worker와 Chromium을 함께 실행하는 조건을 측정한다.

### Flux2 Klein 4B 비교 프로파일

`Runpod/FLUX.2-klein-4B-mflux-4bit`는 2026-09-07에 `127.0.0.1:11235` 전용 MLX Serve로
기동해 이미지 endpoint 응답과 상세페이지 2건을 확인했다. 프로세스 peak memory와 p95는
기록하지 않았으므로 4B의 실제 메모리 예산은 미확정이다. 4B는 개발 비교용으로만 사용하고,
운영 기본값·9B의 설계 추정치·동시성 판단을 자동으로 바꾸지 않는다.

React AST builder/validator와 `react_document.json` 직렬화는 모델을 추가 상주시킬 필요가 없는
작은 in-process 단계로, 현재 메모리 추정의 API/worker·파일 저장 범주에 포함한다. 다만 큰
문서의 노드 수·JSON 직렬화 비용은 실제 output height와 함께 측정한다.

## 배치 권장

### 개발용 통합 장비

- MLX Serve: `127.0.0.1:11234`에 바인딩
- 텍스트 모델: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`
- 이미지 모델: `mlx-community/flux2-klein-9b-4bit`
- 비교 테스트 이미지 모델: `Runpod/FLUX.2-klein-4B-mflux-4bit` (전용 `127.0.0.1:11235`, 필요 시에만)
- API/worker: 기본 동시성 1, 메모리 압력 시 신규 작업을 큐에 적재
- 32GB 통합 메모리부터 검증하고, swap이 발생하면 동시성을 늘리지 않음

### 역할별 분리

API/worker와 모델 서버를 별도 로컬 장비에 둘 수 있다. 이 경우 모델 서버는 로컬망에서만
접근 가능하게 하고, API는 `LOCAL_TEXT_URL`과 `LOCAL_IMAGE_URL`만 사용한다. 외부 모델 API,
클라우드 자격 증명, 원본 이미지의 외부 전송은 운영 경로에 포함하지 않는다.

## 측정 체크리스트

- 이미지 512/1024/2048px와 상세페이지 높이별 RSS 및 통합 메모리 peak
- Qwen 첫 로딩·첫 이미지 추론·반복 추론의 peak와 p95 처리시간
- Flux 생성 해상도·단계 수별 peak와 실패율
- Chromium 프로세스 수와 캡처 중 peak
- 동시 작업 1/2/4의 Pillow·SQLite·파일 저장 사용량
- 모델 두 개를 동시에 상주시킨 경우와 순차 실행한 경우의 차이
- swap 발생 여부, 로컬 서버 timeout, 작업별 처리시간 p95
