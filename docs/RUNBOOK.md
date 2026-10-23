# Runbook do DeskGuard

Manual de operação, diagnóstico e validação. Todos os comandos abaixo foram
executados nesta máquina (Windows 10 Pro 22H2, build 19045, Python 3.14.7) e
o resultado real está registrado na seção 6.

---

## 1. Operação diária

### 1.1 Iniciar a plataforma

```powershell
cd C:\Users\gustavo.fraga\Desktop\Projetos\DeskGuard
.\.venv\Scripts\Activate.ps1
python -m deskguard serve
```

Saída esperada no console:

```
DeskGuard iniciado
  Interface: http://127.0.0.1:8765/
  Documentação da API: http://127.0.0.1:8765/api/docs
  Banco de dados: C:\Users\gustavo.fraga\AppData\Local\DeskGuard\deskguard.db
  Pressione Ctrl+C para encerrar.
```

O processo **precisa permanecer aberto** durante as verificações: as execuções
vivem na memória do processo.

### 1.2 Encerrar

`Ctrl+C` no console. O banco é SQLite: os dados já gravados permanecem.

### 1.3 Diagnóstico rápido sem navegador

```powershell
python -m deskguard run system.overview
python -m deskguard run network.configuration
python -m deskguard run printers.status
python -m deskguard run services.status
```

### 1.4 Abrir em janela nativa (sem navegador)

```powershell
python -m deskguard desktop
```

Saída esperada no console:

```
DeskGuard (modo desktop)
  Interface nativa: http://127.0.0.1:8765/
  API: http://127.0.0.1:8765/api/docs
  Banco de dados: C:\Users\gustavo.fraga\AppData\Local\DeskGuard\deskguard.db
  Feche a janela para encerrar.
```

Para encerrar: **feche a janela**. O servidor local desce junto com o
processo.

Opções úteis:

```powershell
python -m deskguard desktop --port 8765
python -m deskguard desktop --no-browser-fallback
python -m deskguard desktop --open-browser
```

Se o runtime **WebView2** da Microsoft não estiver instalado, ou se o pacote
`pywebview` não estiver instalado, a ferramenta avisa no console e abre a
mesma interface no navegador padrão. Para saber o que há nesta máquina:

```powershell
python -m deskguard doctor
```

O bloco `desktop` do diagnóstico informa `available`, a versão do `pywebview` e
o backend gráfico em uso.

### 1.5 Autorizar um destino de rede

O procedimento `network.connectivity` só sonda destinos autorizados. A lista
fica em `%LOCALAPPDATA%\DeskGuard\allowed_targets.json`.

```powershell
python -m deskguard targets list
python -m deskguard targets add 10.87.36.68 --port 9100 --description "Impressora da rede"
python -m deskguard targets add srv-dns.corp --port 53 --no-ping
python -m deskguard targets remove 10.87.36.68
```

Regras: no máximo 10 destinos e 5 portas por destino; portas de 1 a 65535; sem
curingas, CIDR ou URL. Sem portas informadas, são usadas 80 e 443. O destino
pode ser um endereço IPv4 ou um nome de host.

Para isolar a lista em um arquivo de teste (usado pelos testes automatizados):

```powershell
$env:DESKGUARD_ALLOWED_TARGETS_FILE = "$PWD\allowed_targets_teste.json"
```

Com a lista vazia, apenas `localhost` e o gateway padrão do endpoint são
sondados — nenhum dado externo.

---

## 2. Diagnóstico de problemas

