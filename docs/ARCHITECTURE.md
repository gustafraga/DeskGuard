# Arquitetura do DeskGuard

## 1. Princípios

1. **Leitura por padrão.** Toda verificação é inócua. Qualquer operação que
   altere o sistema precisa declarar a capacidade `MODIFYING` e receber
   aprovação explícita.
2. **Inconclusivo ≠ falha.** Uma verificação que não pôde ser executada
   precisa ser marcada como tal, com o motivo. Essa distinção existe em
   todas as camadas — do coletor ao relatório.
3. **A interface web nunca toca o sistema.** Ela conhece apenas o catálogo.
   O único caminho para o sistema operacional passa pelos coletores.
4. **Nada de execução de comandos arbitrários.** Não existe endpoint de
   shell, nem campo de texto livre que vire comando.
5. **Execução local.** SQLite no diretório do usuário, API em `127.0.0.1`,
   sem dependência de rede para as funções essenciais.

---

## 2. Camadas e responsabilidades

| Camada | Pacote | Responsabilidade | Não deve fazer |
|---|---|---|---|
| Domínio | `domain/` | Vocabulário, estados, resultados, especificações | Acessar I/O |
| Catálogo | `catalog/` | Registrar e localizar procedimentos | Executar coleta |
| Procedimentos | `procedures/` | Orquestrar coletores em etapas | Acessar o banco ou a API |
| Coletores | `collectors/` | Falar com o sistema operacional | Interpretar regras de negócio |
| Persistência | `storage/` | Gravar e consultar o SQLite | Decidir o que é um desvio |
| Serviços | `services/` | Regras de negócio, orquestração, relatório | Formatar HTTP |
| API | `api/` | Validar entrada, autorizar, serializar | Coletar dados do sistema |
| Interface | `web/` | Apresentar dados e capturing input | Calcular indicadores |
| Desktop | `desktop.py` | Abrir a interface em janela nativa e servir a API local | Conter regra de negócio |

A regra de dependência aponta sempre para dentro: `api → services →
procedures → collectors`. O domínio não depende de ninguém.

A camada desktop fica **fora** dessa cadeia: ela não conhece procedimentos,
nem coleta, nem banco. Ela apenas sobe a mesma API FastAPI em uma thread e
aponta uma janela para `http://127.0.0.1:<porta>/`. Nenhuma regra de negócio
muda de lugar: continua na API e nos serviços, exatamente como antes.

---

## 3. Fluxo de uma execução

```
POST /api/executions  {procedure_id, params, mode}
        │
        ├─ require_csrf ──────────────► 403 se o token não bater
        ├─ CapabilityPolicy.authorize ─► 403 se a capacidade exigir aprovação
        ├─ validate_params ───────────► 422 se houver chave/tipo/faixa inválida
        ├─ create_execution (status=queued)
        ├─ record_audit(execution.started)
        │
        ▼  (thread do ThreadPoolExecutor)
   _execute()
        ├─ mark_running (started_at)
        ├─ Procedure.for_mode(mode)   ← demo ou live
        ├─ run_collectors()
        │     ├─ dependência satisfeita?  senão → SKIPPED
        │     ├─ exceção?                 senão → INCONCLUSIVE
        │     └─ resultado normal         → PASS / FAIL / WARN
        ├─ aggregate_outcome(checks)   ← HEALTHY / ISSUES_FOUND / INCONCLUSIVE / ERROR
        ├─ finish_execution (etapas gravadas)
        └─ record_audit(execution.finished)

GET /api/executions/{id}   → interface acompanha o progresso por polling
GET /api/executions/{id}/report → relatório técnico editável
```

A execução acontece em uma thread separada para que a requisição retorne
imediatamente (`202 Accepted`) e a interface possa mostrar o progresso sem
bloquear a API.

---

## 4. Catálogo de procedimentos

Um procedimento é uma classe que declara sua própria especificação:

```python
@register
class SystemOverviewProcedure(Procedure):
    spec = ProcedureSpec(
        id="system.overview",
        title="Visão geral do sistema",
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=("Nenhuma configuração do sistema é alterada.",),
        params=(ParamSpec(name="include_account", type="boolean", default=False),),
        steps=(StepSpec(id="os.version", title="Versão do Windows", ...),),
    )

    def build_collectors(self) -> list[Collector]:
        return [Collector(check_id="system.runtime", title="...", fn=collect_runtime)]
```

