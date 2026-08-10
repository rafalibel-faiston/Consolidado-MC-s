# Painel de MC — Faiston

Painel de Margem de Contribuição. Lê as planilhas do modelo oficial de MC da Faiston
no backend e replica o `DASHBOARD_GERENCIAL_CONTRATOS`, com drill-down por
categoria de custo.

**Estado atual:** backend FastAPI + Postgres em `faiston-mc/`, pronto pra subir no
Railway. Front-end continua sendo o `Painel_MC_Faiston.html` original (agora em
`faiston-mc/frontend/index.html`), só trocando `localStorage` por `fetch` na API e
ganhando uma tela de login. Parsing das planilhas saiu do navegador e agora roda no
servidor (`faiston-mc/app/parser.py`), compartilhado pela equipe toda.

**Para quem:** Bruna (gestora de operações, dona do processo de MC). Rafael desenvolve.

---

## 1. O modelo de MC (o que a planilha é)

Workbook `.xlsb`/`.xlsx` com ~27 abas. Só estas importam:

| Aba | O que tem |
|---|---|
| `1.DADOS_INICIAIS` | cliente, produto, responsável, datas, nº de meses do contrato, descrição |
| `2.1.EQUIPE.FAISTON` | headcount: GRUPO, TIPO DE CONTRATO, CARGO, QTDE MESES, QTDE DE RECURSOS, CUSTO BASE, CUSTO FINAL |
| `2.2.SUPORTE.CAMPO` | TIPO DE SERVIÇO, TIPO DE CONTRATO, QTDE MESES, QTDE, VALOR UNIT., COMENTÁRIO, CUSTO FINAL |
| `2.3.EQUIPAMENTOS.LOGISTICA` | TIPO DE SERVIÇO, DESCRIÇÃO, LOCAL, QTDE, VALOR UNIT, CUSTO FINAL — **sem coluna de meses** |
| `2.4.INVESTIMENTOS` | CATEGORIA, DESCRIÇÃO, FORNECEDOR, QTDE MESES, QTDE, CUSTO UNIT., CUSTO FINAL |
| `2.6.IMPOSTOS` | fator único (ex: 0,1125) |
| `3.RATEIOS` | Custo com Vendas 7%, Administrativo 3%, Risco 0% — **sobre receita líquida** |
| `4.CUSTOS` | consolidação por pilar (usada só pra conferência) |
| `5.DRE` | o demonstrativo pronto — fonte da verdade pra auditoria |

As 4 abas `2.x` são os **pilares**. Cada uma tem uma coluna de categoria com uma lista
fechada — as "caixinhas" internas da MC (19 no total):

- Equipe → CLT, PJ, BUDGET, OUTROS
- Suporte de Campo → Telecom (Redes) N1, Servidores e Storage S1, Cabeamento D1, Microinformática M1
- Equip./Logística → Armazenagem, Seguro, Distribuição, Movimentação de peças, Reparo, Outros
- Investimentos → Compra de peças, Equipamentos, Ferramentas de trabalho, Sistemas, Outros

### O cálculo (validado, não mexer sem motivo)

```
Receita bruta
− Impostos            (fator de 2.6.IMPOSTOS)
= Receita líquida     ("net revenue")
− Custos diretos      (soma dos 4 pilares)
= MC do projeto       ("DM" no dashboard gerencial)
− Rateios             (percentuais de 3.RATEIOS aplicados sobre a RECEITA LÍQUIDA)
= MC direta Faiston
```

**MC% é sobre a receita líquida, não sobre o TCV.** Errar isso foi a primeira coisa
que corrigi neste projeto.

Custo de cada linha: `qtde × valor unitário × meses`, e **meses só entra se o bloco
tiver a coluna** — a aba 2.3 não tem, então lá é `qtde × unitário`. Se meses estiver
0 ou vazio num bloco que tem a coluna, o custo é 0 (é assim que a planilha zera linha
descartada, tipo "NÃO CONTEMPLA").

### Números de referência — `MC F260153-2 NTT - Instalação.xlsx`

Qualquer refactor no parser tem que continuar batendo nisto:

```
equipe        1.271,4933      campo      8.052,00
log               0,00        invest       805,75
custo        10.129,2433   == 3. CUSTOS do 5.DRE
receita      17.600,00     impostos   1.980,00 (11,25%)
receita líq  15.620,00
DM            5.490,7568   == 4.1 do 5.DRE   → 35,15%
rateios       1.562,00     (7% + 3% + 0%)
MC direta     3.928,7568   == 6.1 do 5.DRE   → 25,15%
```

