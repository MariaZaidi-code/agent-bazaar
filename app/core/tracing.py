from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.db import connect
from app.schemas import BaseMessage, TaskResult, TraceEvent, utcnow


class TraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._connection = connect(path)
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trace_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                summary TEXT NOT NULL,
                data_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trace_task ON trace_events(task_id, seq);
            CREATE TABLE IF NOT EXISTS task_results (
                task_id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                kind TEXT NOT NULL,
                sender TEXT NOT NULL,
                recipient TEXT,
                timestamp TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def add_event(
        self,
        task_id: str,
        event_type: str,
        actor: str,
        summary: str,
        data: dict[str, Any] | None = None,
    ) -> TraceEvent:
        timestamp = utcnow()
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(seq), 0) AS seq FROM trace_events WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            seq = int(row["seq"]) + 1
            self._connection.execute(
                """
                INSERT INTO trace_events
                    (task_id, seq, timestamp, event_type, actor, summary, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    seq,
                    timestamp.isoformat(),
                    event_type,
                    actor,
                    summary,
                    json.dumps(data or {}, default=str),
                ),
            )
            self._connection.commit()
        return TraceEvent(
            task_id=task_id,
            seq=seq,
            timestamp=timestamp,
            event_type=event_type,
            actor=actor,
            summary=summary,
            data=data or {},
        )

    def events(self, task_id: str) -> list[TraceEvent]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM trace_events WHERE task_id = ? ORDER BY seq", (task_id,)
            ).fetchall()
        events = []
        for row in rows:
            events.append(
                TraceEvent(
                    task_id=row["task_id"],
                    seq=row["seq"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    event_type=row["event_type"],
                    actor=row["actor"],
                    summary=row["summary"],
                    data=json.loads(row["data_json"]),
                )
            )
        return events

    def save_result(self, result: TaskResult) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO task_results (task_id, task, status, result_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    task = excluded.task,
                    status = excluded.status,
                    result_json = excluded.result_json,
                    created_at = excluded.created_at
                """,
                (
                    result.task_id,
                    result.task,
                    result.status.value,
                    result.model_dump_json(),
                    result.created_at.isoformat(),
                ),
            )
            self._connection.commit()

    def get_result(self, task_id: str) -> TaskResult | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT result_json FROM task_results WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        return TaskResult.model_validate_json(row["result_json"])

    def list_results(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT task_id, task, status, created_at
                FROM task_results
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def result_rows(self, limit: int = 2000) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT task_id, task, status, result_json, created_at
                FROM task_results
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def log_message(self, message: BaseMessage, task_id: str | None = None) -> None:
        payload = message.model_dump(mode="json")
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO messages (task_id, kind, sender, recipient, timestamp, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    message.kind,
                    message.sender,
                    message.recipient,
                    message.timestamp.isoformat(),
                    json.dumps(payload, default=str),
                ),
            )
            self._connection.commit()

    def messages(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM messages WHERE task_id = ? ORDER BY id", (task_id,)
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]