O decorador `@register` popula o registro. O carregador (`catalog/loader.py`)
importa automaticamente todos os módulos de `deskguard/procedures/` via
`pkgutil`, então **um novo procedimento entra no catálogo apenas por ser
criado como módulo** — nenhuma lista central precisa ser editada.

> **Cuidado no build congelado.** No executável do PyInstaller os módulos
> vivem dentro do arquivo PYZ e não aparecem no disco, então `pkgutil` não
> encontra nada. Por isso o `packaging/deskguard.spec` embarca os fontes de
> `deskguard/procedures/` como *dados* (para que a descoberta no disco
> funcione) e declara cada módulo em `hiddenimports` (para que ele exista
> dentro do executável). É a razão de o build congelado precisar listar
> `deskguard/procedures/*.py` de forma explícita.

A especificação é a fonte única de verdade: a interface, a API e o relatório
consomem `ProcedureSpec.to_dict()`. Não há metadado duplicado.

### Como adicionar um procedimento

1. Crie `src/deskguard/procedures/meu_procedimento.py`.
2. Declare `spec` com id, título, categoria, risco, pré-requisitos, passos e
   parâmetros.
3. Implemente `build_collectors()`.
4. Opcionalmente implemente `build_demo_collectors()` para o modo demonstração.
5. Escreva os testes e registre o resultado no `docs/ROADMAP.md`.

---

## 5. Camada de coleta

### 5.1 PowerShell

- Os scripts são arquivos `.ps1` versionados em `collectors/scripts/`.
- A execução usa `-EncodedCommand` com o conteúdo do arquivo — não há
  concatenação de comando nem uso de `-ExecutionPolicy Bypass`.
- Parâmetros trafegam por **arquivo JSON temporário**, cujo caminho é
  entregue ao processo pela variável de ambiente `DESKGUARD_PAYLOAD_PATH`.
  Portanto, **nenhum valor vindo do usuário chega à linha de comando**.
- Flags: `-NoProfile` (ignora perfil do usuário), `-NonInteractive` (evita
  prompts), `CREATE_NO_WINDOW` (não abre janela) e limite de tempo.
- O script devolve um único objeto JSON em `stdout`; erros viram resultado
  inconclusivo.
- **Os scripts são mantidos em ASCII puro.** O PowerShell 5.1 lê arquivos `.ps1`
  sem BOM usando a codificação ANSI do sistema e reconhece aspas “inteligentes”
  (U+201C/U+201D) como delimitadores de string: um único caractere não-ASCII
  dentro de um comentário pode encerrar a string mais cedo e derrubar o parser.
  O runner lê o arquivo com `utf-8-sig`, tolerante a BOM, mas a regra de
  escrita continua sendo ASCII.

### 5.2 Controle de destinos de rede

O procedimento `network.connectivity` emite pacotes de rede, e por isso tem
três barreiras independentes:

1. **Validação** (`security/validation.py`): o parâmetro `targets` é do tipo
   `host_list`; cada destino precisa ser sintaticamente válido **e** constar
   da lista de autorizados. Destino fora da lista vira erro 422 na API, e a
   execução nem chega à coleta.
2. **Coleta** (`collectors/scripts/network_connectivity.ps1`): o script relê a
   lista do disco e descarta o que não estiver nela, registrando em
   `rejected_targets`. Destinos solicitados que escapem da lista não geram
   pacote algum.
3. **Escopo** (`security/allowlist.py`): a lista começa vazia; sem autorização
   explícita, apenas `localhost` e o gateway padrão do próprio endpoint são
   sondados — nenhum dado externo é aceito.

As portas testadas, a opção de ICMP e a descrição de cada destino vêm
**sempre da lista relida dentro do script**, nunca do pedido recebido. Assim,
adulterar o payload não amplia a faixa de sondagem.

A lista vive em `allowed_targets.json`, no diretório de dados da plataforma
(`%LOCALAPPDATA%\DeskGuard`), e é administrada por `deskguard targets`.

### 5.3 Biblioteca padrão do Python

Usada para o que é acessível de forma confiável sem privilégio elevado:
volumes (`shutil.disk_usage` + `GetDriveTypeW`), memória
(`GlobalMemoryStatusEx`), contexto do processo e, na próxima iteração,
resolução DNS e teste de conexão TCP (`socket`).

### 5.4 Leitura de serviços do Windows

O procedimento `services.status` tem um contrato estrito de **somente
leitura**, garantido em três camadas:

1. **Coleta** (`collectors/scripts/services_status.ps1`): usa `Get-Service`
   (Gerenciador de Controle de Serviço) como fonte primária de estado e tipo
   de inicialização, e `Get-CimInstance Win32_Service` apenas para
   complementar caminho do executável e código de saída. Não há
   `Start-Service`, `Stop-Service`, `Restart-Service`, `Set-Service` nem
   `sc.exe config` — o teste automatizado varre o script e falha se um desses
   comandos aparecer.
2. **Módulo de interpretação** (`collectors/service_status.py`): é onde vive o
   **perfil de cada serviço** — criticidade, impacto no atendimento, tipo de
   inicialização esperado e se o serviço pode estar parado em uma operação
   normal. O coletor só coleta; a decisão acontece aqui.
3. **Procedimento** (`procedures/services_status.py`): consolida os
   resultados e declara `capability=READ_ONLY` e `privilege=USER`.

O perfil é o que separa *desvio real* de *estado normal*: `BITS`, `DPS` e
`wuauserv` são serviços por evento e ficam parados por padrão em quase toda
máquina — tratá-los como falha produziria alarme falso constante.

### 5.5 Modo demonstração

`collectors/demo.py` fornece dados sintéticos. As garantias são: nenhuma
coleta real ocorre, todo resultado tem `simulated=True` e todo bloco de
evidências carrega o aviso `DADOS SIMULADOS`. A execução é gravada com
`mode="demo"` e aparece separada na interface e no relatório.

---

## 6. Modelo de dados

```
executions
  id (uuid) · procedure_id · procedure_title · procedure_version
  capability · mode (live|demo) · status · outcome
  params_json · started_at · finished_at · duration_ms
  summary · error · tool_version · host · actor · approval_granted

execution_steps
  execution_id (FK) · seq · check_id · title · status · severity
  message · evidence_json · duration_ms · error_code · remediation · simulated

audit_events
  occurred_at · execution_id · actor · action · target · outcome
  mode · approval_granted · details_json
```

Datas são gravadas em UTC e lidas com fuso horário (`UtcDateTime`), o que
evita a ambiguidade de horário de verão em relatórios.

O SQLite roda em modo WAL, com chaves estrangeiras ativas e
`busy_timeout` de 5 segundos.

---

## 7. Decisões técnicas

| Decisão | Alternativa descartada | Motivo |
|---|---|---|
| FastAPI | Flask | Validação de entrada com Pydantic e OpenAPI gerado sem esforço extra. |
| SQLite | PostgreSQL | Requisito do projeto, zero infraestrutura, portabilidade por arquivo. |
| SQLAlchemy 2.0 | SQL puro | Mapper com tipos explícitos e migrações mais simples depois. |
| JavaScript sem build (ES modules) | React + Vite | Sem Node.js, sem `npm install`, sem etapa de build: instala e funciona. |
| Jinja2 para o shell da página | HTML estático | O único dado dinâmico da página é o token anti-CSRF. |
| ThreadPoolExecutor | Async subprocess | A coleta é bloqueante por natureza (subprocesso); threads bastam. |
| `-EncodedCommand` + payload em arquivo | `-Command` com string interpolada | Elimina a concatenação de comando: o script é estático. |
| `StrEnum` + dataclasses | Enum clássico + dicts | Código mais legível e menos serialização manual. |
| `pywebview` para a janela nativa | Electron / Tauri | Empacotaria um navegador inteiro; o WebView2 já existe no Windows e a camada desktop vira um wrapper de ~350 linhas. |
| PyInstaller em modo pasta e em arquivo único | Apenas wheel | O executável é o que o técnico leva para o endpoint; o wheel continua disponível para quem instala por `pip`. |
| `Get-Service` como fonte primária de serviços | Só `Win32_Service` (WMI) | `Win32_Service.Dependencies` veio vazio nesta máquina: o WMI não devolve as dependências. `Get-Service` devolve estado, tipo de inicialização e as duas listas de dependência; o WMI entra só como complemento (caminho do executável e código de saída). |
| Perfil por serviço, com criticidade e impacto | Regra genérica "parado = falha" | Serviços por evento (`BITS`, `DPS`, `wuauserv`) ficam parados por padrão; sem perfil, todo endpoint apareceria com alarme falso. |

---

## 8. Segurança na API local

