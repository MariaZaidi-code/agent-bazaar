from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.db import connect


def make_key(namespace: str, payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


class Cache:
    def __init__(
        self,
        path: Path,
        ttl_seconds: int = 86_400,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._lock = threading.RLock()
        self._connection = connect(path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        self._connection.commit()

    def get(self, key: str) -> tuple[Any, str] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value, source, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] < self.clock():
                self._connection.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._connection.commit()
                return None
            try:
                return json.loads(row["value"]), row["source"]
            except json.JSONDecodeError:
                return None

    def set(
        self,
        key: str,
        value: Any,
        source: str = "live",
        ttl_seconds: int | None = None,
    ) -> None:
        now = self.clock()
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        payload = json.dumps(value, default=str, sort_keys=True)
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO cache (key, value, source, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (key, payload, source, now, now + ttl),
            )
            self._connection.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._connection.commit()

    def clear(self) -> int:
        with self._lock:
            cursor = self._connection.execute("DELETE FROM cache")
            self._connection.commit()
            return cursor.rowcount

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS total FROM cache").fetchone()
            return int(row["total"])
