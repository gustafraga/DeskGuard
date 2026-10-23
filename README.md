# DeskGuard

**Diagnóstico inteligente e relatórios técnicos padronizados para o Service Desk Windows.**

O DeskGuard é uma plataforma **local e defensiva** para acelerar o primeiro atendimento de TI. Em vez de rodar comandos manualmente e montar o relatório no bloco de notas, o técnico executa um procedimento guiado, obtém evidências reais do endpoint, classifica achados por severidade e gera um **relatório técnico pronto para o chamado** — tudo em poucos cliques ou via linha de comando.

## Valor para o Service Desk

- **Agilidade no atendimento:** Reduz o tempo de triagem ao centralizar os checks mais frequentes (sistema, rede, impressoras, serviços e segurança) em um único painel.
- **Relatórios padronizados:** Gera relatórios claros com resumo executivo, tabelas técnicas e evidências rastreáveis, prontos para colar no sistema de chamados.
- **Sem adivinhação:** Coleta **somente leitura** com dados reais do Windows (PowerShell, WMI/CIM), evitando alterações acidentais no equipamento.
- **Segurança e governança:** Lista de destinos autorizados para testes de rede, sem shell dinâmico, validação estrita de parâmetros e trilha de auditoria.
- **Funciona onde precisa:** Roda 100% local (sem SaaS), em **janela nativa do Windows** ou via navegador, e pode ser distribuído como **executável único** (`DeskGuard.exe`).
- **Confiável:** Suíte automatizada com 274 testes garantindo estabilidade entre versões.

**Estado atual:** MVP Fase 1 concluído + **Fase 2 iniciada** — **seis** procedimentos reais de diagnóstico (somente leitura), gerador de relatório com visão em 3 níveis (resumo N1, tabelas técnicas N2/N3 e JSON bruto recolhido em bloco retrátil), histórico, auditoria, **Módulo G - Auto-Remediação** (reiniciar Print Spooler com confirmação obrigatória), interface web, janela nativa, instalador Inno Setup e GitHub Actions para Releases. Suíte automatizada com **276 testes**. Desde a versão **0.2.0** a plataforma também roda em **janela nativa do Windows** (sem navegador) e é distribuída como **executável único** (`DeskGuard.exe`) ou via instalador. Ao abrir o executável sem argumentos, ele assume automaticamente o comando `desktop`.

---

## Screenshots

> *Adicione capturas de tela aqui para enriquecer o portfólio.* Sugestões: tela inicial com catálogo de procedimentos, execução em andamento, relatório com visão em 3 níveis (resumo + tabelas técnicas), módulo de segurança com achados por severidade e janela nativa do `DeskGuard.exe`.

| Tela | Descrição |
|---|---|
| ![Tela Inicial](docs/screenshots/home.png) | Catálogo de procedimentos com status e execução em um clique. |
| ![Execução](docs/screenshots/execution.png) | Acompanhamento em tempo real das etapas e evidências coletadas. |
| ![Relatório](docs/screenshots/report.png) | Relatório técnico com resumo N1, tabelas N2/N3 e cópia pronta para o chamado. |
| ![Auditoria de Segurança](docs/screenshots/security-audit.png) | Módulo `security.audit` com Firewall, UAC, RDP, BitLocker e classificação por severidade. |

---

## 1. Requisitos

| Item | Versão verificada | Observação |
|---|---|---|
| Sistema operacional | Windows 10 Pro 22H2 (build 19045) | Desenhado para Windows 10/11 e Windows Server 2019+ |
| Python | 3.14.7 | Mínimo suportado: 3.11 (`StrEnum`, `match` opcional) |
| PowerShell | 5.1 (Windows PowerShell) | Executado com `-NoProfile -NonInteractive` |
| Navegador | Edge/Chrome/Firefox recentes | Interface em JavaScript com módulos ES nativos |

Não é necessário Docker, banco de dados remoto, Node.js nem build de frontend.

---

## 2. Instalação

```powershell
# 1. Entrar na pasta do projeto
cd C:\Users\gustavo.fraga\Desktop\Projetos\DeskGuard

# 2. Criar o ambiente virtual
python -m venv .venv

# 3. Ativar o ambiente virtual
.\.venv\Scripts\Activate.ps1

# 4. Instalar o DeskGuard em modo editável (desenvolvimento)
python -m pip install -e ".[dev,desktop]"
```

