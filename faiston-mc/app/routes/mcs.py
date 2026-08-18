from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..compat import mc_to_frontend
from ..database import get_db
from ..edicao import aplicar_edicao
from ..parser import MC, Linha, parse_mc

router = APIRouter(prefix="/api/mcs", tags=["mcs"])

ALLOWED_EXT = {"xlsx", "xlsm", "xlsb"}
MAX_FILE_BYTES = 30 * 1024 * 1024  # 30 MB

STATUS_PADRAO = "a_validar"
STATUS_VALIDOS = {"ativo", "finalizado", "a_validar"}


def _serialize(rec: models.MCRecord) -> dict:
    """O JSON salvo é o objeto MC puro (saída do parser) — status é um dado
    operacional à parte, não vem da planilha, então entra por cima aqui."""
    return {**rec.dados, "status": rec.status or STATUS_PADRAO}


def _refresh_cliente(db: Session, nome: str) -> None:
    """Recalcula o consolidado de um cliente a partir das MCs que estão no banco agora."""
    if not nome:
        return
    n, receita, receita_liq, custo, mcp, mcd = db.query(
        func.count(models.MCRecord.id),
        func.coalesce(func.sum(models.MCRecord.receita), 0.0),
        func.coalesce(func.sum(models.MCRecord.receita_liq), 0.0),
        func.coalesce(func.sum(models.MCRecord.custo), 0.0),
        func.coalesce(func.sum(models.MCRecord.mc_projeto), 0.0),
        func.coalesce(func.sum(models.MCRecord.mc_direta), 0.0),
    ).filter(models.MCRecord.cliente == nome).one()

    cli = db.query(models.Cliente).filter(models.Cliente.nome == nome).one_or_none()
    if n == 0:
        if cli:
            db.delete(cli)
        return
    if cli is None:
        cli = models.Cliente(nome=nome)
        db.add(cli)
    cli.n_contratos = n
    cli.receita_total = receita
    cli.receita_liq_total = receita_liq
    cli.custo_total = custo
    cli.mc_projeto_total = mcp
    cli.mc_direta_total = mcd


def _upsert(db: Session, parsed: MC, frontend_mc: dict, status: str = STATUS_PADRAO) -> models.MCRecord:
    mc_id = frontend_mc["id"]
    rec = db.get(models.MCRecord, mc_id)
    cliente_anterior = rec.cliente if rec else None
    if rec is None:
        rec = models.MCRecord(id=mc_id, status=status)
        db.add(rec)

    _aplicar_totais(rec, frontend_mc)
    _gravar_linhas(db, mc_id, parsed.linhas)

    db.flush()
    if cliente_anterior and cliente_anterior != rec.cliente:
        _refresh_cliente(db, cliente_anterior)
    _refresh_cliente(db, rec.cliente)
    return rec


def _gravar_linhas(db: Session, mc_id: str, linhas: list[Linha]) -> None:
    db.query(models.MCLinha).filter(models.MCLinha.mc_id == mc_id).delete()
    for l in linhas:
        db.add(models.MCLinha(
            mc_id=mc_id, pilar_k=l.pilar_k, pilar=l.pilar, aba=l.aba, idx=l.idx,
            cat=l.cat, desc=l.desc, extra=l.extra, g1=l.g1,
            meses=l.meses, qtd=l.qtd, unit=l.unit, total=l.total,
            hm=l.hm, calc=l.calc, caixa=l.caixa,
        ))


def _aplicar_totais(rec: models.MCRecord, dados: dict) -> None:
    rec.contrato = dados.get("contrato") or ""
    rec.cliente = dados.get("cliente") or ""
    rec.projeto = dados.get("projeto") or ""
    rec.arquivo = dados.get("arquivo") or ""
    rec.receita = dados.get("receita")
    rec.receita_liq = dados.get("receitaLiq")
    rec.custo = dados.get("custo")
    rec.mc_projeto = dados.get("mcProjeto")
    rec.mc_projeto_pct = dados.get("mcProjetoPct")
    rec.mc_direta = dados.get("mcDireta")
    rec.mc_direta_pct = dados.get("mcDiretaPct")
    rec.alerta = bool(dados.get("divergencias") or dados.get("linhasForaDaConta"))
    rec.dados = dados


@router.get("")
def listar(db: Session = Depends(get_db)):
    recs = db.query(models.MCRecord).order_by(models.MCRecord.criado_em.asc()).all()
    return [_serialize(r) for r in recs]