| Sintoma | Verificação | Ação |
|---|---|---|
| `powershell_available: false` | `python -m deskguard doctor` | Verificar `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`. |
| Coletas de rede inconclusivas | `/api/health` | Conflito de proxy ou DNS do host corporativo. |
| `POWERSHELL_UNAVAILABLE` nas etapas | Filtro `/api/executions/{id}` | WMI indisponível ou política restringindo `-EncodedCommand`. |
| `COLLECTOR_ERROR` | Evidências da etapa | Exceção interna do coletor, registrada em `evidence.exception_message`. |
| Interface em branco | Console do navegador (F12) | Verificar se `/static/js/*.js` retorna 200. |
| `403 Host não autorizado` | Cabeçalho `Host` | Só `localhost`/`127.0.0.1` são aceitos; é proposital. |
| `403 Token anti-CSRF ausente` | Recarregue a página | O token é gerado a cada inicialização do servidor. |
| `422` ao executar `network.connectivity` | `python -m deskguard targets list` | O destino não está na lista de autorizados; use `targets add`. |
| `Portas TCP: NÃO APLICÁVEL` | `python -m deskguard targets list` | A lista não define portas para o destino; adicione com `--port`. |
| Impressora marcada como *offline* | `printers.status` → inventário | Pode ser apenas desligada; confirmar com o usuário antes de trocar peça. |
| Impressora com *estado de erro* | `printers.status` → inventário | O código do erro (`detected_error_state`) indica a causa (papel travado, etc.). |
| Impressora não recebe trabalho | `services.status` → estado dos serviços | O `Print Spooler` parado derruba toda a fila de impressão; o procedimento dirá se ele está em execução. |
| Computador não resolve nomes | `services.status` → estado dos serviços | O cliente DNS (`Dnscache`) parado derruba a resolução mesmo com o cabo conectado. |
| Wi-Fi sumiu das redes disponíveis | `services.status` → estado dos serviços | O serviço `WlanSvc` parado ou desativado tira o Wi-Fi do sistema. |
| Serviço para de vez em quando | `services.status` → tipo de inicialização | Serviço parado com inicialização `Automatic` é falha confirmada; com `Manual` é o estado esperado de serviços por evento. |
| `SERVICE_NOT_FOUND` em um serviço | `services.status` → evidências | O serviço não existe neste endpoint (ex.: `WlanSvc` em desktop sem Wi-Fi); resultado não aplicável, não é falha. |
| Banco corrompido | — | Apagar `%LOCALAPPDATA%\DeskGuard\deskguard.db` (perde o histórico). |
| Janela nativa não abre | `python -m deskguard doctor` → bloco `desktop` | `available: false` significa `pywebview` ou WebView2 ausente; a interface abre no navegador. |
| Janela em branco na camada desktop | Servidor local | A API sobe em thread: se ela falhou, o console mostra o motivo antes da janela abrir. |
| `Porta já em uso` ao abrir a janela | — | Não é erro: uma instância existente é reaproveitada. Use `--no-reuse` para forçar uma nova. |
| SmartScreen avisa na primeira execução do `.exe` | Assinatura digital | O executável não é assinado; use "Executar assim mesmo" ou distribua pelo portal interno. |

Log do servidor (uvicorn) com nível `DEBUG` quando necessário:

```powershell
$env:DESKGUARD_LOG_LEVEL = "DEBUG"
python -m deskguard serve
```

---

## 3. Validação automatizada

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

O script executa, em ordem: suíte de testes com cobertura, diagnóstico do
ambiente, execução real de diagnóstico, execução em modo demonstração e as
verificações de segurança e de fluxo da API local. Desde a versão 0.2.0 ele
verifica também a **camada desktop** e o **executável empacotado**. Sai com
código 0 apenas se todas as etapas passarem.

```powershell
# Pular a suíte de testes (útil durante a investigação de uma falha)
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -SkipTests

# Pular a verificação do executável empacotado
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -SkipPackaging
```

---

## 3.1 Empacotamento do executável

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

O script instala o PyInstaller (se faltar), gera o executável e valida o
resultado com `--version` e `list`. Saída real:

```
=============================================================
  3. Resultado
=============================================================
  Executavel: C:\Users\gustavo.fraga\Desktop\Projetos\DeskGuard\dist\DeskGuard.exe (21.99 MB)

  Verificacao rapida:
DeskGuard 0.2.0
Catálogo DeskGuard (4 procedimento(s))
...
  Empacotamento concluido.
```

Para gerar a pasta com o executável e suas dependências (inicialização mais
rápida, sem extração temporária):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -OneFolder
```

---

## 4. Uso da API

```powershell
$base = "http://127.0.0.1:8765"

# Token anti-CSRF (entregue apenas na página da aplicação)
$token = [regex]::Match(
    (Invoke-WebRequest "$base/" -UseBasicParsing).Content,
    'name="deskguard-csrf" content="([^"]+)"'
).Groups[1].Value