---

## 2. O dashboard gerencial (o que a Bruna já usa)

`DASHBOARD_GERENCIAL_CONTRATOS_07.08.2026.xlsm`, aba `Contratos`, cabeçalho na
**linha 6**, dados da linha 7 em diante, ~293 contratos. Fórmulas relevantes:

```
VALOR MENSAL  = TOTAL CONTRATO / meses de vigência
% FAT         = VALOR MENSAL / 12
IMP           = TOTAL CONTRATO × TAX          (TAX = 0,1125)
NET REVENUE   = TOTAL CONTRATO − IMP
COSTS MENSAIS = SUM(U:AH)                      -- as 14 caixinhas, MENSAIS
COSTS TOTAIS  = COSTS MENSAIS × meses
DM            = NET REVENUE − COSTS TOTAIS
%             = DM / NET REVENUE
```

Ou seja: **`DM` do dashboard == `MC do projeto` da MC**, antes de rateios. É o que
amarra os dois documentos. O dashboard não conhece rateios nem MC direta.

O dashboard trabalha em **custo mensal**; a MC em **total do contrato**. O painel
tem um switch Total/Mês por causa disso.

### De-para: 4 pilares da MC → 14 colunas do dashboard

Implementado em `classificar()` — hoje em dois lugares que têm que ficar em sincronia:
`faiston-mc/app/caixinhas.py` (backend, roda na ingestão) e o bloco DE-PARA dentro do
`<script>` do `frontend/index.html` (usado pelo simulador e pela aba "Equip./Logística"
etc. do detalhe, que recalculam caixinha ao vivo). Ordem das regras importa.

| Coluna | Regra |
|---|---|
| N1 | equipe, texto casa `\bN1\b` ou `SERVICE DESK`/`HELP DESK` |
| N2 | equipe, `\bN2\b` |
| SDM2 | equipe, `\bSDM\b` ou `SERVICE DELIVERY` |
| M.O. Logistica | equipe, `LOGISTIC` |
| GP | equipe, `\bGP\b`, `GERENTE/GERENCIA DE PROJET`, `ANALISTA DE PROJETOS`, `COORDENADOR DE PROJETO` |
| ADM(MO-AL-FC) | equipe, `BACKOFFICE`, `ADMINISTRAT`, `FACILIT`, `FINANCEIR`, `LIDER`, `TICKET MANAGER`, `COORDENADOR` |
| (fallback equipe) | `SUPORTE`, `INFRAESTRUT`, `TECNIC`, `CAMPO`, `REDES`, `SEGURANC` → N2 |
| Tec campo | **todo** o pilar 2.2 |
| Armazenagem | 2.3, `ARMAZENAG` ou `SEGURO` |
| Logistica de peças | 2.3, `DISTRIBUI`, `MOVIMENTAC`, `FRETE`, `TRANSPORT`, `LOGISTIC` |
| Reparos peças | 2.3, `REPARO` |
| SISTEMA | 2.4, `SISTEMA`, `SOFTWARE`, `LICENC` |
| TELEFONIA | `TELEFON`, `VOZ`, `PABX`, `CELULAR`, `LINK DE`, `OMNIPBX`, `CALL CENTER`, `E1`, `RAMAL` |
| Locação | `LOCACAO`, `ALUGUEL`, `ESPACO COMERCIAL`, `COMODATO` |
| Invest. Spare | 2.4, `COMPRA DE PECA`, `PECA`, `SPARE`, `EQUIPAMENT`, `FERRAMENT`, `NOTEBOOK`, `SERVIDOR`, `STORAGE` |
| **Não mapeado** | resto — bucket de auditoria, aparece cinza tracejado na UI |

O texto testado é `GRUPO + CATEGORIA + DESCRIÇÃO` normalizado (maiúscula, sem acento).

**Invariante:** `soma das 14 caixinhas + não mapeado == custo total da MC`. Sempre.
Nada pode sumir na classificação. Validado localmente com um workbook sintético
(ver seção 6) batendo a soma exata do custo total.

### Pendência conhecida

Na `F260153-2` sobram **R$ 805,75** em `2.4.INVESTIMENTOS` categoria "Outros":
`Miscelâneas por EQTO` (440,00), `KM budget` (365,75), `Sefaz` (0,00).
Rafael ainda não definiu a coluna de destino. Não inventar — deixar em Não mapeado
até ele decidir.

