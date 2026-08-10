"""
Leitor do modelo oficial de Memória de Cálculo (MC) da Faiston.

Porta em Python do parser validado no navegador. Lê as abas 2.1 a 2.4
(levantamento de custos), 2.6 (impostos), 3 (rateios), 5.DRE e 1.DADOS_INICIAIS.

Validado contra 'MC F260153-2 NTT - Instalação.xlsx':
    equipe    1.271,4933
    campo     8.052,00
    log           0,00
    invest      805,75
    custo    10.129,2433   == 3. CUSTOS do 5.DRE
    DM        5.490,7568   == 4.1 do 5.DRE  (35,15%)
    MC direta 3.928,7568   == 6.1 do 5.DRE  (25,15%)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# ---------------------------------------------------------------- helpers

def norm(v: Any) -> str:
    """Maiúscula, sem acento, espaços colapsados. Base de toda comparação."""
    if v is None:
        return ""
    s = str(v).strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s)


def num(v: Any) -> float:
    """Aceita float, '1.234,56' (pt-BR) e '1234.56'. Nunca levanta."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) if v == v and abs(v) != float("inf") else 0.0
    s = re.sub(r"[R$\s%]", "", str(v))
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        f = float(s)
    except ValueError:
        return 0.0
    return f if f == f else 0.0


def fmt_date(v: Any) -> str:
    if isinstance(v, (datetime, date)):
        return v.strftime("%d/%m/%Y")
    return str(v) if v is not None else ""


def to_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


# ---------------------------------------------------------------- pilares

PILARES = [
    {"k": "equipe", "n": "Equipe Faiston", "frag": "EQUIPE"},
    {"k": "campo", "n": "Suporte de Campo", "frag": "SUPORTE"},
    {"k": "log", "n": "Equipamentos/Logística", "frag": "LOGISTICA"},
    {"k": "invest", "n": "Investimentos", "frag": "INVESTIMENTOS"},
]

# nome lógico -> possíveis cabeçalhos na planilha, em ordem de preferência
COLMAP: dict[str, dict[str, list[str]]] = {
    "equipe": {
        "cat": ["TIPO DE CONTRATO"], "desc": ["CARGO"], "e1": ["GRUPO"],
        "e2": ["DEDICADO/COMPARTILHADO", "DEDICADO"], "e3": ["TIPO"],
        "meses": ["QTDE MESES"], "qtd": ["QTDE DE RECURSOS"],
        "unit": ["CUSTO BASE"], "total": ["CUSTO FINAL"],
    },
    "campo": {
        "cat": ["TIPO DE SERVICO"], "desc": ["COMENTARIO"], "e1": ["TIPO DE CONTRATO"],
        "meses": ["QTDE MESES"], "qtd": ["QTDE"],
        "unit": ["VALOR UNIT.", "VALOR UNIT"], "total": ["CUSTO FINAL"],
    },
    "log": {
        "cat": ["TIPO DE SERVICO"], "desc": ["DESCRICAO"], "e1": ["LOCAL"],
        "meses": ["QTDE MESES"], "qtd": ["QTDE"],
        "unit": ["VALOR UNIT", "CUSTO UNIT"], "total": ["CUSTO FINAL"],
    },
    "invest": {
        "cat": ["CATEGORIA DE INVESTIMENTO", "CATEGORIA"], "desc": ["DESCRICAO"],
        "e1": ["FORNECEDOR"], "meses": ["QTDE MESES"], "qtd": ["QTDE"],
        "unit": ["CUSTO UNIT.", "CUSTO UNIT", "VALOR UNIT"], "total": ["CUSTO FINAL"],
    },
}


# ---------------------------------------------------------------- leitura da pasta de trabalho

class Workbook:
    """Adapta openpyxl (.xlsx/.xlsm) e pyxlsb (.xlsb) numa interface só: grade de células."""

    def __init__(self, grids: dict[str, list[list[Any]]]):
        self.grids = grids

    @property
    def sheet_names(self) -> list[str]:
        return list(self.grids)

    def find_sheet(self, frag: str) -> str | None:
        f = norm(frag)
        for name in self.grids:
            if f in norm(name):
                return name
        return None

    def grid(self, name: str | None) -> list[list[Any]]:
        return self.grids.get(name or "", [])

    # ---- construtores

    @classmethod
    def open(cls, path_or_buf, filename: str) -> "Workbook":
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext == "xlsb":
            return cls._from_xlsb(path_or_buf)
        return cls._from_openpyxl(path_or_buf)

    @classmethod
    def _from_openpyxl(cls, src) -> "Workbook":
        import openpyxl

        wb = openpyxl.load_workbook(src, data_only=True, read_only=True)
        grids: dict[str, list[list[Any]]] = {}
        for ws in wb.worksheets:
            grids[ws.title] = [[c.value for c in row] for row in ws.iter_rows()]
        wb.close()
        return cls(grids)

    @classmethod
    def _from_xlsb(cls, src) -> "Workbook":
        from pyxlsb import open_workbook  # type: ignore

        grids: dict[str, list[list[Any]]] = {}
        with open_workbook(src) as wb:
            for name in wb.sheets:
                with wb.get_sheet(name) as sheet:
                    grids[name] = [[c.v for c in row] for row in sheet.rows()]
        return cls(grids)


