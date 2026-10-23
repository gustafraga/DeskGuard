# Segurança do DeskGuard

## 1. Postura adotada

O DeskGuard é uma ferramenta de diagnóstico defensivo. O objetivo é coletar
evidências com a menor perturbação possível no endpoint e transformar essas
evidências em documentação de chamado confiável.

O MVP inteiro é **somente leitura**. A capacidade de alterar o sistema já
existe no modelo de domínio e nas políticas, mas nenhum procedimento a
utiliza.

---

## 2. Controles implementados

### 2.1 Princípio do menor privilégio

- Todo procedimento declara `capability` (`READ_ONLY` ou `MODIFYING`) e
  `privilege` (`USER` ou `ELEVATED`) na própria especificação.
- `CapabilityPolicy.evaluate()` decide: leitura é liberada; alteração exige
  aprovação explícita.
- A ausência de elevação **não** é reportada como desvio do endpoint: as
  coletas que dependem dela ficam `inconclusive` com o motivo, evitando que
  uma limitação da ferramenta pareça um problema do computador.

### 2.2 Proteção contra injeção de comando

O risco clássico deste tipo de ferramenta é montar uma linha de comando com
dados vindos do usuário. A implementação elimina a categoria inteira:

1. Não existe endpoint de execução de comandos.
2. Só procedimentos do catálogo podem ser executados.
3. Parâmetros são validados contra a especificação: chave desconhecida é
   erro, tipo incompatível é erro, valor fora de faixa é erro.
4. Os scripts PowerShell são arquivos estáticos versionados no projeto e são
   executados por `-EncodedCommand` — o conteúdo do comando nunca é
   montado em tempo de execução.
5. Os parâmetros trafegam por arquivo JSON temporário, cujo caminho chega
   ao processo por variável de ambiente, nunca pela linha de comando.

Além disso, o acesso a recursos do sistema é feito por API do Windows
(`ctypes`) e por cmdlets com parâmetros fixos, não por shell.

### 2.3 Validação de entradas

- Pydantic nos modelos de requisição, com `extra="forbid"`.
- `validate_params()` aplica a especificação do procedimento: tipos,
  intervalos, listas de escolha, padrões regex e tamanho máximo.
- Hostnames aceitos por `ParamSpec.pattern` seguem
  `[A-Za-z0-9._-]{1,253}`.
- O tipo de parâmetro `host_list` exige que cada destino seja um nome de host
  ou um endereço IPv4 válido **e** que conste da lista de autorizados.

### 2.4 Controle de destinos de rede

O procedimento `network.connectivity` é o único que emite pacotes de rede.
Ele é protegido por três barreiras independentes:

1. **Validação antecipada.** Destino fora da lista de autorizados é recusado
   com **422** na API e com erro de domínio na CLI, antes de qualquer coleta.
2. **Revalidação dentro do script.** O script relê a lista do disco e descarta
   o que não estiver nela, registrando em `rejected_targets`. A proteção
   existe mesmo que o arquivo seja alterado entre a validação e a execução.
3. **Escopo restrito.** A lista começa vazia. Sem autorização explícita,
   apenas `localhost` e o gateway padrão do próprio endpoint são sondados.

As portas testadas, a opção de ICMP e a descrição de cada destino vêm sempre
da lista relida no script — nunca do pedido — de modo que adulterar o payload
não amplia a faixa de sondagem. Os limites são rígidos: 10 destinos, 5 portas
por destino, portas de 1 a 65535 e nomes de host sem curinga, CIDR ou URL.

A lista é um arquivo JSON local (`allowed_targets.json`, no diretório de dados
da plataforma), administrado por `deskguard targets`, e pode ser isolada por
variável de ambiente (`DESKGUARD_ALLOWED_TARGETS_FILE`).

### 2.5 Proteção da API local

