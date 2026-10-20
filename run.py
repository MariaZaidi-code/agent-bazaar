from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("AB_HOST", "127.0.0.1"),
        port=int(os.getenv("AB_PORT", "8000")),
        reload=os.getenv("AB_RELOAD", "false").lower() == "true",
    )