| Ameaça | Controle | Onde |
|---|---|---|
| DNS rebinding | Recusa cabeçalhos `Host` não locais | `api/middleware.py` |
| CSRF | Token por sessão na página + cabeçalho obrigatório | `api/deps.py` |
| XSS | Interface montada com `textContent`, sem `innerHTML` com dados da API | `web/static/js/ui.js` |
| Clickjacking | `X-Frame-Options: DENY` + `frame-ancestors 'none'` | `api/middleware.py` |
| Injeção de comando | Catálogo fechado + validação de parâmetros | `security/validation.py` |
| Execução arbitrária | Nenhum endpoint de shell; capacidade declarada | `security/capabilities.py` |
| Vazamento de segredo em log | Auditoria guarda ação/alvo/resultado, não conteúdo de coleta | `storage/repository.py` |
| Coleta excessiva | Minimização por padrão; conta em uso é opt-in | `procedures/system_overview.py` |
| Sonda de rede arbitrária | Lista de destinos autorizados validada em duas camadas | `security/allowlist.py`, `collectors/scripts/network_connectivity.ps1` |
| Alteração de serviço do Windows | Coleta somente leitura (`Get-Service` + WMI), sem comando de escrita no script | `collectors/scripts/services_status.ps1`, `collectors/service_status.py` |
| Dados fictícios confundidos com reais | `mode` explícito + `simulated=True` + aviso no relatório | `collectors/demo.py`, `services/report.py` |

---

## 9. Camada desktop e empacotamento

### 9.1 Camada desktop

`src/deskguard/desktop.py` tem quatro responsabilidades, nenhuma delas sendo
regra de negócio:

1. **Porta e reaproveitamento** — `find_free_port()` escolhe a porta preferida
   se ela estiver livre; `is_deskguard_server()` consulta `/api/health` e
   confere a marca `application == "deskguard"`, para não confundir com outro
   serviço local que responda JSON. Se já existe uma instância, ela é
   reaproveitada em vez de disputar a porta.
2. **Servidor local** — `BackgroundServer` sobe o `uvicorn.Server` em uma
   thread daemon, com os *signal handlers* desabilitados (o `uvicorn.run()`
   normal não pode ser usado dentro de uma thread).
3. **Janela** — `open_native_window()` usa o `pywebview`. Se o pacote ou o
   runtime WebView2 não estiverem disponíveis, a exceção vira
   `DesktopUnavailableError` e o modo navegador assume.
4. **Diagnóstico** — `desktop_availability()` responde se a janela_native está
   disponível nesta máquina; é o que o `deskguard doctor` e a tela de
   configurações exibem.

### 9.2 Empacotamento

`packaging/deskguard.spec` é a fonte do build. Ele declara:

- **dados**: o modelo HTML, o CSS, o JavaScript e os scripts `.ps1` — são
  arquivos que o pacote precisa em disco, não módulos;
- **fontes de `deskguard/procedures/`**: necessários para que `pkgutil`
  descubra os módulos de procedimento no build congelado (ver seção 4);
- **hidden imports**: os módulos do `uvicorn` carregados dinamicamente e os
  módulos de procedimento;
- **exclusões**: `tkinter`, `matplotlib`, `numpy`, `PIL` e `pytest`, que
  inflariam o executável sem uso.

`scripts/build.ps1` conduz o build e valida o resultado (`--version` e
`list`). O modo padrão gera **um único arquivo** (`dist\DeskGuard.exe`); o
modo `-OneFolder` gera a pasta com o executável e suas dependências.

---

## 10. Pontos de extensão

| Necessidade | Onde mexer |
|---|---|
| Novo procedimento | Novo módulo em `procedures/` |
| Nova coleta de sistema | Novo `Collector` em `collectors/` (Python ou script `.ps1`) |
| Nova categoria na interface | Rótulo em `api/routes/catalog.py` (`_CATEGORY_LABELS`) |
| Novo formato de relatório | `services/report.py` |
| Nova ação corretiva | Declarar `Capability.MODIFYING`, implementar `build_collectors` e o controle de aprovação já existente |
| Novo destino de rede autorizado | `deskguard targets add <host> --port <n>` |
| Integração com sistema de chamados | Novo módulo em `services/` consumindo `build_report_markdown()` |
| Migração de banco | Alembic, a ser adicionado junto com a primeira alteração de esquema |
| Ícone, assinatura digital ou instalador do Windows | `packaging/deskguard.spec` (campo `icon`) e um passo de empacotamento dedicado |

