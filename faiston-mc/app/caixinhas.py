"""
De-para: linhas da MC -> as 14 caixinhas do Dashboard Gerencial.

Porta exata da lógica validada em Painel_MC_Faiston.html (função `classificar`).
Ordem das regras importa — não reordenar sem checar o de-para no CLAUDE.md.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .parser import norm

if TYPE_CHECKING:
    from .parser import Linha

CAIXAS = [
    {"k": "n1", "n": "N1", "col": "N1", "pil": "equipe"},
    {"k": "n2", "n": "N2", "col": "N2", "pil": "equipe"},
    {"k": "campo", "n": "Tec campo", "col": "Tec campo", "pil": "campo"},
    {"k": "logpecas", "n": "Logística de peças", "col": "Logistica de peças", "pil": "log"},
    {"k": "molog", "n": "M.O. Logística", "col": "M.O. Logistica", "pil": "equipe"},
    {"k": "armaz", "n": "Armazenagem", "col": "Armazenagem", "pil": "log"},
    {"k": "reparo", "n": "Reparos peças", "col": "Reparos peças", "pil": "log"},
    {"k": "spare", "n": "Invest. Spare", "col": "Invest. Spare", "pil": "invest"},
    {"k": "locacao", "n": "Locação", "col": "Locação", "pil": "invest"},
    {"k": "sdm", "n": "SDM", "col": "SDM2", "pil": "equipe"},
    {"k": "sistema", "n": "Sistema", "col": "SISTEMA", "pil": "invest"},
    {"k": "tel", "n": "Telefonia", "col": "TELEFONIA", "pil": "invest"},
    {"k": "adm", "n": "ADM (MO-AL-FC)", "col": "ADM(MO - AL - FC )", "pil": "equipe"},
    {"k": "gp", "n": "GP", "col": "GP", "pil": "equipe"},
    {"k": "nao", "n": "Não mapeado", "col": "—", "pil": "*"},
]
CAIXA_BY_K = {c["k"]: c for c in CAIXAS}

RX_TEL = re.compile(r"(TELEFON|VOZ|PABX|CELULAR|LINK DE|OMNIPBX|CALL CENTER|E1\b|RAMAL)")
RX_LOC = re.compile(r"(LOCACAO|ALUGUEL|LOCAC|ESPACO COMERCIAL|COMODATO)")


def classificar(l: "Linha") -> str:
    override = getattr(l, "caixa_override", "") or ""
    if override and override in CAIXA_BY_K:
        return override

    t = norm(" ".join(x for x in (l.g1, l.cat, l.desc) if x))
    pilar_k = l.pilar_k

    if pilar_k == "campo":
        return "campo"

    if pilar_k == "equipe":
        if re.search(r"\bN1\b", t) or re.search(r"SERVICE DESK|HELP ?DESK", t):
            return "n1"
        if re.search(r"\bN2\b", t):
            return "n2"
        if re.search(r"\bSDM\b|SERVICE DELIVERY", t):
            return "sdm"
        if re.search(r"LOGISTIC", t):
            return "molog"
        if re.search(r"\bGP\b|GEREN(TE|CIA) DE PROJET|ANALISTA DE PROJETOS|COORDENADOR DE PROJETO", t):
            return "gp"
        if re.search(r"BACKOFFICE|BACK OFFICE|ADMINISTRAT|FACILIT|FINANCEIR|LIDER|TICKET MANAGER|COORDENADOR", t):
            return "adm"
        if re.search(r"SUPORTE|INFRAESTRUT|TECNIC|CAMPO|REDES|SEGURANC", t):
            return "n2"
        return "nao"

    if pilar_k == "log":
        if re.search(r"ARMAZENAG|SEGURO", t):
            return "armaz"
        if re.search(r"DISTRIBUI|MOVIMENTAC|FRETE|TRANSPORT|LOGISTIC", t):
            return "logpecas"
        if re.search(r"REPARO", t):
            return "reparo"
        if RX_TEL.search(t):
            return "tel"
        if RX_LOC.search(t):
            return "locacao"
        return "nao"

    if pilar_k == "invest":
        if re.search(r"SISTEMA|SOFTWARE|LICENC", t):
            return "sistema"
        if RX_TEL.search(t):
            return "tel"
        if RX_LOC.search(t):
            return "locacao"
        if re.search(r"COMPRA DE PECA|PECA|SPARE|EQUIPAMENT|FERRAMENT|NOTEBOOK|SERVIDOR|STORAGE", t):
            return "spare"
        return "nao"

    return "nao"


def soma_caixas(linhas: list["Linha"]) -> dict:
    s = {c["k"]: 0.0 for c in CAIXAS}
    for l in linhas:
        s[l.caixa] += l.total
    return s