O extra `desktop` instala o `pywebview`, que habilita a janela nativa do
Windows. Ele é **opcional**: a CLI e a interface web funcionam sem ele — a
janela nativa apenas volta a abrir no navegador padrão.

Instalação alternativa, a partir dos arquivos de dependências:

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pip install -e .
```

### Verificação da instalação

```powershell
python -m deskguard doctor
```

Saída real obtida nesta máquina (22/10/2026):

```json
{
  "version": "0.2.0",
  "python": "3.14.7",
  "platform": "Windows-10-10.0.19045-SP0",
  "data_dir": "C:\\Users\\gustavo.fraga\\AppData\\Local\\DeskGuard",
  "database_path": "C:\\Users\\gustavo.fraga\\AppData\\Local\\DeskGuard\\deskguard.db",
  "database_exists": true,
  "powershell_available": true,
  "is_admin": false,
  "procedures": 6,
  "mode": "live",
  "allowlist": {
    "path": "C:\\Users\\gustavo.fraga\\AppData\\Local\\DeskGuard\\allowed_targets.json",
    "available": false,
    "targets": 0
  },
  "desktop": {
    "available": true,
    "pywebview_version": "6.2.1",
    "backend": "edgechromium",
    "reason": null,
    "hint": null
  }
}
```

O bloco `desktop` diz se a janela nativa está disponível nesta máquina.

### Atalho deduplo clique

```powershell
scripts\DeskGuard.bat
```

O atalho localiza o projeto, sobe a API local e abre a interface em uma
**janela nativa** (sem barra de endereço e sem abas). Fechar a janela
encerra o servidor.

### Validação automatizada ponta a ponta

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

O script executa a suíte de testes, o diagnóstico do ambiente, as execuções
reais de diagnóstico, as execuções em modo demonstração e as verificações de
segurança e de fluxo da API local. Sai com código `0` apenas se todas as
etapas passarem. Detalhes e saída real em
[docs/RUNBOOK.md](docs/RUNBOOK.md).

### Empacotamento (executável único)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

Gera `dist\DeskGuard.exe`: um executável autocontido (22 MB) que carrega a
aplicação, os scripts PowerShell e a interface web. Não precisa de Python
instalado na máquina de destino.

```powershell
# Modo pasta (inicializa mais rápido, sem extração temporária)
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -OneFolder
```

O wheel continua disponível para quem prefere instalar por `pip`:

```powershell
python -m pip wheel . --no-deps -w dist
```

O wheel gerado foi instalado em um ambiente virtual limpo e validado:
catálogo com os procedimentos do momento, scripts PowerShell localizados e
execução real concluída com o desvio de **papel travado** corretamente
detectado.

---

## 3. Uso

### 3.1 Interface web

```powershell
python -m deskguard serve
```

Depois abra **http://127.0.0.1:8765/** no navegador.

| Tela | O que faz |
|---|---|
| **Painel** | Indicadores calculados a partir do banco local (execuções, desvios confirmados, inconclusões, severidade). |
| **Catálogo** | Procedimentos agrupados por categoria, com busca. |
| **Detalhe do procedimento** | O que verifica, pré-requisitos, riscos, parâmetros e execução. |
| **Histórico** | Execuções anteriores com busca e filtros por situação, resultado e origem dos dados. |
| **Relatório** | Relatório técnico em Markdown, editável, com cópia e exportação `.md`/`.txt`. |
| **Auditoria** | Trilha append-only das ações realizadas pela plataforma. |
| **Configurações** | Configuração efetiva, privilégio do processo, disponibilidade da janela nativa, regras de segurança e destinos autorizados para sondagem de rede. |

### 3.2 Linha de comando

```powershell
# Catálogo de procedimentos
python -m deskguard list

# Diagnóstico direto, somente leitura
python -m deskguard run system.overview
python -m deskguard run network.configuration
python -m deskguard run printers.status
python -m deskguard run network.connectivity
python -m deskguard run services.status

# Com parâmetros e saída em JSON
python -m deskguard run system.overview --param include_account=true --json

# Modo demonstração (não toca o sistema real)
python -m deskguard run system.overview --mode demo

# Salvando o relatório técnico
python -m deskguard run system.overview --out relatorio-chamado.md

