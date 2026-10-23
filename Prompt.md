# Projeto DeskGuard — Plataforma de Automação de Service Desk e Segurança de TI

## 1. Seu papel

Atue como um engenheiro de software sênior, arquiteto de sistemas e especialista em automação de TI, suporte técnico, administração Windows, infraestrutura e cibersegurança defensiva.

Você será responsável por me ajudar a projetar, implementar, testar, documentar e evoluir uma plataforma profissional chamada DeskGuard.

Não quero apenas um protótipo visual. Quero um sistema funcional, seguro, modular, sustentável e útil para atividades reais de suporte técnico, respeitando as permissões e políticas da organização em que for utilizado.

## 2. Contexto e objetivo

Sou estudante de Ciência da Computação e trabalho com atividades de Service Desk e Help Desk.

No cotidiano, realizo procedimentos repetitivos de diagnóstico, atendimento, manutenção lógica, análise de conectividade, impressoras, sistemas corporativos e resolução de incidentes.

Quero transformar esses procedimentos em ferramentas reutilizáveis e automatizadas, reduzindo o tempo necessário para diagnosticar problemas, padronizando atendimentos e melhorando a documentação técnica.

Também quero utilizar o projeto para desenvolver competências profissionais em infraestrutura, automação, observabilidade e cibersegurança defensiva, construindo um portfólio público para o mercado de trabalho.

A plataforma deve permitir adicionar novos procedimentos ao longo do tempo sem precisar reconstruir todo o sistema.

## 3. Conceito do produto

O DeskGuard será uma plataforma de automação de suporte técnico e diagnóstico de endpoints Windows, com recursos de segurança e auditoria.

A plataforma deverá reunir:

- Ferramentas de diagnóstico de TI.
- Procedimentos guiados de troubleshooting.
- Automação de tarefas repetitivas autorizadas.
- Coleta organizada de informações técnicas.
- Geração de relatórios para documentação de chamados.
- Auditoria de segurança e verificação de configurações.
- Histórico de execuções e resultados.
- Catálogo modular de procedimentos.

A prioridade é construir uma base funcional e confiável, começando por um MVP pequeno e evoluindo de acordo com necessidades reais.

## 4. Módulos planejados

### Módulo A — Central de ferramentas

Criar uma interface que reúna os procedimentos disponíveis, com categorias, descrição, pré-requisitos, nível de privilégio exigido e indicação dos riscos de cada operação.

Cada ferramenta deve informar o que verifica ou altera antes de ser executada.

### Módulo B — Diagnóstico de Windows

Implementar verificações de leitura para coletar informações úteis ao suporte, conforme disponibilidade e permissão:

- Versão do Windows e informações básicas do sistema.
- Nome do computador e configuração de rede necessária para o diagnóstico.
- Estado da conectividade.
- Resolução DNS e conectividade com destinos autorizados.
- Configuração de IP e gateway.
- Estado de adaptadores de rede.
- Disponibilidade de impressoras e informações de filas de impressão.
- Estado de serviços relevantes para o diagnóstico.
- Informações disponíveis sobre firewall e proteção antivírus.
- Espaço em disco e utilização de recursos.
- Informações de atualizações do Windows, quando acessíveis.

Diferenciar claramente uma falha confirmada de uma verificação inconclusiva.

Não coletar senhas, tokens, chaves privadas, conteúdo pessoal ou dados desnecessários.

### Módulo C — Procedimentos automatizados de Service Desk

Criar um catálogo de procedimentos independentes, começando por:

1. Diagnóstico de ausência de conectividade de rede.
2. Diagnóstico de DNS e conectividade.
3. Diagnóstico de impressoras locais e de rede.
4. Coleta de informações para incidentes de Wi-Fi e Bluetooth.
5. Diagnóstico básico de serviços e aplicativos Windows.
6. Coleta de informações para lentidão do computador.
7. Verificação de espaço em disco e recursos do sistema.
8. Geração de resumo técnico para abertura ou atualização de chamados.

Cada procedimento deverá possuir etapas claras, verificações, resultados esperados, tratamento de erros e recomendações.

Comece somente com operações de leitura. Futuras ações corretivas devem ser implementadas individualmente, documentadas, autorizadas pelo usuário e precedidas de confirmação quando houver impacto no sistema.

Não automatize exclusão de arquivos, alterações de firewall, reinicializações, reinstalação de aplicativos ou mudanças de rede sem controles explícitos.

### Módulo D — Segurança e auditoria de endpoints

Desenvolver recursos de cibersegurança defensiva:

- Auditoria de configurações de segurança disponíveis no Windows.
- Verificação do estado do firewall.
- Consulta ao estado da proteção antivírus quando possível.
- Identificação de configurações que precisam de atenção.
- Registro dos resultados das verificações.
- Recomendações baseadas em referências documentadas.
- Classificação da severidade e justificativa de cada alerta.
- Histórico de auditorias e exportação de relatórios.

A plataforma não deverá afirmar que um computador está totalmente seguro apenas porque as verificações implementadas foram aprovadas.

Diferenciar resultados aprovados, problemas confirmados, verificações inconclusivas e itens não aplicáveis.

### Módulo E — Gerador de relatórios de chamados

Criar um módulo que transforme resultados de diagnóstico em relatórios técnicos claros e padronizados.

O relatório deve conter, quando aplicável:

- Resumo do problema.
- Verificações realizadas.
- Procedimentos executados.
- Resultados observados.
- Solução aplicada, se houver.
- Pendências e próximos passos.
- Data e duração da execução.
- Identificador da execução.

Permitir copiar o relatório e exportá-lo para formatos adequados.

