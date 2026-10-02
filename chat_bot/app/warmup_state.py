"""챗봇 API 워밍업 상태 — LLM 사이드카보다 API가 먼저 뜨는 기동 순서 문제 대응.

배경 (Stage 실측, 2026-10-01):
  같은 파드의 두 컨테이너(chatbot-api, chatbot-llm)는 쿠버네티스가 순서 보장 없이
  동시에 띄운다. 챗봇 API는 몇 초 만에 뜨지만 Ollama는 모델(7.8GB) 적재에 수십~백여
  초가 걸린다. 그래서 lifespan에서 한 번만 시도하던 워밍업이 연결 거부로 실패하고,
  BGE-M3·시스템 프롬프트 캐시가 차가운 채로 첫 사용자를 받았다.

이 모듈은 두 가지를 맡는다.
  1. start_background / run_until_ready: Ollama가 뜰 때까지 워밍업을 백그라운드에서
     재시도한다. 서버 기동은 막지 않는다 — 모델 적재(최대 백여 초)를 lifespan에서
     기다리면 그동안 /ai/health도 응답하지 못해, livenessProbe가 이 컨테이너를
     재시작시키는 루프에 빠질 수 있다.
  2. is_done / mark_done: 워밍업 완료 여부를 readiness(_check_warmup)가 읽게 한다.

무거운 의존성(LLM·DB·임베딩)을 import하지 않아 단위 테스트가 가볍다.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_DEFAULT_MAX_WAIT_SECONDS = 600.0
_DEFAULT_INTERVAL_SECONDS = 5.0

_done = threading.Event()


def is_done() -> bool:
    """앱 워밍업(BGE-M3 로딩 + 시스템 프롬프트 캐시)이 한 번이라도 끝났는가."""
    return _done.is_set()


def mark_done() -> None:
    """워밍업 완료를 기록한다. 대화 중 재예열(main._background_rewarmup)이 성공해도 호출한다."""
    _done.set()


def reset() -> None:
    """테스트용 — 상태를 초기화한다."""
    _done.clear()


def run_until_ready(
    warmup: Callable[[], object],
    *,
    max_wait: float = _DEFAULT_MAX_WAIT_SECONDS,
    interval: float = _DEFAULT_INTERVAL_SECONDS,
    sleep: Callable[[float], object] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    should_stop: Callable[[], bool] = lambda: False,
) -> bool:
    """warmup()이 성공할 때까지 interval 간격으로 재시도한다. 성공하면 True.

    max_wait를 넘기면 실패여도 mark_done()을 호출하고 False를 돌려준다(fail-open).
    readinessProbe가 /ai/ready를 보게 되면, 워밍업이 LLM과 무관한 이유(코드 버그 등)로
    영영 실패할 때 파드가 영구 NotReady가 되어 챗봇 전체가 막히기 때문이다. 이 경우
    콜드 상태로라도 서비스하고, DB·임베딩·LLM 자체의 준비 여부는 readiness의 다른
    확인이 계속 지킨다.

    should_stop()이 True가 되면(앱 종료 시) 준비 상태를 바꾸지 않고 즉시 멈춘다.
    sleep·clock·should_stop은 테스트에서 시간·종료를 흉내 내기 위한 주입점이다.
    """
    deadline = clock() + max_wait
    attempt = 0
    while not should_stop():
        attempt += 1
        try:
            warmup()
        except Exception as exc:  # noqa: BLE001 — 어떤 실패든 재시도 대상이다
            if clock() >= deadline:
                logger.error(
                    "워밍업 시간 초과(%.0f초, %d회 시도) — 콜드 상태로 서비스한다: %s",
                    max_wait,
                    attempt,
                    exc,
                )
                mark_done()  # fail-open: 영구 NotReady 방지(docstring 참고)
                return False
            logger.warning(
                "워밍업 실패(%d회차, LLM 사이드카 미준비 가능) — %.0f초 후 재시도: %s",
                attempt,
                interval,
                exc,
            )
            sleep(interval)
            continue

        mark_done()
        # 앱 로거는 기본 설정에서 INFO가 출력되지 않을 수 있어(uvicorn은 자기 로거만
        # 설정한다) 배포 로그에서 반드시 보이도록 WARNING으로 남긴다.
        logger.warning("워밍업 완료(%d회차)", attempt)
        return True

    logger.warning("워밍업 재시도 중단(앱 종료) — %d회 시도", attempt)
    return False


class BackgroundWarmup:
    """백그라운드 워밍업 스레드 핸들 — lifespan 종료 시 stop()으로 멈춘다."""

    def __init__(self, warmup: Callable[[], object], **kwargs) -> None:
        self._stop = threading.Event()
        kwargs.setdefault(
            "sleep", self._stop.wait
        )  # 종료 신호가 오면 대기 중에도 즉시 깨어남
        kwargs.setdefault("should_stop", self._stop.is_set)
        self.thread = threading.Thread(
            target=run_until_ready,
            args=(warmup,),
            kwargs=kwargs,
            daemon=True,
            name="app-warmup",
        )

    def start(self) -> BackgroundWarmup:
        self.thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self.thread.join(timeout=timeout)


def start_background(warmup: Callable[[], object], **kwargs) -> BackgroundWarmup:
    """run_until_ready를 데몬 스레드로 띄운다. lifespan에서 호출해 기동을 막지 않는다."""
    return BackgroundWarmup(warmup, **kwargs).start()