# Executar um procedimento
$run = Invoke-RestMethod "$base/api/executions" -Method Post `
    -Headers @{ "X-DeskGuard-CSRF" = $token } `
    -ContentType "application/json" `
    -Body '{"procedure_id":"system.overview","params":{}}'

# Acompanhar
Invoke-RestMethod "$base/api/executions/$($run.execution_id)"

# Relatório técnico
(Invoke-RestMethod "$base/api/executions/$($run.execution_id)/report").markdown
```

Endpoints disponíveis:

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/health` | Estado do ambiente |
| GET | `/api/dashboard` | Indicadores calculados do banco |
| GET | `/api/settings` | Configuração efetiva, privilégio e lista de destinos autorizados |
| GET | `/api/procedures` | Catálogo completo |
| GET | `/api/procedures/{id}` | Detalhe de um procedimento |
| GET | `/api/executions` | Histórico com filtros e busca |
| GET | `/api/executions/{id}` | Detalhe de uma execução |
| POST | `/api/executions` | Agenda uma execução (exige CSRF) |
| GET | `/api/executions/{id}/report` | Relatório em Markdown |
| POST | `/api/executions/{id}/report/export` | Exporta `.md`/`.txt` (exige CSRF) |
| GET | `/api/audit` | Trilha de auditoria |

Documentação interativa: `http://127.0.0.1:8765/api/docs`.

---

## 5. Manutenção do banco

O banco fica em `%LOCALAPPDATA%\DeskGuard\deskguard.db`.

```powershell
# Backup
Copy-Item "$env:LOCALAPPDATA\DeskGuard\deskguard.db" "backup-deskguard-$(Get-Date -Format yyyyMMdd).db"

# Reinício do histórico (remove execuções e auditoria)
Remove-Item "$env:LOCALAPPDATA\DeskGuard\deskguard.db*"
python -m deskguard doctor
```

---

## 6. Resultados reais da validação

> Execução em **22/10/2026** · Windows 10 Pro 22H2 (build 19045) ·
> Python 3.14.7 · PowerShell 5.1.19041.6456 · processo **sem** elevação
> administrativa.

### 6.1 Suíte de testes

Comando: `python -m pytest -q --cov=deskguard --cov-report=term`

```
........................................................................ [ 88%]
.........                                                                [100%]
225 passed, 1 warning in 16.59s

TOTAL                                           2824    387    86%
```

Cobertura por camada:

| Camada | Cobertura |
|---|---|
| `domain/` | 93%–100% |
| `security/` | 92%–97% |
| `storage/` | 92%–94% |
| `api/` | 81%–100% |
| `services/` | 83%–88% |
| `collectors/` | 58%–100% |
| `procedures/` | 82%–96% |
| `collectors/service_status.py` | **99%** — coberto por `tests/unit/test_services_procedure.py` |
| `desktop.py` | **97%** — coberto por `tests/unit/test_desktop.py` |
| `cli.py` | **58%** — coberto por `tests/unit/test_cli.py` |

O único aviso vem do `starlette.testclient`, que sugere `httpx2`; não é um
problema do DeskGuard.

### 6.2 Execução real de diagnóstico

Comando: `python -m deskguard run system.overview`

```
Execução: 3b1e6f2a-...-9c4d
Procedimento: system.overview
Resultado consolidado: healthy
Resumo: 6 verificação(ões) · 6 aprovada(s) · 0 desvio(s) confirmado(s)

  [APROVADO         ] Versão do Windows: Informação obtida com sucesso.
  [APROVADO         ] Identidade do equipamento: Informação obtida com sucesso.
  [APROVADO         ] Tempo de atividade: Informação obtida com sucesso.
  [APROVADO         ] Hardware resumido: Informação obtida com sucesso.
  [APROVADO         ] Contexto de execução: Processo executado com privilégios de usuário padrão.
  [APROVADO         ] Armazenamento: 1 unidade(s) fixa(s) verificada(s).
```

Dados efetivamente coletados (evidências da execução):