@router.get("/{mc_id}")
def detalhe(mc_id: str, db: Session = Depends(get_db)):
    rec = db.get(models.MCRecord, mc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="MC não encontrada")
    return _serialize(rec)


class StatusBody(BaseModel):
    status: str


@router.patch("/{mc_id}/status")
def atualizar_status(mc_id: str, body: StatusBody, db: Session = Depends(get_db)):
    if body.status not in STATUS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"status inválido — use um de {sorted(STATUS_VALIDOS)}")
    rec = db.get(models.MCRecord, mc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="MC não encontrada")
    rec.status = body.status
    rec.dados = {**rec.dados, "status": body.status}
    db.commit()
    return _serialize(rec)


@router.put("/{mc_id}")
def editar(mc_id: str, body: dict = Body(...), db: Session = Depends(get_db)):
    """Salva a edição manual da MC — mesma coisa que a Bruna vê simulada na tela.

    Recalcula custo, MC do projeto, MC direta e as caixinhas com o núcleo do
    parser; o 5.DRE guardado continua sendo a foto da planilha original.
    """
    rec = db.get(models.MCRecord, mc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="MC não encontrada")

    try:
        dados, linhas = aplicar_edicao(rec.dados or {}, body or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"não consegui aplicar a edição ({e})")

    cliente_anterior = rec.cliente
    _aplicar_totais(rec, dados)
    _gravar_linhas(db, mc_id, linhas)
    db.flush()
    if cliente_anterior and cliente_anterior != rec.cliente:
        _refresh_cliente(db, cliente_anterior)
    _refresh_cliente(db, rec.cliente)
    db.commit()
    return _serialize(rec)


@router.post("/upload")
async def upload(
    files: list[UploadFile] = File(...),
    status: str = Form(STATUS_PADRAO),
    db: Session = Depends(get_db),
):
    status_novas = status if status in STATUS_VALIDOS else STATUS_PADRAO
    added: list[str] = []
    erros: list[dict] = []

    for f in files:
        ext = (f.filename or "").rsplit(".", 1)[-1].lower()
        content = await f.read()

        if len(content) > MAX_FILE_BYTES:
            msg = "arquivo maior que 30 MB."
            erros.append({"arquivo": f.filename, "mensagem": msg})
            db.add(models.Ingestao(arquivo=f.filename or "", status="erro", mensagem=msg))
            continue

        if ext not in ALLOWED_EXT:
            msg = "formato não suportado — envie .xlsx, .xlsm ou .xlsb."
            erros.append({"arquivo": f.filename, "mensagem": msg})
            db.add(models.Ingestao(arquivo=f.filename or "", status="erro", mensagem=msg))
            continue

        try:
            parsed = parse_mc(BytesIO(content), f.filename or "")
        except Exception as e:  # arquivo corrompido, xlsb ilegível, etc.
            msg = f"não consegui ler o arquivo ({e})."
            erros.append({"arquivo": f.filename, "mensagem": msg})
            db.add(models.Ingestao(arquivo=f.filename or "", status="erro", mensagem=msg))
            continue

        if not parsed.calc.get("receita") and not sum(parsed.somas.values()):
            msg = "não encontrei as abas do modelo de MC (2.1 a 2.4 / 5.DRE)."
            erros.append({"arquivo": f.filename, "mensagem": msg})
            db.add(models.Ingestao(arquivo=f.filename or "", status="erro", mensagem=msg))
            continue

        frontend_mc = mc_to_frontend(parsed)
        _upsert(db, parsed, frontend_mc, status=status_novas)
        added.append(frontend_mc["id"])
        db.add(models.Ingestao(arquivo=f.filename or "", mc_id=frontend_mc["id"], status="ok"))

    db.commit()
    return {"ok": added, "erros": erros}


@router.delete("/{mc_id}")
def remover(mc_id: str, db: Session = Depends(get_db)):
    rec = db.get(models.MCRecord, mc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="MC não encontrada")
    cliente = rec.cliente
    db.delete(rec)
    db.flush()
    _refresh_cliente(db, cliente)
    db.commit()
    return {"ok": True}


@router.post("/clear")
def limpar(db: Session = Depends(get_db)):
    db.query(models.MCLinha).delete()
    db.query(models.MCRecord).delete()
    db.query(models.Cliente).delete()
    db.commit()
    return {"ok": True}
