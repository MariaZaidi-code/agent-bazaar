"""Tests for deterministic PDF, DOCX, and text document ingestion."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from agent_bazaar.config import IngestionSettings
from agent_bazaar.ingestion.documents import chunk_text
from agent_bazaar.ingestion.utility import IngestionUtility
from tests.fixtures.builders import write_sample_docx, write_sample_pdf


def test_docx_extracts_paragraphs_and_table_rows(tmp_path: Path) -> None:
    source = write_sample_docx(tmp_path / "sample.docx")
    spec = IngestionUtility().ingest(source)
    text = "\n".join(chunk.text for chunk in spec.chunks)

    assert spec.spec_format == "docx"
    assert spec.title == "Agent Bazaar sample document."
    assert "Agent Bazaar sample document." in text
    assert "This document is used to verify DOCX extraction." in text
    assert "alpha | beta" in text
    assert "gamma | delta" in text
    assert spec.fields == []
    assert spec.metadata["source"] == str(source)


def test_pdf_extraction_and_page_metadata(tmp_path: Path) -> None:
    source = write_sample_pdf(tmp_path / "sample.pdf")
    reader = PdfReader(str(source))
    assert reader.pages[0].extract_text().strip() == "hello ingestion world"

    spec = IngestionUtility().ingest(source)
    text = "\n".join(chunk.text for chunk in spec.chunks)

    assert spec.spec_format == "pdf"
    assert spec.title == "hello ingestion world"
    assert "hello ingestion world" in text
    assert spec.metadata["page_count"] == 1
    assert spec.chunks[0].source == str(source)


def test_chunking_uses_configured_size_and_overlap(tmp_path: Path) -> None:
    content = "abcdefghijklmnopqrstuvwxyz"
    source = tmp_path / "letters.txt"
    source.write_text(content, encoding="utf-8")
    settings = IngestionSettings(chunk_size_chars=10, chunk_overlap_chars=3)
    spec = IngestionUtility(settings).ingest(source)
    chunks = spec.chunks

    assert [chunk.chunk_id for chunk in chunks] == [
        "chunk-0001",
        "chunk-0002",
        "chunk-0003",
        "chunk-0004",
    ]
    assert [(chunk.start, chunk.end) for chunk in chunks] == [
        (0, 10),
        (7, 17),
        (14, 24),
        (21, 26),
    ]
    assert all(content[chunk.start : chunk.end] == chunk.text for chunk in chunks)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.start == previous.end - 3
        assert previous.text[-3:] == current.text[:3]


def test_chunk_text_clamps_invalid_overlap() -> None:
    chunks = chunk_text("abcdef", 4, 9)
    assert [chunk.text for chunk in chunks] == ["abcd", "bcde", "cdef"]


def test_empty_document_produces_zero_chunks(tmp_path: Path) -> None:
    source = tmp_path / "empty.txt"
    source.write_text("", encoding="utf-8")
    spec = IngestionUtility().ingest(source)

    assert spec.chunks == []
    assert spec.fields == []
    assert spec.title == ""


def test_text_and_markdown_format(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Agent Bazaar\n\nDeterministic text ingestion.", encoding="utf-8")
    spec = IngestionUtility().ingest(source)
    text = "\n".join(chunk.text for chunk in spec.chunks)

    assert spec.spec_format == "text"
    assert spec.title == "# Agent Bazaar"
    assert "Deterministic text ingestion." in text


def test_latin1_fallback_for_text(tmp_path: Path) -> None:
    source = tmp_path / "latin1.txt"
    source.write_bytes(b"caf\xe9 au lait")
    spec = IngestionUtility().ingest(source)

    assert spec.chunks[0].text == "café au lait"


def test_malformed_pdf_returns_error_object(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"this is not a pdf")
    spec, error = IngestionUtility().try_ingest(source)

    assert spec is None
    assert error is not None
    assert error.code == "parse_error"
    assert error.source == str(source)