---

## 3. O backend (`faiston-mc/`)

FastAPI + Postgres, pensado pra rodar como um único serviço no Railway (a API serve
o HTML do painel também — não tem front e back separados).

```
faiston-mc/
  app/
    parser.py       # leitura das planilhas — porta validada do parser client-side
    caixinhas.py     # de-para linha → caixinha (classificar / soma_caixas)
    compat.py        # serializa o MC no MESMO formato de objeto que o front espera
    models.py         # SQLAlchemy: MCRecord, MCLinha, Ingestao
    database.py        # engine/session, cria as tabelas no startup
    config.py            # lê APP_PASSWORD / SECRET_KEY / etc do ambiente
    main.py                # FastAPI app, serve o index.html, healthcheck
    routes/
      auth.py               # POST /api/login, /api/logout, GET /api/me
      mcs.py                 # upload/list/detail/delete/clear das MCs
  frontend/
    index.html                # o painel — mesmo HTML de sempre, só fetch em vez de localStorage
  requirements.txt
  Dockerfile
  railway.json
  .env.example
```

### Por que o front quase não mudou

A ideia do parser em Python (`parser.py`) sempre foi ser uma porta 1:1 do parser que
rodava no navegador. Isso permitiu ir um passo além: `compat.py` serializa a saída do
parser Python **no exato mesmo formato de objeto** que o `parseMC()` do JavaScript
produzia (mesmo `mc.blocos.{pilar}.rows`, mesmo `mc.dre`, mesmo `mc.rateios` etc).
Resultado: a UI inteira (`render`, as 4 abas macro, os 9 drill-downs, as 8 abas de
detalhe, o simulador) não precisou ser tocada. Só três coisas mudaram no front:

1. `save()`/`load()` viraram `loadMCs()` — `fetch('/api/mcs')` em vez de `localStorage`.
2. `handleFiles()` não lê mais o xlsx no navegador — manda os arquivos crus pro
   `POST /api/mcs/upload` via `FormData` e recarrega a lista.
3. Ganhou uma tela de login (`#loginScreen`) na frente de tudo, gated por
   `GET /api/me`.

SheetJS (a lib que lia xlsx no navegador) saiu — não é mais necessário. Chart.js
continua, é só pra desenhar os gráficos.

### Autenticação

Senha única (`APP_PASSWORD`), compartilhada pela equipe. `POST /api/login` valida e
seta um cookie assinado (`itsdangerous`, `httpOnly`, `SameSite=Lax`, `Secure` em
produção) — não guarda sessão no banco, só o cookie assinado com `SECRET_KEY`. Toda
rota de `/api/mcs/*` exige esse cookie.

### Rotas

```
GET  /healthz              healthcheck do Railway
GET  /                     serve o painel (index.html)
POST /api/login            {senha} → seta cookie
POST /api/logout           limpa cookie
GET  /api/me                200 se autenticado, 401 se não
POST /api/mcs/upload        multipart (files[]) → parse no servidor → upsert → {ok:[ids], erros:[...]}
GET  /api/mcs                lista todas as MCs (formato compatível com o front)
GET  /api/mcs/{id}            detalhe de uma MC
DELETE /api/mcs/{id}          remove uma MC
POST /api/mcs/clear           remove todas (usado pelo botão "Limpar painel")
```

`id` de uma MC é `"{contrato}|{arquivo}"` — reenviar o mesmo arquivo faz upsert, não
duplica.

### Banco

Três tabelas (Postgres, mas cai pra SQLite local se `DATABASE_URL` não estiver
setado — só pra rodar/testar sem banco):

- **mcs** — cabeçalho + totais + o objeto MC inteiro em JSON (é o que a API devolve
  direto pro front, sem recomputar nada)
- **mc_linhas** — linha a linha já classificada, pra dar pra consultar por caixinha
  sem abrir o JSON no futuro
- **ingestoes** — histórico de cada upload (arquivo, resultado, mensagem de erro)

Tabelas são criadas automaticamente no startup (`Base.metadata.create_all`) — sem
Alembic por enquanto, é cedo pro projeto pra valer a complexidade de migrations.

### Deploy no Railway

1. Criar um projeto no Railway, adicionar um plugin **Postgres**.
2. Criar o serviço a partir deste repo, apontando o **root directory** pra
   `faiston-mc` (é onde estão o `Dockerfile` e o `railway.json`).
