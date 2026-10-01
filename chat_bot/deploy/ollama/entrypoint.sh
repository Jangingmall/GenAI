#!/bin/sh
# Ollama 서버를 띄운 뒤, 실제 챗봇 API(app/pipeline/llm.py)가 쓰는 것과 동일한 옵션
# (num_ctx=16384, keep_alive=-1)으로 모델을 미리 로딩한다.
#
# 이게 없으면: LLM 사이드카만 재시작됐을 때(챗봇 API 파드 전체 워밍업은 안 도는 경우)
# 모델이 메모리에 없는 채로 "서버는 떠있다"는 이유만으로 준비 완료 취급되고, 첫
# 사용자 요청이 콜드 로딩(수십~백 초)을 그대로 떠안는다(Stage 실측 확인, 2026-10-01).
#
# 사전 로딩 호출이 실제 앱과 다른 num_ctx로 모델을 올리면, 모델은 로딩됐는데도
# readiness 체크(또는 /api/ps 기준 확인)가 기대하는 context 길이와 달라 계속
# "준비 안 됨"으로 남는 새 버그가 생길 수 있어 반드시 같은 옵션을 써야 한다.
set -e

ollama serve &
SERVE_PID=$!

# 서버가 요청을 받을 수 있을 때까지 대기(최대 60초)
i=0
until ollama list >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "entrypoint: ollama serve가 60초 안에 뜨지 않음" >&2
    exit 1
  fi
  sleep 1
done

echo "entrypoint: ${OLLAMA_MODEL} 사전 로딩 시작(num_ctx=16384, keep_alive=-1)"
PRELOAD_RESPONSE=$(curl -sf http://127.0.0.1:11434/api/chat \
  -d "{\"model\":\"${OLLAMA_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"keep_alive\":-1,\"stream\":false,\"options\":{\"num_ctx\":16384}}")

# message.content가 비어있지 않은지까지 확인 — 단순히 HTTP 200만으로는 "진짜 생성
# 성공"을 보장 못 한다(이미 F-? 조사에서 확인된 패턴과 같은 이유).
echo "$PRELOAD_RESPONSE" | grep -q '"content":"' || {
  echo "entrypoint: 모델 사전 로딩 응답에 content가 없음 — $PRELOAD_RESPONSE" >&2
  exit 1
}

echo "entrypoint: ${OLLAMA_MODEL} 사전 로딩 완료"

wait "$SERVE_PID"
