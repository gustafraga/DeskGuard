# Roadmap incremental do DeskGuard

Cada incremento é pequeno, executável e verificável. Um incremento só é
encerrado quando a funcionalidade está **conectada de ponta a ponta** — não
quando apenas os arquivos existem.

---

## Incremento 1 — Fundação + primeiro procedimento real ✅ CONCLUÍDO

**Objetivo:** plataforma operacional de ponta a ponta com um procedimento real.

| Item | Situação |
|---|---|
| Domínio (status, severidade, resultado, especificação) | ✅ |
| Catálogo com registro automático por decorador | ✅ |
| Coleta somente leitura (stdlib + PowerShell com payload isolado) | ✅ |
| Persistência SQLite (execuções, etapas, auditoria) | ✅ |
| Serviço de execução em thread + indicador consolidado | ✅ |
| Gerador de relatório técnico editável | ✅ |
| API local com CSRF, validação de Host e cabeçalhos de segurança | ✅ |
| Interface web funcional (7 telas) | ✅ |
| Procedimento real `system.overview` | ✅ |
| Modo demonstração separado do real | ✅ |
| CLI (`serve`, `list`, `run`, `doctor`) | ✅ |
| Suíte de testes | ✅ 81 testes, 79% de cobertura (no fechamento do incremento 1; hoje são 225 testes e 86%) |

**Critérios de conclusão verificados**

- [x] `python -m deskguard run system.overview` coleta dados reais do host.
- [x] `python -m pytest -q` → suíte completa passando (274 testes no estado atual).
- [x] A API recusa requisição sem token anti-CSRF (403) e com `Host` externo (403).
- [x] O relatório identifica a origem dos dados (real × simulado).
- [x] Uma exceção em coletor vira `inconclusive`, nunca `fail`.
- [x] Procedimento com capacidade `MODIFYING` é recusado sem aprovação (403).

---

## Incremento 2 — Diagnóstico de rede e de impressoras ✅ CONCLUÍDO

**Objetivo:** o segundo, o terceiro e o quarto procedimento real de diagnóstico,
com controle rigoroso sobre quais destinos de rede podem ser sondados.

### Procedimento `network.configuration`

- Configuração de IP, gateway e DNS por interface (PowerShell / `Get-NetIPConfiguration`).
- Estado dos adaptadores: descrição, tipo, status, velocidade, MAC.
- Rotas ativas e perfil de rede (categoria e conectividade informada pelo Windows).

### Procedimento `network.connectivity`

- Resolução DNS, resposta ICMP e conexão TCP **apenas** em destinos autorizados.
- Lista de autorizados em arquivo JSON (`allowed_targets.json`), administrada por
  `deskguard targets`.
- Distinção clara entre: DNS falhou / porta recusada / tempo esgotado / sem rota.

### Procedimento `printers.status`

- Impressoras instaladas, porta, driver e estado (`Get-CimInstance Win32_Printer`).
- Fila de trabalhos de cada impressora (`Get-PrintJob`).
- Estado do serviço `Print Spooler`.

### Barreira de segurança: lista de destinos autorizados

- Destino fora da lista é recusado com **422** antes de qualquer coleta.
- O script relê a lista do disco e descarta destinos não autorizados
  (`rejected_targets`), protegendo a camada de coleta.
- Sem lista, apenas `localhost` e o gateway padrão do próprio endpoint são testados.
- As portas testadas vêm sempre da lista relida no script, nunca do pedido.

### Requisitos

- [x] `collectors/scripts/network_configuration.ps1`
- [x] `collectors/scripts/network_connectivity.ps1`
- [x] `collectors/scripts/printers_status.ps1`
- [x] `security/allowlist.py` com leitura, gravação e validação da lista
- [x] Tipo de parâmetro `host_list` com validação estrita em `validation.py`
- [x] Testes unitários dos coletores, da allowlist e da CLI
- [x] Testes de integração da API (422 para destino não autorizado, demo)
- [x] Teste real executado e registrado no `docs/RUNBOOK.md`

**Critérios de conclusão verificados**

