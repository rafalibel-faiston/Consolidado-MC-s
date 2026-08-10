from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .database import init_db
from .routes.clientes import router as clientes_router
from .routes.mcs import router as mcs_router

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Painel de MC — Faiston")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(mcs_router)
app.include_router(clientes_router)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
