# Painel de MC — Faiston

Painel de Margem de Contribuição. Lê as planilhas do modelo oficial de MC da Faiston
no backend e replica o `DASHBOARD_GERENCIAL_CONTRATOS`, com drill-down por
categoria de custo.

**Estado atual:** backend FastAPI + Postgres em `faiston-mc/`, no ar no Railway.
Front-end continua sendo o `Painel_MC_Faiston.html` original (agora em
`faiston-mc/frontend/index.html`), só trocando `localStorage` por `fetch` na API.
Parsing das planilhas saiu do navegador e agora roda no servidor
(`faiston-mc/app/parser.py`), compartilhado pela equipe toda.

**Sem autenticação.** Não tem senha nem login — qualquer um com a URL do Railway
acessa o painel e os dados de contrato/margem direto. Decisão explícita do Rafael em
10/08/2026, revertendo a exigência de senha que existia antes (ver seção 4). Rever
isso se o painel deixar de ser só interno.

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
    edicao.py         # aplica a edição manual de uma MC e recalcula tudo
    compat.py        # serializa o MC no MESMO formato de objeto que o front espera
    models.py         # SQLAlchemy: MCRecord, MCLinha, Ingestao, Cliente
    database.py        # engine/session, cria/migra as tabelas no startup
    main.py                # FastAPI app, serve o index.html, healthcheck
    routes/
      mcs.py                 # upload/list/detail/delete/clear das MCs
      clientes.py            # consolidado por cliente
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

SheetJS (a lib que lia xlsx no navegador) saiu — não é mais necessário. Chart.js
continua, é só pra desenhar os gráficos.

### Sem autenticação

O painel não pede senha — qualquer um com a URL acessa tudo, upload incluso. Rotas
`/api/login`, `/api/logout`, `/api/me` e o cookie assinado existiram numa versão
anterior e foram removidos a pedido do Rafael (10/08/2026). Ver seção 4 sobre
reabrir isso se o painel deixar de ser só uso interno da equipe.

### Rotas

```
GET  /healthz              healthcheck do Railway
GET  /                     serve o painel (index.html)
POST /api/mcs/upload        multipart (files[]) → parse no servidor → upsert → {ok:[ids], erros:[...]}
GET  /api/mcs                lista todas as MCs (formato compatível com o front)
GET  /api/mcs/{id}            detalhe de uma MC
PATCH /api/mcs/{id}/status    troca a classificação (ativo/finalizado/a_validar)
PUT  /api/mcs/{id}            salva a edição manual da MC (campos + linhas) e recalcula tudo
DELETE /api/mcs/{id}          remove uma MC
POST /api/mcs/clear           remove todas (usado pelo botão "Limpar painel")
GET  /api/clientes            consolidado por cliente (contratos, receita, custo, MC)
```

`id` de uma MC é `"{contrato}|{arquivo}"` — reenviar o mesmo arquivo faz upsert, não
duplica. Número de contrato é extraído do nome do arquivo (`CONTRATO_RX` em
`parser.py`): uma letra (`F`, `C`, ...) + 6 dígitos, com sufixo opcional `-N` ou
`-N` + uma letra (`F221082-6`, `C260020-2B`). Não tem fallback pra `1.DADOS_INICIAIS`
— se o nome do arquivo não bater com o padrão, contrato fica vazio.

### Edição manual da MC

Tudo que a MC tem é editável direto no painel, na tela de detalhe: cabeçalho
(contrato, arquivo, projeto, cliente, produto, responsável, início, fim, meses,
comentários), receita bruta, fator de imposto, os percentuais de rateio e, linha a
linha nos 4 pilares, categoria, descrição, detalhe, meses, qtde, valor unitário,
custo final e a caixinha do dashboard (força uma caixinha manualmente, por linha,
por cima do de-para automático). Cada pilar também tem **+ Nova linha** (adiciona
uma linha em branco no fim da tabela, pra "gastar mais" numa caixinha que ainda
não tem linha nenhuma) e um ✕ por linha pra remover — dá pra montar a composição
de qualquer uma das 14 caixinhas do zero, direto no painel, sem precisar que a
linha já exista na planilha original.

Clicar numa caixinha **dentro do detalhe de uma MC** (aba Caixinhas ou o badge de
cada linha nas abas dos pilares) abre as linhas dela sem sair do detalhe nem do
modo edição — é o mesmo drill-down por caixinha que existe na carteira consolidada
(`viewDrill`), só que embutido no detalhe (`tabDrillCaixa`) pra continuar editável.
O drill-down da carteira (fora de uma MC, várias MCs de uma vez) continua só
leitura — editar ali não faz sentido porque pode misturar mais de uma MC.

Fluxo: botão **Editar valores** → a tela inteira passa a mostrar o cenário editado
(KPIs, DRE, caixinhas, auditoria recalculam a cada tecla, client-side) → rodapé fixo
mostra quantos campos mudaram no total (em qualquer aba, não só a que está na tela —
`countDirtyFields()` no HTML) e o delta de DM/custo → **Salvar alterações** manda
`PUT /api/mcs/{id}` e aí sim vira verdade pra equipe toda. **Descartar** joga fora.

