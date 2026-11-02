from __future__ import annotations

import io
import json
import re
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.core.db import connect
from app.knowledge.retrieval import TfidfIndex, tokenize
from app.providers.base import BaseProvider
from app.schemas import DocumentInfo

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class DocumentStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.ensure_dirs()
        self._lock = threading.RLock()
        self._connection = connect(settings.documents_db)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                text TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                version INTEGER NOT NULL DEFAULT 1,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
            )
            """
        )
        self._connection.commit()
        for column, definition in (
            ("tags", "TEXT NOT NULL DEFAULT '[]'"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("chunk_count", "INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                self._connection.execute(f"ALTER TABLE documents ADD COLUMN {column} {definition}")
                self._connection.commit()
            except sqlite3.OperationalError:
                pass
        if settings.seed_document and not self.list():
            self.add_document(
                "agent_bazaar_project_brief.txt",
                (
                    b"Agent Bazaar project brief. Agent Bazaar is a multi-agent system that "
                    b"validates third-party services before a developer relies on them. "
                    b"The system maps service listings to a shared ontology and stores them in "
                    b"a knowledge graph. The Client agent finds, ranks, composes and executes "
                    b"tools, while the Auditor verifies provider claims with documentation and "
                    b"live probes. The Mapper learns from corrections and repairs drifted "
                    b"mappings. The project uses free resources and reports its results against "
                    b"two baselines: plain LLM tool-calling and retrieval without the ontology. "
                    b"The main goal is to make third-party service use discoverable, verifiable, "
                    b"composable and self-healing. The demonstration chains geocoding, weather "
                    b"and currency tools, shows claim badges, and recovers from an injected "
                    b"provider outage using a compatible substitute."
                ),
            )

    @staticmethod
    def _extract_text(name: str, data: bytes) -> str:
        suffix = Path(name).suffix.lower()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(data))
                return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            except Exception as exc:
                raise ValueError(f"could not parse PDF: {exc}") from exc
        if suffix == ".docx":
            try:
                from docx import Document

                document = Document(io.BytesIO(data))
                return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
            except Exception as exc:
                raise ValueError(f"could not parse DOCX: {exc}") from exc
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return data.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore").strip()

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 500) -> list[str]:
        pieces = [part.strip() for part in re.split(r"\n+", text) if part.strip()]
        chunks: list[str] = []
        for piece in pieces:
            if len(piece) <= max_chars:
                chunks.append(piece)
                continue
            sentences = SENTENCE_SPLIT.split(piece)
            current = ""
            for sentence in sentences:
                if len(current) + len(sentence) + 1 > max_chars and current:
                    chunks.append(current.strip())
                    current = sentence
                else:
                    current = f"{current} {sentence}".strip()
            if current:
                chunks.append(current.strip())
        if not chunks:
            chunks = [
                text[i : i + max_chars].strip()
                for i in range(0, len(text), max_chars)
                if text[i : i + max_chars].strip()
            ]
        return chunks or [text[:max_chars]]

    def add_document(self, name: str, data: bytes) -> DocumentInfo:
        if not data:
            raise ValueError("document is empty")
        text = self._extract_text(name, data)
        if not text:
            raise ValueError("no text could be extracted from the document")
        document_id = f"doc_{uuid4().hex[:12]}"
        suffix = Path(name).suffix.lower() or ".txt"
        path = self.settings.uploads_dir / f"{document_id}{suffix}"
        path.write_bytes(data)
        created_at = datetime.now(UTC)
        chunks = self._chunk_text(text, 500)
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO documents
                    (document_id, name, path, size_bytes, text, tags, version, chunk_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    name,
                    str(path),
                    len(data),
                    text,
                    "[]",
                    1,
                    len(chunks),
                    created_at.isoformat(),
                ),
            )
            for index, chunk in enumerate(chunks):
                self._connection.execute(
                    """
                    INSERT INTO document_chunks (chunk_id, document_id, chunk_index, text)
                    VALUES (?, ?, ?, ?)
                    """,
                    (f"{document_id}_{index}", document_id, index, chunk),
                )
            self._connection.commit()
        return DocumentInfo(
            document_id=document_id,
            name=name,
            size_bytes=len(data),
            text_chars=len(text),
            tags=[],
            version=1,
            chunks=len(chunks),
            created_at=created_at,
        )

    def _parse_tags(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT document_id, name, size_bytes, length(text) AS text_chars, tags, version, chunk_count, created_at
                FROM documents ORDER BY created_at DESC
                """
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["tags"] = self._parse_tags(item.get("tags"))
            item["version"] = int(item.get("version") or 1)
            item["chunks"] = int(item.get("chunk_count") or 0)
            result.append(item)
        return result

    def get(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["tags"] = self._parse_tags(item.get("tags"))
        item["version"] = int(item.get("version") or 1)
        item["chunks"] = int(item.get("chunk_count") or 0)
        return item

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM documents ORDER BY created_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def get_chunks(self, document_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT chunk_id, document_id, chunk_index, text
                FROM document_chunks WHERE document_id = ? ORDER BY chunk_index
                """,
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_tags(self, document_id: str, tags: list[str]) -> bool:
        with self._lock:
            row = self._connection.execute(
                "SELECT document_id FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
            if row is None:
                return False
            self._connection.execute(
                """
                UPDATE documents SET tags = ?, version = version + 1 WHERE document_id = ?
                """,
                (json.dumps(tags), document_id),
            )
            self._connection.commit()
        return True

    def search_documents(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT dc.document_id, dc.chunk_index, dc.text, d.name
                FROM document_chunks dc JOIN documents d ON d.document_id = dc.document_id
                """
            ).fetchall()
        if not rows:
            return []
        documents = {f"{row['document_id']}:{row['chunk_index']}": row["text"] for row in rows}
        index = TfidfIndex(documents)
        ranked = index.search(query, top_k=top_k)
        meta = {f"{row['document_id']}:{row['chunk_index']}": row for row in rows}
        results = []
        for key, score in ranked:
            if float(score) <= 0.0:
                continue
            row = meta[key]
            results.append(
                {
                    "document_id": row["document_id"],
                    "name": row["name"],
                    "chunk_index": row["chunk_index"],
                    "snippet": row["text"][:300],
                    "text": row["text"],
                    "score": round(float(score), 4),
                }
            )
        return results

    def delete(self, document_id: str) -> bool:
        with self._lock:
            row = self._connection.execute(
                "SELECT path FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
            if row is None:
                return False
            self._connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
            self._connection.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
            self._connection.commit()
        path = Path(row["path"])
        try:
            resolved = path.resolve()
            if resolved.is_file() and self.settings.uploads_dir.resolve() in resolved.parents:
                resolved.unlink()
        except OSError:
            pass
        return True


class DocumentQAProvider(BaseProvider):
    def __init__(self, *args: Any, document_store: DocumentStore, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.document_store = document_store

    @staticmethod
    def _chunks(text: str, max_chars: int = 700) -> list[str]:
        paragraphs = [piece.strip() for piece in text.split("\n") if piece.strip()]
        chunks: list[str] = []
        for paragraph in paragraphs:
            if len(paragraph) <= max_chars:
                chunks.append(paragraph)
                continue
            sentences = SENTENCE_SPLIT.split(paragraph)
            current = ""
            for sentence in sentences:
                if len(current) + len(sentence) > max_chars and current:
                    chunks.append(current.strip())
                    current = sentence
                else:
                    current = f"{current} {sentence}".strip()
            if current:
                chunks.append(current.strip())
        return chunks or [text[:max_chars]]

    def _answer(self, params: dict[str, Any]) -> dict[str, Any]:
        question = str(params.get("question", "")).strip()
        if not question:
            raise ValueError("question is required")
        document_id = str(params.get("document_id", "") or "")
        document = self.document_store.get(document_id) if document_id else self.document_store.latest()
        if document is None:
            raise ValueError("upload a document before asking a document question")
        chunks = self._chunks(document["text"])
        index = TfidfIndex({str(number): chunk for number, chunk in enumerate(chunks)})
        ranked = index.search(question, top_k=3)
        query_tokens = set(tokenize(question))
        best = ""
        best_score = 0.0
        for doc_id, score in ranked:
            chunk = chunks[int(doc_id)]
            for sentence in SENTENCE_SPLIT.split(chunk):
                overlap = len(query_tokens & set(tokenize(sentence)))
                weighted = score + overlap * 0.05
                if weighted > best_score:
                    best = sentence.strip()
                    best_score = weighted
        if not best or best_score <= 0.0:
            best = chunks[0]
            answer = f"The document does not directly answer that question. The closest passage is: {best}"
        else:
            answer = best
        citations = [
            {
                "document_id": document["document_id"],
                "name": document["name"],
                "quote": chunks[int(doc_id)][:350],
                "score": round(score, 4),
            }
            for doc_id, score in ranked[:2]
        ]
        return {
            "answer": {
                "answer": answer,
                "citations": citations,
                "document_id": document["document_id"],
            }
        }

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._answer(params)

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._answer(params)
