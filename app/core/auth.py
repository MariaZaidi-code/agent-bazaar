from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from app.core.db import connect


class AuthManager:
    def __init__(self, db_path: Path, secret: str = "") -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = connect(db_path)
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                csrf_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS favorites (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                tool_id TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saved_tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                encrypted_value TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                action TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()
        key_material = (secret or "agent-bazaar-dev-key").encode("utf-8")
        digest = hashlib.sha256(key_material).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def _hash_password(self, password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()

    def signup(self, email: str, password: str) -> dict[str, Any]:
        email = email.strip().lower()
        if not email or "@" not in email:
            raise ValueError("a valid email is required")
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        salt = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt)
        user_id = "user_" + secrets.token_hex(8)
        now = datetime.now(UTC).isoformat()
        with self._lock:
            try:
                self._connection.execute(
                    "INSERT INTO users (id, email, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, email, password_hash, salt, now),
                )
                self._connection.execute(
                    "INSERT INTO user_settings (user_id, settings_json) VALUES (?, ?)",
                    (user_id, json.dumps({"theme": "light", "offline_mode": False})),
                )
                self._connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("email is already registered") from exc
        self.audit(user_id, "signup", {"email": email})
        return {"id": user_id, "email": email, "created_at": now}

    def login(self, email: str, password: str) -> tuple[str, str]:
        email = email.strip().lower()
        with self._lock:
            row = self._connection.execute(
                "SELECT id, password_hash, salt FROM users WHERE email = ?", (email,)
            ).fetchone()
        if row is None or self._hash_password(password, row["salt"]) != row["password_hash"]:
            raise ValueError("invalid email or password")
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        expires = now + timedelta(days=14)
        with self._lock:
            self._connection.execute(
                "INSERT INTO sessions (token_hash, user_id, csrf_token, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (token_hash, row["id"], csrf_token, now.isoformat(), expires.isoformat()),
            )
            self._connection.commit()
        self.audit(row["id"], "login", {"email": email})
        return token, csrf_token

    def user_from_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.now(UTC).isoformat()
        with self._lock:
            row = self._connection.execute(
                """
                SELECT users.id, users.email, sessions.csrf_token, sessions.expires_at
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "email": row["email"], "csrf_token": row["csrf_token"]}

    def logout(self, token: str | None) -> None:
        if not token:
            return
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            self._connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            self._connection.commit()

    def settings(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT settings_json FROM user_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
        return json.loads(row["settings_json"]) if row else {}

    def update_settings(self, user_id: str, values: dict[str, Any]) -> dict[str, Any]:
        current = self.settings(user_id)
        current.update(values)
        with self._lock:
            self._connection.execute(
                "INSERT INTO user_settings (user_id, settings_json) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET settings_json = excluded.settings_json",
                (user_id, json.dumps(current)),
            )
            self._connection.commit()
        self.audit(user_id, "update_settings", {"keys": sorted(values)})
        return current

    def add_favorite(self, user_id: str, tool_id: str, note: str = "", tags: list[str] | None = None) -> dict[str, Any]:
        favorite_id = "fav_" + secrets.token_hex(8)
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._connection.execute(
                "INSERT INTO favorites (id, user_id, tool_id, note, tags_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (favorite_id, user_id, tool_id, note, json.dumps(tags or []), now),
            )
            self._connection.commit()
        return {
            "id": favorite_id,
            "user_id": user_id,
            "tool_id": tool_id,
            "note": note,
            "tags": tags or [],
            "created_at": now,
        }

    def favorites(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, tool_id, note, tags_json, created_at FROM favorites "
                "WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "tool_id": row["tool_id"],
                "note": row["note"],
                "tags": json.loads(row["tags_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def save_task(self, user_id: str, task_id: str, note: str = "") -> dict[str, Any]:
        saved_id = "saved_" + secrets.token_hex(8)
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._connection.execute(
                "INSERT INTO saved_tasks (id, user_id, task_id, note, created_at) VALUES (?, ?, ?, ?, ?)",
                (saved_id, user_id, task_id, note, now),
            )
            self._connection.commit()
        return {"id": saved_id, "user_id": user_id, "task_id": task_id, "note": note, "created_at": now}

    def saved_tasks(self, user_id: str, query: str = "") -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, task_id, note, created_at FROM saved_tasks WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        items = [
            {
                "id": row["id"],
                "task_id": row["task_id"],
                "note": row["note"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        if query:
            needle = query.lower()
            items = [item for item in items if needle in item["task_id"].lower() or needle in item["note"].lower()]
        return items

    def add_workflow(self, user_id: str, name: str, steps: list[Any]) -> dict[str, Any]:
        workflow_id = "wf_" + secrets.token_hex(8)
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._connection.execute(
                "INSERT INTO workflows (id, user_id, name, steps_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (workflow_id, user_id, name, json.dumps(steps), now),
            )
            self._connection.commit()
        return {"id": workflow_id, "user_id": user_id, "name": name, "steps": steps, "created_at": now}

    def workflows(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, name, steps_json, created_at FROM workflows WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "steps": json.loads(row["steps_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def store_api_key(self, user_id: str, name: str, value: str) -> dict[str, Any]:
        key_id = "key_" + secrets.token_hex(8)
        now = datetime.now(UTC).isoformat()
        encrypted = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        with self._lock:
            self._connection.execute(
                "INSERT INTO api_keys (id, user_id, name, encrypted_value, created_at) VALUES (?, ?, ?, ?, ?)",
                (key_id, user_id, name, encrypted, now),
            )
            self._connection.commit()
        self.audit(user_id, "store_api_key", {"name": name})
        return {"id": key_id, "name": name, "created_at": now}

    def api_keys(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, name, created_at FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [{"id": row["id"], "name": row["name"], "created_at": row["created_at"]} for row in rows]

    def audit(self, user_id: str | None, action: str, detail: dict[str, Any] | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._connection.execute(
                "INSERT INTO audit_log (user_id, action, detail_json, created_at) VALUES (?, ?, ?, ?)",
                (user_id, action, json.dumps(detail or {}, default=str), now),
            )
            self._connection.commit()

    def audit_log(self, user_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            if user_id:
                rows = self._connection.execute(
                    "SELECT user_id, action, detail_json, created_at FROM audit_log "
                    "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT user_id, action, detail_json, created_at FROM audit_log ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "user_id": row["user_id"],
                "action": row["action"],
                "detail": json.loads(row["detail_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
