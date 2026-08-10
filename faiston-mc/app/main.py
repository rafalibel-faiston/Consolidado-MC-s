from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .config import settings
from .database import init_db
from .routes.auth import router as auth_router
from .routes.clientes import router as clientes_router
from .routes.mcs import router as mcs_router

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Painel de MC — Faiston")


@app.on_event("startup")
def on_startup() -> None:
    if not settings.app_password or not settings.secret_key:
        raise RuntimeError(
            "Configure APP_PASSWORD e SECRET_KEY nas variáveis de ambiente antes de subir o backend."
        )
    init_db()


app.include_router(auth_router)
app.include_router(mcs_router)
app.include_router(clientes_router)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
