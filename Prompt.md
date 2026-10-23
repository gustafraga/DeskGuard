# Projeto DeskGuard Fase 2 — Plataforma de Resolução Ativa e Integração

## 1. Objetivo Geral
Evoluir o MVP do DeskGuard (Fase 1) de um diagnosticador passivo para uma plataforma de resolução ativa de problemas de Service Desk. A Fase 2 deve automatizar correções de baixo risco, integrar-se ao sistema de chamados (GLPI) e, opcionalmente, utilizar IA local gratuita para auxiliar o técnico. O projeto deve continuar sendo 100% gratuito, seguro e focado na experiência do técnico de N1.

## 2. Pilares da Fase 2 (Novos Módulos)
- **Módulo G - Auto-Remediação:** Implementar um sistema de "detecção e correção" para problemas comuns. Cada procedimento de correção deve consistir em dois scripts PowerShell: um de detecção (que verifica se há um problema e retorna um código de saída) e um de remediação (que corrige o problema, somente se a detecção indicar a falha).
    - **Exemplos de correções:** Reiniciar o serviço do Spooler de impressão, reativar o perfil do Firewall do Windows, limpar arquivos temporários quando o disco estiver com pouco espaço.
    - **Segurança:** As correções só devem ser executadas após confirmação explícita do usuário na interface. Nenhuma alteração deve ser feita sem consentimento.

- **Módulo H - Integração com GLPI:** Criar uma funcionalidade para enviar os resultados do diagnóstico diretamente para o GLPI. O técnico poderá, com um clique, criar um novo chamado ou anexar o relatório a um chamado existente. A integração deve usar a API REST do GLPI e ser configurável (URL do servidor, token de aplicação, etc.).

- **Módulo I - Assistente de IA (Opcional e Gratuito):** Implementar um "copiloto" que utiliza um modelo de linguagem local (ex: via `freeaiagent`) para:
    - Gerar um resumo em linguagem natural do diagnóstico para o técnico.
    - Sugerir os próximos passos de troubleshooting com base nos resultados.
    - (Opcional) Analisar o histórico de chamados e sugerir soluções para problemas recorrentes.

## 3. Requisitos de Segurança (Mantidos e Expandidos)
- **Confirmação Explícita:** Qualquer ação de remediação deve ser precedida por uma confirmação clara na interface, explicando o que será alterado.
- **Escopo Mínimo:** As correções devem ser específicas e ter o menor impacto possível no sistema.
- **Auditoria:** Todas as ações de remediação (detecção e correção) devem ser registradas no histórico do DeskGuard.
- **Integração Segura:** As credenciais do GLPI (tokens) devem ser armazenadas de forma segura e nunca expostas nos logs.
- **IA Local:** Se a IA for usada, ela deve ser executada localmente, sem enviar dados do endpoint para a nuvem.

## 4. Requisitos de Qualidade
- **Testes:** Cada script de detecção e remediação deve ter testes unitários que simulem o cenário de falha e sucesso.
- **Documentação:** Atualizar o `README.md`, `ARCHITECTURE.md` e `SECURITY.md` para refletir a nova arquitetura de remediação e integração.
- **Interface:** A tela de resultados deve ser atualizada para incluir um botão "Corrigir" (quando aplicável) e as opções de integração com o GLPI.

## 5. Forma de Trabalho
1.  Comece pelo **Módulo G (Auto-Remediação)**, implementando um ou dois casos de uso simples (ex: reiniciar Spooler, reativar Firewall).
2.  Em seguida, implemente o **Módulo H (Integração com GLPI)**, criando a camada de comunicação e a interface de envio.
3.  Por último, avalie a implementação do **Módulo I (IA)**, garantindo que seja totalmente opcional e gratuita.
4.  Mantenha a arquitetura de "Collectors" e a separação entre interface, lógica e execução.
5.  A cada módulo concluído, execute a suíte de testes e valide o build do executável.