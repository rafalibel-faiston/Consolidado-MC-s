from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _normalize_url(url: str) -> str:
    """Railway (como o Heroku antes dele) entrega DATABASE_URL com o esquema
    'postgres://', que o SQLAlchemy/psycopg2 modernos não aceitam mais."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


DATABASE_URL = _normalize_url(os.environ.get("DATABASE_URL", "sqlite:///./dev.db"))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (registra os modelos em Base antes do create_all)

    Base.metadata.create_all(bind=engine)
