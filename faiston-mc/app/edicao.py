"""
Edição manual de uma MC já importada.

O painel deixa a Bruna mexer em qualquer campo da MC (receita, imposto, rateios,
cabeçalho e linha a linha dos 4 pilares). O front simula na hora; quando ela
salva, o payload cai aqui: reaplicamos os campos por cima do objeto MC guardado
e **recalculamos tudo** com o mesmo núcleo do parser (`calc_dre`, `line_cost`,
`classificar`), pra não existir um segundo jeito de calcular MC no projeto.

O 5.DRE original NÃO é tocado — ele continua sendo a foto da planilha. Quem
edita passa a divergir do DRE de propósito, e a aba Auditoria mostra isso.
"""
from __future__ import annotations

from typing import Any

from .caixinhas import classificar
from .parser import PILARES, Linha, calc_dre, line_cost, num

# campos de cabeçalho que dá pra editar no painel (contrato e arquivo ficam de
# fora: o id da MC é "{contrato}|{arquivo}" e mexer neles quebraria o upsert)
META_TEXTO = ("cliente", "projeto", "produto", "responsavel", "comentarios", "inicio", "fim")


def _txt(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _linha_dict(r: dict, hm_base: int = 0) -> dict:
    """Normaliza uma linha vinda do front: números viram número e o custo
    recalcula quando o usuário não mandou um custo final explícito."""
    hm = int(num(r.get("hm", hm_base)) or 0)
    qtd = num(r.get("qtd"))
    unit = num(r.get("unit"))
    meses = num(r.get("meses"))
    calc = line_cost(qtd, unit, meses, hm)
    total = num(r.get("total")) if r.get("total") is not None else calc
    return {
        "cat": _txt(r.get("cat")), "desc": _txt(r.get("desc")),
        "g1": _txt(r.get("g1")), "extra": _txt(r.get("extra")),
        "meses": meses, "qtd": qtd, "unit": unit, "total": total,
        "hm": hm, "calc": calc,
    }


def _linhas_de(blocos: dict) -> tuple[list[Linha], dict[str, float]]:
    linhas: list[Linha] = []
    somas: dict[str, float] = {}
    for p in PILARES:
        k = p["k"]
        bloco = blocos.get(k) or {}
        do_pilar: list[Linha] = []
        for i, r in enumerate(bloco.get("rows") or []):
            l = Linha(
                pilar_k=k, pilar=p["n"], aba=bloco.get("sheet") or "", idx=i + 1,
                cat=r.get("cat", ""), desc=r.get("desc", ""),
                extra=r.get("extra", ""), g1=r.get("g1", ""),
                meses=num(r.get("meses")), qtd=num(r.get("qtd")), unit=num(r.get("unit")),
                total=num(r.get("total")), hm=int(r.get("hm") or 0), calc=num(r.get("calc")),
            )
            l.caixa = classificar(l)
            do_pilar.append(l)
        linhas.extend(do_pilar)
        somas[k] = sum(l.total for l in do_pilar)
    return linhas, somas


def aplicar_edicao(dados: dict, edit: dict) -> tuple[dict, list[Linha]]:
    """Devolve (objeto MC atualizado no formato do front, linhas já classificadas)."""
    out: dict[str, Any] = dict(dados)

    for k in META_TEXTO:
        if edit.get(k) is not None:
            out[k] = _txt(edit[k])

    if "mesesContrato" in edit:
        m = int(num(edit.get("mesesContrato")))
        out["mesesContrato"] = m if m > 0 else None

    if edit.get("receita") is not None:
        out["receita"] = num(edit["receita"])
    if edit.get("impostoFator") is not None:
        out["impostoFator"] = num(edit["impostoFator"])
    if edit.get("rateios") is not None:
        out["rateios"] = [{"nome": _txt(r.get("nome")), "p": num(r.get("p"))}
                          for r in (edit["rateios"] or [])]

    # blocos: copia profunda do que está salvo e sobrescreve com o que veio
    blocos: dict[str, Any] = {}
    for k, b in (out.get("blocos") or {}).items():
        blocos[k] = {**b, "rows": [dict(r) for r in (b.get("rows") or [])]}

    for p in PILARES:
        k = p["k"]
        novas = (edit.get("blocos") or {}).get(k)
        if novas is None:
            continue
        bloco = blocos.setdefault(k, {"rows": [], "sheet": ""})
        antigas = bloco.get("rows") or []
        hm_bloco = int(antigas[0].get("hm") or 0) if antigas else 0
        bloco["rows"] = [_linha_dict(r, hm_bloco) for r in novas]

    out["blocos"] = blocos

    linhas, somas = _linhas_de(blocos)
    out["somas"] = somas
    out.update(calc_dre(out.get("receita") or 0.0, somas,
                        out.get("impostoFator") or 0.0, out.get("rateios") or []))
    out["custoLinhas"] = sum(somas.values())

    dre = out.get("dre") or {}
    out["custoDRE"] = dre.get("custos")
    divergencias = []
    if dre.get("found"):
        for p in PILARES:
            d = (dre.get("pilar") or {}).get(p["k"])
            if d is not None and abs(d - somas[p["k"]]) > 0.05:
                divergencias.append({"pilar": p["n"], "linhas": somas[p["k"]],
                                     "dre": d, "dif": somas[p["k"]] - d})
    out["divergencias"] = divergencias
    out["linhasForaDaConta"] = [
        {"pilar": l.pilar, "idx": l.idx, "desc": l.desc or l.cat, "calc": l.calc, "total": l.total}
        for l in linhas if abs(l.calc - l.total) > 0.05
    ]
    out["editado"] = True
    return out, linhas