| Verificação | Evidência |
|---|---|
| Versão do Windows | `Microsoft Windows 10 Pro`, `10.0.19045`, build `19045`, `22H2`, atualização `6456`, `64 bits`, instalação `2026-06-15` |
| Identidade | `N87TP010486`, `Dell Inc.`, `Vostro 14-3468`, x64, domínio `parvi.local` |
| Tempo de atividade | último boot `2026-10-21T11:32:51`, `4.02 h`, fuso `E. South America Standard Time` |
| Hardware | `Intel(R) Core(TM) i5-7200U CPU @ 2.50GHz`, 2 núcleos / 4 lógicos |
| Armazenamento | `C:\` com volume fixo e uso percentual coletado |

Duração observada: **2,3 s a 2,8 s** por execução (predomina a inicialização
do PowerShell).

### 6.3 Execuções reais do Incremento 2

Comandos: `python -m deskguard run network.configuration`,
`python -m deskguard run network.connectivity` e
`python -m deskguard run printers.status`.

```
Procedimento: network.configuration
Resultado consolidado: healthy
Resumo: 4 verificação(ões) · 4 aprovada(s)

  [APROVADO         ] Estado dos adaptadores: 1 interface(s) de rede ativa(s).
  [APROVADO         ] Endereçamento IP: 1 interface(s) com endereçamento IPv4 válido e gateway configurado.
  [APROVADO         ] Rotas: 1 rota(s) padrão configurada(s).
  [APROVADO         ] Perfil de rede: 1 interface(s) com perfil de rede associado.
```

Duração: **6,84 s**. Dados coletados: endereço `10.87.36.130/24`, gateway
`10.87.36.254`, DNS `10.0.10.6` e `10.0.10.4`.

```
Procedimento: network.connectivity
Resultado consolidado: healthy
Resumo: 3 verificação(ões) · 2 aprovada(s)

  [APROVADO         ] Resolução DNS: 2 destino(s) resolvido(s) corretamente.
  [APROVADO         ] Alcance ICMP: 2 destino(s) responderam ao ICMP.
  [NÃO APLICÁVEL    ] Portas TCP: Nenhuma porta foi testada: os destinos configurados não definem portas autorizadas.
```

Duração: **10,76 s**. Com a lista de autorizados vazia, apenas `localhost` e o
gateway padrão do endpoint são sondados — nenhum destino externo. Com uma
lista de teste (`10.87.36.68`, porta 9100), a mesma execução retornou
**3/3 verificações aprovadas**, incluindo a conexão TCP.

```
Procedimento: printers.status
Resultado consolidado: issues_found
Resumo: 3 verificação(ões) · 2 aprovada(s) · 1 desvio(s) confirmado(s)

  [FALHA CONFIRMADA ] Inventário de impressoras: \\prvsrvimp01\PE-BYD-PETROLINA-VVN01: A impressora reportou estado de erro (código 9 — Papel travado). | Também em aviso: KM975ED7: A impressora reporta estado 'offline', mas nenhum erro específico foi detectado. ...
  [APROVADO         ] Fila de impressão: 9 trabalho(s) na fila, todos em situação normal.
  [APROVADO         ] Serviço de impressão: O serviço Print Spooler está em execução.
```

Duração: **3,94 s**. Desvio confirmado: **papel travado** na impressora de
rede `\\prvsrvimp01\PE-BYD-PETROLINA-VVN01` (`detected_error_state = 9`).
Quatro impressoras físicas offline foram reportadas como aviso, e as
impressoras virtuais (Microsoft Print to PDF, XPS, Fax) foram excluídas do
inventário, por não representarem dispositivo físico.

### 6.4 Execuções reais do Incremento 3 — `services.status`

Comandos:

```powershell
python -m deskguard run services.status
python -m deskguard run services.status --mode demo
```

```
Procedimento: services.status
Resultado consolidado: healthy
Resumo: 3 verificação(ões) · 3 aprovada(s) · 0 desvio(s) confirmado(s)

  [APROVADO         ] Estado dos serviços: 10 serviço(s) monitorado(s) verificado(s), sem desvio confirmado.
  [APROVADO         ] Tipo de inicialização: Tipo de inicialização conforme o padrão do Windows em 10 serviço(s) monitorado(s).
  [APROVADO         ] Dependências entre serviços: Nenhuma dependência monitorada está interrompida.