# Destinos de rede autorizados para sondagem
python -m deskguard targets list
python -m deskguard targets add 10.87.36.68 --port 9100 --description "Impressora de rede"
python -m deskguard targets add srv-dns.corp --port 53 --no-ping
python -m deskguard targets remove 10.87.36.68
```

A lista de autorizados fica em `%LOCALAPPDATA%\DeskGuard\allowed_targets.json`.
Sem ela, `network.connectivity` sonda apenas `localhost` e o gateway padrão do
endpoint; qualquer outro destino é recusado com erro **422**.

### 3.3 Janela nativa do Windows (modo desktop)

```powershell
python -m deskguard desktop
```

A interface abre em uma **janela nativa** — sem barra de endereço, sem abas e
sem um navegador aberto no meio do atendimento. Por baixo, é exatamente a
mesma aplicação FastAPI, com o mesmo token anti-CSRF, os mesmos cabeçalhos de
segurança e o mesmo catálogo: a camada desktop só cuida da janela.

| Opção | Efeito |
|---|---|
| `--host` / `--port` | Endereço de escuta da API local (padrão `127.0.0.1:8765`). |
| `--title` | Título da janela. |
| `--width` / `--height` | Tamanho inicial da janela. |
| `--no-reuse` | Não reaproveita uma instância do DeskGuard já em execução. |
| `--no-browser-fallback` | Não abre o navegador se a janela nativa falhar. |
| `--open-browser` | Abre também o navegador padrão, junto com a janela. |

Regras de comportamento:

- Se já existir um DeskGuard rodando na porta, a janela **reaproveita** a
  instância em vez de tentar occupy a mesma porta.
- Se o WebView2 do Windows não estiver instalado, a ferramenta **não falha**:
  ela avisa no console e abre a mesma interface no navegador padrão (a menos
  que `--no-browser-fallback` seja usado).
- Ao fechar a janela, o servidor local é encerrado junto com o processo.

### 3.4 Variáveis de ambiente

| Variável | Padrão | Função |
|---|---|---|
| `DESKGUARD_HOME` | `%LOCALAPPDATA%\DeskGuard` | Diretório de dados. |
| `DESKGUARD_DB` | `<DESKGUARD_HOME>\deskguard.db` | Caminho do banco SQLite. |
| `DESKGUARD_HOST` | `127.0.0.1` | Endereço de escuta da API. |
| `DESKGUARD_PORT` | `8765` | Porta da API. |
| `DESKGUARD_TIMEOUT` | `25` | Tempo limite de cada coleta, em segundos. |
| `DESKGUARD_MODE` | `live` | `live` ou `demo`. |
| `DESKGUARD_MAX_CONCURRENCY` | `2` | Execuções simultâneas. |
| `DESKGUARD_ALLOWED_TARGETS_FILE` | `<DESKGUARD_HOME>\allowed_targets.json` | Lista de destinos de rede autorizados para sondagem. |

---

## 4. Arquitetura

```
     Janela nativa (desktop.py)  ou  Navegador
            │  HTTP (127.0.0.1) + token anti-CSRF
            ▼
    ┌───────────────────────┐
    │  API FastAPI (api/)   │  ← valida entrada, autoriza capacidade
    └───────────┬───────────┘
                │
        ┌───────▼────────┐
        │ Services        │  ← regras de negócio, orquestração
        │ execution/report│
        └───────┬────────┘
                │
        ┌───────▼────────┐
        │ Procedures      │  ← catálogo versionado, com especificação
        │ (procedures/)   │
        └───────┬────────┘
                │
        ┌───────▼────────┐
        │ Collectors      │  ← ÚNICO ponto de contato com o SO
        │ stdlib/PowerShell│
        └───────┬────────┘
                │
        ┌───────▼────────┐
        │ SQLite local    │  ← execuções, etapas, auditoria
        └─────────────────┘