# ---------------------------------------------------------------- blocos 2.1 a 2.4

@dataclass
class Linha:
    pilar_k: str
    pilar: str
    aba: str
    idx: int
    cat: str = ""
    desc: str = ""
    extra: str = ""
    g1: str = ""
    meses: float = 0.0
    qtd: float = 0.0
    unit: float = 0.0
    total: float = 0.0
    hm: int = 0          # o bloco tem coluna de meses?
    calc: float = 0.0    # qtd * unit * (meses se hm)
    caixa: str = "nao"

    def to_dict(self) -> dict:
        return {
            "pilarK": self.pilar_k, "pilar": self.pilar, "aba": self.aba, "idx": self.idx,
            "cat": self.cat, "desc": self.desc, "extra": self.extra, "g1": self.g1,
            "meses": self.meses, "qtd": self.qtd, "unit": self.unit, "total": self.total,
            "hm": self.hm, "calc": self.calc, "caixa": self.caixa,
        }


def line_cost(qtd: float, unit: float, meses: float, hm: int) -> float:
    return qtd * unit * (meses if hm else 1)


def _find_header(grid: list[list[Any]], must: list[str]) -> int:
    for i, row in enumerate(grid[:25]):
        cells = [norm(v) for v in row]
        if all(any(m in c for c in cells) for m in must):
            return i
    return -1


def _col_of(cells: list[str], pats: list[str]) -> int:
    """Match exato primeiro — evita 'TIPO' casar com 'TIPO DE CONTRATO'."""
    for p in pats:
        for j, c in enumerate(cells):
            if c == p:
                return j
    for p in pats:
        for j, c in enumerate(cells):
            if c and p in c:
                return j
    return -1


def parse_bloco(wb: Workbook, pilar: dict) -> tuple[list[Linha], str]:
    name = wb.find_sheet(pilar["frag"])
    if not name:
        return [], ""
    grid = wb.grid(name)
    hi = _find_header(grid, ["#", "CUSTO FINAL"])
    if hi < 0:
        return [], name

    cells = [norm(v) for v in grid[hi]]
    cmap = COLMAP[pilar["k"]]
    idx = {k: _col_of(cells, pats) for k, pats in cmap.items()}
    hm = 1 if idx.get("meses", -1) >= 0 else 0

    def get(row: list[Any], key: str) -> Any:
        j = idx.get(key, -1)
        return row[j] if 0 <= j < len(row) else None

    linhas: list[Linha] = []
    for row in grid[hi + 1:]:
        cat = str(get(row, "cat") or "").strip()
        desc = str(get(row, "desc") or "").strip()
        total = num(get(row, "total"))
        qtd = num(get(row, "qtd"))
        unit = num(get(row, "unit"))
        if not cat and not desc and not total and not qtd and not unit:
            continue  # linha do formulário ainda em branco
        extra = " · ".join(
            str(get(row, k)).strip()
            for k in ("e1", "e2", "e3")
            if get(row, k) is not None and str(get(row, k)).strip()
        )
        meses = num(get(row, "meses"))
        l = Linha(
            pilar_k=pilar["k"], pilar=pilar["n"], aba=name, idx=len(linhas) + 1,
            cat=cat, desc=desc, extra=extra, g1=str(get(row, "e1") or "").strip(),
            meses=meses, qtd=qtd, unit=unit, total=total, hm=hm,
            calc=line_cost(qtd, unit, meses, hm),
        )
        linhas.append(l)
    return linhas, name


# ---------------------------------------------------------------- 5.DRE, impostos e rateios

