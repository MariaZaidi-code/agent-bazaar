from __future__ import annotations


def test_discovery_candidates_and_sync(services, api):
    before = api.get("/api/discovery/candidates")
    assert before.status_code == 200
    assert before.json()["count"] >= 1

    sync = api.post("/api/discovery/sync")
    assert sync.status_code == 200
    assert isinstance(sync.json()["added"], list)

    # installed flags reflect sync
    after = api.get("/api/discovery/candidates").json()
    for candidate in after["candidates"]:
        assert "installed" in candidate