- [x] `python -m deskguard run network.configuration` coleta dados reais do host.
- [x] `python -m deskguard run network.connectivity` testa apenas destinos autorizados.
- [x] `python -m deskguard run printers.status` identifica a impressora com papel travado.
- [x] `python -m deskguard targets add 10.0.0.5 --port 443` autoriza um destino.
- [x] Destino não autorizado é recusado com 422 pela API e pela CLI.
- [x] `python -m pytest -q` → 225 passed, 86% de cobertura.

---

## Incremento 2.5 — Camada desktop e empacotamento ✅ CONCLUÍDO

**Objetivo:** tirar o DeskGuard do navegador e entregar um executável que o
técnico leva para o endpoint.

### Camada desktop (`src/deskguard/desktop.py`)

- Interface aberta em **janela nativa do Windows** (WebView2), sem barra de
  endereço e sem abas.
- A API local sobe em **thread de background**; a janela aponta para
  `http://127.0.0.1:<porta>/`.
- Reaproveitamento de instância: se já houver um DeskGuard na porta, ele é
  reutilizado em vez de disputar a porta.
- **Fallback para o navegador** quando o `pywebview` ou o WebView2 não
  existirem — a ferramenta nunca falha por causa da interface.
- `deskguard doctor` informa se a janela nativa está disponível.

### Empacotamento

- `packaging/deskguard.spec` (PyInstaller) com scripts PowerShell, modelo
  HTML, CSS e JavaScript embarcados como dados.
- `scripts/build.ps1` conduz o build e valida o executável gerado.
- Modo padrão: **executável único** (`dist\DeskGuard.exe`, 22 MB), sem
  necessidade de Python na máquina de destino.
- Modo `-OneFolder`: pasta com o executável e suas dependências, para
  inicialização mais rápida.

### Requisitos

- [x] `src/deskguard/desktop.py` com janela nativa, fallback e diagnóstico
- [x] Comando `deskguard desktop` na CLI, com `--no-reuse`,
      `--no-browser-fallback` e `--open-browser`
- [x] `tests/unit/test_desktop.py` — 39 testes, 97% de cobertura da camada
- [x] `packaging/deskguard.spec` e `scripts/build.ps1`
- [x] Extra `desktop` (`pywebview`) e extra `build` (`pyinstaller`) no
      `pyproject.toml`
- [x] `scripts/DeskGuard.bat` — atalho de duplo clique

**Critérios de conclusão verificados**

- [x] `python -m deskguard desktop` abre a janela nativa com a API no ar.
- [x] `dist\DeskGuard.exe list` lista os 5 procedimentos.
- [x] `dist\DeskGuard.exe run printers.status` coleta dados reais do host
      (o desvio de papel travado foi detectado).
- [x] `dist\DeskGuard.exe serve` responde em `/`, `/static/css/styles.css`,
      `/static/js/app.js` e `/api/health`.
- [x] `python -m pytest -q` → 225 passed, 86% de cobertura.

---

## Incremento 3 — Serviços do Windows ✅ CONCLUÍDO

**Objetivo:** o quinto procedimento real de diagnóstico, capaz de responder se
um serviço está parado — e se volta a funcionar depois de um reinício.

### Procedimento `services.status`

- Estado atual e tipo de inicialização dos serviços que sustentam o
  atendimento: **Spooler**, **cliente DNS** (`Dnscache`), **cliente DHCP**,
  **rede sem fio** (`WlanSvc`) e **Windows Update** (`wuauserv`).
- Com `include_supporting` ligado, também entram **WMI**, **RPC**, **DCOM**,
  **BITS** e a **política de diagnóstico**.
- Tipo de inicialização (`Automatic`, `Manual`, `Disabled`) e caminho do
  executável do serviço.
- Cadeia de dependências: serviços dos quais cada um depende e serviços que
  dependem dele, com o impacto no atendimento.

### Leitura pelo coletor, sem tocar na API do Windows

- A coleta passa pelo `Get-Service` (Gerenciador de Controle de Serviço) e é
  complementada pelo WMI (`Win32_Service`) para caminho do executável e
  código de saída.