| Controle | Implementação |
|---|---|
| Escuta restrita | `127.0.0.1` por padrão (`DESKGUARD_HOST`) |
| DNS rebinding | Cabeçalho `Host` precisa ser `localhost`/`127.0.0.1`/`[::1]` |
| CSRF | Token aleatório por processo, entregue só na página, exigido via `X-DeskGuard-CSRF` |
| XSS | Interface constrói DOM com `textContent`; nenhum dado da API vira HTML |
| Clickjacking | `X-Frame-Options: DENY` e `frame-ancestors 'none'` |
| MIME sniffing | `X-Content-Type-Options: nosniff` |
| Cache | `Cache-Control: no-store` nas respostas da API |
| CSP | `default-src 'self'`, sem `unsafe-inline` |
| Vazamento por referência | `Referrer-Policy: no-referrer` |

O token anti-CSRF é comparado com `hmac.compare_digest`, evitando
comparação sujeita a ataque de tempo.

### 2.6 Minimização de dados

- Não são coletados senhas, tokens, chaves privadas, arquivos do usuário ou
  conteúdo pessoal.
- A conta em uso é **opt-in** (`include_account`), desligada por padrão.
- O que é coletado fica em três tabelas, com dados técnicos do endpoint e
  metadados de execução. O relatório técnico é gerado sob demanda.
- O modo demonstração é totalmente separado: não consulta o sistema e é
  gravado com `mode="demo"`.

### 2.7 Logs e auditoria

A trilha de auditoria registra **o que** foi feito, não o conteúdo coletado:

```
occurred_at · execution_id · actor · action · target · outcome
mode · approval_granted · details_json
```

`details_json` guarda apenas metadados de execução (quantidade de
verificações, parâmetros usados, formato de exportação). Nenhum segredo é
gravado, porque nenhum segredo é coletado.

### 2.8 Tratamento seguro de erros

- Exceções dentro de um coletor viram `inconclusive` com `error_code`; a
  exceção original fica em `evidence`, truncada, sem dados sensíveis.
- Erros da API retornam mensagens de domínio (`detail`) sem stack trace.
- Falhas do PowerShell viram resultado inconclusivo com o `stderr` truncado.

### 2.9 Leitura de serviços do Windows

O procedimento `services.status` toca no subsistema de serviços do Windows, o
que normalmente traz o risco de uma ferramenta "deixar o sistema diferente do
que estava". Aqui o contrato é estritamente de leitura, e ele é verificado:

1. **O script não escreve.** `collectors/scripts/services_status.ps1` usa
   `Get-Service` (leitura) e `Get-CimInstance Win32_Service` (leitura). Não
   há `Start-Service`, `Stop-Service`, `Restart-Service`, `Set-Service`,
   `New-Service`, `Remove-Service` nem `sc.exe config`. Um teste automatizado
   varre o script e falha a suíte se qualquer um desses comandos aparecer.
2. **A capability é declarada.** O procedimento declara
   `capability=READ_ONLY` e `privilege=USER`, então ele nem entra no caminho
   de aprovação que a plataforma reserva para alterações.
3. **O dado coletado é técnico e não pessoal.** Estado, tipo de
   inicialização, caminho do executável, código de saída e a cadeia de
   dependências entre serviços monitorados.
4. **A lista é fixa.** Os serviços monitorados são declarados no código
   (Spooler, cliente DNS, cliente DHCP, rede sem fio, Windows Update e, no
   modo ampliado, WMI, RPC, DCOM, BITS e diagnóstico). Não existe parâmetro
   para listar ou inspecionar serviços arbitrários — a superfície coletada não
   cresce por requisição do usuário.

### 2.10 Camada desktop e executável empacotado

A camada desktop **não amplia a superfície de ataque** da plataforma:

- a janela nativa carrega a **mesma** API local, com o mesmo token anti-CSRF,
  as mesmas validações e os mesmos cabeçalhos de segurança — nada foi
  relaxado para caber na janela;
- ela **escuta apenas em `127.0.0.1`** e reaproveita o cabeçalho `Host` local
  exigido pelo middleware;
- o `pywebview` é **opcional**: a CLI e a interface web funcionam sem ele, e
  uma falha ao abrir a janela apenas aciona o fallback para o navegador
  padrão;
- o executável empacotado **não pede elevação**: `uac_admin=False` no spec do
  PyInstaller, e a tool continua operada com o privilégio do usuário;