```

O projeto segue uma regra central: **a interface web nunca fala com o sistema
operacional**. Ela só conhece procedimentos catalogados, e todo procedimento
declara o que faz, o que exige e o que pode alterar. Detalhes em
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Estrutura de pastas

```
DeskGuard/
├── Prompt.md                       # escopo original do projeto
├── pyproject.toml                  # dependências, metadados e entrypoint
├── requirements.txt                # dependências de execução fixadas
├── requirements-dev.txt            # dependências de teste fixadas
├── packaging/
│   └── deskguard.spec              #empacotamento PyInstaller
├── scripts/
│   ├── check.ps1                   # validação automatizada ponta a ponta
│   ├── build.ps1                   # empacotamento em executável
│   └── DeskGuard.bat               # atalho de duplo clique (janela nativa)
├── src/deskguard/
│   ├── domain/                     # enums, resultados e especificações
│   ├── catalog/                    # registro e carregamento de procedimentos
│   ├── procedures/                 # procedimentos do catálogo
│   ├── collectors/                 # coleta (stdlib, PowerShell, demo)
│   │   └── scripts/               # scripts .ps1 versionados
│   ├── storage/                    # modelos, conexão e repositório SQLite
│   ├── services/                   # execução e geração de relatórios
│   ├── security/                   # capacidade, aprovação e validação
│   ├── api/                        # FastAPI, middlewares e rotas
│   ├── web/                        # interface (HTML, CSS, JS sem build)
│   ├── cli.py                      # interface de linha de comando
│   ├── desktop.py                  # camada desktop (janela nativa do Windows)
│   └── config.py                   # configuração por ambiente
├── tests/
│   ├── unit/                       # testes unitários (allowlist, rede, CLI, desktop, etc.)
│   ├── integration/                # testes de integração da API
│   └── fakes.py                    # procedimentos sintéticos para os testes
└── docs/                          # arquitetura, segurança, roadmap, runbook
```

---

## 5. Procedimentos disponíveis nesta versão

### `system.overview` — Visão geral do sistema

Coleta **somente leitura** do inventário do endpoint, em seis verificações:

| # | Verificação | Origem | O que obtém |
|---|---|---|---|
| 1 | Versão do Windows | PowerShell / WMI | Edição, build, versão de atualização, data de instalação, arquitetura, locale |
| 2 | Identidade do equipamento | PowerShell / WMI | Nome do computador, fabricante, modelo, série, domínio |
| 3 | Tempo de atividade | PowerShell / WMI | Último boot, horas de atividade, hora local, fuso horário |
| 4 | Hardware resumido | PowerShell / WMI | Processador, núcleos físicos e lógicos, memória física total |
| 5 | Contexto de execução | Python (stdlib) | Privilégio do processo, memória em uso, versão do Python, CPU lógica |
| 6 | Armazenamento | Python (stdlib) | Volumes fixos com espaço total, livre e percentual de uso |

Nenhuma configuração é alterada. A conta em uso **não** é coletada por padrão:
o parâmetro `include_account` precisa ser ativado explicitamente.

### `network.configuration` — Configuração de rede

Levanta a configuração de rede do endpoint, em quatro verificações:

| # | Verificação | O que obtém |
|---|---|---|
| 1 | Estado dos adaptadores | Descrição, tipo, status, velocidade e MAC de cada interface |
| 2 | Endereçamento IP | IPv4/IPv6, máscara, gateway padrão e servidores DNS por interface |
| 3 | Rotas | Rotas ativas e rota padrão configurada |
| 4 | Perfil de rede | Categoria e conectividade informada pelo Windows por interface |

### `network.connectivity` — Conectividade de rede

Testa DNS, ICMP e TCP **apenas em destinos autorizados**, em três verificações:

| # | Verificação | Desvio quando |
|---|---|---|
| 1 | Resolução DNS | O nome não resolve (severidade alta) |
| 2 | Alcance ICMP | O destino não responde (severidade baixa — firewall pode bloquear ping) |
| 3 | Portas TCP | A porta não aceita conexão (severidade média) |

Parâmetros: `targets` (lista de destinos autorizados) e `probe_timeout_s`
(1 a 10 segundos, padrão 3). Destino fora da lista de autorizados é recusado
com **422** antes de qualquer coleta, e o script relê a lista do disco para
descartar o que não estiver autorizado.

### `printers.status` — Estado das impressoras

| # | Verificação | O que obtém |
|---|---|---|
| 1 | Inventário de impressoras | Nome, porta, driver, se é de rede/virtual, status e código de erro |
| 2 | Fila de impressão | Trabalhos pendentes por impressora, com situação (normal, pausado, erro) |
| 3 | Serviço de impressão | Estado e tipo de inicialização do `Print Spooler` |

Impressoras virtuais (Microsoft Print to PDF, XPS, Fax) são identificadas e
apartadas do inventário físico. O código de erro do Windows é traduzido em
linguagem clara — por exemplo, `detected_error_state = 9` vira
**"papel travado"**.

### `services.status` — Estado dos serviços do Windows

Verifica os serviços que sustentam o atendimento, em três verificações:

| # | Verificação | O que obtém |
|---|---|---|
| 1 | Estado dos serviços | Estado atual (`Running`, `Stopped`, `Paused`) de cada serviço monitorado |
| 2 | Tipo de inicialização | Se o serviço volta a subir após um reinício (`Automatic`, `Manual`, `Disabled`) |
| 3 | Dependências entre serviços | Serviços dos quais cada um depende e serviços que dependem dele |

Serviços monitorados: **Spooler** (fila de impressão), **cliente DNS**
(`Dnscache`), **cliente DHCP**, **rede sem fio** (`WlanSvc`) e **Windows
Update** (`wuauserv`). Com o parâmetro `include_supporting` (padrão ligado),
também entram WMI, RPC, DCOM, BITS e a política de diagnóstico.

A leitura é feita pelo Gerenciador de Controle de Serviço
(`Get-Service`), com o caminho do executável e o código de saída completados
pelo WMI quando disponível. **Nenhuma ação é executada sobre os serviços**:
o DeskGuard não inicia, não para, não reinicia e não reconfigura serviço
algum.

O diagnóstico distingue o desvio real do estado normal:

| Situação | Resultado |
|---|---|
| Serviço parado com inicialização `Automatic` | Falha confirmada (severidade pela criticidade) |
| Serviço `Disabled` | Falha confirmada nos serviços críticos; aviso nos demais |
| Serviço parado com inicialização `Manual` (Windows Update, BITS) | Estado esperado — **não** é falha |
| Serviço inexistente no endpoint | Não aplicável |
| Serviço em estado transitório (`Start Pending`) | Inconclusivo |

Cada serviço tem um perfil com o impacto no atendimento — por exemplo, o
Spooler parado derruba a impressão, e o cliente DNS parado derruba a
resolução de nomes mesmo com o cabo conectado.

---

## 6. Modelo de resultado

O ponto central do projeto é a distinção entre *problema confirmado* e
*verificação inconclusiva*. Cada verificação retorna um `CheckStatus`:

| Status | Significado |
|---|---|
| `pass` | Executada, nenhum desvio encontrado. |
| `fail` | Executada, **problema confirmado**. |
| `warn` | Executada, desvio de menor impacto. |
| `inconclusive` | **Não foi possível determinar** (permissão, componente indisponível, timeout). |
| `not_applicable` | Não se aplica a este endpoint. |
| `skipped` | Dispensada porque um pré-requisito não foi satisfeito. |

Regras aplicadas na implementação:

- uma exceção dentro de um coletor **nunca** vira `fail` — vira `inconclusive`;
- executar sem privilégio administrativo **não** é tratado como desvio do
  endpoint, e sim como limitação declarada da coleta;
- o relatório nunca afirma que um problema foi resolvido, porque nenhum
  procedimento de leitura altera o sistema.

---

## 7. Segurança

- **Menor privilégio:** o MVP inteiro é somente leitura. A capacidade
  `MODIFYING` já existe no modelo e é recusada sem aprovação explícita
  (`CapabilityPolicy`), com registro na trilha de auditoria.
- **API local:** escuta apenas em `127.0.0.1`; requisições com cabeçalho
  `Host` não local são recusadas (proteção contra DNS rebinding).
- **CSRF:** operações que alteram estado exigem o token anti-CSRF emitido na
  própria página.
- **Sem execução de comandos arbitrários:** não existe endpoint de shell. Só
  procedimentos do catálogo podem ser executados, com parâmetros validados
  (chave desconhecida, tipo errado ou valor fora de faixa são rejeitados).
- **Sem injeção de comando no PowerShell:** os scripts são arquivos versionados
  do projeto, executados com `-EncodedCommand`; os parâmetros trafegam por
  arquivo JSON temporário cujo caminho chega ao processo por variável de
  ambiente — nunca pela linha de comando.
- **Minimização de dados:** sem senhas, tokens, chaves ou conteúdo pessoal.
  A conta em uso é opt-in. O modo demonstração é totalmente separado do real.
- **Sondagem de rede restrita:** `network.connectivity` só testa destinos da
  lista de autorizados, validada em duas camadas (a API recusa com 422 e o
  script relê a lista do disco). As portas testadas vêm sempre da lista
  relida, nunca do pedido.
- **Serviços somente leitura:** `services.status` lê estado, tipo de
  inicialização, caminho do executável e dependências. O script não contém
  nenhum comando que inicie, pare, reinicie ou reconfigure serviço — e um
  teste automatizado falha a suíte se algum desses aparecer.
- **Logs limpos:** a trilha de auditoria guarda ação, alvo, resultado e
  confirmações; nenhum segredo é registrado.

Detalhamento em [docs/SECURITY.md](docs/SECURITY.md).

---

## 8. Testes

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

**Resultado real desta execução (22/10/2026):**

```
225 passed, 1 warning in 16.59s
```

Com cobertura:

```powershell
python -m pytest -q --cov=deskguard --cov-report=term-missing
```

```
TOTAL                                           2824    387    86%
225 passed, 1 warning in 16.59s
```

| Área | Cobertura |
|---|---|
| `domain/` (resultados, enums, especificações) | 93%–100% |
| `security/` (capacidade, validação e allowlist) | 92%–97% |
| `storage/` (modelos, repositório, indicadores) | 92%–94% |
| `api/` (rotas, middlewares, schemas) | 81%–100% |
| `services/` (execução e relatório) | 83%–88% |
| `procedures/` (regras de interpretação) | 82%–96% |
| `collectors/service_status.py` (interpretação de serviços) | **99%** |
| `collectors/` | 58%–100% (o executor PowerShell real é coberto por execução manual e pela integração) |
| `desktop.py` (camada desktop) | **97%** — coberto por `tests/unit/test_desktop.py` |
| `cli.py` | **58%** — coberto por `tests/unit/test_cli.py` |

Estratégia: os testes de integração usam **procedimentos sintéticos**
(`tests/fakes.py`) e um banco temporário, de modo que a suíte **não executa
nenhuma coleta real no computador do operador**. Os procedimentos reais
(`system.overview`, `network.configuration`, `network.connectivity`,
`printers.status`, `services.status`) foram validados à parte, com execução
manual registrada em [docs/RUNBOOK.md](docs/RUNBOOK.md).

A suíte também cobre a camada desktop sem abrir janela nenhuma: o `pywebview`
é substituído por um dublê e a API local é realmente posta no ar em uma
thread, para validar que a janela nativa receberia uma aplicação funcional.

---

## 9. Documentação

| Documento | Conteúdo |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Camadas, decisões técnicas e como estender o catálogo |
| [docs/SECURITY.md](docs/SECURITY.md) | Controles implementados, riscos residuais e como reportar problemas |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Plano incremental, critérios de conclusão e pendências |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Operação, diagnóstico e resultados reais das validações |

---

## 10. Limitações conhecidas

1. A sondagem de rede é limitada à lista de autorizados: destinos fora dela
   são recusados por desenho, e a lista precisa ser mantida por quem opera a
   ferramenta.
2. O serviço em segundo plano não sobrevive ao encerramento do processo: a
   aplicação deve ser mantida aberta durante as verificações.
3. O SQLite é local e de usuário único; não há sincronização nem acesso
   simultâneo por várias máquinas.
4. Coletas que exigem elevação administrativa ficam inconclusivas quando o
   processo não é elevado — por desenho, para não mascarar a limitação.
5. A execução via PowerShell depende da disponibilidade do serviço WMI.
6. As sondagens de rede são visíveis nos logs de firewall do endpoint e do
   destino; a ferramenta não oculta esse rastro.
7. A janela nativa depende do runtime **WebView2** da Microsoft e do
   `pywebview`; sem eles, a interface abre no navegador padrão.
8. O executável empacotado não é assinado: o Windows pode exibir o aviso do
   SmartScreen na primeira execução. O código-fonte do empacotamento está em
   [packaging/deskguard.spec](packaging/deskguard.spec).
9. O executável é uma foto do código no momento do empacotamento: não há
   atualização automática. Para ter correções, é preciso gerar uma nova
   versão.
10. `services.status` lê apenas um conjunto fixo de serviços do Windows; não
    há um modo de listar todos os serviços do endpoint. Serviços fora da
    lista só podem ser consultados por inspeção manual.

---

## 11. Aviso de uso

O DeskGuard é voltado a **sistemas próprios ou ambientes com autorização
explícita**. O MVP não executa alterações, mas as estruturas para ações
corretivas já foram desenhadas. Use a ferramenta apenas onde você tem
autoridade para diagnosticar.

## 12. Licença

MIT.