- **Nenhuma ação é executada sobre os serviços:** não inicia, não para, não
  reinicia e não reconfigura serviço algum. O serviço Spooler é apenas lido.
- O script é um arquivo versionado em `collectors/scripts/services_status.ps1`,
  em ASCII puro, e recebe os parâmetros por arquivo JSON temporário.

### Interpretação com perfis de serviço

Cada serviço monitorado tem um perfil que declara criticidade, impacto no
atendimento, tipo de inicialização esperado e se pode estar parado em uma
operação normal. Isso evita o falso positivo clássico:

| Situação | Resultado |
|---|---|
| Parado com inicialização `Automatic` | Falha confirmada |
| `Disabled` | Falha confirmada (crítico) ou aviso (demais) |
| Parado com inicialização `Manual` (Windows Update, BITS) | Estado esperado |
| Inexistente no endpoint | Não aplicável |
| Estado transitório (`Start Pending`) | Inconclusivo |

### Requisitos

- [x] `collectors/scripts/services_status.ps1` (ASCII puro, sem comandos de escrita)
- [x] `collectors/service_status.py` com os perfis e a classificação
- [x] `procedures/services_status.py` e registro automático no catálogo
- [x] Coletores de demonstração para o modo `demo`
- [x] `tests/unit/test_services_procedure.py` — 34 testes, incluindo a
      garantia de que o script não executa comandos que alteram o sistema
- [x] Execução real registrada no `docs/RUNBOOK.md`

**Critérios de conclusão verificados**

- [x] `python -m deskguard run services.status` coleta dados reais do host.
- [x] `dist\DeskGuard.exe run services.status` coleta dados reais a partir do
      executável empacotado.
- [x] O procedimento aparece no catálogo com capacidade `read_only` e
      privilégio `user`.
- [x] O script não contém `Start-Service`, `Stop-Service`, `Restart-Service`,
      `Set-Service` nem `sc.exe config`.
- [x] `python -m pytest -q` → 225 passed, 86% de cobertura.

---

## Incremento 4 — Desempenho e recursos

### Procedimento `performance.resources`

- Top de processos por CPU e memória.
- Carga média, tempo de atividade e tempo de disco.
- Espaço em disco com ranqueamento de volumes críticos.

---

## Incremento 5 — Segurança defensiva e auditoria de configuração ✅ CONCLUÍDO

**Objetivo:** procedimento real `security.audit` (somente leitura), com
classificação por severidade, evidências tabuladas e distinção honesta entre
falhas, avisos, inconclusivos e aprovados.

### Escopo

- [x] **Windows Firewall** por perfil (Domínio, Privado, Público): ativo/inativo.
- [x] **Proteção antivírus**: produtos registrados no SecurityCenter2, estado em tempo real, idade de assinaturas e varreduras, com decodificação conservadora de `productState`.
- [x] **Configurações de segurança**: UAC, bloqueio de tela, acesso remoto (RDP), criptografia do disco (BitLocker) e conta Guest.
- [x] **Classificação por severidade** com impacto, recomendação e referência.
- [x] **Falhas de permissão/indisponibilidade** viram `inconclusive`, nunca `fail`.
- [x] **Regra explícita:** aprovação das verificações **não** equivale a certificação de segurança do equipamento.
- [x] Evidências tabuladas na visão técnica e JSON bruto recolhido em bloco retrátil.

### Requisitos

- [x] `collectors/scripts/security_audit.ps1`
- [x] `collectors/security_audit.py` (classificação e `SecurityFinding`)
- [x] `procedures/security_audit.py` com 3 etapas
- [x] Evidências tabuladas no relatório/visão técnica
- [x] Testes unitários e integração no modo demonstração
- [x] Atualizar documentação (README, ROADMAP, SECURITY) e garantir que todos os testes passem

### Critérios de conclusão

