from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..compat import mc_to_frontend
from ..database import get_db
from ..parser import MC, parse_mc

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

    rec.contrato = frontend_mc.get("contrato") or ""
    rec.cliente = frontend_mc.get("cliente") or ""
    rec.projeto = frontend_mc.get("projeto") or ""
    rec.arquivo = frontend_mc.get("arquivo") or ""
    rec.receita = frontend_mc.get("receita")
    rec.receita_liq = frontend_mc.get("receitaLiq")
    rec.custo = frontend_mc.get("custo")
    rec.mc_projeto = frontend_mc.get("mcProjeto")
    rec.mc_projeto_pct = frontend_mc.get("mcProjetoPct")
    rec.mc_direta = frontend_mc.get("mcDireta")
    rec.mc_direta_pct = frontend_mc.get("mcDiretaPct")
    rec.alerta = bool(parsed.divergencias or parsed.linhas_fora)
    rec.dados = frontend_mc

    db.query(models.MCLinha).filter(models.MCLinha.mc_id == mc_id).delete()
    for l in parsed.linhas:
        db.add(models.MCLinha(
            mc_id=mc_id, pilar_k=l.pilar_k, pilar=l.pilar, aba=l.aba, idx=l.idx,
            cat=l.cat, desc=l.desc, extra=l.extra, g1=l.g1,
            meses=l.meses, qtd=l.qtd, unit=l.unit, total=l.total,
            hm=l.hm, calc=l.calc, caixa=l.caixa,
        ))

    db.flush()
    if cliente_anterior and cliente_anterior != rec.cliente:
        _refresh_cliente(db, cliente_anterior)
    _refresh_cliente(db, rec.cliente)
    return rec


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