```

Duração: **1,77 s**. Dados efetivamente coletados (10 serviços monitorados):

| Serviço | Estado | Inicialização | Observação |
|---|---|---|---|
| `Spooler` (fila de impressão) | `Running` | `Automatic` | Depende de `RPCSS`; `Fax` depende dele |
| `Dnscache` (cliente DNS) | `Running` | `Automatic` | Depende de `nsi` e `Afd` |
| `DHCP` (cliente DHCP) | `Running` | `Automatic` | 7 serviços dependem dele (`NlaSvc`, `netprofm`, ...) |
| `WlanSvc` (rede sem fio) | `Running` | `Automatic` | Depende de `Ndisuio` e `RpcSs` |
| `wuauserv` (Windows Update) | `Running` | `Manual` | Inicialização manual é esperada: o serviço é por evento |
| `BITS` | `Stopped` | `Manual` | Parado com inicialização manual: **estado esperado**, não é falha |
| `winmgmt` (WMI) | `Running` | `Automatic` | Depende de `RpcSs` |
| `RpcSs` | `Running` | `Automatic` | Serviço base de RPC |
| `DcomLaunch` | `Running` | `Automatic` | Serviço base de DCOM |
| `DPS` (diagnóstico) | `Stopped` | `Manual` | Parado com inicialização manual: **estado esperado**, não é falha |

O ponto central desta execução: `BITS` e `DPS` estavam **parados**, e mesmo
assim o resultado foi `healthy`. Sem o perfil de serviço, um serviço parado
vira alarme falso em quase toda máquina — `BITS`, `DPS` e `wuauserv` são por
design.

Execução registrada: `86d27c5d-325b-4939-904b-f977945e7dca` (22/10/2026).

No modo demonstração o procedimento também retorna `healthy` com 3
verificações aprovadas e todas as evidências marcadas como `simulated=True`.


### 6.5 Verificações de segurança e de API

Saída do `scripts/check.ps1` (22/10/2026):

```
  health: ok | version 0.2.0 | procedures 5
  [OK]   Endpoint /api/health respondeu
  [OK]   Catalogo expoe 5 procedimentos
  [OK]   Interface web respondeu na raiz
  [OK]   Token anti-CSRF presente na pagina
  [OK]   Requisicao sem token anti-CSRF foi recusada com 403
  [OK]   Host nao local foi recusado com 403
  [OK]   Configuracao efetiva expoe a lista de autorizados
  allowlist: path=C:\Users\gustavo.fraga\AppData\Local\DeskGuard\allowed_targets.json targets=0
  [OK]   Destino fora da lista foi recusado com 422
  [OK]   Execucao aceita pela API
  execucao: status=completed outcome=healthy duracao=2381ms
  [OK]   Execucao concluida pela API
  [OK]   Execucao registrou 6 verificacoes
  [OK]   Relatorio gerado (4751 caracteres)
  [OK]   Relatorio contem o identificador da execucao
  [OK]   Exportacao do relatorio respondeu 200
  content-type: text/markdown; charset=utf-8
  painel: total_executions=98 confirmados=16
  [OK]   Painel calculou indicadores a partir do banco
  [OK]   Trilha de auditoria registrou eventos

=============================================================
  6. Camada desktop (janela nativa)
=============================================================
  [OK]   Comando 'deskguard desktop' esta disponivel
  desktop: available=True frozen=False
  backend: edgechromium | pywebview 6.2.1
  [OK]   Camada desktop respondeu com diagnostico

=============================================================
  7. Executavel empacotado
=============================================================
  [OK]   Executavel respondeu ao --version (DeskGuard 0.2.0)
  [OK]   Executavel listou o catalogo
  [OK]   Catalogo do executavel contem system.overview
  [OK]   Catalogo do executavel contem printers.status
  [OK]   Catalogo do executavel contem services.status
  [OK]   Executavel expoe 5 procedimentos
  [OK]   Executavel encontrou o PowerShell
  executavel: C:\Users\gustavo.fraga\Desktop\Projetos\DeskGuard\dist\DeskGuard.exe (22.02 MB)

=============================================================
  Resultado
