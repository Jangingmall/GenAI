# GenAI 이미지 용량·자원 점검

기준: `Jangingmall/GenAI` main `535f1ac` 기반 · `linux/amd64` 로컬 검증 · 2026-09-19

## 이미지 빌드 결과

| 서비스 | Dockerfile / context | ECR | 로컬 이미지 크기 | 검증 |
| --- | --- | --- | ---: | --- |
| 상세페이지 통합 | `page_generation/deploy/sglang/Dockerfile` / `page_generation` | `jangin-ai/sglang` | 16,612,710,340 bytes ≈ **15.47 GiB** | 전체 build 성공 |
| 챗봇 API | `chat_bot/Dockerfile` / `chat_bot` | `jangin-ai/ollama` | 635,286,596 bytes ≈ **0.59 GiB** | 전체 build 성공 |

두 이미지는 모델 가중치를 이미지에 넣지 않는다. 위 용량은 Docker의 로컬
uncompressed image size이며, ECR의 실제 압축 layer 저장·전송 크기와는 다르다.
두 이미지 모두 `linux/amd64`로 빌드·inspect했다.

## 컨테이너 메모리 기준선

모델 서버를 시작하지 않은 API-only 상태에서 측정한 샘플이다.

| 서비스 | 실행 상태 | 측정 RSS |
| --- | --- | ---: |
| 상세페이지 | `serve-ai`만 기동, SGLang 미기동 | 약 **62.29 MiB** |
| 챗봇 API | 기본 entrypoint 기동, DB/LLM 연결 실패 상태 | 약 **73.52 MiB** |

상세페이지의 실제 L40S VRAM은 모델 적재 후 별도 측정해야 한다. 저장소의 EKS
명세 기준 계산값은 Qwen 텍스트 약 19.6 GiB, FLUX 이미지 약 10.2 GiB, 텍스트
서버 정적 선점 포함 약 32.6 GiB이며, L40S 가용 VRAM 44.7 GiB 기준 약 12 GiB가
남는다는 추정이다. 이는 GPU에서 실제 추론을 성공시킨 수치가 아니다.

챗봇 API는 CPU용 BGE-M3 실행 코드만 포함한다. BGE-M3는 `/models/bge-m3`에
마운트하며, 고정 revision `5617a9f61b028005a4858fdac845db406aefb181`, CPU
SentenceTransformers subset 약 2.30 GB(2.14 GiB)다. T4 LLM은 별도 컨테이너이므로
최종 엔진·정밀도·VRAM·CPU/RAM은 [챗봇 LLM 인계 문서](./chatbot-llm-handoff-2026-09-19.md)의
미확정 항목을 받은 후 측정한다.

## CI runner 요구량

상세페이지 이미지는 15.47 GiB이므로 BuildKit 임시 layer와 base/cache를 포함해
최소 **35 GiB free disk**를 workflow preflight 기준으로 잡았다. 챗봇은 안전 여유를
포함해 10 GiB를 기준으로 잡았다. 현재 workflow는 부족하면 ECR 인증 전에 Summary와
오류로 중단한다.

PR과 main 모두 정확한 context/file로 `linux/amd64` build를 사용한다. `ubuntu-24.04`
표준 runner가 35 GiB를 제공하지 못하면 상세페이지 job은 성공한 것으로 처리하지
않고, larger/self-hosted runner로 교체해야 한다.

## 실행 확인 범위

- 상세페이지: 전체 이미지 build 성공, `npm`/`npx` 실행, SGLang Python 경로,
  `DRY_RUN=1` entrypoint, API-only `/health=200`을 확인했다.
- 챗봇: 전체 이미지 build 성공, 앱 import, `/ai/health=200`, DB·모델·LLM이 없는
  상태의 `/ai/ready=503`을 확인했다.
- 실제 L40S/T4 GPU 적재·추론, DB 연결, BGE-M3 임베딩, 별도 LLM 호출은 AWS/GPU와
  Native가 제공할 모델·Secret·DB가 필요하므로 아직 검증하지 않았다.
