# 챗봇 API·LLM 인계 계약

기준: `Jangingmall/GenAI` main `535f1ac` · 2026-09-19

## 이미지 경계

챗봇 API 이미지는 ECR `jangin-ai/ollama`에 커밋 SHA 태그로 발행한다. 저장소 이름과
달리 현재 `chat_bot/Dockerfile`에는 Ollama, SGLang, 모델 가중치가 들어 있지 않다.
이미지는 Python 3.11 FastAPI API와 CPU용 BGE-M3 실행 코드만 포함하며, LLM은 Native가
T4 Pod의 별도 컨테이너로 배치한다. API 컨테이너에는 GPU를 할당하지 않는다.

## API 컨테이너 실행값

| 항목 | 값 |
| --- | --- |
| Port | `8000` |
| Liveness | `GET /ai/health` — 기존 응답 계약 유지 |
| Readiness | `GET /ai/ready` — DB·BGE-M3 파일·LLM 모델 목록 검사 |
| BGE-M3 mount | `/models/bge-m3` |
| BGE-M3 model | `BAAI/bge-m3` |
| BGE-M3 revision | `5617a9f61b028005a4858fdac845db406aefb181` |
| BGE-M3 dimension | `1024` |
| BGE-M3 runtime subset | 약 `2.30 GB` / `2.14 GiB` |
| Secret file | `DB_PASSWORD_FILE=/mnt/secrets-store/password` |

`DB_PASSWORD_FILE`이 설정되면 파일의 내용이 `DB_PASSWORD`보다 우선한다. 파일을 읽을
수 없으면 설정 오류로 시작을 중단한다. Native는 Secret Store CSI 경로를 해당 환경변수에
연결해야 한다.

## LLM 클라이언트 계약

현재 코드가 지원하는 연결 방식은 아래 세 가지다.

| `LLM_BACKEND` | Base URL 변수 | 호출 | 모델 목록 readiness |
| --- | --- | --- | --- |
| `ollama` | `OLLAMA_HOST` | `POST /api/chat` | `GET /api/tags` |
| `sglang` | `SGLANG_HOST` | `POST /v1/chat/completions` | `GET /v1/models` |
| `mlx-serve` | `MLX_SERVE_HOST` | `POST /v1/chat/completions` | `GET /v1/models` |

모든 환경에서 `LLM_MODEL`은 모델 목록의 `name` 또는 `id`와 일치해야 한다. SGLang과
MLX Serve는 OpenAI 호환 JSON schema 응답을 사용한다. Gemma 계열의 system role 제약을
피하기 위해 요청 시 첫 system message를 첫 user message에 합친다.

## Native/모델 담당 추가 인계 필요

다음 값은 현재 저장소에서 임의로 확정하지 않았다.

- 최종 LLM 엔진 및 공식 이미지 이름
- 이미지 버전과 immutable digest
- 모델 이름, 양자화/정밀도, 모델 파일 크기
- T4 16GB에서 사용하는 실행 command와 port
- LLM 컨테이너 health/readiness endpoint
- T4에서의 실제 VRAM·host CPU/RAM·응답 시간 측정 결과
- API 컨테이너와 같은 Pod에서 LLM 컨테이너만 `nvidia.com/gpu: 1`을 할당하는지 여부

현재 앱은 LLM 서버를 자동으로 띄우거나 모델을 다운로드하지 않는다. 위 계약을 받으면
Native가 별도 LLM 컨테이너와 `/ai/ready` probe를 연결한다.
