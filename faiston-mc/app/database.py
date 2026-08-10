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
    from sqlalchemy import inspect

    insp = inspect(engine)
    tabelas_existentes = set(insp.get_table_names())

    Base.metadata.create_all(bind=engine)

    # create_all() só cria tabela que não existe — não adiciona coluna nova em
    # tabela que já existia antes deste deploy. Como ainda não vale a pena ter
    # Alembic pro tamanho do projeto, cobre esse caso com ALTER TABLE ADD COLUMN
    # (só adiciona coluna faltando, nunca altera/remove nada existente).
    _adicionar_colunas_faltando(tabelas_existentes)


def _adicionar_colunas_faltando(tabelas_existentes: set[str]) -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in tabelas_existentes:
                continue  # tabela nova: create_all() já criou com todas as colunas
            colunas_atuais = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in colunas_atuais:
                    continue
                tipo = col.type.compile(dialect=conn.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {tipo}'))