- o executável grava dados **no mesmo diretório do usuário**
  (`%LOCALAPPDATA%\DeskGuard`), sem tocar em nada fora dele;
- o executável **não é assinado digitalmente** — é uma limitação conhecida,
  registrada no README e no runbook, e não uma garantia de origem.

O empacotamento **inclui** o `pywebview` e o runtime WebView2: a janela nativa
funciona no `.exe` sem instalação adicional.

---

## 3. Limitações conhecidas

1. **A API não tem autenticação de usuário.** Ela é local e protegida por
   Host + CSRF. Em um modelo de uso corporativo com vários usuários por
   máquina, seria preciso adicionar autenticação e perfis.
2. **A proteção contra DNS rebinding depende do cabeçalho `Host`.** Um
   atacante local com acesso ao mesmo usuário ainda poderia chamar a API
   diretamente. É uma limitação aceita do modelo "aplicação local".
3. **O token anti-CSRF fica no HTML da página.** Quem consegue ler a página
   consegue executá-la — comportamento esperado em uma aplicação local.
4. **`is_admin` pode retornar `None`.** A ferramenta não afirmar que tem
   privilégio quando não conseguiu verificar.
5. **Sem trilha de auditoria imutável.** O SQLite local permite alteração
   externa; em ambiente corporativo seria necessário envio para um servidor
   de logs.
6. **As sondagens de rede são visíveis do outro lado.** Mesmo restritas à
   lista de autorizados, as sondagens de DNS, ICMP e TCP aparecem nos logs de
   firewall do endpoint e do destino. A ferramenta não oculta esse rastro.
7. **O executável empacotado não é assinado.** Não há garantia de origem
   verificável pelo Windows, e o SmartScreen pode bloquear a primeira
   execução. Distribuir internamente, com hash conferido, ou assinar o
   executável.
8. **A janela nativa depende de componentes de terceiros.** WebView2 (Microsoft)
   e `pywebview` ficam fora do controle do projeto; uma versão vulnerável
   desses componentes seria usada pela janela. Atualizar o WebView2 pela
   Microsoft e o `pywebview` pelo `pip` faz parte da manutenção.
9. **O estado dos serviços é uma leitura, não um diagnóstico completo.** O
   procedimento mostra o que está parado e como sobe, mas não diz *por que*
   parou (falha de dependência, cota, política de grupo, consumo de recurso).
   O log de eventos do Windows (`Get-WinEvent`) ainda precisa ser consultado
   pelo técnico.
10. **A auditoria de segurança não certifica o equipamento.** O procedimento
   `security.audit` é estritamente somente leitura, classifica achados por
   severidade e deixa itens inconclusivos quando não há privilégio ou quando
   o componente não está disponível. A aprovação das verificações **não**
   equivale a uma certificação de segurança.


---

## 4. Riscos residuais e mitigações

| Risco | Mitigação atual | Próximo passo |
|---|---|---|
| Coleta de dado pessoal | Opt-in explícito | Revisão por categoria antes de cada procedimento novo |
| Comando malicioso em nome do operador | Catálogo fechado e script estático | Manter a regra "sem shell" |
| Escalonamento de privilégio pelo técnico | Capability + aprovação + auditoria | Duas etapas de confirmação na interface |
| Uso em máquina não autorizada | Aviso no README e na interface | Bloqueio por domínio/inventário autorizado |
| Relatório usado como "certificado de segurança" | Nota explícita no relatório | Reforçar na UI do módulo de segurança |
| Ferramenta usada como sonda de rede | Lista de autorizados validada em duas camadas (API e script) | Revisar a lista periodicamente e registrar quem a alterou |
| Ferramenta alterando o endpoint sem querer | Script de serviços somente leitura, verificado por teste automatizado | Manter a varredura de comandos de escrita a cada novo script |

---

## 5. Como reportar um problema

Abra uma issue com: versão do DeskGuard, versão do Windows, passos para
reproduzir e o resultado esperado. **Não** inclua dados sensíveis no relato:
o procedimento de diagnóstico já é a forma correta de coletar informações do
endpoint.
