from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import inventory, orders, products, reports, settings, system


app = FastAPI(title="布店经营台", version="1.0.0", docs_url="/api/docs", redoc_url=None)
for router in (system.router, settings.router, products.router, orders.router, inventory.router, reports.router):
    app.include_router(router)


def _frontend_dist() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "frontend" / "dist"


dist = _frontend_dist()
if (dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def home():
    index = dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"message": "前端尚未构建，请运行 scripts/build_windows.ps1"}, status_code=503)

