from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any

from app.schemas import new_id, utcnow


class JobManager:
    def __init__(self, max_workers: int = 2) -> None:
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="ab-job")
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, kind: str, function: Callable[..., Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        job_id = new_id("job")
        job = {
            "id": job_id,
            "kind": kind,
            "status": "queued",
            "created_at": utcnow().isoformat(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": "",
        }
        with self._lock:
            self._jobs[job_id] = job
        future = self._executor.submit(self._run, job_id, function, args, kwargs)
        future.add_done_callback(lambda completed: self._finished(job_id, completed))
        return dict(job)

    def _run(
        self,
        job_id: str,
        function: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        with self._lock:
            self._jobs[job_id]["status"] = "running"
            self._jobs[job_id]["started_at"] = utcnow().isoformat()
        return function(*args, **kwargs)

    def _finished(self, job_id: str, future: Future[Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["finished_at"] = utcnow().isoformat()
            error = future.exception()
            if error is None:
                job["status"] = "completed"
                job["result"] = future.result()
            else:
                job["status"] = "failed"
                job["error"] = str(error)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda item: str(item["created_at"]),
                reverse=True,
            )[:limit]
            return [dict(job) for job in jobs]

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def elapsed_ms(started: datetime, finished: datetime | None = None) -> float:
    end = finished or utcnow()
    return (end - started).total_seconds() * 1000.0
