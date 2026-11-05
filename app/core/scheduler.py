from __future__ import annotations

import threading
from collections.abc import Callable


class BackgroundScheduler:
    def __init__(self, interval_seconds: float = 300.0) -> None:
        self.interval_seconds = max(1.0, interval_seconds)
        self._callbacks: list[Callable[[], None]] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def register(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="agent-bazaar-scheduler", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            for callback in list(self._callbacks):
                try:
                    callback()
                except Exception:
                    pass

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