Não afirmar que um procedimento foi executado ou que um problema foi resolvido se isso não estiver confirmado pelos resultados.

Os textos gerados devem ser editáveis antes de serem utilizados em um chamado.

### Módulo F — Histórico e auditoria de operações

Registrar as execuções da plataforma de forma estruturada:

- Ferramenta executada.
- Horário de início e término.
- Resultado.
- Identificador da execução.
- Operações realizadas.
- Erros encontrados.
- Confirmações concedidas para ações que modificam o sistema.

Não registrar segredos nem armazenar dados pessoais ou informações corporativas sem necessidade.

Os registros de auditoria devem distinguir resultados reais de exemplos demonstrativos.

## 5. Arquitetura e tecnologias

Antes de escolher a arquitetura definitiva, analise a finalidade, os requisitos e as limitações do ambiente.

Considere:

- Python para a lógica de diagnóstico e automação.
- PowerShell para operações específicas do Windows, quando adequado.
- Uma interface web moderna, responsiva e acessível.
- Uma API local para comunicação entre interface e ferramentas.
- SQLite para o MVP local, se for adequado.
- Testes automatizados e documentação.
- Empacotamento e instalação simples no Windows.

Avalie se a primeira versão deve funcionar como aplicação local, sem depender de servidores externos.

Não introduza Docker, Kubernetes, banco de dados remoto ou infraestrutura complexa sem uma justificativa concreta.

Não exponha uma API de execução de comandos à rede. Restrinja as operações ao catálogo permitido, valide os parâmetros e aplique controles de acesso adequados.

Não execute comandos arbitrários enviados pela interface ou pelo usuário como parte de uma execução automatizada.

## 6. Interface e experiência do usuário

Quero uma interface moderna, profissional e funcional, com aparência de uma ferramenta corporativa de TI.

A interface deve ter:

- Dashboard com indicadores realmente calculados a partir dos dados disponíveis.
- Catálogo de ferramentas organizado por categoria.
- Tela detalhada para cada procedimento.
- Indicadores de execução, sucesso, falha e inconclusão.
- Histórico pesquisável.
- Visualização de relatórios.
- Configurações e informações sobre permissões.
- Mensagens claras de erro e de confirmação.

Evite excesso de elementos decorativos e gráficos sem utilidade.

Não use dados fictícios como se fossem resultados reais. Se houver modo de demonstração, deixe-o explicitamente identificado e separado do ambiente real.

## 7. Requisitos de segurança

A segurança deve fazer parte da arquitetura desde o início.

- Princípio do menor privilégio.
- Operações de leitura por padrão.
- Validação de entradas.
- Proteção contra injeção de comandos.
- Controle explícito das ações permitidas.
- Tratamento seguro de erros.
- Armazenamento mínimo de dados.
- Proteção de informações sensíveis.
- Dependências documentadas e verificáveis.
- Testes de segurança para as funções críticas.
- Logs sem senhas, tokens ou outros segredos.
- Nenhuma execução remota sem autorização e controles apropriados.

A plataforma destina-se a sistemas próprios ou ambientes para os quais exista autorização explícita.

Não implemente exploração de terceiros, roubo de credenciais, persistência não autorizada, evasão de mecanismos de segurança ou ocultação de atividades.

## 8. Qualidade e testes

Quero um projeto organizado, legível e com qualidade profissional.

Implemente:

- Separação entre interface, lógica de negócio e execução de procedimentos.
- Tratamento de exceções.
- Testes unitários.
- Testes de integração quando adequados.
- Dados simulados para testar cenários sem modificar o computador.
- Documentação das limitações.
- Arquivo de dependências.
- Instruções de instalação, execução e atualização.
- Verificações de segurança antes de qualquer futura ação modificadora.

Não declare que os testes passaram sem executá-los. Informe quais comandos foram executados, quais resultados foram obtidos e quais testes ficaram pendentes.

## 9. Forma de trabalho

Trabalhe como um engenheiro responsável pelo produto.

Primeiro, inspecione o ambiente e os arquivos existentes. Não sobrescreva nem exclua arquivos sem autorização.

Depois:

1. Apresente a arquitetura recomendada.
2. Explique as tecnologias escolhidas.
3. Defina o MVP e os critérios objetivos de conclusão.
4. Identifique os riscos técnicos e as limitações.
5. Proponha uma estrutura de pastas.
6. Apresente um plano incremental de implementação.

Após o planejamento, comece a desenvolver a primeira etapa funcional.

Implemente em incrementos pequenos, execute os testes e corrija os problemas encontrados antes de avançar.

Não pare em uma interface visual ou em arquivos que apenas parecem completos. Verifique se as funções estão conectadas e operacionais.

Explique as decisões técnicas de forma didática, pois quero aprender durante o desenvolvimento.

Se houver dúvidas sobre procedimentos específicos do meu trabalho, não invente regras corporativas: crie uma interface configurável e solicite informações quando forem necessárias.

## 10. Resultado esperado

Quero uma primeira versão funcional do DeskGuard que possa ser executada no meu próprio Windows, demonstrada com segurança e evoluída por módulos.

O MVP deverá entregar pelo menos:

- Uma interface funcional.
- Um catálogo inicial de ferramentas.
- Dois ou três procedimentos reais de diagnóstico somente de leitura.
- Um gerador de relatórios técnicos.
- Histórico de execução.
- Testes automatizados.
- Documentação de instalação e uso.

O projeto deverá ser organizado para futuramente adicionar novas automações, recursos de segurança, integrações com sistemas de chamados e suporte a ambientes autorizados.

Comece agora inspecionando o ambiente, propondo a arquitetura e definindo o primeiro marco funcional. Não implemente tudo de uma só vez.