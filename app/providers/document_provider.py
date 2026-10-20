from __future__ import annotations

import io
import re
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
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()
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
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO documents
                    (document_id, name, path, size_bytes, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    name,
                    str(path),
                    len(data),
                    text,
                    created_at.isoformat(),
                ),
            )
            self._connection.commit()
        return DocumentInfo(
            document_id=document_id,
            name=name,
            size_bytes=len(data),
            text_chars=len(text),
            created_at=created_at,
        )

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT document_id, name, size_bytes, length(text) AS text_chars, created_at
                FROM documents ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return dict(row) if row else None

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM documents ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None


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
        document = (
            self.document_store.get(document_id)
            if document_id
            else self.document_store.latest()
        )
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
            answer = (
                "The document does not directly answer that question. "
                f"The closest passage is: {best}"
            )
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