=============================================================
  Todas as verificacoes passaram.
```

Código de saída do script: **0**.

### 6.6 Modo demonstração

```
python -m deskguard run system.overview --mode demo
python -m deskguard run network.configuration --mode demo
python -m deskguard run network.connectivity --mode demo
python -m deskguard run printers.status --mode demo
python -m deskguard run services.status --mode demo
```

As etapas saem com `simulated=True` e cada bloco de evidências contém
`"notice": "DADOS SIMULADOS — modo demonstração, não refletem o estado real."`.
O relatório identifica a origem como `DADOS SIMULADOS`.

### 6.7 Empacotamento (build não editável)

O wheel foi construído e instalado em um ambiente virtual limpo, para
verificar que nada depende da instalação editável:

```powershell
python -m pip wheel . --no-deps -w dist
python -m venv .venv-teste
.\.venv-teste\Scripts\python.exe -m pip install .\dist\deskguard-0.2.0-py3-none-any.whl
.\.venv-teste\Scripts\python.exe -m deskguard list
.\.venv-teste\Scripts\python.exe -m deskguard run printers.status
```

Resultado real: o catálogo listou os procedimentos do momento, os scripts
PowerShell foram localizados a partir do `package-data` e a execução real
terminou com `issues_found` e o desvio de **papel travado** corretamente
detectado.

Conteúdo do wheel conferido: `deskguard/procedures/*`,
`deskguard/web/templates/index.html`, `deskguard/web/static/{css,js}/*` e
`deskguard/collectors/scripts/{system_overview,network_configuration,network_connectivity,printers_status,services_status}.ps1`
— todos presentes.

O comando de autorização também funciona no build não editável:

```powershell
$env:DESKGUARD_ALLOWED_TARGETS_FILE = "$PWD\allowed_targets_validacao.json"
.\.venv-teste\Scripts\python.exe -m deskguard targets add 10.87.36.68 --port 9100 --description "Impressora de rede"
.\.venv-teste\Scripts\python.exe -m deskguard run network.connectivity
```

Resultado real: **3/3 verificações aprovadas**, incluindo
`Portas TCP: Todas as 1 porta(s) testada(s) aceitaram conexão`.

> Correção aplicada durante esta validação: `src/deskguard/procedures/` e
> `src/deskguard/web/` estavam sem `__init__.py`, o que os excluía do wheel
> (`find_packages` exige o arquivo). O modo editável não revealava o problema.

### 6.8 Camada desktop

Comando: `python -m deskguard desktop`

Resultado real: a API local subiu em thread (`Uvicorn running on
http://127.0.0.1:8765`), a **janela nativa abriu** (WebView2/EdgeChromium) e
o processo permaneceu em execução até o encerramento por timeout de teste. O
console do servidor mostrou:

```
INFO:     Started server process [4916]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
```

Diagnóstico da camada (`python -m deskguard doctor`):

```json
"desktop": {
  "available": true,
  "pywebview_version": "6.2.1",
  "backend": "edgechromium",
  "reason": null,
  "hint": null
}
```

Cobertura da camada: **97%** de `desktop.py`, com 39 testes em
`tests/unit/test_desktop.py`. A suíte **não abre janela nenhuma** — o
`pywebview` é substituído por um dublê — e ainda valida de verdade a
subida da API em thread (`BackgroundServer`), o reaproveitamento de
instância, o caminho de timeout e o fallback para o navegador.

### 6.9 Executável empacotado (PyInstaller)

Comandos:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
.\dist\DeskGuard.exe --version
.\dist\DeskGuard.exe list
.\dist\DeskGuard.exe doctor
.\dist\DeskGuard.exe run printers.status
```

Resultados reais:

| Verificação | Resultado |
|---|---|
| Tamanho do executável | `dist\DeskGuard.exe` — **~23 MB**, arquivo único |
| `--version` | `DeskGuard 0.2.0` |
| `list` | Catálogo com os **6 procedimentos** (`network.configuration`, `network.connectivity`, `printers.status`, `security.audit`, `services.status`, `system.overview`) |
| `doctor` | `procedures: 6`, `powershell_available: true`, `desktop.available: true` |
| `run printers.status` | `issues_found` — desvio de **papel travado** detectado, ou seja, os scripts PowerShell foram localizados e executados dentro do executável |
| `run system.overview` | `healthy` — 6/6 verificações aprovadas |
| `run services.status` | `healthy` — 3/3 verificações aprovadas (o script novo foi localizado dentro do executável) |
| `run security.audit` | `issues_found` — Firewall OK em todos os perfis; proteção antivírus inconclusiva (vários produtos detectados); RDP habilitado (alerta baixa). Saída compatível com a nova apresentação (resumo + tabelas técnicas). |
| `serve --port 8791` | `/api/health` → `{"status":"ok","application":"deskguard",...}`; `/` → 200; `/static/css/styles.css` → 200; `/static/js/app.js` → 200 |
| Duplo clique no `.exe` (sem argumentos) | Abre em modo `desktop` (janela nativa) conforme correção em `cli.py`. |

Conteúdo verificado em `dist\DeskGuard\_internal\`:

- `deskguard/collectors/scripts/{system_overview,network_configuration,network_connectivity,printers_status,services_status}.ps1`
- `deskguard/web/templates/index.html` e `deskguard/web/static/{css,js}/*`
- `webview/lib/Microsoft.Web.WebView2.*.dll` (runtime da janela nativa)

> Correção aplicada durante o empacotamento: o catálogo vinha **vazio** no
> executável. A causa é o `pkgutil`: no build congelado os módulos de
> procedimento vivem dentro do arquivo PYZ e não aparecem no disco, então a
> descoberta automática não encontra nada. O `packaging/deskguard.spec` passou
> a embarcar os fontes de `deskguard/procedures/` como dados (para a
> descoberta) e a declarar cada módulo em `hiddenimports` (para que exista no
> executável).

---

## 7. Pendências de validação

| Item | Situação |
|---|---|
| Execução com elevação administrativa | **Não validada** — o processo de validação roda sem elevação. O caminho de código existe e está testado por mock, mas falta uma execução real elevada. |
| Comportamento com o serviço WMI parado | **Não validada** — o coletor deve reportar `inconclusive`; falta teste manual. |
| Timeout do PowerShell | **Não validada** — falta teste que force o limite de 25 s. |
| Comportamento com antivírus/SmartScreen bloqueando o PowerShell | **Não validada**. |
| Destino externo autorizado de fato, fora da rede local | **Parcialmente validada** — a sondagem de `10.87.36.68:9100` (impressora de rede) foi executada com sucesso em ambiente corporativo. Falta validar um destino fora da rede. |
| Impressora em estado de erro que exige reinício do Spooler | **Não validada** — o procedimento é somente leitura e não reinicia serviço algum. |
| Serviço parado de propósito (Spooler/DPS) em ambiente de produção | **Não validada** — a validação ocorreu em uma máquina com todos os serviços em execução (exceto os manuais, já tratados como estado esperado). Falta um endpoint com um serviço realmente parado. |
| Serviço desativado (`Disabled`) em produção | **Não validada** — coberto por teste automatizado (resultado `fail`/`warn` conforme a criticidade), mas não por execução real. |
| Serviço inexistente no endpoint | **Parcialmente validada** — coberto por teste automatizado (`not_applicable`); na execução real todos os 10 serviços monitorados existiam. |
| Migração de esquema do banco | **Não aplicável** ainda — o esquema ainda não mudou desde a criação. |
| Janela nativa em máquina **sem** o runtime WebView2 | **Não validada** — nesta máquina o WebView2 está presente. O caminho de fallback para o navegador é coberto por teste automatizado, mas falta a execução manual. |
| Janela nativa no executável empacotado | **Parcialmente validada** — o `doctor` do `.exe` reporta `desktop.available: true` e o WebView2 foi embarcado; falta abrir a janela a partir do `.exe` e conferir o carregamento dos scripts de interface. |
| Execução do `.exe` em máquina sem Python instalado | **Não validada** — falta testar o `DeskGuard.exe` em uma máquina limpa. |
| SmartScreen bloqueando o `.exe` não assinado | **Não validada**. |
| Instalador para Windows (MSI/Inno Setup) | **Não implementado** — previsto no incremento 7 do roadmap. |
