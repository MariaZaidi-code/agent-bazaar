from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.db import connect

SESSION_COOKIE = "ab_session"
WORKSPACE_COOKIE = "ab_workspace"
DEMO_USER_ID = "user_demo"
DEMO_WORKSPACE_ID = "ws_demo"
SESSION_DAYS = 30


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime | None = None) -> str:
    return (value or utcnow()).isoformat()


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 210_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${b64(salt)}${b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, digest = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = unb64(digest)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), unb64(salt), int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def encrypt_secret(secret: bytes, plaintext: str) -> str:
    nonce = secrets.token_bytes(16)
    cipher = _xor_stream(secret, nonce, plaintext.encode("utf-8"))
    tag = hmac.new(secret, nonce + cipher, hashlib.sha256).digest()
    return f"v1${b64(nonce)}${b64(cipher)}${b64(tag)}"


def decrypt_secret(secret: bytes, payload: str) -> str:
    try:
        version, nonce, cipher, tag = payload.split("$", 3)
        if version != "v1":
            raise ValueError("unsupported secret version")
        nonce_bytes = unb64(nonce)
        cipher_bytes = unb64(cipher)
        expected = hmac.new(secret, nonce_bytes + cipher_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, unb64(tag)):
            raise ValueError("secret integrity check failed")
        return _xor_stream(secret, nonce_bytes, cipher_bytes).decode("utf-8")
    except (ValueError, TypeError) as exc:
        raise ValueError("stored credential could not be decrypted") from exc


def _xor_stream(secret: bytes, nonce: bytes, data: bytes) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < len(data):
        block = hashlib.sha256(secret + nonce + counter.to_bytes(8, "big")).digest()
        output.extend(block)
        counter += 1
    return bytes(left ^ right for left, right in zip(data, output, strict=False))


