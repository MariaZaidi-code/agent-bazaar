"""Tests for document knowledge-base features."""

from __future__ import annotations


def test_document_chunks_and_search(api) -> None:
    facts = b"The demo capital is Lahore. The demo has forty two tools."
    upload = api.post(
        "/api/documents",
        files={"file": ("facts.txt", facts, "text/plain")},
    )
    assert upload.status_code == 200
    document_id = upload.json()["document"]["document_id"]
    assert upload.json()["document"]["chunks"] >= 1
    assert upload.json()["document"]["tags"] == []
    assert upload.json()["document"]["version"] == 1

    chunks = api.get(f"/api/documents/{document_id}/chunks")
    assert chunks.status_code == 200
    assert chunks.json()["chunks"]

    search = api.get("/api/documents/search", params={"q": "capital", "top_k": 3})
    assert search.status_code == 200
    assert search.json()["results"]
    assert any("Lahore" in item["snippet"] for item in search.json()["results"])

    tagged = api.put(f"/api/documents/{document_id}/tags", json={"tags": ["demo", "facts"]})
    assert tagged.status_code == 200
    assert tagged.json()["document"]["tags"] == ["demo", "facts"]
    assert tagged.json()["document"]["version"] == 2


def test_document_search_missing(api) -> None:
    response = api.get("/api/documents/search", params={"q": "capital"})
    assert response.status_code == 200
    assert response.json()["results"] == []
