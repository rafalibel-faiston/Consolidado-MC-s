"""
Serializa o MC do parser Python no MESMO formato de objeto que o parser
client-side (JS) do Painel_MC_Faiston.html produzia.

Isso é o que permite o front-end continuar com toda a UI (render, tabs,
drill-down, simulador) sem reescrita: ele recebe do backend exatamente o
`mc` que antes montava sozinho lendo o xlsx no navegador.
"""
from __future__ import annotations

from typing import Any

from .parser import MC, PILARES, Linha


def _row_json(l: Linha) -> dict:
    return {
        "cat": l.cat, "desc": l.desc, "g1": l.g1, "extra": l.extra,
        "meses": l.meses, "qtd": l.qtd, "unit": l.unit, "total": l.total,
        "hm": l.hm, "calc": l.calc,
    }


def mc_to_frontend(mc: MC) -> dict:
    blocos: dict[str, Any] = {}
    for p in PILARES:
        k = p["k"]
        rows = [_row_json(l) for l in mc.linhas if l.pilar_k == k]
        blocos[k] = {"rows": rows, "sheet": mc.abas.get(k, "")}

    out: dict[str, Any] = {
        "id": f'{mc.meta.get("contrato", "")}|{mc.meta.get("arquivo", "")}',
        **mc.meta,
        "blocos": blocos,
        "somas": mc.somas,
        "dre": mc.dre,
        "impostoFator": mc.imposto_fator,
        "rateios": mc.rateios,
        "custoLinhas": sum(mc.somas.values()),
        "custoDRE": mc.dre.get("custos"),
        "divergencias": mc.divergencias,
        "linhasForaDaConta": mc.linhas_fora,
    }
    out.update(mc.calc)
    return out