def pdf_document(title: str, lines: list[str]) -> bytes:
    escaped_title = _pdf_text(title)
    body = [f"BT /F1 16 Tf 50 780 Td ({escaped_title}) Tj ET"]
    y = 752
    for line in lines:
        for chunk in _wrap_pdf_line(line):
            body.append(f"BT /F1 10 Tf 50 {y} Td ({_pdf_text(chunk)}) Tj ET")
            y -= 14
            if y < 50:
                break
        if y < 50:
            break
    content = "\n".join(body).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def _pdf_text(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def _wrap_pdf_line(value: str, width: int = 92) -> list[str]:
    words = str(value).split()
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        if length + len(word) + 1 > width and current:
            lines.append(" ".join(current))
            current = []
            length = 0
        current.append(word)
        length += len(word) + 1
    lines.append(" ".join(current) or " ")
    return lines


class PlatformStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._connection = connect(path)
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS platform_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memberships (
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'viewer',
                PRIMARY KEY (user_id, workspace_id)
            );
            CREATE TABLE IF NOT EXISTS favorites (
                user_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                tool_id TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, workspace_id, tool_id)
            );
            CREATE TABLE IF NOT EXISTS saved_tasks (
                saved_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (user_id, workspace_id, task_id)
            );
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                name TEXT NOT NULL,
                task TEXT NOT NULL,
                document_id TEXT,
                plan_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shares (
                token TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                user_id TEXT PRIMARY KEY,
                theme TEXT NOT NULL DEFAULT 'dark',
                offline_mode INTEGER NOT NULL DEFAULT 1,
                notifications INTEGER NOT NULL DEFAULT 1,
                high_contrast INTEGER NOT NULL DEFAULT 0,
                workspace_id TEXT NOT NULL DEFAULT 'ws_demo',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'info',
                read_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feature_flags (
                name TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                description TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS webhooks (
                webhook_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                url TEXT NOT NULL,
                event TEXT NOT NULL DEFAULT 'task.completed',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scheduled_runs (
                schedule_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                task TEXT NOT NULL,
                cadence TEXT NOT NULL DEFAULT 'daily',
                next_run_at TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_overrides (
                tool_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tool_id, field_name)
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                ciphertext TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, provider)
            );
            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at DESC);
            """
        )
        self._connection.commit()
        self._ensure_demo()
        self._seed_flags()

    def _secret(self) -> bytes:
        row = self._connection.execute(
            "SELECT value FROM platform_meta WHERE key = 'secret'"
        ).fetchone()
        if row:
            return unb64(row["value"])
        value = secrets.token_bytes(32)
        self._connection.execute(
            "INSERT INTO platform_meta (key, value) VALUES ('secret', ?)", (b64(value),)
        )
        self._connection.commit()
        return value

    def _ensure_demo(self) -> None:
        now = iso()
        with self._lock:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO users
                    (user_id, email, display_name, password_hash, is_admin, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (DEMO_USER_ID, "demo@agentbazaar.local", "Demo explorer", "", now),
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO workspaces (workspace_id, name, created_at) VALUES (?, ?, ?)",
                (DEMO_WORKSPACE_ID, "Acme Engineering", now),
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO memberships (user_id, workspace_id, role)
                VALUES (?, ?, 'admin')
                """,
                (DEMO_USER_ID, DEMO_WORKSPACE_ID),
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO settings
                    (user_id, theme, offline_mode, notifications, high_contrast, workspace_id, updated_at)
                VALUES (?, 'dark', 1, 1, 0, ?, ?)
                """,
                (DEMO_USER_ID, DEMO_WORKSPACE_ID, now),
            )
            self._connection.execute(
                """
                INSERT INTO notifications (user_id, workspace_id, title, body, kind, created_at)
                SELECT ?, ?, ?, ?, 'info', ?
                WHERE NOT EXISTS (SELECT 1 FROM notifications WHERE user_id = ?)
                """,
                (
                    DEMO_USER_ID,
                    DEMO_WORKSPACE_ID,
                    "Welcome to Agent Bazaar",
                    "Start with a starter question, then save the runs you want to keep.",
                    now,
                    DEMO_USER_ID,
                ),
            )
            self._connection.commit()

    def _seed_flags(self) -> None:
        flags = {
            "marketplace": ("Search and inspect the tool catalogue.", 1),
            "sharing": ("Create read-only share links for task results.", 1),
            "analytics": ("Show usage and provider health dashboards.", 1),
            "webhooks": ("Send completion events to registered webhooks.", 1),
            "scheduled_runs": ("Allow saved tasks to be scheduled.", 0),
            "high_contrast": ("Offer the high-contrast theme.", 1),
        }
        with self._lock:
            for name, (description, enabled) in flags.items():
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO feature_flags (name, enabled, description)
                    VALUES (?, ?, ?)
                    """,
                    (name, enabled, description),
                )
            self._connection.commit()

    def user(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT user_id, email, display_name, is_admin, created_at FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()
        return dict(row) if row else None

    def create_user(self, email: str, password: str, display_name: str, workspace_name: str = "") -> dict[str, Any]:
        normalized = email.strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("Enter a valid email address.")
        if len(password) < 8:
            raise ValueError("Use at least 8 characters for the password.")
        if self.user_by_email(normalized):
            raise ValueError("An account with that email already exists.")
        user_id = f"user_{secrets.token_hex(8)}"
        workspace_id = f"ws_{secrets.token_hex(8)}"
        now = iso()
        name = display_name.strip() or normalized.split("@")[0]
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO users (user_id, email, display_name, password_hash, is_admin, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (user_id, normalized, name, hash_password(password), now),
            )
            self._connection.execute(
                "INSERT INTO workspaces (workspace_id, name, created_at) VALUES (?, ?, ?)",
                (workspace_id, workspace_name.strip() or f"{name}'s workspace", now),
            )
            self._connection.execute(
                "INSERT INTO memberships (user_id, workspace_id, role) VALUES (?, ?, 'admin')",
                (user_id, workspace_id),
            )
            self._connection.execute(
                """
                INSERT INTO settings
                    (user_id, theme, offline_mode, notifications, high_contrast, workspace_id, updated_at)
                VALUES (?, 'dark', 1, 1, 0, ?, ?)
                """,
                (user_id, workspace_id, now),
            )
            self._connection.commit()
        self.audit(user_id, workspace_id, "account.created", normalized)
        self.notify(user_id, workspace_id, "Account ready", "Your workspace is ready for saved tasks and favorites.")
        return {"user": self.user(user_id), "workspace_id": workspace_id}

    def login(self, email: str, password: str) -> tuple[str, dict[str, Any]] | None:
        row = self.user_by_email(email)
        if not row or not verify_password(password, row["password_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        now = utcnow()
        with self._lock:
            self._connection.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, row["user_id"], now.isoformat(), (now + timedelta(days=SESSION_DAYS)).isoformat()),
            )
            self._connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(),))
            self._connection.commit()
        return token, self.user(row["user_id"]) or {}

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
            self._connection.commit()

    def session_user(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self._lock:
            row = self._connection.execute(
                """
                SELECT u.user_id, u.email, u.display_name, u.is_admin, u.created_at, s.expires_at
                FROM sessions s JOIN users u ON u.user_id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
        if not row or row["expires_at"] < utcnow().isoformat():
            return None
        return dict(row)

    def workspaces(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT w.workspace_id, w.name, m.role, w.created_at
                FROM memberships m JOIN workspaces w ON w.workspace_id = m.workspace_id
                WHERE m.user_id = ? ORDER BY w.created_at
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def workspace(self, workspace_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT workspace_id, name, created_at FROM workspaces WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_workspace(self, user_id: str, name: str) -> dict[str, Any]:
        clean = name.strip()
        if not clean:
            raise ValueError("Give the workspace a name.")
        workspace_id = f"ws_{secrets.token_hex(8)}"
        now = iso()
        with self._lock:
            self._connection.execute(
                "INSERT INTO workspaces (workspace_id, name, created_at) VALUES (?, ?, ?)",
                (workspace_id, clean, now),
            )
            self._connection.execute(
                "INSERT INTO memberships (user_id, workspace_id, role) VALUES (?, ?, 'admin')",
                (user_id, workspace_id),
            )
            self._connection.commit()
        return {"workspace_id": workspace_id, "name": clean, "role": "admin", "created_at": now}

    def member_role(self, user_id: str, workspace_id: str) -> str:
        with self._lock:
            row = self._connection.execute(
                "SELECT role FROM memberships WHERE user_id = ? AND workspace_id = ?",
                (user_id, workspace_id),
            ).fetchone()
        return str(row["role"]) if row else "viewer"

    def preferred_workspace(self, user_id: str) -> str:
        with self._lock:
            row = self._connection.execute(
                "SELECT workspace_id FROM settings WHERE user_id = ?", (user_id,)
            ).fetchone()
        workspace_id = str(row["workspace_id"]) if row else ""
        if workspace_id and self.member_role(user_id, workspace_id) != "viewer":
            return workspace_id
        rows = self.workspaces(user_id)
        for workspace in rows:
            if workspace["role"] != "viewer":
                return str(workspace["workspace_id"])
        return str(rows[0]["workspace_id"]) if rows else DEMO_WORKSPACE_ID

    def settings(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            now = iso()
            with self._lock:
                self._connection.execute(
                    """
                    INSERT INTO settings
                        (user_id, theme, offline_mode, notifications, high_contrast, workspace_id, updated_at)
                    VALUES (?, 'dark', 1, 1, 0, ?, ?)
                    """,
                    (user_id, self.preferred_workspace(user_id), now),
                )
                self._connection.commit()
            row = self._connection.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
        data = dict(row)
        data["offline_mode"] = bool(data["offline_mode"])
        data["notifications"] = bool(data["notifications"])
        data["high_contrast"] = bool(data["high_contrast"])
        return data

    def update_settings(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.settings(user_id)
        theme = str(payload.get("theme", current["theme"]))
        if theme not in {"dark", "light", "contrast", "system"}:
            theme = "dark"
        workspace_id = str(payload.get("workspace_id", current["workspace_id"]))
        if self.member_role(user_id, workspace_id) == "viewer":
            workspace_id = current["workspace_id"]
        with self._lock:
            self._connection.execute(
                """
                UPDATE settings SET theme = ?, offline_mode = ?, notifications = ?,
                    high_contrast = ?, workspace_id = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    theme,
                    int(bool(payload.get("offline_mode", current["offline_mode"]))),
                    int(bool(payload.get("notifications", current["notifications"]))),
                    int(bool(payload.get("high_contrast", current["high_contrast"]))),
                    workspace_id,
                    iso(),
                    user_id,
                ),
            )
            self._connection.commit()
        self.audit(user_id, workspace_id, "settings.updated", "Preferences saved.")
        return self.settings(user_id)

    def favorites(self, user_id: str, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT tool_id, note, tags, created_at FROM favorites
                WHERE user_id = ? AND workspace_id = ? ORDER BY created_at DESC
                """,
                (user_id, workspace_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_favorite(
        self, user_id: str, workspace_id: str, tool_id: str, note: str = "", tags: str = ""
    ) -> dict[str, Any]:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO favorites (user_id, workspace_id, tool_id, note, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, workspace_id, tool_id) DO UPDATE SET
                    note = excluded.note, tags = excluded.tags
                """,
                (user_id, workspace_id, tool_id, note, tags, iso()),
            )
            self._connection.commit()
        self.audit(user_id, workspace_id, "tool.saved", tool_id)
        return {"tool_id": tool_id, "note": note, "tags": tags}

    def remove_favorite(self, user_id: str, workspace_id: str, tool_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM favorites WHERE user_id = ? AND workspace_id = ? AND tool_id = ?",
                (user_id, workspace_id, tool_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def saved_tasks(self, user_id: str, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT saved_id, task_id, title, created_at FROM saved_tasks
                WHERE user_id = ? AND workspace_id = ? ORDER BY created_at DESC
                """,
                (user_id, workspace_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_task(self, user_id: str, workspace_id: str, task_id: str, title: str) -> dict[str, Any]:
        saved_id = f"save_{secrets.token_hex(8)}"
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO saved_tasks (saved_id, user_id, workspace_id, task_id, title, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, workspace_id, task_id) DO UPDATE SET title = excluded.title
                """,
                (saved_id, user_id, workspace_id, task_id, title, iso()),
            )
            self._connection.commit()
            row = self._connection.execute(
                """
                SELECT saved_id, task_id, title, created_at FROM saved_tasks
                WHERE user_id = ? AND workspace_id = ? AND task_id = ?
                """,
                (user_id, workspace_id, task_id),
            ).fetchone()
        self.audit(user_id, workspace_id, "task.saved", task_id)
        return dict(row) if row else {"saved_id": saved_id, "task_id": task_id, "title": title}

    def remove_saved_task(self, user_id: str, workspace_id: str, task_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM saved_tasks WHERE user_id = ? AND workspace_id = ? AND task_id = ?",
                (user_id, workspace_id, task_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def workflows(self, user_id: str, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT workflow_id, name, task, document_id, plan_json, created_at FROM workflows
                WHERE user_id = ? AND workspace_id = ? ORDER BY created_at DESC
                """,
                (user_id, workspace_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_workflow(
        self,
        user_id: str,
        workspace_id: str,
        name: str,
        task: str,
        document_id: str | None,
        plan: dict[str, Any] | None,
    ) -> dict[str, Any]:
        workflow_id = f"flow_{secrets.token_hex(8)}"
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO workflows
                    (workflow_id, user_id, workspace_id, name, task, document_id, plan_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    user_id,
                    workspace_id,
                    name.strip() or "Saved workflow",
                    task,
                    document_id,
                    json.dumps(plan or {}, default=str),
                    iso(),
                ),
            )
            self._connection.commit()
        self.audit(user_id, workspace_id, "workflow.saved", workflow_id)
        return {
            "workflow_id": workflow_id,
            "name": name.strip() or "Saved workflow",
            "task": task,
            "document_id": document_id,
        }

    def remove_workflow(self, user_id: str, workspace_id: str, workflow_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM workflows WHERE user_id = ? AND workspace_id = ? AND workflow_id = ?",
                (user_id, workspace_id, workflow_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def share(self, task_id: str) -> str:
        with self._lock:
            row = self._connection.execute("SELECT token FROM shares WHERE task_id = ?", (task_id,)).fetchone()
            if row:
                return str(row["token"])
            token = secrets.token_urlsafe(12)
            self._connection.execute(
                "INSERT INTO shares (token, task_id, created_at) VALUES (?, ?, ?)",
                (token, task_id, iso()),
            )
            self._connection.commit()
        return token

    def shared_task(self, token: str) -> str | None:
        with self._lock:
            row = self._connection.execute("SELECT task_id FROM shares WHERE token = ?", (token,)).fetchone()
        return str(row["task_id"]) if row else None

    def audit(self, user_id: str, workspace_id: str, action: str, detail: str = "") -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO audit_log (user_id, workspace_id, action, detail, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, workspace_id, action, detail, iso()),
            )
            self._connection.commit()

    def audit_log(self, user_id: str, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT action, detail, created_at FROM audit_log
                WHERE user_id = ? AND workspace_id = ? ORDER BY id DESC LIMIT ?
                """,
                (user_id, workspace_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def notify(
        self, user_id: str, workspace_id: str, title: str, body: str, kind: str = "info"
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO notifications (user_id, workspace_id, title, body, kind, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, workspace_id, title, body, kind, iso()),
            )
            self._connection.commit()

    def notifications(self, user_id: str, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, title, body, kind, read_at, created_at FROM notifications
                WHERE user_id = ? AND workspace_id = ? ORDER BY id DESC LIMIT ?
                """,
                (user_id, workspace_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_notifications_read(self, user_id: str, workspace_id: str, ids: list[int] | None = None) -> int:
        with self._lock:
            if ids:
                placeholders = ",".join("?" for _ in ids)
                cursor = self._connection.execute(
                    f"""
                    UPDATE notifications SET read_at = ?
                    WHERE user_id = ? AND workspace_id = ? AND read_at IS NULL
                      AND id IN ({placeholders})
                    """,
                    (iso(), user_id, workspace_id, *ids),
                )
            else:
                cursor = self._connection.execute(
                    """
                    UPDATE notifications SET read_at = ?
                    WHERE user_id = ? AND workspace_id = ? AND read_at IS NULL
                    """,
                    (iso(), user_id, workspace_id),
                )
            self._connection.commit()
        return cursor.rowcount

    def feature_flags(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT name, enabled, description FROM feature_flags ORDER BY name"
            ).fetchall()
        return [{**dict(row), "enabled": bool(row["enabled"])} for row in rows]

    def set_feature_flag(self, name: str, enabled: bool) -> dict[str, Any] | None:
        with self._lock:
            self._connection.execute(
                "UPDATE feature_flags SET enabled = ? WHERE name = ?", (int(enabled), name)
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT name, enabled, description FROM feature_flags WHERE name = ?", (name,)
            ).fetchone()
        return {**dict(row), "enabled": bool(row["enabled"])} if row else None

    def webhooks(self, user_id: str, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT webhook_id, url, event, created_at FROM webhooks
                WHERE user_id = ? AND workspace_id = ? ORDER BY created_at DESC
                """,
                (user_id, workspace_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_webhook(self, user_id: str, workspace_id: str, url: str, event: str) -> dict[str, Any]:
        if not url.startswith(("http://", "https://")):
            raise ValueError("Webhook URLs must start with http:// or https://.")
        webhook_id = f"hook_{secrets.token_hex(8)}"
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO webhooks (webhook_id, user_id, workspace_id, url, event, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (webhook_id, user_id, workspace_id, url, event, iso()),
            )
            self._connection.commit()
        self.audit(user_id, workspace_id, "webhook.created", url)
        return {"webhook_id": webhook_id, "url": url, "event": event}

    def remove_webhook(self, user_id: str, workspace_id: str, webhook_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM webhooks WHERE user_id = ? AND workspace_id = ? AND webhook_id = ?",
                (user_id, workspace_id, webhook_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def scheduled_runs(self, user_id: str, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT schedule_id, task, cadence, next_run_at, enabled, created_at
                FROM scheduled_runs WHERE user_id = ? AND workspace_id = ?
                ORDER BY created_at DESC
                """,
                (user_id, workspace_id),
            ).fetchall()
        return [{**dict(row), "enabled": bool(row["enabled"])} for row in rows]

    def add_scheduled_run(self, user_id: str, workspace_id: str, task: str, cadence: str) -> dict[str, Any]:
        clean = task.strip()
        if len(clean) < 3:
            raise ValueError("Describe the task to run.")
        cadence = cadence if cadence in {"hourly", "daily", "weekly"} else "daily"
        next_run = utcnow() + timedelta(hours=1 if cadence == "hourly" else 24 if cadence == "daily" else 168)
        schedule_id = f"sched_{secrets.token_hex(8)}"
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO scheduled_runs
                    (schedule_id, user_id, workspace_id, task, cadence, next_run_at, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (schedule_id, user_id, workspace_id, clean, cadence, next_run.isoformat(), iso()),
            )
            self._connection.commit()
        self.audit(user_id, workspace_id, "schedule.created", schedule_id)
        return {"schedule_id": schedule_id, "task": clean, "cadence": cadence, "next_run_at": next_run.isoformat()}

    def remove_scheduled_run(self, user_id: str, workspace_id: str, schedule_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM scheduled_runs WHERE user_id = ? AND workspace_id = ? AND schedule_id = ?",
                (user_id, workspace_id, schedule_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def due_schedules(self, now: datetime | None = None) -> list[dict[str, Any]]:
        moment = (now or utcnow()).isoformat()
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM scheduled_runs
                WHERE enabled = 1 AND next_run_at <= ? ORDER BY next_run_at LIMIT 10
                """,
                (moment,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_schedule_ran(self, schedule_id: str, cadence: str) -> None:
        hours = 1 if cadence == "hourly" else 24 if cadence == "daily" else 168
        with self._lock:
            self._connection.execute(
                "UPDATE scheduled_runs SET next_run_at = ? WHERE schedule_id = ?",
                ((utcnow() + timedelta(hours=hours)).isoformat(), schedule_id),
            )
            self._connection.commit()

    def overrides(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT tool_id, field_name, value, updated_at FROM provider_overrides ORDER BY tool_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def set_override(self, tool_id: str, field_name: str, value: str) -> dict[str, Any]:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO provider_overrides (tool_id, field_name, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tool_id, field_name) DO UPDATE SET
                    value = excluded.value, updated_at = excluded.updated_at
                """,
                (tool_id, field_name, value, iso()),
            )
            self._connection.commit()
        return {"tool_id": tool_id, "field_name": field_name, "value": value}

    def set_api_key(self, user_id: str, provider: str, key: str) -> None:
        if not provider.strip() or not key.strip():
            raise ValueError("Choose a provider and enter a key.")
        encrypted = encrypt_secret(self._secret(), key.strip())
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO api_keys (user_id, provider, ciphertext, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    ciphertext = excluded.ciphertext, updated_at = excluded.updated_at
                """,
                (user_id, provider.strip(), encrypted, iso()),
            )
            self._connection.commit()
        self.audit(user_id, self.preferred_workspace(user_id), "credential.saved", provider.strip())

    def api_keys(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT provider, ciphertext, updated_at FROM api_keys WHERE user_id = ? ORDER BY provider",
                (user_id,),
            ).fetchall()
        result = []
        for row in rows:
            try:
                plain = decrypt_secret(self._secret(), row["ciphertext"])
                masked = f"{'*' * max(0, min(8, len(plain) - 4))}{plain[-4:]}"
            except ValueError:
                masked = "unreadable"
            result.append({"provider": row["provider"], "masked": masked, "updated_at": row["updated_at"]})
        return result

    def delete_api_key(self, user_id: str, provider: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM api_keys WHERE user_id = ? AND provider = ?", (user_id, provider)
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def workspace_export(self, user_id: str, workspace_id: str) -> dict[str, Any]:
        return {
            "version": 1,
            "exported_at": iso(),
            "workspace": self.workspace(workspace_id),
            "settings": self.settings(user_id),
            "favorites": self.favorites(user_id, workspace_id),
            "saved_tasks": self.saved_tasks(user_id, workspace_id),
            "workflows": self.workflows(user_id, workspace_id),
            "webhooks": self.webhooks(user_id, workspace_id),
            "scheduled_runs": self.scheduled_runs(user_id, workspace_id),
        }

    def workspace_import(self, user_id: str, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        counts = Counter()
        for favorite in payload.get("favorites", []):
            if favorite.get("tool_id"):
                self.save_favorite(
                    user_id,
                    workspace_id,
                    str(favorite["tool_id"]),
                    str(favorite.get("note", "")),
                    str(favorite.get("tags", "")),
                )
                counts["favorites"] += 1
        for saved in payload.get("saved_tasks", []):
            if saved.get("task_id"):
                self.save_task(user_id, workspace_id, str(saved["task_id"]), str(saved.get("title", "Saved task")))
                counts["saved_tasks"] += 1
        for workflow in payload.get("workflows", []):
            if workflow.get("task"):
                self.save_workflow(
                    user_id,
                    workspace_id,
                    str(workflow.get("name", "Imported workflow")),
                    str(workflow["task"]),
                    workflow.get("document_id"),
                    workflow.get("plan") if isinstance(workflow.get("plan"), dict) else {},
                )
                counts["workflows"] += 1
        return {"imported": dict(counts)}


class RateLimiter:
    def __init__(self, limit: int = 180, window_seconds: int = 60) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            hits = [stamp for stamp in self._hits[key] if now - stamp < self.window_seconds]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False, max(1, int(self.window_seconds - (now - hits[0])))
            hits.append(now)
            self._hits[key] = hits
            return True, 0


def task_summary(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("result_json") or row.get("result") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    steps = ((payload.get("plan") or {}).get("steps") or []) if isinstance(payload, dict) else []
    capabilities = sorted({str(step.get("capability")) for step in steps if step.get("capability")})
    tools = sorted({str(step.get("tool_id")) for step in steps if step.get("tool_id")})
    return {
        "task_id": row.get("task_id"),
        "task": row.get("task"),
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "capabilities": capabilities,
        "tools": tools,
        "duration_ms": float((payload.get("metrics") or {}).get("total_ms") or payload.get("duration_ms") or 0)
        if isinstance(payload, dict)
        else 0.0,
    }


def analytics_payload(rows: list[dict[str, Any]], providers: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [task_summary(row) for row in rows]
    total = len(summaries)
    completed = sum(1 for item in summaries if item["status"] == "completed")
    durations = [item["duration_ms"] for item in summaries if item["duration_ms"]]
    by_day: dict[str, int] = {}
    tool_counts: Counter[str] = Counter()
    capability_counts: Counter[str] = Counter()
    failures = 0
    for item in summaries:
        day = str(item["created_at"] or "")[:10]
        if day:
            by_day[day] = by_day.get(day, 0) + 1
        for tool in item["tools"]:
            tool_counts[tool] += 1
        for capability in item["capabilities"]:
            capability_counts[capability] += 1
        if item["status"] != "completed":
            failures += 1
    days = sorted(by_day)[-14:]
    return {
        "totals": {
            "tasks": total,
            "completed": completed,
            "failed": failures,
            "success_rate": round(completed / total, 3) if total else 0.0,
            "average_latency_ms": round(sum(durations) / len(durations), 1) if durations else 0.0,
        },
        "by_day": [{"date": day, "tasks": by_day[day]} for day in days],
        "top_tools": [{"tool_id": tool, "tasks": count} for tool, count in tool_counts.most_common(8)],
        "top_capabilities": [
            {"capability": capability, "tasks": count}
            for capability, count in capability_counts.most_common(8)
        ],
        "providers": [
            {
                "provider_id": item.get("provider_id"),
                "tool_name": item.get("tool_name"),
                "trust": item.get("trust", 0.5),
                "calls": item.get("calls", 0),
                "probes": item.get("probes", 0),
                "contradictions": item.get("contradictions", 0),
                "status": "paused" if item.get("demoted") else "healthy",
            }
            for item in providers
        ],
    }
