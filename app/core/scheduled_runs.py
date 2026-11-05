from __future__ import annotations

import secrets
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.db import connect


class ScheduledRunManager:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = connect(db_path)
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS scheduled_runs (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                next_run TEXT NOT NULL,
                last_run TEXT,
                last_status TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def create(self, task: str, interval_seconds: int = 3600, enabled: bool = True) -> dict[str, Any]:
        run_id = "sched_" + secrets.token_hex(8)
        now = datetime.now(UTC)
        next_run = now + timedelta(seconds=max(60, interval_seconds))
        with self._lock:
            self._connection.execute(
                "INSERT INTO scheduled_runs (id, task, interval_seconds, enabled, next_run, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, task, max(60, interval_seconds), int(enabled), next_run.isoformat(), now.isoformat()),
            )
            self._connection.commit()
        return self.get(run_id) or {}

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM scheduled_runs WHERE id = ?", (run_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM scheduled_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(row) for row in rows]

    def delete(self, run_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute("DELETE FROM scheduled_runs WHERE id = ?", (run_id,))
            self._connection.commit()
            return cursor.rowcount > 0

    def due(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM scheduled_runs WHERE enabled = 1 AND next_run <= ?", (now,)
            ).fetchall()
        return [self._row(row) for row in rows]

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "task": row["task"],
            "interval_seconds": row["interval_seconds"],
            "enabled": bool(row["enabled"]),
            "next_run": row["next_run"],
            "last_run": row["last_run"],
            "last_status": row["last_status"],
            "created_at": row["created_at"],
        }

    async def execute_due(self, services: Any) -> list[dict[str, Any]]:
        results = []
        for run in self.due():
            now = datetime.now(UTC)
            try:
                result = await services.client.run(run["task"])
                status = getattr(result, "status", "completed")
                status_value = status.value if hasattr(status, "value") else str(status)
            except Exception as exc:  # pragma: no cover - defensive boundary
                status_value = f"error: {exc}"
            next_run = now + timedelta(seconds=run["interval_seconds"])
            with self._lock:
                self._connection.execute(
                    "UPDATE scheduled_runs SET last_run = ?, last_status = ?, next_run = ? WHERE id = ?",
                    (now.isoformat(), status_value, next_run.isoformat(), run["id"]),
                )
                self._connection.commit()
            results.append({"id": run["id"], "status": status_value})
        return results

    async def run_now(self, run_id: str, services: Any) -> dict[str, Any]:
        run = self.get(run_id)
        if run is None:
            raise ValueError("scheduled run not found")
        self.execute_due.__wrapped__ if hasattr(self.execute_due, "__wrapped__") else None
        # Execute one run directly.
        now = datetime.now(UTC)
        try:
            result = await services.client.run(run["task"])
            status = getattr(result, "status", "completed")
            status_value = status.value if hasattr(status, "value") else str(status)
        except Exception as exc:  # pragma: no cover - defensive boundary
            status_value = f"error: {exc}"
        next_run = now + timedelta(seconds=run["interval_seconds"])
        with self._lock:
            self._connection.execute(
                "UPDATE scheduled_runs SET last_run = ?, last_status = ?, next_run = ? WHERE id = ?",
                (now.isoformat(), status_value, next_run.isoformat(), run_id),
            )
            self._connection.commit()
        return {"id": run_id, "status": status_value}
