from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

from agent_bazaar_auditor.api import create_server
from agent_bazaar_auditor.auditor import Auditor
from agent_bazaar_auditor.config import Settings


def test_health_and_verify_endpoints(tmp_path: Path) -> None:
    settings = Settings(
        outputs_dir=tmp_path / "outputs",
        cache_dir=tmp_path / "cache",
        live=False,
    )
    auditor = Auditor(settings=settings, persist=False)
    server = create_server(auditor, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=5) as response:
            health = json.loads(response.read())
        assert health["status"] == "ok"
        assert health["tools"] == 15

        body = json.dumps({"tool_id": "frankfurter"}).encode("utf-8")
        request = urllib.request.Request(
            f"{base}/verify",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read())["result"]
        assert result["tool_id"] == "frankfurter"
        assert {item["label"] for item in result["assessments"]} == {"Verified", "Supported"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