- Mexeu em qtde, valor unitário ou meses → o custo final da linha recalcula sozinho
  (`qtde × unit × meses`, meses só se o bloco tiver a coluna). Dá pra digitar o custo
  final por cima, que é como a planilha às vezes faz.
- Caixinha: por padrão é "Automático" (`classificar()` decide pelo de-para). Escolher
  uma caixinha específica no select da linha grava `caixaOverride`, que passa a valer
  sempre — tanto em `classificar()` do backend (`app/caixinhas.py`) quanto no mirror
  do JS — até alguém voltar pra "Automático" ou reimportar a planilha.
- O preview client-side (`recalcMC()` no HTML) e o servidor (`app/edicao.py`) usam a
  mesma conta — o servidor reaproveita `calc_dre`/`line_cost`/`classificar` do parser,
  não existe um segundo jeito de calcular MC no projeto. Mexer num lado sem mexer no
  outro faz o preview mentir.
- O **5.DRE guardado não é tocado** — ele continua sendo a foto da planilha original.
  Quem edita passa a divergir do DRE de propósito, e a aba Auditoria avisa isso
  (`editado: true` no JSON, badge "editada no painel" no cabeçalho).
- `contrato` e `arquivo` **são** editáveis, mas formam o id da MC
  (`"{contrato}|{arquivo}"`): mudar qualquer um dos dois migra o registro pra um id
  novo (`PUT /api/mcs/{id}` recusa com 400 se já existir outra MC com o novo id). A
  tela avisa: reimportar depois a planilha original de novo vai criar uma MC nova,
  não vai mais fazer upsert nesta.
- Reimportar a mesma planilha sobrescreve a edição inteira, incluindo `caixaOverride`
  (é upsert por id) — a planilha continua sendo a fonte, a edição é ajuste por cima.

### Detalhe de uma MC — comparação com a carteira e navegação

Rafael pediu (19/08/2026) pra focar na visão individual de uma MC, não só na
carteira consolidada — e prefere número a gráfico. Duas coisas no detalhe:

- **Comparação numérica com a carteira**, sem gráfico nenhum. Na aba Resumo/DRE,
  cada linha (impostos, custo, cada pilar, DM, rateios, cada rateio, MC direta)
  mostra o delta em pontos percentuais contra a média das outras MCs importadas
  (`statsCarteira()`, exclui a própria MC da média). Custo/impostos/rateios: mais
  que a média é ruim (vermelho). DM/MC direta: mais que a média é bom (verde).
  Na aba Caixinhas, cada caixinha mostra o delta de participação no custo total
  contra a média da carteira (`statsCaixasCarteira()`) — sem cor de bem/mal, é
  composição, não mérito (`vsNeutral()`). Com só uma MC no painel não tem com o
  que comparar — os dois casos mostram isso em vez de inventar um número.
- **Navegação ◀ anterior / próxima ▶** no topo do detalhe, com posição ("2 de 3").
  Usa a mesma ordenação/filtro da tabela Gerencial (`sortRows`), mas ignora o
  filtro de MC específica (`filtradasParaNav()`) — senão a lista de navegação
  ficaria com 1 item só quando você chega no detalhe filtrando por uma MC.

### Classificação da MC (status)

Espelha as pastas que a Bruna usa no OneDrive (`01-CONTRATOS ATIVOS`,
`02-CONTRATOS FINALIZADOS`, `03-STATUS A VALIDAR`): campo `status` em `mcs`
(`ativo` | `finalizado` | `a_validar`), independente do que vem da planilha — não
existe em `1.DADOS_INICIAIS` nem em lugar nenhum do modelo de MC, é classificação
manual feita no painel. MC nova entra como `a_validar`; reenviar a mesma planilha
(upsert) não reseta o status já definido. Editável direto na tabela Gerencial
(coluna "Situação", um `<select>` por linha) ou na tela de detalhe da MC. O JSON em
`mcs.dados` guarda uma cópia do status também, pra ficar redundante com a coluna e
não precisar de join pra montar a resposta da API.

### Banco

Quatro tabelas (Postgres, mas cai pra SQLite local se `DATABASE_URL` não estiver
setado — só pra rodar/testar sem banco):

- **mcs** — cabeçalho + totais + o objeto MC inteiro em JSON (é o que a API devolve
  direto pro front, sem recomputar nada)
- **mc_linhas** — linha a linha já classificada, pra dar pra consultar por caixinha
  sem abrir o JSON no futuro
- **ingestoes** — histórico de cada upload (arquivo, resultado, mensagem de erro)
- **clientes** — consolidado por cliente (contratos, receita, receita líquida, custo,
  MC do projeto, MC direta), recalculado a cada upload/delete/clear em
  `routes/mcs.py::_refresh_cliente`. Some da tabela quando o cliente fica sem
  nenhuma MC.

