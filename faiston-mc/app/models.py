from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MCRecord(Base):
    """Cabeçalho + totais + o objeto MC inteiro (já no formato que o front-end espera)."""

    __tablename__ = "mcs"

    id = Column(String, primary_key=True)  # "{contrato}|{arquivo}"
    contrato = Column(String, index=True)
    cliente = Column(String, index=True)
    projeto = Column(String)
    arquivo = Column(String)
    receita = Column(Float)
    receita_liq = Column(Float)
    custo = Column(Float)
    mc_projeto = Column(Float)
    mc_projeto_pct = Column(Float)
    mc_direta = Column(Float)
    mc_direta_pct = Column(Float)
    status = Column(String, nullable=True)  # 'ativo' | 'finalizado' | 'a_validar'
    alerta = Column(Boolean, default=False, nullable=False)
    dados = Column(JSON, nullable=False)
    criado_em = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    atualizado_em = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    linhas = relationship("MCLinha", back_populates="mc", cascade="all, delete-orphan")


class MCLinha(Base):
    """Linha a linha já classificada — pra query por caixinha sem abrir o JSON."""

    __tablename__ = "mc_linhas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mc_id = Column(String, ForeignKey("mcs.id", ondelete="CASCADE"), index=True, nullable=False)
    pilar_k = Column(String)
    pilar = Column(String)
    aba = Column(String)
    idx = Column(Integer)
    cat = Column(String)
    desc = Column(Text)
    extra = Column(Text)
    g1 = Column(String)
    meses = Column(Float)
    qtd = Column(Float)
    unit = Column(Float)
    total = Column(Float)
    hm = Column(Integer)
    calc = Column(Float)
    caixa = Column(String, index=True)

    mc = relationship("MCRecord", back_populates="linhas")


class Ingestao(Base):
    """Histórico de quem subiu o quê e o resultado."""

    __tablename__ = "ingestoes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    arquivo = Column(String, nullable=False)
    mc_id = Column(String, nullable=True)
    status = Column(String, nullable=False)  # 'ok' | 'erro'
    mensagem = Column(Text, nullable=True)
    criado_em = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Cliente(Base):
    """Consolidado por cliente — recalculado a cada upload/remoção, pra
    dar pra consultar sem somar as MCs na hora (mesma ideia da mc_linhas)."""

    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String, unique=True, nullable=False, index=True)
    n_contratos = Column(Integer, default=0, nullable=False)
    receita_total = Column(Float, default=0.0, nullable=False)
    receita_liq_total = Column(Float, default=0.0, nullable=False)
    custo_total = Column(Float, default=0.0, nullable=False)
    mc_projeto_total = Column(Float, default=0.0, nullable=False)
    mc_direta_total = Column(Float, default=0.0, nullable=False)
    criado_em = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    atualizado_em = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
