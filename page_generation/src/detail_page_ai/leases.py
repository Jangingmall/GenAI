from __future__ import annotations

from threading import Event, Thread
from typing import Callable

from .persistence import LeaseOwnershipError


class LeaseHeartbeat:
    """Renew a claimed record while one blocking provider operation is running."""

    def __init__(
        self,
        renew: Callable[[], bool],
        *,
        interval_seconds: float,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._renew = renew
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self._lost = Event()
        self._thread: Thread | None = None

    def __enter__(self) -> "LeaseHeartbeat":
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def ensure_active(self) -> None:
        if self._lost.is_set():
            raise LeaseOwnershipError("lease ownership was lost")

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                renewed = self._renew()
            except Exception:
                renewed = False
            if not renewed:
                self._lost.set()
                return