def parse_dre(wb: Workbook) -> dict:
    """Lê o 5.DRE por rótulo: o valor é o último número da linha, o % é um número <= 5 antes dele."""
    out: dict[str, Any] = {"found": False, "linhas": {}}
    name = wb.find_sheet("DRE")
    if not name:
        return out
    out["found"] = True

    for row in wb.grid(name):
        label = None
        nums: list[float] = []
        for v in row:
            if isinstance(v, str) and v.strip() and label is None:
                label = v.strip()
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                nums.append(float(v))
        if not label or not nums:
            continue
        p = next((n for n in reversed(nums[:-1]) if abs(n) <= 5), None)
        out["linhas"][norm(label)] = {"label": label, "value": nums[-1], "pct": p}

    def pick(*frags):
        for f in frags:
            key = next((k for k in out["linhas"] if k.startswith(norm(f))), None)
            if key:
                return out["linhas"][key]
        return None

    def val(x):
        return x["value"] if x else None

    out["receitaBruta"] = val(pick("1. RECEITA BRUTA", "1.RECEITA BRUTA"))
    out["impostos"] = val(pick("2. IMPOSTOS"))
    out["custos"] = val(pick("3. CUSTOS"))
    out["pilar"] = {
        "equipe": val(pick("3.1.")), "campo": val(pick("3.2.")),
        "log": val(pick("3.3.")), "invest": val(pick("3.4.")),
    }
    mcp, mcd = pick("4.1."), pick("6.1.")
    out["mcProjeto"] = val(mcp)
    out["mcProjetoPct"] = mcp["pct"] if mcp else None
    out["mcDireta"] = val(mcd)
    out["mcDiretaPct"] = mcd["pct"] if mcd else None
    out["rateios"] = val(pick("5. RATEIOS"))
    out["rateioLinhas"] = [
        {"nome": re.sub(r"^5\.\d\.\s*", "", x["label"]), "valor": x["value"]}
        for x in (pick("5.1."), pick("5.2."), pick("5.3.")) if x
    ]
    return out