- [x] `security.audit` aparece no catálogo e roda em modo demonstração
- [x] Achados falhos aparecem com severidade e recomendação
- [x] Itens inconclusivos por permissão ficam claros, sem false negative
- [x] `python -m pytest -q` passa sem falhas (274 testes)

---

## Incremento 6 — Ações corretivas controladas

Somente depois que a coleta estiver madura.

- Procedimentos com `Capability.MODIFYING`.
- Confirmação explícita em duas etapas na interface.
- Botão de cancelar execução.
- Pré-condições verificáveis antes de cada ação.
- Registro de aprovação, ação executada e resultado na auditoria.

> Regra do projeto: exclusão de arquivos, alteração de firewall,
> reinicialização, reinstalação de aplicativos e mudanças de rede exigem
> controles explícitos e nunca entram em ação automática.

---

## Incremento 7 — Empacotamento e integração

- ✅ Executável único via PyInstaller (`deskguard.exe`).
- ✅ Instalador para Windows (Inno Setup) com atalhos na Área de Trabalho e Menu Iniciar.
- ✅ GitHub Actions para build automático e publicação em Releases.
- [ ] Exportação do relatório para sistema de chamados (CSV/JSON).
- [ ] Migrações de esquema com Alembic.

## Fase 2 — Resolução Ativa e Integração

### Módulo G — Auto-Remediação ✅ INICIADO
- [x] Estrutura de ações com confirmação obrigatória
- [x] Reiniciar serviço Print Spooler com confirmação na interface
- [x] API `/api/remediation/actions` e `/api/remediation/execute`
- [x] Modal de confirmação com aviso de alteração
- [ ] Reativar perfil do Firewall do Windows
- [ ] Limpar arquivos temporários quando disco com pouco espaço

### Módulo H — Integração com GLPI
- [ ] Configuração (URL, token de aplicação)
- [ ] Criar chamado ou anexar relatório
- [ ] Armazenamento seguro de credenciais

### Módulo I — Assistente de IA (Opcional e Gratuito)
- [ ] Integração com modelo local (via freeaiagent)
- [ ] Resumo em linguagem natural
- [ ] Sugestões de troubleshooting
- [ ] Totalmente opcional e local

---

## Backlog técnico

| Item | Prioridade | Observação |
|---|---|---|
| Testes automatizados para `cli.py` | ✅ Feito | Cobertura da CLI subiu de 0% para 58% com `tests/unit/test_cli.py`. |
| Testes automatizados para a camada desktop | ✅ Feito | `tests/unit/test_desktop.py` cobre 97% de `desktop.py`, sem abrir janela. |
| Testes de integração que derrubem o processo PowerShell | Média | Validar o caminho de timeout. |
| `scripts/check.ps1` como checagem local | ✅ Feito | Executa testes, diagnóstico, execução real, demo e as verificações de API. Falta versionar como etapa obrigatória de revisão. |
| Empacotamento PyInstaller | ✅ Feito | `packaging/deskguard.spec` + `scripts/build.ps1` geram `dist\DeskGuard.exe`. |
| Instalador para Windows (MSI/Inno Setup) | Baixa | O executável único já cobre o uso em campo; o instalador facilita_updates e atalhos. |
| Assinatura digital do executável | Média | Sem assinatura, o SmartScreen avisa na primeira execução. |
| Fila de execução persistente | Baixa | Execuções interrompidas hoje perdem o estado. |
| Internacionalização (pt-BR / en) | Baixa | Textos hoje estão fixos em português. |
| Modo "somente leitura" reforçado por ACL de processo | Baixa | defense in depth para o futuro. |

---

## Como o próximo incremento deve ser feito

1. Atualizar a seção do incremento no `docs/ROADMAP.md` com a lista de tarefas.
2. Escrever primeiro o teste que falha.
3. Implementar por camadas: domínio → coletor → procedimento → serviço → API.
4. Rodar `python -m pytest -q` e corrigir até zerar as falhas.
5. Executar o procedimento **de verdade** na máquina e registrar o resultado real.
6. Atualizar `docs/RUNBOOK.md` com o comando e a saída obtida.
7. Só então marcar o incremento como concluído.
