from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


@router.get("")
def listar(db: Session = Depends(get_db)):
    recs = db.query(models.Cliente).order_by(models.Cliente.nome.asc()).all()
    return [
        {
            "nome": r.nome,
            "contratos": r.n_contratos,
            "receita": r.receita_total,
            "receitaLiq": r.receita_liq_total,
            "custo": r.custo_total,
            "mcProjeto": r.mc_projeto_total,
            "mcProjetoPct": (r.mc_projeto_total / r.receita_liq_total) if r.receita_liq_total else None,
            "mcDireta": r.mc_direta_total,
            "mcDiretaPct": (r.mc_direta_total / r.receita_liq_total) if r.receita_liq_total else None,
        }
        for r in recs
    ]