def parse_fatores(wb: Workbook) -> dict:
    """2.6.IMPOSTOS -> fator único somado. 3.RATEIOS -> lista de percentuais sobre receita líquida."""
    out: dict[str, Any] = {"impostoFator": None, "rateios": []}

    si = wb.find_sheet("IMPOSTOS")
    if si:
        total, ok = 0.0, False
        for row in wb.grid(si):
            label = next((v for v in row if isinstance(v, str) and v.strip()), None)
            nums = [float(v) for v in row if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if label and len(nums) >= 2 and abs(nums[-1]) <= 1:
                total += nums[-1]
                ok = True
        if ok:
            out["impostoFator"] = total

    sr = wb.find_sheet("RATEIOS")
    if sr:
        for row in wb.grid(sr):
            strs = [v for v in row if isinstance(v, str) and v.strip()]
            nums = [float(v) for v in row if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if strs and len(nums) >= 2 and abs(nums[-1]) <= 1 and norm(strs[0]) != "RATEIO":
                out["rateios"].append({"nome": strs[0].strip(), "p": nums[-1]})
    return out


# ---------------------------------------------------------------- cabeçalho

def parse_meta(wb: Workbook, filename: str) -> dict:
    base = re.sub(r"\.[^.]+$", "", filename)
    m = re.search(r"F\s?\d{6}(?:-\d+)?", base, re.I)

    meta: dict[str, Any] = {
        "arquivo": filename,
        "contrato": re.sub(r"\s", "", m.group(0)).upper() if m else "",
    }
    resto = re.sub(r"^[\s\-–_]+", "", re.sub(r"F\s?\d{6}(?:-\d+)?", "",
                   re.sub(r"^MC\s*", "", base, flags=re.I), flags=re.I)).strip()
    parts = re.split(r"\s+[-–]\s+", resto)
    meta["cliente"] = (parts[0] or "").strip()
    meta["projeto"] = (" - ".join(parts[1:]) or parts[0] or base).strip()

    sd = wb.find_sheet("DADOS_INICIAIS") or wb.find_sheet("DADOS INICIAIS")
    if sd:
        grid = wb.grid(sd)

        def find_val(frag: str):
            f = norm(frag)
            for row in grid:
                for j, v in enumerate(row):
                    if isinstance(v, str) and norm(v).startswith(f):
                        for k in range(j + 1, len(row)):
                            if row[k] is not None and str(row[k]).strip():
                                return row[k]
            return None

        for key, frag in (
            ("cliente", "NOME DO CLIENTE"), ("projeto", "NOME DO PRODUTO"),
            ("produto", "TIPO DO PRODUTO"), ("responsavel", "RESPONSAVEL1"),
            ("comentarios", "DESCRICAO DO PROJETO"),
        ):
            v = find_val(frag)
            if v:
                meta[key] = str(v).strip()

        ms = find_val("N MESES CONTRATO") or find_val("No MESES") or find_val("Nº MESES")
        if ms:
            meta["mesesContrato"] = int(num(ms))

        ini, fim = find_val("INICIO CONTRATO"), find_val("FIM CONTRATO")
        if ini:
            meta["inicio"] = fmt_date(ini)
        if fim:
            meta["fim"] = fmt_date(fim)
        if not meta.get("mesesContrato"):
            d1, d2 = to_date(ini), to_date(fim)
            if d1 and d2:
                meta["mesesContrato"] = max(1, round((d2 - d1).days / 30.44))

    meta.setdefault("cliente", "Não informado")
    meta.setdefault("projeto", base)
    return meta


# ---------------------------------------------------------------- o cálculo

def calc_dre(receita: float, somas: dict[str, float], imposto_fator: float,
             rateios: list[dict]) -> dict:
    """Núcleo do 5.DRE. MC% é sobre a RECEITA LÍQUIDA, não sobre o TCV."""
    impostos = receita * imposto_fator
    receita_liq = receita - impostos
    custo = sum(somas.get(p["k"], 0.0) for p in PILARES)
    mc_projeto = receita_liq - custo
    rateio_vals = [{"nome": r["nome"], "p": r["p"], "valor": receita_liq * r["p"]} for r in rateios]
    rateio_tot = sum(r["valor"] for r in rateio_vals)
    mc_direta = mc_projeto - rateio_tot
    return {
        "receita": receita, "impostos": impostos, "receitaLiq": receita_liq, "custo": custo,
        "mcProjeto": mc_projeto, "mcDireta": mc_direta,
        "mcProjetoPct": (mc_projeto / receita_liq) if receita_liq else None,
        "mcDiretaPct": (mc_direta / receita_liq) if receita_liq else None,
        "rateioVals": rateio_vals, "rateioTot": rateio_tot,
    }


# ---------------------------------------------------------------- entrada principal

@dataclass
class MC:
    meta: dict
    linhas: list[Linha]
    somas: dict[str, float]
    abas: dict[str, str]
    dre: dict
    imposto_fator: float
    rateios: list[dict]
    calc: dict
    divergencias: list[dict] = field(default_factory=list)
    linhas_fora: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        from .caixinhas import soma_caixas

        d = {**self.meta, **self.calc}
        d.update({
            "somas": self.somas,
            "abas": self.abas,
            "dre": self.dre,
            "impostoFator": self.imposto_fator,
            "rateios": self.rateios,
            "custoLinhas": sum(self.somas.values()),
            "custoDRE": self.dre.get("custos"),
            "divergencias": self.divergencias,
            "linhasForaDaConta": self.linhas_fora,
            "linhas": [l.to_dict() for l in self.linhas],
            "caixas": soma_caixas(self.linhas),
        })
        return d


def parse_mc(src, filename: str) -> MC:
    from .caixinhas import classificar

    wb = Workbook.open(src, filename)
    meta = parse_meta(wb, filename)

    linhas: list[Linha] = []
    somas: dict[str, float] = {}
    abas: dict[str, str] = {}
    for pilar in PILARES:
        bloco, aba = parse_bloco(wb, pilar)
        for l in bloco:
            l.caixa = classificar(l)
        linhas.extend(bloco)
        somas[pilar["k"]] = sum(l.total for l in bloco)
        abas[pilar["k"]] = aba

    dre = parse_dre(wb)
    fat = parse_fatores(wb)

    receita = dre.get("receitaBruta") or 0.0
    imposto_fator = fat["impostoFator"]
    if imposto_fator is None:
        imposto_fator = ((dre.get("impostos") or 0.0) / receita) if receita else 0.0

    rateios = fat["rateios"]
    if not rateios and dre.get("rateioLinhas"):
        base = receita - (dre.get("impostos") or 0.0)
        rateios = [{"nome": r["nome"], "p": (r["valor"] / base) if base else 0.0}
                   for r in dre["rateioLinhas"]]

    calc = calc_dre(receita, somas, imposto_fator, rateios)

    # auditoria 1: soma das linhas x 5.DRE
    divergencias = []
    if dre.get("found"):
        for p in PILARES:
            d = (dre.get("pilar") or {}).get(p["k"])
            if d is not None and abs(d - somas[p["k"]]) > 0.05:
                divergencias.append({"pilar": p["n"], "linhas": somas[p["k"]],
                                     "dre": d, "dif": somas[p["k"]] - d})

    # auditoria 2: qtde x valor x meses != custo final
    linhas_fora = [
        {"pilar": l.pilar, "idx": l.idx, "desc": l.desc or l.cat,
         "calc": l.calc, "total": l.total}
        for l in linhas if abs(l.calc - l.total) > 0.05
    ]

    return MC(meta=meta, linhas=linhas, somas=somas, abas=abas, dre=dre,
              imposto_fator=imposto_fator, rateios=rateios, calc=calc,
              divergencias=divergencias, linhas_fora=linhas_fora)