3. Variáveis de ambiente do serviço:
   - `DATABASE_URL` → referenciar o Postgres do Railway (`${{Postgres.DATABASE_URL}}`)
   - `APP_PASSWORD` → a senha que a Bruna (e o resto da equipe) vai usar
   - `SECRET_KEY` → uma string aleatória longa (`python3 -c "import secrets; print(secrets.token_hex(32))"`)
4. Deploy. O healthcheck é `/healthz`.

O app recusa subir (`RuntimeError` no startup) se `APP_PASSWORD` ou `SECRET_KEY` não
estiverem setados — de propósito, pra nunca subir sem autenticação por engano.

---

## 4. Decisões já tomadas (não reabrir sem motivo)

- MC% sobre receita líquida, não sobre TCV
- Mostrar MC do projeto **e** MC direta, projeto em destaque
- Ler as linhas **e** o 5.DRE, e comparar — é o que dá a auditoria de graça
- **Sem semáforo de cor** por faixa de margem. A diretoria não definiu meta. Só ranking.
- MCs legadas do Faiston Ops (só equipe + investimentos, sem imposto nem rateio) ficam **de fora**
- Nada de "calcular custo sem tal pilar" — os toggles foram removidos, filtro agora é por MC
- Categoria não classificada vai pra "Não mapeado", nunca some
- Visual segue o Ops (roxo), não o brand guideline azul/ciano
- Parsing das planilhas roda no backend (Python), não mais no navegador — só o
  simulador (`calcDRE`/`lineCost`/`classificar` do JS) continua client-side, porque é
  cenário hipotético que não deveria bater no servidor a cada tecla
- Senha única compartilhada pra começar — sem usuário/senha por pessoa ainda

## 5. Ideias que ficaram de fora

Comparar duas versões da mesma MC, histórico de margem por contrato ao longo do
tempo, puxar as MCs direto do OneDrive usando o conector de MC que o Faiston Ops já
tem, autenticação por pessoa (hoje é senha única), Alembic quando o schema começar a
mudar de verdade.

## 6. Como testar

Não tem framework de teste automatizado ainda. O que foi feito até aqui:

- **Backend:** gerado um workbook sintético (`openpyxl`) reproduzindo a estrutura das
  8 abas relevantes, rodado `parse_mc()` direto e conferido: soma dos pilares bate
  com `custo`, `mcProjeto`/`mcDireta` batem com o cálculo manual, zero divergências
  entre linhas e DRE, e a invariante `soma das caixinhas == custo total` fecha exato.
  Depois, subido o servidor local e exercitado o ciclo HTTP completo: login com senha
  errada/certa, `/api/me` antes/depois, upload multipart (incluindo arquivo inválido,
  que retorna erro claro em vez de 500), upsert do mesmo arquivo (não duplica),
  detalhe, delete, clear e logout.
- **O que falta:** rodar contra uma planilha real da Faiston e conferir os números de
  referência da seção 1 (`MC F260153-2 NTT - Instalação.xlsx`) — isso só dá pra fazer
  com o arquivo de verdade em mãos, que não estava disponível nesta sessão.
- **Front-end:** ainda não testado num navegador de verdade contra o backend rodando
  (precisa `npm`/servidor local + Postgres ou SQLite). Vale abrir o painel depois do
  deploy e conferir visualmente: tela de login, upload arrastando um xlsx real,
  as 4 abas macro, um drill-down, o detalhe de uma MC e o simulador.

Planilhas de referência: `MC F260153-2 NTT - Instalação.xlsx` e
`DASHBOARD_GERENCIAL_CONTRATOS_07.08.2026.xlsm`.

## 7. Cuidados

- Não quebrar a invariante da soma das caixinhas
- `num()` (e o `norm()`/`num()` do Python) precisa continuar aceitando `'20,53'` —
  CUSTO BASE às vezes vem como texto
- Match de coluna é **exato primeiro, depois substring**: `TIPO` casaria com `TIPO DE CONTRATO`
- O nome da aba varia entre planilhas; buscar por fragmento (`EQUIPE`, `SUPORTE`, `LOGISTICA`,
  `INVESTIMENTOS`, `DRE`), nunca por nome exato
- Dado de margem e custo de contrato é sensível — por isso a autenticação por senha
  antes de qualquer rota de dados, e o cookie é sempre `httpOnly`
- Mudar `classificar()` num lado (`app/caixinhas.py` ou o JS do front) sem mudar no
  outro quebra a sincronia entre o que a ingestão grava e o que o simulador mostra