Tabelas são criadas automaticamente no startup (`Base.metadata.create_all`) — sem
Alembic por enquanto, é cedo pro projeto pra valer a complexidade de migrations.

### Deploy no Railway

1. Criar um projeto no Railway, adicionar um plugin **Postgres**.
2. Criar o serviço a partir deste repo, apontando o **root directory** pra
   `faiston-mc` (é onde estão o `Dockerfile` e o `railway.json`).
3. Variável de ambiente do serviço:
   - `DATABASE_URL` → referenciar o Postgres do Railway (`${{Postgres.DATABASE_URL}}`)
4. Deploy. O healthcheck é `/healthz`.

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
- Valores editáveis no painel com preview ao vivo e save explícito (a Bruna pediu em
  18/08/2026): simular e manter a alteração sem precisar mexer na planilha
- Header enxuto: só a marca Faiston. O selo "OPS" e o rótulo "Margem de Contribuição"
  do topo saíram a pedido do Rafael (18/08/2026) — o H1 da página já diz isso
- Foco no detalhe individual de uma MC, não só na carteira consolidada (Rafael,
  19/08/2026) — comparação numérica com a média da carteira e navegação entre
  MCs, **número em vez de gráfico** (preferência explícita dele)
- **Sem autenticação** (revertido em 10/08/2026 — tinha senha única antes). Painel
  público pra quem tiver a URL. Decisão explícita do Rafael, sabendo do risco pro
  dado de margem/custo — não reabrir sem ele pedir

## 5. Ideias que ficaram de fora

Comparar duas versões da mesma MC, histórico de margem por contrato ao longo do
tempo, puxar as MCs direto do OneDrive usando o conector de MC que o Faiston Ops já
tem, autenticação (hoje não tem nenhuma — ver seção 4), Alembic quando o schema
começar a mudar de verdade.

## 6. Como testar

Não tem framework de teste automatizado ainda. O que foi feito até aqui:

- **Backend:** gerado um workbook sintético (`openpyxl`) reproduzindo a estrutura das
  8 abas relevantes, rodado `parse_mc()` direto e conferido: soma dos pilares bate
  com `custo`, `mcProjeto`/`mcDireta` batem com o cálculo manual, zero divergências
  entre linhas e DRE, e a invariante `soma das caixinhas == custo total` fecha exato.
  Servidor local exercitado no ciclo HTTP completo: upload multipart (incluindo
  arquivo inválido, que retorna erro claro em vez de 500), upsert do mesmo arquivo
  (não duplica), detalhe, delete, clear, e as rotas sem exigir cookie/senha nenhuma.
  `CONTRATO_RX` (extração do nº de contrato pelo nome do arquivo) testada contra os
  nomes reais que a Bruna usa na pasta do OneDrive (`F221082-6 - NTT - ...`,
  `C260020-2B - NAVEGACAO GUARITA`, etc). Tabela `clientes` testada com MCs
  sintéticas de clientes diferentes: soma bate no upload, recalcula certo no delete
  e zera no clear. `fmt_date`/`to_date` testados com célula de data que perdeu o
  formato e virou número de série cru do Excel.
- **Produção:** a Bruna já importou MCs reais no Railway. Bugs encontrados e
  corrigidos nessa rodada: 500 em `/api/mcs` por coluna nova faltando no banco
  (resolvido com migração leve no `database.py::init_db`), datas cruas no
  início/fim, linha de total da aba Gerencial desalinhada da coluna fixa por causa
  de `colspan`.
- **O que falta:** conferir os números de referência da seção 1
  (`MC F260153-2 NTT - Instalação.xlsx`) contra o parser — ainda não foi feito com
  esse arquivo específico em mãos.

Planilhas de referência: `MC F260153-2 NTT - Instalação.xlsx` e
`DASHBOARD_GERENCIAL_CONTRATOS_07.08.2026.xlsm`.

## 7. Cuidados

- Não quebrar a invariante da soma das caixinhas
- `num()` (e o `norm()`/`num()` do Python) precisa continuar aceitando `'20,53'` —
  CUSTO BASE às vezes vem como texto
- Match de coluna é **exato primeiro, depois substring**: `TIPO` casaria com `TIPO DE CONTRATO`
- O nome da aba varia entre planilhas; buscar por fragmento (`EQUIPE`, `SUPORTE`, `LOGISTICA`,
  `INVESTIMENTOS`, `DRE`), nunca por nome exato
- Dado de margem e custo de contrato é sensível, e o painel **não tem autenticação**
  (decisão explícita, seção 4) — não linkar a URL do Railway fora da equipe
- Mudar `classificar()` num lado (`app/caixinhas.py` ou o JS do front) sem mudar no
  outro quebra a sincronia entre o que a ingestão grava e o que o simulador mostra
- Mesma coisa pro recálculo da edição: `recalcMC()` (front) e `app/edicao.py` (back)
  precisam continuar dando o mesmo número, senão o preview promete uma coisa e o
  salvar entrega outra
